"""Anotação clínica das variantes (TCC, seção 4.3): cruzamento com a tabela curada (ClinVar/dbSNP) ou com o
subconjunto real do ClinVar/dbSNP descrito na seção 4.2, classificação de patogenicidade e estado de revisão.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import DIR_DADOS, GENES

CAMINHO_TABELA = DIR_DADOS / "variantes_curadas.csv"
CLASSES = ("risco", "vus", "benigna", "nao_anotada", "intermediaria", "normal", "nao_classificada")
LIMIAR_PADRAO = {"patogenico": 30, "intermediario": 24}


def classificar_clnsig(clnsig) -> str:
    """Mapa CLNSIG → classe de risco (TCC 4.2: P/LP sustentam risco; VUS e conflitantes não)."""
    if clnsig is None or (isinstance(clnsig, float) and np.isnan(clnsig)) or str(clnsig).strip() == "":
        return "nao_classificada"
    s = str(clnsig).lower().replace(" ", "_")
    if "conflicting" in s:
        return "vus"
    if "pathogenic" in s and "benign" not in s:
        return "risco"
    if "benign" in s:
        return "benigna"
    if "uncertain" in s:
        return "vus"
    return "nao_classificada"


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


def carregar_tabela_curada(caminho: str | Path | None = None) -> pd.DataFrame:
    t = pd.read_csv(caminho or CAMINHO_TABELA, dtype={"cromossomo": str, "rs": str, "variation_id_clinvar": str})
    t["cromossomo"] = t["cromossomo"].astype(str)
    t["posicao_grch38"] = t["posicao_grch38"].astype(int)
    t["estrelas"] = t["estrelas"].fillna(0).astype(int)
    t["classe"] = t["clnsig"].map(classificar_clnsig)
    return t


def _anotar_repeticao(linha: pd.Series, tabela: pd.DataFrame, limiar: dict) -> dict:
    cand = tabela[(tabela.tipo == "repeticao") & (tabela.gene == linha.gene)]
    base = {"anotada": not cand.empty, "fonte_anotacao": "tabela_curada" if not cand.empty else None}
    if not cand.empty:
        r = cand.iloc[0]
        base.update({"clnsig": r.clnsig, "estrelas": int(r.estrelas), "heranca": r.heranca, "nome_curto": r.nome_curto,
                     "hgvs_p": r.hgvs_p, "rs_tabela": r.rs, "citacao": r.citacao})
    n = linha.repeticoes
    pat = int(cand.iloc[0].repeticoes_min) if (not cand.empty and pd.notna(cand.iloc[0].repeticoes_min)) else int(limiar["patogenico"])
    inter = int(limiar.get("intermediario", 24))
    if pd.isna(n):
        base["classe"] = "nao_classificada"
    elif n >= pat:
        base["classe"] = "risco"
    elif n >= inter:
        base["classe"] = "intermediaria"
    else:
        base["classe"] = "normal"
    base["limiar_patogenico"] = pat
    return base


def anotar(variantes: pd.DataFrame, tabela: pd.DataFrame | None = None, limiar_repeticoes: dict | None = None) -> pd.DataFrame:
    """Cruza as variantes ingeridas com a tabela de anotação.

    Ordem das chaves: (cromossomo, posição, ref, alt) → identificador rs (coluna ID do VCF) → para repetições,
    gene + contagem de repetições. Variantes sem correspondência recebem classe "nao_anotada".
    """
    tabela = carregar_tabela_curada() if tabela is None else tabela
    limiar = {**LIMIAR_PADRAO, **(limiar_repeticoes or {})}
    cols = ["clnsig", "estrelas", "heranca", "nome_curto", "hgvs_p", "rs_tabela", "citacao", "classe", "anotada", "fonte_anotacao", "limiar_patogenico"]
    saida = []
    snv = tabela[tabela.tipo != "repeticao"]
    por_chave = {(r.cromossomo, int(r.posicao_grch38), r.ref, r.alt): r for r in snv.itertuples(index=False)}
    por_rs = {r.rs: r for r in snv.itertuples(index=False) if isinstance(r.rs, str) and r.rs.startswith("rs")}
    for _, v in variantes.iterrows():
        a = {c: None for c in cols}
        a["anotada"], a["classe"] = False, "nao_anotada"
        if v.tipo == "repeticao":
            a.update(_anotar_repeticao(v, tabela, limiar))
        else:
            r = por_chave.get((str(v.cromossomo), int(v.posicao), v.ref, v.alt))
            fonte = "posicao_alelos"
            if r is None and isinstance(v.id, str) and v.id.startswith("rs"):
                r = por_rs.get(v.id)
                fonte = "rs"
            if r is not None:
                a.update({"anotada": True, "fonte_anotacao": f"tabela_curada:{fonte}", "clnsig": r.clnsig,
                          "estrelas": int(r.estrelas), "heranca": r.heranca if isinstance(r.heranca, str) else None,
                          "nome_curto": r.nome_curto, "hgvs_p": r.hgvs_p, "rs_tabela": r.rs, "citacao": r.citacao,
                          "classe": classificar_clnsig(r.clnsig)})
        saida.append(a)
    extra = pd.DataFrame(saida, index=variantes.index)
    return pd.concat([variantes, extra], axis=1)


def resumo_anotacao(anotadas: pd.DataFrame) -> pd.DataFrame:
    """Tabela 1 do relatório: perfil de variantes por amostra, gene e classe (apenas aprovadas no filtro)."""
    ap = anotadas[anotadas.aprovado]
    return (ap.groupby(["amostra", "gene", "classe"]).size().rename("n").reset_index()
            .pivot_table(index=["amostra", "gene"], columns="classe", values="n", fill_value=0).reset_index())


# ---------------------------------------------------------------------------
# Carregadores opcionais do subconjunto real (ClinVar variant_summary e exportação do dbSNP), TCC 4.2
# ---------------------------------------------------------------------------
def carregar_variant_summary(caminho: str | Path, genes=GENES, montagem: str = "GRCh38") -> pd.DataFrame:
    """Converte `variant_summary.txt` (filtrado pelos genes e pela montagem) para o formato da tabela curada."""
    usar = lambda c: True  # noqa: E731
    df = pd.read_csv(caminho, sep="\t", dtype=str, usecols=usar, low_memory=False)
    col = {c.lower(): c for c in df.columns}
    sig = col.get("germlineclassification") or col.get("clinicalsignificance")
    rev = col.get("germlinereviewstatus") or col.get("reviewstatus")
    df = df[df[col["genesymbol"]].isin(genes) & (df[col["assembly"]] == montagem)].copy()
    pos = pd.to_numeric(df[col["positionvcf"]], errors="coerce")
    df = df[pos.notna() & (pos > 0)]
    out = pd.DataFrame({
        "gene": df[col["genesymbol"]], "cromossomo": df[col["chromosome"]].astype(str),
        "posicao_grch38": pd.to_numeric(df[col["positionvcf"]]).astype(int),
        "ref": df[col["referenceallelevcf"]], "alt": df[col["alternateallelevcf"]],
        "rs": df[col["rs# (dbsnp)"]].map(lambda x: f"rs{x}" if str(x) not in ("-1", "nan", "") else None),
        "variation_id_clinvar": df[col["variationid"]], "hgvs_c": df[col["name"]], "hgvs_p": None,
        "nome_curto": df[col["name"]].str.extract(r"\((p\.[^)]+)\)")[0],
        "clnsig": df[sig], "estrelas": df[rev].map(estrelas_de_revstat), "heranca": None,
        "tipo": np.where((df[col["referenceallelevcf"]].str.len() == 1) & (df[col["alternateallelevcf"]].str.len() == 1), "snv", "indel"),
        "repeticoes_min": None, "citacao": "ClinVar variant_summary.txt (release informado em docs/05)", "conferido_em": None,
    })
    out["classe"] = out["clnsig"].map(classificar_clnsig)
    return out.reset_index(drop=True)


def desdobrar_frequencias(frequency: str) -> list[dict]:
    """Campo `frequency` do dbSNP: 'T:0.242812:1216:1000Genomes|...' → lista de dicionários (TCC 4.2.3)."""
    itens = []
    for bloco in re.split(r"[|;,]\s*", str(frequency or "")):
        partes = bloco.split(":")
        if len(partes) >= 4:
            itens.append({"alelo": partes[0], "frequencia": float(partes[1]), "contagem": int(float(partes[2])), "estudo": partes[3]})
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
