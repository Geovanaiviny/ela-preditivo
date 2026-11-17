"""Transmissão do C9orf72 por número de repetições GGGGCC (extensão experimental).

O núcleo do artefato representa cada lócus pela dosagem alélica 0/1/2 (TCC 4.3). Para a expansão do C9orf72, cujo
laudo laboratorial informa o número de repetições de cada alelo (TCC 4.2.1), este módulo modela a transmissão
no nível do alelo:

- cada genitor tem dois alelos (um informado = o outro é suposto normal, `alelo_normal_suposto` no YAML);
- cada genitor transmite um dos dois alelos com probabilidade 1/2 (segregação mendeliana), o que dá quatro genótipos
  equiprováveis para o descendente;
- hipótese de instabilidade na transmissão: o alelo transmitido muda de `delta_mae`/`delta_pai` repetições quando já está
  na faixa intermediária ou acima (`instabilidade_a_partir_de`); alelos normais são considerados estáveis;
- o descendente é portador quando algum alelo recebido atinge o limiar patogênico (classe `risco` de `anotacao`);
- hipótese de antecipação: a idade de início do descendente é deslocada `antecipacao` anos para antes (G(t) deslocada).

A **dosagem efetiva** de um genitor (número de alelos que estarão acima do limiar após a transmissão) alimenta o núcleo
estocástico existente sem alterá-lo: P(portador) = 1 − (1 − d_m/2)(1 − d_f/2) coincide com a enumeração dos quatro
genótipos. Com deltas e antecipação iguais a zero o resultado é idêntico ao do modelo por dosagem.

Tudo aqui é **hipótese experimental**: a literatura citada no TCC não traz parâmetros de instabilidade nem de
antecipação para o C9orf72, e as saídas são rotuladas como tal. Não usar em decisões sobre pacientes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from . import anotacao
from .calibracao import Parametros
from .exato import prob_portador
from .genotipo import GENE_EXPANSAO
from .monte_carlo import Locus

ROTULO_EXPERIMENTAL = "hipótese experimental (sem parâmetro na literatura citada no TCC); não usar clinicamente"
ALELO_NORMAL_PADRAO = 2  # repetições supostas para o alelo não informado no laudo (faixa normal: 2 a 23)


@dataclass(frozen=True)
class HipotesesC9orf72:
    """Hipóteses experimentais da tela de análise: `c9_delta_mae`, `c9_delta_pai` (repetições, ±) e `c9_antecipacao` (anos)."""

    delta_mae: int = 0
    delta_pai: int = 0
    antecipacao: float = 0.0

    @classmethod
    def de_dict(cls, d: dict | None) -> "HipotesesC9orf72":
        d = d or {}

        def _int(chave):
            v = d.get(chave, d.get(f"c9_{chave}"))
            return 0 if v is None or v == "" else int(v)

        v = d.get("antecipacao", d.get("c9_antecipacao"))
        return cls(_int("delta_mae"), _int("delta_pai"), 0.0 if v is None or v == "" else float(v))

    @property
    def ativa(self) -> bool:
        return bool(self.delta_mae or self.delta_pai or self.antecipacao)

    def como_dict(self) -> dict:
        return {"delta_mae": self.delta_mae, "delta_pai": self.delta_pai, "antecipacao": self.antecipacao}


def alelos_do_laudo(valor, alelo_normal: int = ALELO_NORMAL_PADRAO) -> tuple[int, int] | None:
    """Laudo de um genitor → (alelo menor, alelo maior). Um só inteiro = o outro alelo é suposto normal."""
    if valor is None:
        return None
    alelos = [int(x) for x in (valor if isinstance(valor, (list, tuple)) else [valor]) if x is not None]
    if not alelos:
        return None
    if len(alelos) == 1:
        alelos.append(int(alelo_normal))
    return tuple(sorted(alelos[:2]))


def alelo_transmitido(repeticoes: int, delta: int, instabilidade_a_partir_de: int) -> int:
    """Repetições do alelo após a transmissão: o delta só se aplica a alelos já instáveis (≥ faixa intermediária)."""
    if delta and repeticoes >= instabilidade_a_partir_de:
        return max(0, int(repeticoes) + int(delta))
    return int(repeticoes)


@dataclass
class TransmissaoC9orf72:
    hipoteses: HipotesesC9orf72
    alelos_mae: tuple[int, int] | None
    alelos_pai: tuple[int, int] | None
    patogenico: int
    intermediario: int
    alelo_normal: int
    genotipos: pd.DataFrame  # quatro genótipos possíveis do descendente, com probabilidade 1/4 cada
    dosagem_laudo_mae: int
    dosagem_laudo_pai: int
    dosagem_efetiva_mae: int
    dosagem_efetiva_pai: int

    @property
    def p_portador(self) -> float:
        return prob_portador(self.dosagem_efetiva_mae, self.dosagem_efetiva_pai, "dominante")

    @property
    def p_portador_sem_hipotese(self) -> float:
        return prob_portador(self.dosagem_laudo_mae, self.dosagem_laudo_pai, "dominante")

    @property
    def p_intermediario(self) -> float:
        g = self.genotipos
        return float(g.loc[g.classe_descendente == "intermediaria", "probabilidade"].sum())

    def resumo(self) -> dict:
        return {
            "rotulo": ROTULO_EXPERIMENTAL,
            "hipoteses": self.hipoteses.como_dict(),
            "alelos_mae": list(self.alelos_mae) if self.alelos_mae else None,
            "alelos_pai": list(self.alelos_pai) if self.alelos_pai else None,
            "alelo_normal_suposto": self.alelo_normal,
            "limiar_patogenico": self.patogenico,
            "limiar_intermediario": self.intermediario,
            "dosagem_laudo": {"mae": self.dosagem_laudo_mae, "pai": self.dosagem_laudo_pai},
            "dosagem_efetiva": {"mae": self.dosagem_efetiva_mae, "pai": self.dosagem_efetiva_pai},
            "p_portador_sem_hipotese": self.p_portador_sem_hipotese,
            "p_portador_com_hipotese": self.p_portador,
            "p_alelo_intermediario_descendente": self.p_intermediario,
            "genotipos": self.genotipos.to_dict(orient="records"),
        }

    def texto(self, mediana_antes: float | None = None, mediana_depois: float | None = None) -> str:
        """Parágrafo do relatório."""
        h = self.hipoteses

        def _al(a):
            return "sem laudo" if a is None else f"({a[0]}, {a[1]})"

        linhas = [
            f"Laudo: mãe {_al(self.alelos_mae)}, pai {_al(self.alelos_pai)} repetições GGGGCC (alelo não informado suposto "
            f"normal = {self.alelo_normal}; limiar patogênico ≥ {self.patogenico}; intermediário {self.intermediario}–{self.patogenico - 1}). "
            f"Hipóteses: Δ materno {h.delta_mae:+d}, Δ paterno {h.delta_pai:+d} repetições no alelo transmitido (só alelos ≥ {self.intermediario}); "
            f"antecipação {h.antecipacao:g} anos.",
            "Genótipos possíveis do descendente (maior alelo recebido, probabilidade 1/4 cada): "
            + "; ".join(f"{r.maior_alelo_descendente} ({r.classe_descendente})" for r in self.genotipos.itertuples())
            + ".",
            f"P(portador) = {100 * self.p_portador:.1f}% com a hipótese (dosagem efetiva mãe {self.dosagem_efetiva_mae}, pai "
            f"{self.dosagem_efetiva_pai}) contra {100 * self.p_portador_sem_hipotese:.1f}% pelo laudo sem hipótese "
            f"(dosagem {self.dosagem_laudo_mae}/{self.dosagem_laudo_pai}); P(alelo intermediário no descendente) = {100 * self.p_intermediario:.1f}%.",
        ]
        if h.antecipacao and mediana_antes is not None and mediana_depois is not None:
            linhas.append(
                f"G(t) do C9orf72 deslocada em −{h.antecipacao:g} anos: idade mediana de início {mediana_antes:.1f} → {mediana_depois:.1f} anos."
            )
        linhas.append(f"Rótulo: {ROTULO_EXPERIMENTAL}.")
        return " ".join(linhas)


def transmissao_c9orf72(
    laudo: dict | None,
    hipoteses: HipotesesC9orf72 | dict | None,
    parametros: Parametros,
    tabela: pd.DataFrame | None = None,
) -> TransmissaoC9orf72 | None:
    """Enumera a transmissão alélica do C9orf72 a partir do laudo dos genitores.

    None se faltar o laudo de qualquer genitor: genitor não testado tem o C9orf72 indeterminado e a hipótese não
    pode supor alelos normais para ele.
    """
    hip = hipoteses if isinstance(hipoteses, HipotesesC9orf72) else HipotesesC9orf72.de_dict(hipoteses)
    laudo = {k: v for k, v in (laudo or {}).items() if k in ("mae", "pai") and v is not None}
    if not laudo or any(lado not in laudo for lado in ("mae", "pai")):
        return None
    tabela = anotacao.carregar_tabela_curada() if tabela is None else tabela
    limiar = {**anotacao.LIMIAR_PADRAO, **(parametros.limiar_repeticoes or {})}
    pat = anotacao.limiar_patogenico_repeticao(tabela, GENE_EXPANSAO, limiar)
    inter = int(limiar.get("intermediario", 24))
    normal = int(limiar.get("alelo_normal_suposto", ALELO_NORMAL_PADRAO))
    instavel = int(limiar.get("instabilidade_a_partir_de", inter))
    alelos = {lado: alelos_do_laudo(laudo.get(lado), normal) or (normal, normal) for lado in ("mae", "pai")}
    deltas = {"mae": hip.delta_mae, "pai": hip.delta_pai}
    linhas = []
    for am in alelos["mae"]:
        tm = alelo_transmitido(am, deltas["mae"], instavel)
        for ap in alelos["pai"]:
            tp = alelo_transmitido(ap, deltas["pai"], instavel)
            maior = max(tm, tp)
            linhas.append(
                {
                    "alelo_materno": am,
                    "alelo_materno_transmitido": tm,
                    "classe_materno": anotacao.classe_por_repeticoes(tm, pat, inter),
                    "alelo_paterno": ap,
                    "alelo_paterno_transmitido": tp,
                    "classe_paterno": anotacao.classe_por_repeticoes(tp, pat, inter),
                    "maior_alelo_descendente": maior,
                    "classe_descendente": anotacao.classe_por_repeticoes(maior, pat, inter),
                    "probabilidade": 0.25,
                }
            )
    genotipos = pd.DataFrame(linhas)

    def _dosagem(lado, com_delta: bool) -> int:
        n = 0
        for a in alelos[lado]:
            t = alelo_transmitido(a, deltas[lado], instavel) if com_delta else a
            n += anotacao.classe_por_repeticoes(t, pat, inter) == "risco"
        return min(2, n)

    return TransmissaoC9orf72(
        hipoteses=hip,
        alelos_mae=alelos_do_laudo(laudo.get("mae"), normal),
        alelos_pai=alelos_do_laudo(laudo.get("pai"), normal),
        patogenico=int(pat),
        intermediario=inter,
        alelo_normal=normal,
        genotipos=genotipos,
        dosagem_laudo_mae=_dosagem("mae", False),
        dosagem_laudo_pai=_dosagem("pai", False),
        dosagem_efetiva_mae=_dosagem("mae", True),
        dosagem_efetiva_pai=_dosagem("pai", True),
    )


def aplicar_ao_vetor(
    vetor: pd.DataFrame, transmissao: TransmissaoC9orf72, parametros: Parametros, tabela: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Vetor de dosagens com a linha do C9orf72 (tipo `repeticao`) substituída pela dosagem efetiva.

    Se o laudo não gerou lócus (nenhum alelo expandido) mas a hipótese faz um alelo cruzar o limiar, a linha é criada a
    partir da linha de repetição da tabela de anotação (mesma fonte de patogenicidade que `genotipo`). Se a hipótese
    faz a dosagem efetiva cair a zero nos dois genitores, a linha é removida (o lócus deixa de ser informativo).
    """
    vetor = vetor.copy()
    indeterminado = (vetor.gene == GENE_EXPANSAO) & (vetor.tipo == "repeticao") & vetor.descartado.astype(bool)
    if indeterminado.any():  # genitor sem laudo: a hipótese não recria um lócus indeterminado
        return vetor
    obs = (
        f"dosagem efetiva pela transmissão por repetições (Δ mãe {transmissao.hipoteses.delta_mae:+d}, Δ pai "
        f"{transmissao.hipoteses.delta_pai:+d}; laudo {transmissao.dosagem_laudo_mae}/{transmissao.dosagem_laudo_pai}); {ROTULO_EXPERIMENTAL}"
    )
    sel = (vetor.gene == GENE_EXPANSAO) & (vetor.tipo == "repeticao") & (~vetor.descartado.astype(bool))
    dm, dp = transmissao.dosagem_efetiva_mae, transmissao.dosagem_efetiva_pai
    if sel.any():
        if dm + dp == 0:
            return vetor[~sel].reset_index(drop=True)
        i = vetor.index[sel][0]
        vetor.loc[i, ["dosagem_mae", "dosagem_pai"]] = [dm, dp]
        vetor.loc[i, "p_portador_exato"] = prob_portador(dm, dp, str(vetor.loc[i, "heranca"]))
        atual = str(vetor.loc[i, "observacao"] or "")
        vetor.loc[i, "observacao"] = (atual + "; " if atual else "") + obs
        return vetor
    if dm + dp == 0:
        return vetor
    tabela = anotacao.carregar_tabela_curada() if tabela is None else tabela
    cand = tabela[(tabela.tipo == "repeticao") & (tabela.gene == GENE_EXPANSAO)]
    if cand.empty or anotacao.classificar_clnsig(cand.iloc[0].clnsig) != "risco":
        raise ValueError(
            f"a tabela de anotação não tem a linha de repetição patogênica do {GENE_EXPANSAO}; sem ela a hipótese não pode criar o lócus"
        )
    r = cand.iloc[0]
    heranca = r.heranca if isinstance(r.heranca, str) else parametros.genes[GENE_EXPANSAO].heranca
    linha = {
        "gene": GENE_EXPANSAO,
        "variante": r.nome_curto if isinstance(r.nome_curto, str) else "expansão GGGGCC",
        "rs": r.rs if isinstance(r.rs, str) else None,
        "tipo": "repeticao",
        "heranca": heranca,
        "dosagem_mae": dm,
        "dosagem_pai": dp,
        "repeticoes_mae": transmissao.alelos_mae[1] if transmissao.alelos_mae else None,
        "repeticoes_pai": transmissao.alelos_pai[1] if transmissao.alelos_pai else None,
        "clnsig": r.clnsig,
        "estrelas": int(r.estrelas),
        "fonte": "laudo",
        "p_portador_exato": prob_portador(dm, dp, heranca),
        "descartado": False,
        "observacao": "lócus criado pela hipótese: alelo intermediário cruza o limiar após a transmissão; " + obs,
    }
    return pd.concat([vetor, pd.DataFrame([linha], columns=vetor.columns)], ignore_index=True)


def aplicar_antecipacao(loci: list[Locus], antecipacao: float) -> list[Locus]:
    """Lóci com G(t) do C9orf72 deslocada `antecipacao` anos para antes (demais lóci inalterados)."""
    if not antecipacao:
        return list(loci)
    return [replace(l, dist=l.dist.deslocar(-float(antecipacao))) if l.gene == GENE_EXPANSAO else l for l in loci]
