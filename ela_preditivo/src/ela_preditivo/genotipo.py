"""Vetor genotípico parental (TCC, seção 4.3): dosagem alélica 0/1/2 por lócus de risco, materna e paterna,
que alimenta o nó inicial da Rede Bayesiana."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calibracao import Parametros
from .exato import prob_portador


def _chave(v: pd.Series) -> str:
    if v.tipo == "repeticao":
        return f"{v.gene}:expansao"
    rs = v.rs_tabela if isinstance(v.rs_tabela, str) else (v.id if isinstance(v.id, str) else None)
    return rs or f"{v.gene}:{v.cromossomo}:{v.posicao}:{v.ref}>{v.alt}"


def vetor_dosagem(anotadas_mae: pd.DataFrame, anotadas_pai: pd.DataFrame, parametros: Parametros) -> pd.DataFrame:
    """Uma linha por lócus de risco (classe "risco", aprovado no filtro) presente em pelo menos um genitor.

    Colunas: gene, variante, rs, heranca, tipo, repeticoes_mae/pai, dosagem_mae, dosagem_pai, p_portador_exato, observacao.
    A herança vem da anotação (ex.: SOD1 p.D91A recessiva) e, na falta dela, do gene no YAML.
    """
    loci: dict[str, dict] = {}
    for lado, df in (("mae", anotadas_mae), ("pai", anotadas_pai)):
        sel = df[df.aprovado & (df.classe == "risco") & df.gene.notna()]
        for _, v in sel.iterrows():
            k = _chave(v)
            d = loci.setdefault(k, {"gene": v.gene, "variante": v.nome_curto or k, "rs": v.rs_tabela or v.id, "tipo": v.tipo,
                                    "heranca": v.heranca if isinstance(v.heranca, str) else parametros.genes[v.gene].heranca,
                                    "dosagem_mae": 0, "dosagem_pai": 0, "repeticoes_mae": None, "repeticoes_pai": None,
                                    "estrelas": int(v.estrelas) if pd.notna(v.estrelas) else 0, "clnsig": v.clnsig, "observacao": ""})
            dose = int(v.dosagem) if pd.notna(v.dosagem) else 0
            if d[f"dosagem_{lado}"] and dose:
                d["observacao"] = "mais de um registro de risco no mesmo lócus; dosagens somadas (máx. 2)"
            d[f"dosagem_{lado}"] = min(2, d[f"dosagem_{lado}"] + dose)
            if v.tipo == "repeticao" and dose > 0:
                d[f"repeticoes_{lado}"] = v.repeticoes
    # dosagem 0 em ambos (ex.: variante de risco registrada como 0/0 nos dois) não é lócus informativo
    linhas = [d for d in loci.values() if d["dosagem_mae"] + d["dosagem_pai"] > 0]
    for d in linhas:
        d["p_portador_exato"] = prob_portador(d["dosagem_mae"], d["dosagem_pai"], d["heranca"])
    cols = ["gene", "variante", "rs", "tipo", "heranca", "dosagem_mae", "dosagem_pai", "repeticoes_mae", "repeticoes_pai",
            "clnsig", "estrelas", "p_portador_exato", "observacao"]
    df = pd.DataFrame(linhas, columns=cols)
    # dois lóci de risco no mesmo gene: tratados como independentes (limitação registrada no relatório)
    dup = df.gene.duplicated(keep=False)
    df.loc[dup, "observacao"] = (df.loc[dup, "observacao"] + "; " if df.loc[dup, "observacao"].ne("").any() else "") + "mais de um lócus de risco no gene, tratados como independentes"
    return df.reset_index(drop=True)


def perfil_variantes(anotadas_mae: pd.DataFrame, anotadas_pai: pd.DataFrame) -> pd.DataFrame:
    """Perfil completo (aprovadas) para o relatório: inclui benignas, VUS, intermediárias e não anotadas."""
    cols = ["amostra", "gene", "cromossomo", "posicao", "ref", "alt", "id", "tipo", "dosagem", "repeticoes",
            "classe", "clnsig", "estrelas", "nome_curto", "heranca", "fonte_anotacao"]
    df = pd.concat([anotadas_mae, anotadas_pai], ignore_index=True)
    df = df.loc[df.aprovado, cols].copy()
    df.loc[df.dosagem.fillna(0) == 0, "repeticoes"] = np.nan   # contagem só faz sentido para o genitor que porta o alelo
    return df.sort_values(["amostra", "cromossomo", "posicao"]).reset_index(drop=True)
