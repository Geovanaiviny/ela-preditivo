"""Vetor genotípico parental (TCC, seção 4.3): dosagem alélica 0/1/2 por lócus de risco, materna e paterna,
que alimenta o nó inicial da Rede Bayesiana.

A expansão do C9orf72 entra pelo laudo laboratorial (`laudo_c9orf72`), porque o VCF de variantes curtas não a
detecta (TCC 4.2.1). Se o VCF trouxer a expansão (caminho secundário), o laudo prevalece e a divergência é anotada.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from . import anotacao
from .calibracao import Parametros
from .exato import prob_portador

GENE_EXPANSAO = "C9orf72"
CHAVE_EXPANSAO = f"{GENE_EXPANSAO}:expansao"
ROTULO_LADO = {"mae": "mãe", "pai": "pai"}
ARTIGO_LADO = {"mae": "a mãe", "pai": "o pai"}


def _chave(v: pd.Series) -> str:
    """Chave do lócus: gene + coordenada + alelos (um rs pode cobrir vários alelos, ex.: FUS p.Arg521Cys/Gly/Ser)."""
    if v.tipo == "repeticao":
        return f"{v.gene}:expansao"
    return f"{v.gene}:{v.cromossomo}:{v.posicao}:{v.ref}>{v.alt}"


def interpretar_laudo_c9orf72(valor) -> tuple[int | None, int | None]:
    """Laudo de um genitor → (dosagem do alelo expandido candidato, maior contagem de repetições).

    Aceita: None (genitor não testado → dosagem indeterminada, `None`; o C9orf72 desse genitor nunca vale como "sem
    expansão"), um inteiro (repetições do maior alelo; o outro é considerado normal) ou um par de inteiros
    (repetições dos dois alelos). A dosagem devolvida ainda não aplica o limiar; ver `vetor_dosagem`.
    """
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None, None
    if isinstance(valor, (list, tuple)):
        alelos = [int(x) for x in valor if x is not None and not (isinstance(x, float) and np.isnan(x))]
    else:
        alelos = [int(valor)]
    if not alelos:
        return None, None
    return len(alelos), max(alelos)


def _locus_laudo_c9orf72(
    laudo: dict, parametros: Parametros, tabela: pd.DataFrame, sempre: bool = False
) -> dict | None:
    """Lócus do C9orf72 construído a partir do laudo dos dois genitores (None se nenhum alelo expandido).

    `sempre=True` devolve a linha mesmo sem alelo expandido: é como `vetor_dosagem` registra o lócus descartado quando
    falta o laudo de um genitor.
    """
    limiar = {**anotacao.LIMIAR_PADRAO, **(parametros.limiar_repeticoes or {})}
    pat = anotacao.limiar_patogenico_repeticao(tabela, GENE_EXPANSAO, limiar)
    inter = int(limiar.get("intermediario", 24))
    cand = tabela[(tabela.tipo == "repeticao") & (tabela.gene == GENE_EXPANSAO)]
    # a patogenicidade da expansão vem da linha de repetição da tabela de anotação (clnsig, estrelas, citação); o artefato
    # não a assume por conta própria (TCC 4.2.2): sem a linha, ou com classificação que não sustenta risco, falha com motivo
    if cand.empty:
        raise ValueError(
            f"a tabela de anotação não tem a linha de repetição do {GENE_EXPANSAO} (tipo = repeticao, com clnsig, estrelas e "
            "citação): sem ela o laudo não pode ser classificado e o artefato não assume patogenicidade por conta própria (TCC 4.2.2)"
        )
    r = cand.iloc[0]
    if anotacao.classificar_clnsig(r.clnsig) != "risco":
        raise ValueError(
            f"a linha de repetição do {GENE_EXPANSAO} na tabela de anotação está classificada como {r.clnsig!r}, que não sustenta risco "
            "(TCC 4.2.2); o laudo não pode virar lócus de risco sem fonte que o classifique como patogênico"
        )
    d = {
        "gene": GENE_EXPANSAO,
        "variante": (r.nome_curto if isinstance(r.nome_curto, str) else "expansão GGGGCC"),
        "rs": (r.rs if isinstance(r.rs, str) else None),
        "tipo": "repeticao",
        "heranca": (r.heranca if isinstance(r.heranca, str) else parametros.genes[GENE_EXPANSAO].heranca),
        "dosagem_mae": 0,
        "dosagem_pai": 0,
        "repeticoes_mae": None,
        "repeticoes_pai": None,
        "clnsig": r.clnsig,
        "estrelas": int(r.estrelas),
        "fonte": "laudo",
        "observacao": "",
    }
    classes = []
    for lado in ("mae", "pai"):
        valor = laudo.get(lado)
        if valor is None:
            continue
        alelos = [int(x) for x in (valor if isinstance(valor, (list, tuple)) else [valor])]
        expandidos = [a for a in alelos if anotacao.classe_por_repeticoes(a, pat, inter) == "risco"]
        intermed = [a for a in alelos if anotacao.classe_por_repeticoes(a, pat, inter) == "intermediaria"]
        d[f"dosagem_{lado}"] = min(2, len(expandidos))
        d[f"repeticoes_{lado}"] = max(alelos) if alelos else None
        if intermed and not expandidos:
            classes.append(
                f"{lado}: {max(intermed)} repetições no C9orf72, faixa intermediária ({inter}–{pat - 1}), não contada como risco"
            )
    if classes:
        d["observacao"] = "; ".join(classes)
    if d["dosagem_mae"] + d["dosagem_pai"] > 0 or sempre:
        return d
    if classes:
        warnings.warn("; ".join(classes), stacklevel=3)
    return None


def _nota_regra(v: pd.Series) -> str:
    """Texto de rastreabilidade quando a classe `risco` veio da regra qualificada para conflitantes."""
    if "regra_qualificada" in v and bool(v.get("regra_qualificada")) and isinstance(v.get("nota_regra"), str):
        return str(v["nota_regra"])
    return ""


def concatenar_anotadas(anotadas_mae: pd.DataFrame, anotadas_pai: pd.DataFrame) -> pd.DataFrame:
    """Anotadas dos dois genitores num só quadro. Colunas totalmente vazias num dos lados (ex.: `nota_regra`, só
    preenchida para variantes aceitas pela regra qualificada) fariam o pandas 2 avisar sobre a inferência futura de
    dtype; o resultado não muda, e o aviso é silenciado para não poluir a saída da linha de comando."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning, message=".*empty or all-NA entries.*")
        return pd.concat([anotadas_mae, anotadas_pai], ignore_index=True)


def _sem_genotipo(df: pd.DataFrame) -> pd.Series:
    """Registros cujo genótipo não foi determinado no VCF (GT ausente ou './.', marcados `genotipo_ausente` na ingestão)."""
    sem = df["dosagem"].isna() if "dosagem" in df else pd.Series(False, index=df.index)
    if "motivo_reprovacao" in df:
        sem = sem | df["motivo_reprovacao"].fillna("").astype(str).str.contains("genotipo_ausente")
    return sem.fillna(False).astype(bool)


def vetor_dosagem(
    anotadas_mae: pd.DataFrame,
    anotadas_pai: pd.DataFrame,
    parametros: Parametros,
    laudo_c9orf72: dict | None = None,
    tabela: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Uma linha por lócus de risco (classe "risco", aprovado no filtro) presente em pelo menos um genitor.

    Colunas: gene, variante, rs, heranca, tipo, repeticoes_mae/pai, dosagem_mae, dosagem_pai, fonte, p_portador_exato, descartado, observacao.
    A herança vem da anotação (ex.: SOD1 p.D91A recessiva) e, na falta dela, do gene no YAML.

    Sítio de risco com genótipo não determinado (GT ausente ou './.') em qualquer genitor: o lócus inteiro é descartado do
    cálculo (TCC 4.3) — nunca vale como dosagem 0 — e permanece na tabela com `descartado = True`, a dosagem desconhecida
    vazia e o motivo em `observacao`; `monte_carlo.loci_de_vetor` ignora essas linhas.

    `laudo_c9orf72`: {"mae": <repetições>, "pai": <repetições>} vindo do laudo laboratorial (TCC 4.2.1); cada valor
    pode ser um inteiro (maior alelo) ou um par de inteiros. Genitor ausente do dicionário = não testado: o C9orf72 desse
    genitor é indeterminado e o lócus inteiro sai do cálculo como genótipo indeterminado (linha com `descartado = True`
    e o motivo em `observacao`), nunca como dosagem 0. O laudo é a única fonte que determina o C9orf72 de um
    genitor; com laudo, uma eventual detecção da expansão no VCF é conferida, prevalece o laudo e a divergência fica
    registrada em `observacao`.
    """
    loci: dict[str, dict] = {}
    for lado, df in (("mae", anotadas_mae), ("pai", anotadas_pai)):
        sel = df[df.aprovado & (df.classe == "risco") & df.gene.notna()]
        for _, v in sel.iterrows():
            k = _chave(v)
            d = loci.setdefault(
                k,
                {
                    "gene": v.gene,
                    "variante": v.nome_curto or k,
                    "rs": v.rs_tabela or v.id,
                    "tipo": v.tipo,
                    "heranca": v.heranca if isinstance(v.heranca, str) else parametros.genes[v.gene].heranca,
                    "dosagem_mae": 0,
                    "dosagem_pai": 0,
                    "repeticoes_mae": None,
                    "repeticoes_pai": None,
                    "estrelas": int(v.estrelas) if pd.notna(v.estrelas) else 0,
                    "clnsig": v.clnsig,
                    "fonte": "vcf",
                    "observacao": _nota_regra(v),  # lócus aceito pela regra qualificada: abertura do conflito
                },
            )
            dose = int(v.dosagem) if pd.notna(v.dosagem) else 0
            if d[f"dosagem_{lado}"] and dose:
                d["observacao"] = "mais de um registro de risco no mesmo lócus; dosagens somadas (máx. 2)"
            d[f"dosagem_{lado}"] = min(2, d[f"dosagem_{lado}"] + dose)
            if v.tipo == "repeticao" and dose > 0:
                d[f"repeticoes_{lado}"] = v.repeticoes
                d["observacao"] = (
                    d["observacao"] + "; " if d["observacao"] else ""
                ) + "expansão lida do VCF (caminho secundário; o fluxo do TCC 4.2.1 usa o laudo)"
    laudo = {k: v for k, v in (laudo_c9orf72 or {}).items() if k in ("mae", "pai") and v is not None}
    sem_laudo = [lado for lado in ("mae", "pai") if lado not in laudo]
    do_vcf = loci.pop(CHAVE_EXPANSAO, None)
    tabela = anotacao.carregar_tabela_curada() if tabela is None else tabela
    if sem_laudo:
        # Genótipo indeterminado (TCC 4.3): genitor sem laudo não foi testado para a expansão; o C9orf72 dele é
        # indeterminado e o lócus inteiro sai do cálculo, registrado com dosagem vazia e o motivo. Nunca vale como
        # dosagem 0, porque subestimaria o risco. O laudo é a única fonte (TCC 4.2.1): um registro da expansão no VCF
        # (caminho secundário) não substitui o laudo e fica só na observação.
        d = _locus_laudo_c9orf72(laudo, parametros, tabela, sempre=True)
        for lado in sem_laudo:
            d[f"dosagem_{lado}"], d[f"repeticoes_{lado}"] = None, None
        quem = " e ".join(ARTIGO_LADO[lado] for lado in sem_laudo)
        msg = f"laudo do C9orf72 não informado para {quem}: lócus indeterminado (TCC 4.3)"
        if do_vcf is not None:
            msg += (
                "; o VCF traz registro da expansão (caminho secundário), mas sem laudo o genitor é indeterminado "
                "(TCC 4.2.1)"
            )
        d["observacao"] = (d["observacao"] + "; " if d["observacao"] else "") + msg
        d["descartado"] = True
        warnings.warn(f"{GENE_EXPANSAO}: {msg}", stacklevel=2)
        loci[CHAVE_EXPANSAO] = d
    else:  # laudo dos dois genitores
        do_laudo = _locus_laudo_c9orf72(laudo, parametros, tabela)
        if do_laudo is not None:
            if do_vcf is not None:
                diverge = [lado for lado in laudo if do_vcf[f"dosagem_{lado}"] != do_laudo[f"dosagem_{lado}"]]
                if diverge:
                    msg = f"laudo e VCF divergem na dosagem do C9orf72 ({', '.join(diverge)}); prevalece o laudo"
                    warnings.warn(msg, stacklevel=2)
                    do_laudo["observacao"] = (do_laudo["observacao"] + "; " if do_laudo["observacao"] else "") + msg
                else:
                    do_laudo["fonte"] = "laudo+vcf"
            loci[CHAVE_EXPANSAO] = do_laudo
        elif do_vcf is not None:
            warnings.warn(
                "laudo do C9orf72 sem expansão, mas o VCF trazia uma; prevalece o laudo (lócus descartado)",
                stacklevel=2,
            )
    # TCC 4.3: sítio com genótipo não determinado em qualquer genitor → o lócus inteiro é descartado do cálculo e fica
    # registrado (dosagem desconhecida vazia, `descartado = True`, motivo em `observacao`); nunca vale como dosagem 0
    rotulo_lado = ROTULO_LADO
    for lado, df_lado in (("mae", anotadas_mae), ("pai", anotadas_pai)):
        sel = df_lado[_sem_genotipo(df_lado) & (df_lado.classe == "risco") & df_lado.gene.notna()]
        for _, v in sel.iterrows():
            k = _chave(v)
            if k == CHAVE_EXPANSAO:  # o C9orf72 é determinado só pelo laudo (TCC 4.2.1); o VCF não decide esse lócus
                continue
            d = loci.get(k)
            if d is None:
                d = loci[k] = {
                    "gene": v.gene,
                    "variante": v.nome_curto or k,
                    "rs": v.rs_tabela or v.id,
                    "tipo": v.tipo,
                    "heranca": v.heranca if isinstance(v.heranca, str) else parametros.genes[v.gene].heranca,
                    "dosagem_mae": 0,
                    "dosagem_pai": 0,
                    "repeticoes_mae": None,
                    "repeticoes_pai": None,
                    "estrelas": int(v.estrelas) if pd.notna(v.estrelas) else 0,
                    "clnsig": v.clnsig,
                    "fonte": "vcf",
                    "observacao": "",
                }
            d[f"dosagem_{lado}"] = None
            lados = d.setdefault("lados_indeterminados", [])
            if rotulo_lado[lado] not in lados:
                lados.append(rotulo_lado[lado])
    for d in loci.values():
        lados = d.pop("lados_indeterminados", None)
        d["descartado"] = bool(lados) or bool(d.get("descartado", False))
        if lados:
            msg = f"genótipo não determinado no VCF ({' e '.join(lados)}); lócus descartado do cálculo, sem atribuir dosagem 0 (TCC 4.3)"
            d["observacao"] = (d["observacao"] + "; " if d["observacao"] else "") + msg
            warnings.warn(f"{d['gene']} {d['variante']}: {msg}", stacklevel=2)
    # dosagem 0 em ambos (ex.: variante de risco registrada como 0/0 nos dois) não é lócus informativo
    linhas = [d for d in loci.values() if d["descartado"] or d["dosagem_mae"] + d["dosagem_pai"] > 0]
    for d in linhas:
        d["p_portador_exato"] = (
            np.nan if d["descartado"] else prob_portador(d["dosagem_mae"], d["dosagem_pai"], d["heranca"])
        )
    cols = [
        "gene",
        "variante",
        "rs",
        "tipo",
        "heranca",
        "dosagem_mae",
        "dosagem_pai",
        "repeticoes_mae",
        "repeticoes_pai",
        "clnsig",
        "estrelas",
        "fonte",
        "p_portador_exato",
        "descartado",
        "observacao",
    ]
    df = pd.DataFrame(linhas, columns=cols)
    df["descartado"] = df["descartado"].astype(bool)
    # dois lóci de risco no mesmo gene (entre os que entram no cálculo): tratados como independentes (limitação registrada no relatório)
    dup = (~df.descartado) & df.gene.where(~df.descartado).duplicated(keep=False)
    df.loc[dup, "observacao"] = (
        df.loc[dup, "observacao"] + "; " if df.loc[dup, "observacao"].ne("").any() else ""
    ) + "mais de um lócus de risco no gene, tratados como independentes"
    return df.reset_index(drop=True)


def perfil_variantes(anotadas_mae: pd.DataFrame, anotadas_pai: pd.DataFrame) -> pd.DataFrame:
    """Perfil completo (aprovadas) para o relatório: inclui benignas, VUS, intermediárias e não anotadas."""
    cols = [
        "amostra",
        "gene",
        "cromossomo",
        "posicao",
        "ref",
        "alt",
        "id",
        "tipo",
        "dosagem",
        "repeticoes",
        "classe",
        "clnsig",
        "estrelas",
        "nome_curto",
        "heranca",
        "regra_qualificada",
        "fonte_anotacao",
    ]
    df = concatenar_anotadas(anotadas_mae, anotadas_pai)
    df = df.loc[df.aprovado, cols].copy()
    df.loc[df.dosagem.fillna(0) == 0, "repeticoes"] = np.nan  # contagem só faz sentido para o genitor que porta o alelo
    return df.sort_values(["amostra", "cromossomo", "posicao"]).reset_index(drop=True)
