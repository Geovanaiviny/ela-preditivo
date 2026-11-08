"""Ingestão e validação de VCF parental (TCC, seções 4.2.1 e 4.3).

Pipeline: leitura com PyVCF (distribuição pyvcf3) → conferência da montagem de referência no cabeçalho (GRCh38) →
filtro de qualidade (FILTER, DP, GQ; QUAL é qualidade do sítio, GQ é qualidade da chamada) → máscara de regiões
GRCh38 dos genes-alvo → decomposição de registros multialélicos → normalização da representação de cada alelo →
dosagem alélica por ALT (0/1/2) → leitura de AC, AN e DB do INFO.

A expansão de hexanucleotídeos do C9orf72 entra no modelo como parâmetro do laudo laboratorial (TCC 4.2.1), via
`genotipo.vetor_dosagem(..., laudo_c9orf72=...)`. A detecção no próprio VCF (ALT <STRn>, FORMAT REPCN ou contagem
do motivo com Biopython) é mantida apenas como caminho secundário, para arquivos que a tragam.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import vcf  # pyvcf3
import yaml
from Bio.Seq import Seq

from . import DIR_CONFIG

CAMINHO_REGIOES = DIR_CONFIG / "regioes_genes_grch38.yaml"
FILTRO_PADRAO = {"dp_minimo": 20, "gq_minimo": 30, "exigir_pass": True}   # TCC 4.3; o pipeline passa `filtro_qualidade` do YAML
MONTAGEM_ESPERADA = "GRCh38"
RE_STR = re.compile(r"^<STR(\d+)>$", re.IGNORECASE)
MOTIVO_C9ORF72 = "GGGGCC"
COLUNAS = ["amostra", "cromossomo", "posicao", "id", "ref", "alt", "indice_alt", "n_alt", "tipo", "qual", "filtro",
           "dp", "gq", "gt", "dosagem", "repeticoes", "motivo_repeticao", "gene", "aprovado", "motivo_reprovacao",
           "posicao_vcf", "ref_vcf", "alt_vcf", "normalizada", "ac", "an", "no_dbsnp", "montagem", "arquivo"]

# Comprimentos de contig que distinguem as montagens (NCBI GRCh38.p14 e GRCh37.p13), usados quando o cabeçalho
# traz `##contig=<ID=...,length=...>` mas não declara `##reference`.
COMPRIMENTOS_CONTIG = {
    "GRCh38": {"1": 248956422, "2": 242193529, "9": 138394717, "16": 90338345, "17": 83257441, "21": 46709983, "X": 156040895},
    "GRCh37": {"1": 249250621, "2": 243199373, "9": 141213431, "16": 90354753, "17": 81195210, "21": 48129895, "X": 155270560},
}


class MontagemDivergente(ValueError):
    """O VCF declara uma montagem de referência diferente da esperada (GRCh38)."""


# ---------------------------------------------------------------------------
# Regiões e cromossomos
# ---------------------------------------------------------------------------
def carregar_regioes(caminho: str | Path | None = None) -> pd.DataFrame:
    with open(caminho or CAMINHO_REGIOES, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    flanco = int(cfg.get("flanco_pb", 0))
    linhas = [{"gene": g, "cromossomo": normalizar_cromossomo(str(r["cromossomo"])),
               "inicio": int(r["inicio"]) - flanco, "fim": int(r["fim"]) + flanco, "fita": r.get("fita")}
              for g, r in cfg["genes"].items()]
    return pd.DataFrame(linhas)


def normalizar_cromossomo(c: str) -> str:
    c = str(c).strip()
    if c.lower().startswith("chr"):
        c = c[3:]
    return "M" if c.upper() in {"MT", "M"} else c


def gene_da_posicao(cromossomo: str, posicao: int, regioes: pd.DataFrame) -> str | None:
    c = normalizar_cromossomo(cromossomo)
    hit = regioes[(regioes.cromossomo == c) & (regioes.inicio <= posicao) & (posicao <= regioes.fim)]
    return None if hit.empty else str(hit.iloc[0].gene)


# ---------------------------------------------------------------------------
# Montagem de referência e normalização da representação (TCC 4.2.1, "quatro cuidados")
# ---------------------------------------------------------------------------
def _classificar_montagem(texto: str) -> str | None:
    t = texto.lower()
    if any(x in t for x in ("grch38", "hg38", "b38", "hs38")):
        return "GRCh38"
    if any(x in t for x in ("grch37", "hg19", "b37", "hs37")):
        return "GRCh37"
    return None


def montagem_do_cabecalho(leitor: vcf.Reader) -> dict:
    """Identifica a montagem pelo cabeçalho: `##reference`, depois `##source`/`##assembly`, depois comprimento dos contigs.

    Devolve {montagem, evidencia, referencia, fileformat, fonte, data_arquivo, amostras}. `montagem` é "GRCh38",
    "GRCh37" ou "desconhecida".
    """
    meta = leitor.metadata or {}

    def _texto(chave: str) -> str:
        v = meta.get(chave)
        if isinstance(v, (list, tuple)):
            v = " ".join(str(x) for x in v)
        return "" if v is None else str(v)

    referencia, fonte = _texto("reference"), _texto("source")
    montagem, evidencia = None, None
    for chave, txt in (("reference", referencia), ("assembly", _texto("assembly")), ("source", fonte)):
        m = _classificar_montagem(txt)
        if m:
            montagem, evidencia = m, f"##{chave}={txt}"
            break
    if montagem is None:
        for nome, contig in (leitor.contigs or {}).items():
            comp = getattr(contig, "length", None)
            if not comp:
                continue
            c = normalizar_cromossomo(nome)
            for cand, tabela in COMPRIMENTOS_CONTIG.items():
                if tabela.get(c) == int(comp):
                    montagem, evidencia = cand, f"##contig {nome} length={comp}"
                    break
            if montagem:
                break
    return {"montagem": montagem or "desconhecida", "evidencia": evidencia, "referencia": referencia or None,
            "fileformat": _texto("fileformat") or None, "fonte": fonte or None, "data_arquivo": _texto("fileDate") or None,
            "amostras": list(leitor.samples)}


def normalizar_alelos(posicao: int, ref: str, alt: str) -> tuple[int, str, str, bool]:
    """Representação parcimoniosa de um par REF/ALT (TCC 4.2.1): remove o sufixo e o prefixo comuns, mantendo
    pelo menos uma base em cada alelo e deslocando POS pelo prefixo removido.

    Sem o genoma de referência em disco não é possível alinhar indels à esquerda; o que se garante aqui é que
    descrições redundantes do mesmo evento (ex.: `pos 10 CAT>CAG` e `pos 12 T>G`) convergem para a mesma chave.
    Alelos simbólicos (`<...>`), `*` e `.` não são alterados. Devolve (posicao, ref, alt, foi_normalizada).
    """
    if not ref or not alt or alt.startswith("<") or alt in ("*", "."):
        return posicao, ref, alt, False
    r, a, p = ref.upper(), alt.upper(), int(posicao)
    while len(r) > 1 and len(a) > 1 and r[-1] == a[-1]:
        r, a = r[:-1], a[:-1]
    while len(r) > 1 and len(a) > 1 and r[0] == a[0]:
        r, a, p = r[1:], a[1:], p + 1
    return p, r, a, (p, r, a) != (int(posicao), ref.upper(), alt.upper())


# ---------------------------------------------------------------------------
# Motivos de repetição (Biopython)
# ---------------------------------------------------------------------------
def _rotacoes(m: str) -> set[str]:
    return {m[i:] + m[:i] for i in range(len(m))}


def mesmo_motivo(a: str, b: str) -> bool:
    """True se b é o motivo a, uma rotação dele ou do seu complemento reverso (GGGGCC ≡ GGCCCC)."""
    a, b = a.upper(), b.upper()
    if len(a) != len(b):
        return False
    return b in _rotacoes(a) or b in _rotacoes(str(Seq(a).reverse_complement()))


def contar_repeticoes(sequencia: str, motivo: str = MOTIVO_C9ORF72) -> int:
    """Número de cópias contíguas do motivo (ou do complemento reverso) na sequência."""
    seq = Seq(sequencia.upper())
    direto = seq.count(motivo.upper())
    reverso = seq.count(str(Seq(motivo.upper()).reverse_complement()))
    return int(max(direto, reverso))


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def _dado(call, campo: str):
    try:
        v = getattr(call.data, campo)
    except AttributeError:
        return None
    return v


def _tipo(ref: str, alt: str, info: dict, gene: str | None) -> str:
    if RE_STR.match(alt) or str(info.get("SVTYPE", "")).upper() == "STR":
        return "repeticao"
    if alt.startswith("<"):
        return "simbolica"
    if len(ref) == 1 and len(alt) == 1:
        return "snv"
    if gene == "C9orf72" and contar_repeticoes(alt) >= 3:
        return "repeticao"
    return "indel"


def _repeticoes(alt: str, tipo: str, info: dict, call, gt_alelos: list, indice_alt: int):
    """Contagem de repetições do alelo ALT: rótulo <STRn>, depois REPCN (alinhado ao GT), depois contagem do motivo."""
    m = RE_STR.match(alt)
    if m:
        return int(m.group(1))
    repcn = _dado(call, "REPCN")
    if repcn:
        partes = str(repcn).replace("|", "/").split("/")
        for a, r in zip(gt_alelos, partes):
            if a == str(indice_alt) and r not in ("", "."):
                return int(r)
    if tipo == "repeticao" and not alt.startswith("<"):
        return contar_repeticoes(alt, str(info.get("RU") or MOTIVO_C9ORF72))
    return np.nan


def _info_por_alt(info: dict, chave: str, indice_alt: int):
    """Valor de uma chave INFO com Number=A (um por ALT) ou escalar."""
    v = info.get(chave)
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        return v[indice_alt - 1] if len(v) >= indice_alt else None
    return v


def ler_vcf(caminho: str | Path, regioes: pd.DataFrame | None = None, filtro: dict | None = None,
            amostra: str | None = None, montagem_esperada: str | None = MONTAGEM_ESPERADA, normalizar: bool = True) -> pd.DataFrame:
    """Lê um VCF (uma amostra) e devolve uma linha por ALT com dosagem, qualidade, gene e situação no filtro.

    - `montagem_esperada`: confere o cabeçalho (TCC 4.2.1). Montagem declarada diferente → `MontagemDivergente`;
      montagem não identificável → aviso e coluna `montagem = "desconhecida"`. `None` desliga a conferência.
    - `normalizar`: aplica `normalizar_alelos` a cada ALT após a decomposição multialélica; os valores originais
      ficam em `posicao_vcf`, `ref_vcf`, `alt_vcf`.
    - `amostra`: nome da coluna de amostra num VCF multiamostra (padrão: a primeira).
    Os metadados do cabeçalho ficam em `df.attrs["vcf"]`.
    """
    caminho = Path(caminho)
    regioes = carregar_regioes() if regioes is None else regioes
    filtro = {**FILTRO_PADRAO, **(filtro or {})}
    leitor = vcf.Reader(filename=str(caminho))
    if not leitor.samples:
        raise ValueError(f"{caminho.name}: o VCF não tem coluna de amostra (FORMAT/genótipo)")
    if amostra and amostra not in leitor.samples:
        raise ValueError(f"{caminho.name}: amostra {amostra!r} não existe; amostras disponíveis: {leitor.samples}")
    meta = montagem_do_cabecalho(leitor)
    if montagem_esperada:
        if meta["montagem"] == "desconhecida":
            warnings.warn(f"{caminho.name}: o cabeçalho não permite identificar a montagem de referência; assumindo {montagem_esperada}. "
                          "Confira ##reference antes de confiar nas coordenadas (TCC 4.2.1).", stacklevel=2)
        elif meta["montagem"] != montagem_esperada:
            raise MontagemDivergente(f"{caminho.name}: montagem {meta['montagem']} declarada no cabeçalho ({meta['evidencia']}); o artefato "
                                     f"opera em {montagem_esperada} (TCC 4.2.1). Converta as coordenadas (liftover) antes da ingestão.")
    idx = leitor.samples.index(amostra) if amostra else 0
    nome_amostra = leitor.samples[idx]
    tem_db = "DB" in (leitor.infos or {})
    linhas = []
    for rec in leitor:
        call = rec.samples[idx]
        gt_alelos = [str(a) for a in (call.gt_alleles or []) if a is not None]
        crom = normalizar_cromossomo(rec.CHROM)
        filtro_txt = "PASS" if rec.FILTER == [] else ("." if rec.FILTER is None else ";".join(rec.FILTER))
        dp, gq = _dado(call, "DP"), _dado(call, "GQ")
        an = rec.INFO.get("AN")
        for i, alt_obj in enumerate(rec.ALT, start=1):
            alt_vcf = str(alt_obj) if alt_obj is not None else "."
            pos, ref, alt, normalizada = normalizar_alelos(rec.POS, rec.REF, alt_vcf) if normalizar else (int(rec.POS), rec.REF, alt_vcf, False)
            gene = gene_da_posicao(crom, pos, regioes)
            tipo = _tipo(ref, alt, rec.INFO, gene)
            dosagem = gt_alelos.count(str(i)) if gt_alelos else np.nan
            motivos = []
            if gene is None:
                motivos.append("fora_das_regioes")
            if not gt_alelos:
                motivos.append("genotipo_ausente")
            if filtro["exigir_pass"] and filtro_txt not in ("PASS", "."):
                motivos.append("filtro_nao_pass")
            if dp is not None and dp < filtro["dp_minimo"]:
                motivos.append("dp_baixo")
            if gq is not None and gq < filtro["gq_minimo"]:
                motivos.append("gq_baixo")
            linhas.append({
                "amostra": nome_amostra, "cromossomo": crom, "posicao": pos, "id": rec.ID or None,
                "ref": ref, "alt": alt, "indice_alt": i, "n_alt": len(rec.ALT), "tipo": tipo,
                "qual": rec.QUAL, "filtro": filtro_txt, "dp": dp, "gq": gq, "gt": call.data.GT if hasattr(call.data, "GT") else None,
                "dosagem": dosagem, "repeticoes": _repeticoes(alt_vcf, tipo, rec.INFO, call, gt_alelos, i),
                "motivo_repeticao": str(rec.INFO.get("RU")) if rec.INFO.get("RU") else (MOTIVO_C9ORF72 if tipo == "repeticao" else None),
                "gene": gene, "aprovado": len(motivos) == 0, "motivo_reprovacao": ";".join(motivos) or None,
                "posicao_vcf": int(rec.POS), "ref_vcf": rec.REF, "alt_vcf": alt_vcf, "normalizada": normalizada,
                "ac": _info_por_alt(rec.INFO, "AC", i), "an": an,
                "no_dbsnp": bool(rec.INFO.get("DB")) if tem_db else None,
                "montagem": meta["montagem"], "arquivo": caminho.name,
            })
    arquivo = getattr(leitor, "_reader", None)
    if arquivo is not None and hasattr(arquivo, "close"):
        arquivo.close()
    df = pd.DataFrame(linhas, columns=COLUNAS)
    df["dosagem"] = df["dosagem"].astype("Int64")
    df.attrs["vcf"] = {**meta, "arquivo": caminho.name, "amostra": nome_amostra, "montagem_esperada": montagem_esperada}
    return df


def resumo_ingestao(df: pd.DataFrame) -> dict:
    """Contagens para o relatório (TCC 4.2.3, verificação de qualidade): registros lidos, aprovados e reprovados por
    motivo, taxa de aprovação, registros normalizados, presença no dbSNP (flag DB) e montagem do cabeçalho."""
    motivos = df.loc[~df.aprovado, "motivo_reprovacao"].fillna("").str.split(";").explode()
    meta = df.attrs.get("vcf", {})
    n = int(len(df))
    return {"registros": n, "aprovados": int(df.aprovado.sum()), "reprovados": int((~df.aprovado).sum()),
            "taxa_aprovacao": (float(df.aprovado.mean()) if n else float("nan")),
            "por_motivo": motivos[motivos != ""].value_counts().to_dict(),
            "por_gene": df.loc[df.aprovado, "gene"].value_counts().to_dict(),
            "normalizadas": int(df.normalizada.sum()) if "normalizada" in df else 0,
            "no_dbsnp": (int(df.no_dbsnp.fillna(False).sum()) if "no_dbsnp" in df and df.no_dbsnp.notna().any() else None),
            "montagem": meta.get("montagem") or (df.montagem.iloc[0] if "montagem" in df and n else None),
            "evidencia_montagem": meta.get("evidencia"), "fileformat": meta.get("fileformat"), "fonte": meta.get("fonte"),
            "amostra": meta.get("amostra"), "amostras_no_arquivo": meta.get("amostras")}
