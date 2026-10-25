"""Ingestão e validação de VCF parental (TCC, seção 4.3).

Pipeline: leitura com PyVCF (distribuição pyvcf3) → filtro de qualidade (FILTER, DP, GQ) → máscara de regiões
GRCh38 dos genes-alvo → decomposição de registros multialélicos → dosagem alélica por ALT (0/1/2) → detecção da
expansão de repetições do C9orf72 (ALT <STRn>, FORMAT REPCN ou contagem do motivo com Biopython).
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import vcf  # pyvcf3
import yaml
from Bio.Seq import Seq

from . import DIR_CONFIG

CAMINHO_REGIOES = DIR_CONFIG / "regioes_genes_grch38.yaml"
FILTRO_PADRAO = {"dp_minimo": 10, "gq_minimo": 20, "exigir_pass": True}
RE_STR = re.compile(r"^<STR(\d+)>$", re.IGNORECASE)
MOTIVO_C9ORF72 = "GGGGCC"
COLUNAS = ["amostra", "cromossomo", "posicao", "id", "ref", "alt", "indice_alt", "n_alt", "tipo", "qual", "filtro",
           "dp", "gq", "gt", "dosagem", "repeticoes", "motivo_repeticao", "gene", "aprovado", "motivo_reprovacao", "arquivo"]


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


def ler_vcf(caminho: str | Path, regioes: pd.DataFrame | None = None, filtro: dict | None = None,
            amostra: str | None = None) -> pd.DataFrame:
    """Lê um VCF (uma amostra) e devolve uma linha por ALT com dosagem, qualidade, gene e situação no filtro."""
    caminho = Path(caminho)
    regioes = carregar_regioes() if regioes is None else regioes
    filtro = {**FILTRO_PADRAO, **(filtro or {})}
    leitor = vcf.Reader(filename=str(caminho))
    if not leitor.samples:
        raise ValueError(f"{caminho.name}: o VCF não tem coluna de amostra (FORMAT/genótipo)")
    idx = leitor.samples.index(amostra) if amostra else 0
    nome_amostra = leitor.samples[idx]
    linhas = []
    for rec in leitor:
        call = rec.samples[idx]
        gt_alelos = [str(a) for a in (call.gt_alleles or []) if a is not None]
        crom = normalizar_cromossomo(rec.CHROM)
        gene = gene_da_posicao(crom, rec.POS, regioes)
        filtro_txt = "PASS" if rec.FILTER == [] else ("." if rec.FILTER is None else ";".join(rec.FILTER))
        dp, gq = _dado(call, "DP"), _dado(call, "GQ")
        for i, alt_obj in enumerate(rec.ALT, start=1):
            alt = str(alt_obj) if alt_obj is not None else "."
            tipo = _tipo(rec.REF, alt, rec.INFO, gene)
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
                "amostra": nome_amostra, "cromossomo": crom, "posicao": int(rec.POS), "id": rec.ID or None,
                "ref": rec.REF, "alt": alt, "indice_alt": i, "n_alt": len(rec.ALT), "tipo": tipo,
                "qual": rec.QUAL, "filtro": filtro_txt, "dp": dp, "gq": gq, "gt": call.data.GT if hasattr(call.data, "GT") else None,
                "dosagem": dosagem, "repeticoes": _repeticoes(alt, tipo, rec.INFO, call, gt_alelos, i),
                "motivo_repeticao": str(rec.INFO.get("RU")) if rec.INFO.get("RU") else (MOTIVO_C9ORF72 if tipo == "repeticao" else None),
                "gene": gene, "aprovado": len(motivos) == 0, "motivo_reprovacao": ";".join(motivos) or None,
                "arquivo": caminho.name,
            })
    df = pd.DataFrame(linhas, columns=COLUNAS)
    df["dosagem"] = df["dosagem"].astype("Int64")
    return df


def resumo_ingestao(df: pd.DataFrame) -> dict:
    """Contagens para o relatório: registros lidos, aprovados e reprovados por motivo."""
    motivos = df.loc[~df.aprovado, "motivo_reprovacao"].fillna("").str.split(";").explode()
    return {"registros": int(len(df)), "aprovados": int(df.aprovado.sum()),
            "reprovados": int((~df.aprovado).sum()), "por_motivo": motivos[motivos != ""].value_counts().to_dict(),
            "por_gene": df.loc[df.aprovado, "gene"].value_counts().to_dict()}
