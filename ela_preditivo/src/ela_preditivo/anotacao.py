"""Anotação clínica das variantes (TCC, seções 4.2.2 e 4.3): cruzamento das variantes ingeridas com a base de
anotação, classificação de patogenicidade (só Pathogenic e Likely pathogenic sustentam risco; significado incerto
e classificações conflitantes não) e estado de revisão em estrelas.

Fontes da base de anotação, em ordem de preferência:
1. subconjunto real do ClinVar dos quatro genes (`base_consolidada_ela.csv`, `clinvar_ela_4genes.csv`/`variant_summary`
   ou `clinvar*.vcf`), lido de `DIR_DADOS_BRUTOS` (variável `ELA_DADOS_BRUTOS`; padrão `dados_reais/` na raiz do repositório);
2. tabela curada `data/variantes_curadas.csv`, que complementa o ClinVar com o modo de herança, nomes curtos e a
   expansão do C9orf72 (sem posição em VCF no ClinVar) e que, sozinha, mantém o protótipo funcional sem os dados reais.
Quando as duas fontes classificam a mesma variante de forma diferente, prevalece o ClinVar e a divergência fica registrada.
"""

from __future__ import annotations

import gzip
import hashlib
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import DIR_CONFIG, DIR_DADOS, DIR_DADOS_BRUTOS, GENES

CAMINHO_TABELA = DIR_DADOS / "variantes_curadas.csv"
CLASSES = ("risco", "vus", "conflitante", "benigna", "nao_anotada", "intermediaria", "normal", "nao_classificada")
LIMIAR_PADRAO = {"patogenico": 30, "intermediario": 24}
# Nomes de arquivo reconhecidos em DIR_DADOS_BRUTOS, em ordem de preferência
ARQUIVOS_BASE_REAL = (
    "base_consolidada_ela.csv",
    "clinvar_ela_4genes.csv",
    "variant_summary.txt",
    "clinvar_ela_4genes.vcf",
)
COLUNAS_TABELA = [
    "gene",
    "cromossomo",
    "posicao_grch38",
    "ref",
    "alt",
    "rs",
    "variation_id_clinvar",
    "allele_id",
    "hgvs_c",
    "hgvs_p",
    "nome_curto",
    "clnsig",
    "estrelas",
    "revstat",
    "n_submissores",
    "conflito",
    "heranca",
    "tipo",
    "repeticoes_min",
    "consequencia",
    "freq_alfa",
    "rs_dbsnp_casado",
    "metodo_dbsnp",
    "citacao",
    "conferido_em",
    "fenotipos",  # PhenotypeList / CLNDN
    "proporcao_patogenica",  # fração de Pathogenic + Likely pathogenic na abertura do conflito
    "heranca_declarada",  # modo de herança declarado num fenótipo de ELA: dominante, recessiva, ambas
    "regra_qualificada",  # True quando a classe `risco` veio da regra qualificada para conflitantes
    "nota_regra",  # rastreabilidade da regra: abertura do conflito, proporção, herança usada ou motivo da recusa
    "fonte",
]
CLASSES_PATOGENICAS = ("pathogenic", "likely pathogenic")
CAMINHO_PARAMETROS = DIR_CONFIG / "parametros_literatura.yaml"
MARCA_PENDENTE = "regra qualificada pendente"


def classificar_clnsig(clnsig) -> str:
    """Mapa CLNSIG → classe (TCC 4.2.2): só Pathogenic/Likely pathogenic sustentam risco; significado incerto ("vus") e
    classificação conflitante ("conflitante") não sustentam e são contadas em separado (Quadro 15 do TCC).

    Ordem dos testes: vazio → "conflicting" ou patogênico e benigno misturados no mesmo valor → patogênico → benigno →
    incerto (Uncertain significance, VUS, VUS-high, Uncertain risk allele) → demais valores (not provided, risk factor...).
    """
    if clnsig is None or (isinstance(clnsig, float) and np.isnan(clnsig)) or str(clnsig).strip() in ("", "-"):
        return "nao_classificada"
    s = str(clnsig).lower().replace(" ", "_")
    patogenico, benigno = "pathogenic" in s, "benign" in s
    if "conflicting" in s or (patogenico and benigno):
        return "conflitante"
    if patogenico:
        return "risco"
    if benigno:
        return "benigna"
    if "uncertain" in s or "vus" in s:
        return "vus"
    return "nao_classificada"


def regra_conflitante_padrao(config: str | Path | None = None) -> dict:
    """Bloco `regra_conflitante` do YAML de parâmetros. Sem o bloco (ou sem o arquivo) a regra fica desligada."""
    caminho = Path(config) if config else CAMINHO_PARAMETROS
    if not caminho.exists():
        return {}
    with open(caminho, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return dict(cfg.get("regra_conflitante") or {})


def _vazio(valor) -> bool:
    return valor is None or (isinstance(valor, float) and np.isnan(valor)) or not str(valor).strip()


def proporcao_patogenica(conflito) -> float:
    """Fração de Pathogenic + Likely pathogenic entre as classificações contadas na abertura do conflito.

    Aceita o formato da base consolidada ("Pathogenic (5)|Likely pathogenic (9)|Uncertain significance (5)") e o do
    CLNSIGCONF do VCF ("Pathogenic(5)|Likely_pathogenic(9)|..."). Só os nomes exatos "Pathogenic" e "Likely
    pathogenic" contam como patogênicos; todas as contagens entram no total. NaN sem abertura.
    """
    if _vazio(conflito):
        return float("nan")
    pares = re.findall(r"([A-Za-z][A-Za-z_ ,/\-]*?)\s*\((\d+)\)", str(conflito))
    total = sum(int(n) for _, n in pares)
    if not total:
        return float("nan")
    patogenicas = sum(int(n) for nome, n in pares if nome.strip().replace("_", " ").lower() in CLASSES_PATOGENICAS)
    return patogenicas / total


def heranca_declarada(fenotipos) -> str | None:
    """Modo de herança declarado num fenótipo de ELA do PhenotypeList (ou CLNDN): "dominante", "recessiva", "ambas"
    quando os dois aparecem, ou None. Fenótipos que não são ELA (ex.: demência frontotemporal) não contam."""
    if _vazio(fenotipos):
        return None
    modos = set()
    for item in re.split(r"[|;]", str(fenotipos).replace("_", " ")):
        t = item.lower()
        if "amyotrophic lateral sclerosis" not in t:
            continue
        if "autosomal dominant" in t:
            modos.add("dominante")
        if "autosomal recessive" in t:
            modos.add("recessiva")
    if not modos:
        return None
    return "ambas" if len(modos) == 2 else modos.pop()


def _aplicar_regra_conflitante(t: pd.DataFrame, regra: dict | None) -> None:
    """Regra qualificada (TCC 4.2.2), aplicada no lugar às linhas de classe `conflitante`.

    Condições: (a) proporção de Pathogenic/Likely pathogenic na abertura do conflito acima de `maioria_minima`
    (`estrita: true` → estritamente maior); (b) herança declarada num fenótipo de ELA (`exigir_heranca_declarada`).
    Modo único declarado → classe `risco`, `regra_qualificada = True` e, se a tabela não trouxer herança, a declarada.
    Os dois modos declarados → fica pendente (`nota_regra` começa com MARCA_PENDENTE) até a mescla com a tabela curada,
    em `tabela_anotacao`. Bloco vazio → nada muda.
    """
    regra = regra_conflitante_padrao() if regra is None else regra
    if not regra:
        return
    minimo = float(regra.get("maioria_minima", 0.5))
    estrita = bool(regra.get("estrita", True))
    exigir = bool(regra.get("exigir_heranca_declarada", True))
    prop = pd.to_numeric(t["proporcao_patogenica"], errors="coerce")
    maioria = ((prop > minimo) if estrita else (prop >= minimo)).fillna(False)
    declarada = t["heranca_declarada"]
    com_heranca = declarada.notna() if exigir else pd.Series(True, index=t.index)
    for i in t.index[(t["classe"] == "conflitante") & maioria & com_heranca]:
        abertura = f"{t.at[i, 'conflito']}; {100 * float(prop[i]):.0f} % patogênico ou provavelmente patogênico"
        modo = declarada[i] if isinstance(declarada[i], str) else None
        if modo == "ambas":
            t.at[i, "nota_regra"] = (
                f"{MARCA_PENDENTE}: PhenotypeList declara os dois modos de herança; depende da tabela curada ({abertura})"
            )
            continue
        t.at[i, "classe"], t.at[i, "regra_qualificada"] = "risco", True
        if not isinstance(t.at[i, "heranca"], str) and modo:
            t.at[i, "heranca"] = modo
        t.at[i, "nota_regra"] = (
            f"classe risco pela regra qualificada para classificação conflitante (TCC 4.2.2): {abertura}; "
            f"herança declarada no PhenotypeList: {modo or 'não exigida'}"
        )


def estrelas_de_revstat(revstat) -> int:
    """Escala de estrelas do ClinVar a partir de CLNREVSTAT/ReviewStatus (NCBI, 2024)."""
    s = str(revstat or "").lower().replace(" ", "_")
    if "practice_guideline" in s:
        return 4
    if "expert_panel" in s:
        return 3
    if "multiple_submitters" in s and "no_conflicts" in s:
        return 2
    if "single_submitter" in s or "conflicting" in s:
        return 1
    return 0


def _completar_colunas(t: pd.DataFrame, fonte: str, regra: dict | None = None) -> pd.DataFrame:
    for c in COLUNAS_TABELA:
        if c not in t.columns:
            t[c] = None
    t["fonte"] = t["fonte"].where(t["fonte"].notna(), fonte)
    t["cromossomo"] = t["cromossomo"].astype(str)
    t["posicao_grch38"] = pd.to_numeric(t["posicao_grch38"], errors="coerce").fillna(-1).astype(int)
    t["estrelas"] = pd.to_numeric(t["estrelas"], errors="coerce").fillna(0).astype(int)
    t["classe"] = t["clnsig"].map(classificar_clnsig)
    t["proporcao_patogenica"] = t["conflito"].map(proporcao_patogenica)
    t["heranca_declarada"] = t["fenotipos"].map(heranca_declarada)
    t["regra_qualificada"] = False
    t["nota_regra"] = None
    _aplicar_regra_conflitante(t, regra)
    return t[COLUNAS_TABELA + ["classe"]]


def carregar_tabela_curada(caminho: str | Path | None = None, regra: dict | None = None) -> pd.DataFrame:
    """Tabela curada (`data/variantes_curadas.csv`): poucas variantes públicas com herança e citação conferidas à mão.
    O caminho lido fica em `attrs["caminho"]` (metadados da execução)."""
    caminho = Path(caminho) if caminho else CAMINHO_TABELA
    t = pd.read_csv(caminho, dtype={"cromossomo": str, "rs": str, "variation_id_clinvar": str})
    t = _completar_colunas(t, "tabela_curada", regra).reset_index(drop=True)
    t.attrs["caminho"] = str(caminho)
    return t


def _descrever_curada(curada) -> str:
    """Identificação da tabela curada para os metadados: o caminho, ou o registrado em `attrs` quando é um DataFrame."""
    if isinstance(curada, pd.DataFrame):
        return str(curada.attrs.get("caminho", "DataFrame em memória"))
    return str(curada or CAMINHO_TABELA)


def limiar_patogenico_repeticao(tabela: pd.DataFrame, gene: str, limiar: dict | None = None) -> int:
    """Número mínimo de repetições para a classe "risco": `repeticoes_min` da tabela curada ou o limiar do YAML."""
    limiar = {**LIMIAR_PADRAO, **(limiar or {})}
    cand = tabela[(tabela.tipo == "repeticao") & (tabela.gene == gene)]
    if not cand.empty and pd.notna(cand.iloc[0].repeticoes_min):
        return int(cand.iloc[0].repeticoes_min)
    return int(limiar["patogenico"])


def classe_por_repeticoes(n, patogenico: int, intermediario: int = 24) -> str:
    """Classe de uma contagem de repetições GGGGCC (TCC 4.2.1): ≥ patogênico → risco; ≥ intermediário → intermediária."""
    if n is None or pd.isna(n):
        return "nao_classificada"
    n = int(n)
    if n >= patogenico:
        return "risco"
    if n >= intermediario:
        return "intermediaria"
    return "normal"


def _anotar_repeticao(linha: pd.Series, tabela: pd.DataFrame, limiar: dict) -> dict:
    cand = tabela[(tabela.tipo == "repeticao") & (tabela.gene == linha.gene)]
    base = {"anotada": not cand.empty, "fonte_anotacao": "tabela_curada" if not cand.empty else None}
    if not cand.empty:
        r = cand.iloc[0]
        base.update(
            {
                "clnsig": r.clnsig,
                "estrelas": int(r.estrelas),
                "heranca": r.heranca,
                "nome_curto": r.nome_curto,
                "hgvs_p": r.hgvs_p,
                "rs_tabela": r.rs,
                "citacao": r.citacao,
            }
        )
    pat = limiar_patogenico_repeticao(tabela, linha.gene, limiar)
    base["classe"] = classe_por_repeticoes(linha.repeticoes, pat, int(limiar.get("intermediario", 24)))
    base["limiar_patogenico"] = pat
    return base


def anotar(
    variantes: pd.DataFrame, tabela: pd.DataFrame | None = None, limiar_repeticoes: dict | None = None
) -> pd.DataFrame:
    """Cruza as variantes ingeridas com a tabela de anotação.

    Ordem das chaves: (cromossomo, posição, ref, alt) → identificador rs (coluna ID do VCF) → para repetições,
    gene + contagem de repetições. Variantes sem correspondência recebem classe "nao_anotada".
    """
    tabela = tabela_anotacao() if tabela is None else tabela
    limiar = {**LIMIAR_PADRAO, **(limiar_repeticoes or {})}
    cols = [
        "clnsig",
        "estrelas",
        "revstat",
        "n_submissores",
        "conflito",
        "heranca",
        "nome_curto",
        "hgvs_p",
        "rs_tabela",
        "allele_id",
        "freq_alfa",
        "citacao",
        "classe",
        "anotada",
        "fonte_anotacao",
        "limiar_patogenico",
        "fenotipos",
        "proporcao_patogenica",
        "heranca_declarada",
        "regra_qualificada",
        "nota_regra",
    ]
    saida = []
    snv = tabela[tabela.tipo != "repeticao"]
    por_chave = {
        (str(r.cromossomo), int(r.posicao_grch38), str(r.ref).upper(), str(r.alt).upper()): r
        for r in snv.itertuples(index=False)
    }
    por_rs: dict[str, list] = {}
    for r in snv.itertuples(index=False):
        if isinstance(r.rs, str) and r.rs.startswith("rs"):
            por_rs.setdefault(r.rs, []).append(r)
    for _, v in variantes.iterrows():
        a = {c: None for c in cols}
        a["anotada"], a["classe"] = False, "nao_anotada"
        if v.tipo == "repeticao":
            a.update(_anotar_repeticao(v, tabela, limiar))
        else:
            r = por_chave.get((str(v.cromossomo), int(v.posicao), str(v.ref).upper(), str(v.alt).upper()))
            chave = "posicao_alelos"
            if r is None and isinstance(v.id, str) and v.id.startswith("rs"):
                cands = por_rs.get(v.id, [])
                if len(cands) == 1:  # o rs só é chave complementar (TCC 4.2.2): um rs pode cobrir vários alelos
                    r, chave = cands[0], "rs"
                elif len(cands) > 1:
                    a["fonte_anotacao"] = f"rs_ambiguo:{len(cands)}_alelos"
            if r is not None:
                a.update(
                    {
                        "anotada": True,
                        "fonte_anotacao": f"{r.fonte}:{chave}",
                        "clnsig": r.clnsig,
                        "estrelas": int(r.estrelas),
                        "revstat": r.revstat,
                        "n_submissores": r.n_submissores,
                        "conflito": r.conflito,
                        "heranca": r.heranca if isinstance(r.heranca, str) else None,
                        "nome_curto": r.nome_curto if isinstance(r.nome_curto, str) else None,
                        "hgvs_p": r.hgvs_p,
                        "rs_tabela": r.rs,
                        "allele_id": r.allele_id,
                        "freq_alfa": r.freq_alfa,
                        "citacao": r.citacao,
                        "classe": r.classe,  # classe final da tabela (inclui a regra qualificada)
                        "fenotipos": r.fenotipos,
                        "proporcao_patogenica": r.proporcao_patogenica,
                        "heranca_declarada": r.heranca_declarada if isinstance(r.heranca_declarada, str) else None,
                        "regra_qualificada": bool(r.regra_qualificada),
                        "nota_regra": r.nota_regra if isinstance(r.nota_regra, str) else None,
                    }
                )
        saida.append(a)
    extra = pd.DataFrame(saida, index=variantes.index)
    out = pd.concat([variantes, extra], axis=1)
    out.attrs = dict(variantes.attrs)  # metadados do cabeçalho do VCF (montagem etc.) seguem para o relatório
    return out


def resumo_anotacao(anotadas: pd.DataFrame) -> pd.DataFrame:
    """Tabela 1 do relatório: perfil de variantes por amostra, gene e classe (apenas aprovadas no filtro)."""
    ap = anotadas[anotadas.aprovado]
    return (
        ap.groupby(["amostra", "gene", "classe"])
        .size()
        .rename("n")
        .reset_index()
        .pivot_table(index=["amostra", "gene"], columns="classe", values="n", fill_value=0)
        .reset_index()
    )


def indicadores_qualidade(anotadas: pd.DataFrame) -> dict:
    """Indicadores da verificação de qualidade (TCC 4.2.3): taxa de variantes aprovadas nos filtros, quantas das
    aprovadas foram encontradas na base de anotação e com que estado de revisão (estrelas), proporção de significado
    incerto e de classificação conflitante (contadas à parte) entre as anotadas e coerência da montagem declarada no VCF.
    """
    n = int(len(anotadas))
    ap = anotadas[anotadas.aprovado]
    anot = ap[ap.anotada.fillna(False).astype(bool)]
    por_classe = ap.classe.value_counts().to_dict()
    meta = anotadas.attrs.get("vcf", {})
    # coerência frequência × classificação (TCC 4.2.2): variante de risco com frequência populacional > 1% é suspeita
    freq = (
        pd.to_numeric(anot.get("freq_alfa", pd.Series(dtype=float)), errors="coerce")
        if len(anot)
        else pd.Series(dtype=float)
    )
    incoerentes = int(((anot.classe == "risco") & (freq > 0.01)).sum()) if len(anot) else 0
    return {
        "risco_com_frequencia_acima_1pct": incoerentes,
        "registros": n,
        "aprovados": int(len(ap)),
        "taxa_aprovacao": (float(len(ap)) / n if n else float("nan")),
        "anotadas": int(len(anot)),
        "taxa_anotacao": (float(len(anot)) / len(ap) if len(ap) else float("nan")),
        "por_estrelas": {
            int(k): int(v) for k, v in anot.estrelas.fillna(0).astype(int).value_counts().sort_index().items()
        },
        "por_classe": {str(k): int(v) for k, v in por_classe.items()},
        "n_risco": int(por_classe.get("risco", 0)),
        "n_vus": int(por_classe.get("vus", 0)),
        "n_conflitante": int(por_classe.get("conflitante", 0)),
        "proporcao_vus": (float(por_classe.get("vus", 0)) / len(anot) if len(anot) else float("nan")),
        "proporcao_conflitante": (float(por_classe.get("conflitante", 0)) / len(anot) if len(anot) else float("nan")),
        "montagem": meta.get("montagem") or (str(anotadas.montagem.iloc[0]) if "montagem" in anotadas and n else None),
        "montagem_coerente": (
            (meta.get("montagem") == meta.get("montagem_esperada")) if meta.get("montagem_esperada") else None
        ),
    }


# ---------------------------------------------------------------------------
# Subconjunto real do ClinVar/dbSNP dos quatro genes (TCC 4.2.2), lido de DIR_DADOS_BRUTOS
# ---------------------------------------------------------------------------
def localizar_base_real(diretorio: str | Path | None = None) -> Path | None:
    """Primeiro arquivo reconhecido (ver `ARQUIVOS_BASE_REAL`) em `diretorio` (padrão: `DIR_DADOS_BRUTOS`); None se não houver."""
    d = Path(diretorio) if diretorio else DIR_DADOS_BRUTOS
    if not d.is_dir():
        return None
    for nome in ARQUIVOS_BASE_REAL:
        p = d / nome
        if p.is_file():
            return p
    for p in sorted(d.glob("clinvar*.vcf")) + sorted(d.glob("clinvar*.vcf.gz")):
        return p
    return None


def _normalizar_data(texto) -> str | None:
    """'20260928' ou '2026-09-28' (em qualquer texto) → '2026-09-28'; None se não houver data."""
    m = re.search(r"(20\d{2})-?(\d{2})-?(\d{2})", str(texto or ""))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def identificar_base(caminho: str | Path) -> dict:
    """Identidade de um arquivo de base, para a rastreabilidade das versões (TCC 4.2; `atualizacao.py`): nome, tamanho,
    sha256 e release do ClinVar, lida do cabeçalho `##fileDate` (VCF) ou de uma data no nome do arquivo
    (`clinvar_20260928.vcf`); None quando não identificável (ex.: `base_consolidada_ela.csv`)."""
    caminho = Path(caminho)
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    release, fonte = None, None
    if ".vcf" in caminho.suffixes or caminho.suffix == ".gz":
        abrir = gzip.open if caminho.suffix == ".gz" else open
        with abrir(caminho, "rt", encoding="utf-8", errors="replace") as f:
            for linha in f:
                if not linha.startswith("##"):
                    break
                if linha.startswith("##fileDate="):
                    release, fonte = _normalizar_data(linha.split("=", 1)[1]), "##fileDate"
                    break
    if release is None and _normalizar_data(caminho.name):
        release, fonte = _normalizar_data(caminho.name), "nome do arquivo"
    return {
        "arquivo": caminho.name,
        "caminho": str(caminho),
        "tamanho_bytes": int(caminho.stat().st_size),
        "sha256": h.hexdigest(),
        "release": release,
        "release_fonte": fonte,
    }


def _gene_alvo(simbolo: str, genes=GENES) -> str | None:
    """`GeneSymbol` do ClinVar pode trazer vários genes ('MASP2;TARDBP'): devolve o gene-alvo contido, se houver."""
    for g in re.split(r"[;|,]", str(simbolo or "")):
        if g.strip() in genes:
            return g.strip()
    return None


def _freq_alelo(valor) -> float | None:
    """'T=0.0000712' (base consolidada) ou '0.13518' (AF_TGP) → float; vazio/'-' → None."""
    s = str(valor or "").strip()
    if s in ("", "-", "na", "nan", "None"):
        return None
    s = s.split("=")[-1]
    try:
        return float(s)
    except ValueError:
        return None


def _nome_curto_de(name: pd.Series) -> pd.Series:
    """'NM_000454.5(SOD1):c.14C>T (p.Ala5Val)' → 'p.Ala5Val'; sem proteína, usa a parte c. ou o próprio nome."""
    p = name.str.extract(r"\((p\.[^)]+)\)")[0]
    c = name.str.extract(r":(c\.[^ ]+)")[0]
    return p.where(p.notna(), c.where(c.notna(), name))


def carregar_variant_summary(
    caminho: str | Path, genes=GENES, montagem: str = "GRCh38", regra: dict | None = None
) -> pd.DataFrame:
    """Converte `variant_summary.txt` (TSV do ClinVar), `clinvar_ela_4genes.csv` (o mesmo, filtrado) ou
    `base_consolidada_ela.csv` (o mesmo + colunas do VCF e do casamento com o dbSNP, TCC 4.2.2) para o formato da
    tabela de anotação, filtrando pelos genes-alvo e pela montagem. Registros sem posição em VCF (ex.: microssatélites
    do C9orf72) ficam de fora e são cobertos pela tabela curada. Chaves duplicadas ficam com o maior número de estrelas.
    """
    caminho = Path(caminho)
    sep = "\t" if caminho.suffix.lower() in (".txt", ".tsv") else ","
    df = pd.read_csv(caminho, sep=sep, dtype=str, keep_default_na=False, encoding="utf-8-sig", low_memory=False)
    col = {c.lower().lstrip("#"): c for c in df.columns}
    sig = col.get("germlineclassification") or col.get("clinicalsignificance")
    rev = col.get("germlinereviewstatus") or col.get("reviewstatus")
    gene = df[col["genesymbol"]].map(lambda s: _gene_alvo(s, genes))
    df = df.assign(_gene=gene)[gene.notna() & (df[col["assembly"]] == montagem)].copy()
    pos = pd.to_numeric(df[col["positionvcf"]], errors="coerce")
    df = df[pos.notna() & (pos > 0)].copy()
    ref, alt = df[col["referenceallelevcf"]].str.upper(), df[col["alternateallelevcf"]].str.upper()
    consolidada = "dbsnp_rsid_casado" in col
    out = pd.DataFrame(
        {
            "gene": df["_gene"],
            "cromossomo": df[col["chromosome"]].astype(str),
            "posicao_grch38": pd.to_numeric(df[col["positionvcf"]]).astype(int),
            "ref": ref,
            "alt": alt,
            "rs": df[col["rs# (dbsnp)"]].map(lambda x: f"rs{x}" if str(x) not in ("-1", "", "-", "nan") else None),
            "variation_id_clinvar": df[col["variationid"]],
            "allele_id": df[col["alleleid"]],
            "hgvs_c": df[col["name"]],
            "hgvs_p": df[col["name"]].str.extract(r"\((p\.[^)]+)\)")[0],
            "nome_curto": _nome_curto_de(df[col["name"]]),
            "clnsig": df[sig].replace({"-": None, "": None}),
            "estrelas": df[rev].map(estrelas_de_revstat),
            "revstat": df[rev],
            "n_submissores": (
                pd.to_numeric(df[col.get("numbersubmitters", col["name"])], errors="coerce")
                if "numbersubmitters" in col
                else None
            ),
            "conflito": (
                df[col["classificacaoconflitante"]].replace("", None) if "classificacaoconflitante" in col else None
            ),
            "heranca": None,
            "tipo": np.where((ref.str.len() == 1) & (alt.str.len() == 1), "snv", "indel"),
            "repeticoes_min": None,
            "consequencia": (
                df[col["molecularconsequence"]].replace("", None) if "molecularconsequence" in col else None
            ),
            "freq_alfa": (
                df[col["freq_alfa"]].map(_freq_alelo)
                if "freq_alfa" in col
                else (df[col["af_tgp"]].map(_freq_alelo) if "af_tgp" in col else None)
            ),
            "rs_dbsnp_casado": (df[col["dbsnp_rsid_casado"]].replace("", None) if consolidada else None),
            "metodo_dbsnp": (df[col["dbsnp_metodo_casamento"]].replace("", None) if consolidada else None),
            "citacao": f"ClinVar {caminho.name} (release 2026-09-28, GRCh38; TCC 4.2.2)",
            "conferido_em": None,
            "fenotipos": (df[col["phenotypelist"]].replace("", None) if "phenotypelist" in col else None),
        }
    )
    out = out.sort_values("estrelas", ascending=False).drop_duplicates(
        ["cromossomo", "posicao_grch38", "ref", "alt"], keep="first"
    )
    out = _completar_colunas(out, "clinvar_base_consolidada" if consolidada else "clinvar_variant_summary", regra)
    return out.sort_values(["cromossomo", "posicao_grch38", "alt"]).reset_index(drop=True)


def carregar_clinvar_vcf(caminho: str | Path, genes=GENES, regra: dict | None = None) -> pd.DataFrame:
    """Converte `clinvar*.vcf` (projeção do ClinVar sobre o VCF 4.1, sem amostras, QUAL e FILTER nulos; TCC 4.2.2)
    para o formato da tabela de anotação. A coluna ID traz o VariationID; o rs vem de INFO/RS."""
    caminho = Path(caminho)
    abrir = __import__("gzip").open if caminho.suffix == ".gz" else open
    linhas, montagem = [], None
    with abrir(caminho, "rt", encoding="utf-8") as f:
        for linha in f:
            if linha.startswith("##"):
                if linha.startswith("##reference="):
                    montagem = linha.split("=", 1)[1].strip()
                continue
            if linha.startswith("#"):
                continue
            c = linha.rstrip("\n").split("\t")
            if len(c) < 8 or c[4] in (".", "N", "") or c[3] in (".", "N", ""):
                continue
            info = dict(kv.split("=", 1) if "=" in kv else (kv, True) for kv in c[7].split(";"))
            gene = _gene_alvo(str(info.get("GENEINFO", "")).replace(":", "|").replace("|", ";"), genes)
            if gene is None:
                continue
            ref, alt = c[3].upper(), c[4].upper()
            linhas.append(
                {
                    "gene": gene,
                    "cromossomo": c[0].replace("chr", ""),
                    "posicao_grch38": int(c[1]),
                    "ref": ref,
                    "alt": alt,
                    "rs": (f"rs{info['RS']}" if info.get("RS") else None),
                    "variation_id_clinvar": c[2],
                    "allele_id": info.get("ALLELEID"),
                    "hgvs_c": info.get("CLNHGVS"),
                    "hgvs_p": None,
                    "nome_curto": info.get("CLNHGVS"),
                    "clnsig": info.get("CLNSIG"),
                    "estrelas": estrelas_de_revstat(info.get("CLNREVSTAT")),
                    "revstat": info.get("CLNREVSTAT"),
                    "n_submissores": (
                        len(str(info.get("CLNSIGSCV", "")).split("|")) if info.get("CLNSIGSCV") else None
                    ),
                    "conflito": info.get("CLNSIGCONF"),
                    "heranca": None,
                    "tipo": ("snv" if len(ref) == 1 and len(alt) == 1 else "indel"),
                    "repeticoes_min": None,
                    "consequencia": info.get("MC"),
                    "freq_alfa": _freq_alelo(info.get("AF_TGP")),
                    "citacao": f"ClinVar {caminho.name} (VCF {montagem or 'GRCh38'}, release 2026-09-28; TCC 4.2.2)",
                    "fenotipos": info.get("CLNDN"),
                }
            )
    out = pd.DataFrame(linhas)
    out = out.sort_values("estrelas", ascending=False).drop_duplicates(
        ["cromossomo", "posicao_grch38", "ref", "alt"], keep="first"
    )
    out = _completar_colunas(out, "clinvar_vcf", regra)
    return out.sort_values(["cromossomo", "posicao_grch38", "alt"]).reset_index(drop=True)


def carregar_base_real(
    caminho: str | Path | None = None, genes=GENES, regra: dict | None = None
) -> pd.DataFrame | None:
    """Carrega a base real pelo tipo do arquivo (`.vcf`/`.vcf.gz` ou tabela). Sem arquivo → None.
    `regra`: bloco `regra_conflitante`; None lê o YAML padrão."""
    caminho = Path(caminho) if caminho else localizar_base_real()
    if caminho is None:
        return None
    df = (
        carregar_clinvar_vcf(caminho, genes, regra)
        if (".vcf" in caminho.suffixes or caminho.suffix == ".gz")
        else carregar_variant_summary(caminho, genes, regra=regra)
    )
    df.attrs["base"] = identificar_base(caminho)  # rastreabilidade da versão usada (TCC 4.2; atualizacao.py)
    return df


def _resolver_pendente(real: pd.DataFrame, i, rotulo: str) -> None:
    """Linha pendente da regra qualificada (os dois modos declarados): aceita se a tabela curada define a herança;
    senão fica `conflitante` e o caso é reportado (aviso + `nota_regra`)."""
    nota = str(real.at[i, "nota_regra"] or "")
    if not nota.startswith(MARCA_PENDENTE):
        return
    if isinstance(real.at[i, "heranca"], str):
        real.at[i, "classe"], real.at[i, "regra_qualificada"] = "risco", True
        real.at[i, "nota_regra"] = (
            nota.replace(
                MARCA_PENDENTE, "classe risco pela regra qualificada para classificação conflitante (TCC 4.2.2)"
            )
            + f"; herança da tabela curada: {real.at[i, 'heranca']}"
        )
    else:
        real.at[i, "nota_regra"] = (
            "não aceita pela regra qualificada: PhenotypeList declara os dois modos de herança e a tabela curada não "
            "define a herança (caso reportado); " + nota.split(": ", 1)[-1]
        )
        warnings.warn(f"{rotulo}: {real.at[i, 'nota_regra']}", stacklevel=3)


def tabela_anotacao(
    base_real: str | Path | pd.DataFrame | None | bool = None,
    curada: str | Path | pd.DataFrame | None = None,
    regra: dict | None = None,
) -> pd.DataFrame:
    """Tabela de anotação usada pelo pipeline: ClinVar real (se disponível) + tabela curada.

    - `base_real`: caminho, DataFrame, `None` (procura em `DIR_DADOS_BRUTOS`) ou `False` (só a tabela curada).
    - `regra`: bloco `regra_conflitante` do YAML; None lê o YAML padrão; `{}` desliga a regra.
    - Linhas presentes nas duas fontes: ficam com a classificação e as estrelas do ClinVar; a tabela curada contribui
      com `heranca`, `nome_curto` (se o ClinVar não trouxer proteína), `citacao` e, quando a classe final difere,
      com as colunas `clnsig_curada`/`divergencia_curada` (a classe segue o ClinVar, TCC 4.2.2, inclusive a regra
      qualificada para conflitantes).
    - Linhas só da tabela curada (ex.: expansão do C9orf72) entram como estão.
    """
    cur = curada if isinstance(curada, pd.DataFrame) else carregar_tabela_curada(curada, regra)
    real = (
        None
        if base_real is False
        else (base_real if isinstance(base_real, pd.DataFrame) else carregar_base_real(base_real, regra=regra))
    )
    if real is None:
        t = cur.copy()
        t["clnsig_curada"], t["divergencia_curada"] = None, None
        t.attrs["fontes"] = {"base_real": None, "curada": _descrever_curada(curada)}
        return t
    chave = ["cromossomo", "posicao_grch38", "ref", "alt"]
    real = real.copy()
    real["clnsig_curada"], real["divergencia_curada"] = None, None
    idx = {tuple(k): i for i, k in enumerate(real[chave].itertuples(index=False))}
    so_curada = []
    for _, r in cur.iterrows():
        k = (str(r.cromossomo), int(r.posicao_grch38), str(r.ref).upper(), str(r.alt).upper())
        if r.tipo == "repeticao" or k not in idx:
            so_curada.append(r)
            continue
        i = idx[k]
        if isinstance(r.heranca, str):
            real.loc[i, "heranca"] = r.heranca
        _resolver_pendente(real, i, f"{r.gene} {r.nome_curto}")
        if not isinstance(real.loc[i, "nome_curto"], str) or not str(real.loc[i, "nome_curto"]).startswith("p."):
            real.loc[i, "nome_curto"] = r.nome_curto
        real.loc[i, "citacao"] = f"{real.loc[i, 'citacao']}; tabela curada: {r.citacao}"
        if classificar_clnsig(r.clnsig) != real.loc[i, "classe"]:
            real.loc[i, "clnsig_curada"] = r.clnsig
            real.loc[i, "divergencia_curada"] = (
                f"tabela curada: {r.clnsig} ({classificar_clnsig(r.clnsig)}); ClinVar: {real.loc[i, 'clnsig']} ({real.loc[i, 'classe']}); prevalece o ClinVar"
            )
            warnings.warn(f"{r.gene} {r.nome_curto}: {real.loc[i, 'divergencia_curada']}", stacklevel=2)
    for i in real.index:  # pendentes sem linha na tabela curada: não aceitas, caso reportado
        _resolver_pendente(real, i, f"{real.at[i, 'gene']} {real.at[i, 'nome_curto']}")
    if so_curada:
        extra = pd.DataFrame(so_curada, columns=cur.columns).assign(clnsig_curada=None, divergencia_curada=None)
        # as linhas que vêm só da tabela curada são reindexadas às colunas do ClinVar e têm o dtype alinhado coluna a
        # coluna: sem isso o pandas precisa inferir o tipo a partir de colunas totalmente vazias e emite FutureWarning
        extra = extra.reindex(columns=real.columns)
        for coluna in real.columns:
            if extra[coluna].isna().all():
                try:
                    extra[coluna] = extra[coluna].astype(real[coluna].dtype)
                except (TypeError, ValueError):
                    pass
        # o pandas 2 avisa que vai mudar como infere dtype quando um dos quadros traz coluna totalmente vazia; aqui o
        # dtype já foi fixado acima e o resultado é reindexado às colunas do ClinVar, então a mudança anunciada não
        # altera o que sai. O aviso é silenciado neste ponto para não poluir a saída da linha de comando.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=FutureWarning, message=".*empty or all-NA entries.*")
            t = pd.concat([real, extra], ignore_index=True)[real.columns]
    else:
        extra, t = cur.iloc[0:0], real.reset_index(drop=True)
    base = real.attrs.get("base", {})
    t.attrs["fontes"] = {
        "base_real": str(real.fonte.iloc[0]) if len(real) else None,
        "curada": _descrever_curada(curada),
        "n_real": int(len(real)),
        "n_curada_extra": int(len(extra)),
        "arquivo_base_real": base.get("arquivo"),
        "release_base_real": base.get("release"),
        "sha256_base_real": base.get("sha256"),
    }
    return t


def desdobrar_frequencias(frequency: str) -> list[dict]:
    """Campo `frequency` do dbSNP: 'T:0.242812:1216:1000Genomes|...' → lista de dicionários (TCC 4.2.3)."""
    itens = []
    for bloco in re.split(r"[|;,]\s*", str(frequency or "")):
        partes = bloco.split(":")
        if len(partes) >= 4:
            itens.append(
                {
                    "alelo": partes[0],
                    "frequencia": float(partes[1]),
                    "contagem": int(float(partes[2])),
                    "estudo": partes[3],
                }
            )
    return itens


def carregar_dbsnp_exportacao(caminhos) -> pd.DataFrame:
    """Lê os `snp_result_*.txt` exportados da interface do dbSNP, removendo cabeçalhos repetidos e duplicatas."""
    partes = []
    for c in caminhos:
        df = pd.read_csv(c, sep="\t", dtype=str)
        df = df[df.iloc[:, 0] != df.columns[0]]
        partes.append(df)
    df = pd.concat(partes, ignore_index=True).drop_duplicates()
    df.columns = [c.strip().lower() for c in df.columns]
    if "snp_id" in df.columns:
        df["rs"] = df["snp_id"].map(lambda x: x if str(x).startswith("rs") else f"rs{x}")
    return df
