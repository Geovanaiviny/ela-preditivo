"""Avaliação do artefato (TCC, seções 3.4 e 4.5): aderência teórica, estabilidade numérica, coerência das curvas,
tempo de processamento e análises de sensibilidade; e a verificação com famílias sintéticas de desfecho conhecido:
calibração (Brier e curva por decis), discriminação (C-index de Harrell e AUC dependente do tempo), erro da idade de
início com o piso teórico, cobertura dos intervalos, divergência entre curvas (Kolmogorov-Smirnov e Wasserstein),
robustez a erros no VCF e sensibilidade tipo tornado.

Com dados sintéticos gerados pelo próprio modelo, essas métricas medem verificação (a implementação reproduz o modelo
especificado), não validação contra pacientes reais. Para não ficar só circular, cada uma é calculada em dois mundos:
verdade = modelo e verdade alternativa (desfecho sorteado com parâmetros diferentes dos da previsão).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import calibracao, sobrevivencia
from .calibracao import Parametros
from .exato import (
    DistribuicaoInicio,
    combinar_independentes,
    desvio_absoluto_inicio_condicional,
    f_qualquer,
    f_qualquer_grade,
    inicio_por_causa,
    prob_portador_condicional,
    quantil_inicio_condicional,
)
from .monte_carlo import Locus, ResultadoSimulacao, repetir, simular_numpy
from .rede_bayesiana import simular_pymc


def aderencia(res_pymc: ResultadoSimulacao, res_numpy: ResultadoSimulacao) -> pd.DataFrame:
    """Tabela 2: probabilidades exatas vs Monte Carlo (PyMC e NumPy), desvio em erros padrão e qui-quadrado do genótipo."""
    rp, rn = res_pymc.resumo(), res_numpy.resumo()
    fg_p, fg_n = res_pymc.frequencias_genotipo(), res_numpy.frequencias_genotipo()
    linhas = []
    for j in range(len(rp)):
        p, n = rp.iloc[j], rn.iloc[j]
        linhas.append(
            {
                "variante": p.variante,
                "n": p.n,
                "p_portador_exato": p.p_portador_exato,
                "p_portador_pymc": p.p_portador_mc,
                "p_portador_numpy": n.p_portador_mc,
                "ep_portador": p.ep_portador,
                "desvio_portador_pymc_em_ep": abs(p.p_portador_mc - p.p_portador_exato) / max(p.ep_portador, 1e-9),
                "desvio_portador_numpy_em_ep": abs(n.p_portador_mc - n.p_portador_exato) / max(n.ep_portador, 1e-9),
                "p_manifesta_exato": p.p_manifesta_exato,
                "p_manifesta_pymc": p.p_manifesta_mc,
                "p_manifesta_numpy": n.p_manifesta_mc,
                "ep_manifesta": p.ep_manifesta,
                "desvio_manifesta_pymc_em_ep": abs(p.p_manifesta_mc - p.p_manifesta_exato) / max(p.ep_manifesta, 1e-9),
                "desvio_manifesta_numpy_em_ep": abs(n.p_manifesta_mc - n.p_manifesta_exato) / max(n.ep_manifesta, 1e-9),
                "qui2_genotipo_pymc": fg_p.iloc[j].qui_quadrado,
                "valor_p_genotipo_pymc": fg_p.iloc[j].valor_p,
                "qui2_genotipo_numpy": fg_n.iloc[j].qui_quadrado,
                "valor_p_genotipo_numpy": fg_n.iloc[j].valor_p,
                "idade_mediana_exata": p.idade_mediana_exata,
                "idade_mediana_pymc": p.idade_mediana_mc,
                "idade_mediana_numpy": n.idade_mediana_mc,
            }
        )
    cp, cn = res_pymc.resumo_combinado(), res_numpy.resumo_combinado()
    linhas.append(
        {
            "variante": sobrevivencia.QUALQUER,
            "n": cp["n"],
            "p_portador_exato": cp["p_portador_qualquer_exato"],
            "p_portador_pymc": cp["p_portador_qualquer_mc"],
            "p_portador_numpy": cn["p_portador_qualquer_mc"],
            "p_manifesta_exato": cp["p_manifesta_qualquer_exato"],
            "p_manifesta_pymc": cp["p_manifesta_qualquer_mc"],
            "p_manifesta_numpy": cn["p_manifesta_qualquer_mc"],
            "ep_manifesta": cp["ep_manifesta_qualquer"],
            "desvio_manifesta_pymc_em_ep": abs(cp["p_manifesta_qualquer_mc"] - cp["p_manifesta_qualquer_exato"])
            / max(cp["ep_manifesta_qualquer"], 1e-9),
            "desvio_manifesta_numpy_em_ep": abs(cn["p_manifesta_qualquer_mc"] - cn["p_manifesta_qualquer_exato"])
            / max(cn["ep_manifesta_qualquer"], 1e-9),
            "idade_mediana_pymc": cp["idade_mediana_primeiro_inicio"],
            "idade_mediana_numpy": cn["idade_mediana_primeiro_inicio"],
        }
    )
    return pd.DataFrame(linhas)


def estabilidade(
    loci: list[Locus], ns=(1_000, 10_000, 100_000), repeticoes: int = 30, seed_inicial: int = 1000, motor: str = "numpy"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Tabela 5: execuções sucessivas por N; DP entre execuções vs erro padrão teórico √(p(1−p)/N)."""
    brutos = []
    for n in ns:
        df = repetir(loci, n=n, repeticoes=repeticoes, seed_inicial=seed_inicial, motor=motor)
        brutos.append(df)
    bruto = pd.concat(brutos, ignore_index=True)
    p_exato = combinar_independentes(l.p_manifesta_exato for l in loci)
    linhas = []
    for n, g in bruto.groupby("n"):
        linha = {
            "motor": motor,
            "n": n,
            "repeticoes": len(g),
            "tempo_medio_s": g.tempo_s.mean(),
            "p_manifesta_qualquer_exato": p_exato,
            "p_manifesta_qualquer_media": g.p_manifesta_qualquer.mean(),
            "p_manifesta_qualquer_dp": g.p_manifesta_qualquer.std(ddof=1),
            "ep_teorico": np.sqrt(p_exato * (1 - p_exato) / n),
        }
        linha["razao_dp_ep"] = (
            linha["p_manifesta_qualquer_dp"] / linha["ep_teorico"] if linha["ep_teorico"] > 0 else np.nan
        )
        linha["idade_mediana_media"] = g.idade_mediana_primeiro_inicio.mean()
        linha["idade_mediana_dp"] = g.idade_mediana_primeiro_inicio.std(ddof=1)
        for l in loci:
            col = f"p_portador[{l.rotulo}]"
            linha[f"dp_portador[{l.rotulo}]"] = g[col].std(ddof=1)
            linha[f"ep_teorico_portador[{l.rotulo}]"] = np.sqrt(l.p_portador_exato * (1 - l.p_portador_exato) / n)
        linhas.append(linha)
    return bruto, pd.DataFrame(linhas)


def tempos(
    loci: list[Locus], ns=(1_000, 10_000, 100_000), repeticoes_numpy: int = 5, repeticoes_pymc: int = 3, seed: int = 7
) -> pd.DataFrame:
    """Tabela 8: tempo de processamento por motor e N (média e máximo)."""
    linhas = []
    for n in ns:
        for motor, fn, rep in (("numpy", simular_numpy, repeticoes_numpy), ("pymc", simular_pymc, repeticoes_pymc)):
            ts = []
            for r in range(rep):
                t0 = time.perf_counter()
                fn(loci, n=n, seed=seed + r)
                ts.append(time.perf_counter() - t0)
            linhas.append(
                {
                    "motor": motor,
                    "n": n,
                    "repeticoes": rep,
                    "tempo_medio_s": float(np.mean(ts)),
                    "tempo_max_s": float(np.max(ts)),
                    "sorteios_por_segundo": n / float(np.mean(ts)),
                }
            )
    return pd.DataFrame(linhas)


ROTULO_DISTRIBUICAO = {"beta": "Beta", "lognormal_truncada": "log-normal truncada em 1"}
FAIXA_INCIDENCIA = (
    60.0,
    75.0,
)  # pico de incidência populacional da ELA (FELDMAN et al., 2022): referência, não critério de aprovação


def _idade_pico(curvas: pd.DataFrame, unidade: str) -> float:
    c = curvas[curvas.unidade == unidade]
    return float(c.t.iloc[int(np.argmax(c.h.values))])


def coerencia(res: ResultadoSimulacao, horizonte: float = 90.0) -> pd.DataFrame:
    """Coerência das curvas (TCC 4.5): risco vitalício exato (até o horizonte) vs Kaplan-Meier, fração que manifesta
    em algum momento, F(∞), vs a recuperada pelo modelo de cura mista (P(portador)·π̂), medianas de início (exata,
    Weibull da Lifelines), parâmetros recuperados e idade do pico de h(t), por lócus e para o risco combinado.

    A faixa de incidência populacional 60–75 anos (FELDMAN et al., 2022) é comparada apenas com o pico do risco
    combinado (`pico_combinado_na_faixa_60_75`, preenchida só na linha "qualquer lócus"): o pico de cada variante é
    propriedade da sua própria distribuição de início (SOD1 p.Ala5Val e FUS têm início precoce) e não é aprovado nem
    reprovado por essa faixa."""
    km = sobrevivencia.tabela_km(res, horizonte).set_index("unidade")
    rec = sobrevivencia.recuperacao_parametros(res, horizonte).set_index("variante")
    curvas = sobrevivencia.curvas_analiticas(res, horizonte)
    linhas = []
    for l in res.loci:
        r = rec.loc[l.rotulo]
        linhas.append(
            {
                "variante": l.rotulo,
                "risco_vitalicio_exato": l.p_manifesta_exato,
                "risco_vitalicio_km": km.loc[l.rotulo, "risco_vitalicio_km"],
                "fracao_manifesta_sem_limite": l.p_manifesta_sem_limite,
                "fracao_sem_limite_recuperada": l.p_portador_exato * r.get("pi_lifelines", np.nan),
                "idade_mediana_exata": l.dist.mediana,
                "idade_mediana_weibull_lifelines": r.get("mediana_weibull_manifestantes", np.nan),
                "pi_recuperado": r.get("pi_lifelines", np.nan),
                "lambda_recuperado": r.get("lambda_lifelines", np.nan),
                "rho_recuperado": r.get("rho_lifelines", np.nan),
                "idade_pico_hazard": _idade_pico(curvas, l.rotulo),
                "pico_combinado_na_faixa_60_75": None,
                "idade_90pct_do_risco": km.loc[l.rotulo, "idade_90pct_do_risco"],
                "mediana_sobrevivencia": km.loc[l.rotulo, "mediana_sobrevivencia"],
            }
        )
    comb, q = res.resumo_combinado(), sobrevivencia.QUALQUER
    pico = _idade_pico(curvas, q)
    linhas.append(
        {
            "variante": q,
            "risco_vitalicio_exato": comb["p_manifesta_qualquer_exato"],
            "risco_vitalicio_km": km.loc[q, "risco_vitalicio_km"],
            "fracao_manifesta_sem_limite": comb["p_manifesta_qualquer_sem_limite"],
            "fracao_sem_limite_recuperada": np.nan,
            "idade_mediana_exata": np.nan,
            "idade_mediana_weibull_lifelines": np.nan,
            "pi_recuperado": np.nan,
            "lambda_recuperado": np.nan,
            "rho_recuperado": np.nan,
            "idade_pico_hazard": pico,
            "pico_combinado_na_faixa_60_75": bool(FAIXA_INCIDENCIA[0] <= pico <= FAIXA_INCIDENCIA[1]),
            "idade_90pct_do_risco": km.loc[q, "idade_90pct_do_risco"],
            "mediana_sobrevivencia": km.loc[q, "mediana_sobrevivencia"],
        }
    )
    return pd.DataFrame(linhas)


def sensibilidade(
    vetor: pd.DataFrame, parametros: Parametros, sexo: str | None, n: int = 20_000, seed: int = 77
) -> pd.DataFrame:
    """Tabela 9: risco vitalício e idade mediana sob (a) calibração pela literatura, (b) a distribuição alternativa
    da penetrância (log-normal truncada em 1, ou a Beta quando a log-normal é a escolhida no YAML), (c) parâmetros do
    exemplo do orientador, (d) C9orf72 com penetrância de coorte familiar (0,90)."""
    from .monte_carlo import loci_de_vetor

    cenarios = {"literatura (Douglas & Baralle 2024; Murphy 2017)": {}}
    alternativa = "lognormal_truncada" if parametros.distribuicao_penetrancia == "beta" else "beta"
    cenarios[f"penetrância {ROTULO_DISTRIBUICAO[alternativa]} (alternativa de calibração; Douglas & Baralle 2024)"] = {
        "priors": parametros.priors_penetrancia(alternativa)
    }
    ex = parametros.sensibilidade.get("exemplo_professor", {}).get("genes", {})
    if ex:
        cenarios["exemplo do orientador (penetrance_max e Weibull fixos)"] = {
            "penetrancia_fixa": {g: float(v["penetrancia"]) for g, v in ex.items()},
            "distribuicoes": {
                g: DistribuicaoInicio("weibull", k=float(v["weibull_k"]), lam=float(v["weibull_lam"]))
                for g, v in ex.items()
            },
        }
    fam = parametros.sensibilidade.get("C9orf72_coorte_familiar", {})
    if fam and (vetor.gene == "C9orf72").any():
        cenarios["C9orf72 com penetrância de coorte familiar (Murphy 2017)"] = {
            "penetrancia_fixa": {"C9orf72": float(fam["penetrancia"])}
        }
    linhas = []
    for nome, kw in cenarios.items():
        loci = loci_de_vetor(vetor, parametros, sexo=sexo, **kw)
        res = simular_numpy(loci, n=n, seed=seed)
        r = res.resumo()
        comb = res.resumo_combinado()
        for _, l in r.iterrows():
            linhas.append(
                {
                    "conjunto_de_parametros": nome,
                    "variante": l.variante,
                    "penetrancia_media": l.penetrancia_media,
                    "p_manifesta_exato": l.p_manifesta_exato,
                    "p_manifesta_mc": l.p_manifesta_mc,
                    "idade_mediana_exata": l.idade_mediana_exata,
                    "idade_mediana_mc": l.idade_mediana_mc,
                }
            )
        linhas.append(
            {
                "conjunto_de_parametros": nome,
                "variante": sobrevivencia.QUALQUER,
                "penetrancia_media": np.nan,
                "p_manifesta_exato": comb["p_manifesta_qualquer_exato"],
                "p_manifesta_mc": comb["p_manifesta_qualquer_mc"],
                "idade_mediana_exata": np.nan,
                "idade_mediana_mc": comb["idade_mediana_primeiro_inicio"],
            }
        )
    return pd.DataFrame(linhas)


# ===========================================================================
# Verificação com famílias sintéticas de desfecho conhecido
# ===========================================================================
ENQUADRAMENTO = (
    "Com dados sintéticos gerados pelo próprio modelo, estas métricas medem verificação (a implementação reproduz o "
    "modelo especificado), não validação contra pacientes reais. Para não ficar só circular, cada métrica é calculada "
    "em dois mundos: verdade = modelo, em que o desfecho é sorteado com os mesmos parâmetros da previsão, e verdade "
    "alternativa, em que o desfecho é sorteado com parâmetros diferentes e as métricas mostram como degradam quando o "
    "modelo está errado."
)
IDADES_COORTE = tuple(range(0, 71, 5))  # idades atuais de 0 a 70 anos: a janela de 20 anos cabe no horizonte de 90
JANELAS = (10, 20)
IDADES_BANDA = (50, 60, 70)
SEXOS = ("F", "M")


@dataclass
class Verdade:
    """Parâmetros com que o desfecho verdadeiro é sorteado: penetrância de cada gene (distribuição, sorteada uma vez
    por mundo, ou valor fixo) e distribuição de início (sem o deslocamento do sexo, aplicado depois)."""

    nome: str
    rotulo: str
    descricao: str
    penetrancia: dict
    inicio: dict

    def sortear_pi(self, gene: str, mundos: int, rng: np.random.Generator) -> np.ndarray:
        p = self.penetrancia[gene]
        return np.full(mundos, float(p)) if isinstance(p, (int, float)) else np.asarray(p.amostrar(rng, mundos), float)


def verdades(parametros: Parametros) -> list[Verdade]:
    """Verdade = modelo e as verdades alternativas, só com parâmetros que o YAML já traz: os do exemplo do orientador
    (`sensibilidade.exemplo_professor`) e a distribuição alternativa da penetrância (log-normal truncada com os
    intervalos publicados, ou a Beta quando a log-normal é a escolhida)."""
    genes = parametros.genes
    out = [
        Verdade(
            "modelo",
            "verdade = modelo",
            "desfecho sorteado com os mesmos parâmetros da previsão",
            {g: p.penetrancia for g, p in genes.items()},
            {g: p.inicio for g, p in genes.items()},
        )
    ]
    ex = parametros.sensibilidade.get("exemplo_professor", {}).get("genes", {})
    if ex:
        out.append(
            Verdade(
                "exemplo_orientador",
                "verdade alternativa: parâmetros do exemplo do orientador",
                "penetrância fixa e Weibull de `sensibilidade.exemplo_professor` do YAML",
                {g: (float(ex[g]["penetrancia"]) if g in ex else p.penetrancia) for g, p in genes.items()},
                {
                    g: (
                        DistribuicaoInicio("weibull", k=float(ex[g]["weibull_k"]), lam=float(ex[g]["weibull_lam"]))
                        if g in ex
                        else p.inicio
                    )
                    for g, p in genes.items()
                },
            )
        )
    alt = "lognormal_truncada" if parametros.distribuicao_penetrancia == "beta" else "beta"
    out.append(
        Verdade(
            "penetrancia_alternativa",
            f"verdade alternativa: penetrância {ROTULO_DISTRIBUICAO[alt]}",
            "mesma idade de início; penetrância sorteada da distribuição alternativa, calibrada aos intervalos publicados",
            parametros.priors_penetrancia(alt),
            {g: p.inicio for g, p in genes.items()},
        )
    )
    return out


def loci_da_verdade(
    vetor: pd.DataFrame, parametros: Parametros, verdade: Verdade, sexo: str | None, horizonte: float | None = None
) -> list[Locus]:
    """Lóci do caso com os parâmetros de uma verdade (penetrância e idade de início), para simular o "mundo real"
    alternativo com o mesmo amostrador do artefato."""
    from .monte_carlo import loci_de_vetor

    fixa = {g: float(p) for g, p in verdade.penetrancia.items() if isinstance(p, (int, float))}
    priors = {g: p for g, p in verdade.penetrancia.items() if not isinstance(p, (int, float))}
    return loci_de_vetor(
        vetor,
        parametros,
        sexo=sexo,
        penetrancia_fixa=fixa or None,
        distribuicoes=dict(verdade.inicio),
        horizonte=horizonte,
        priors=priors or None,
    )


@dataclass
class Estrato:
    """Um tipo de pessoa da coorte: cenário familiar, sexo e idade atual, com a previsão do artefato (exata)."""

    cenario: str
    sexo: str
    idade: float
    loci: list
    previsao: dict = field(default_factory=dict)


def previsao_exata(loci: list[Locus], idade: float, horizonte: float, janelas=JANELAS) -> dict:
    """Previsão do artefato para uma pessoa sem sintomas na idade atual, pela mesma conta exata dos indicadores:
    P(portador de ≥ 1 lócus | assintomático), risco nos próximos 10 e 20 anos e até o horizonte, e a mediana
    condicional da idade de início; mais o piso teórico do erro dessa idade (desvio absoluto médio em torno da
    mediana, entre quem manifesta). `por_gene` traz a mediana e o piso da idade de início de cada gene do caso,
    condicionadas à idade atual e a ser aquele gene o primeiro a iniciar (com um só lócus, é a própria G do gene)."""
    comps = [(l.p_manifesta_sem_limite, l.dist) for l in loci]
    fa = f_qualquer(idade, comps)

    def risco(t: float) -> float:
        return float(np.clip((f_qualquer(min(t, horizonte), comps) - fa) / (1.0 - fa), 0.0, 1.0))

    p_cond = [prob_portador_condicional(idade, l.p_portador_exato, l.pen_media, l.dist) for l in loci]
    out = {
        "p_portador": combinar_independentes(p_cond),
        "risco_horizonte": risco(horizonte),
        "mediana_inicio": quantil_inicio_condicional(0.5, idade, horizonte, comps),
        "piso_erro_idade": desvio_absoluto_inicio_condicional(idade, horizonte, comps),
        "por_gene": {l.gene: par for l, par in zip(loci, inicio_por_causa(idade, horizonte, comps))},
    }
    for j in janelas:
        out[f"risco_{j}"] = risco(idade + j)
    return out


def montar_estratos(
    casos: dict[str, pd.DataFrame],
    parametros: Parametros,
    idades=IDADES_COORTE,
    sexos=SEXOS,
    horizonte: float | None = None,
) -> list[Estrato]:
    """Mistura de cenários × sexos × idades atuais. `casos`: {rótulo do cenário: vetor de dosagens}. Sem essa mistura
    não haveria discriminação a medir: dentro de um só cenário todos têm a mesma previsão."""
    from .monte_carlo import loci_de_vetor

    h = float(horizonte if horizonte is not None else parametros.horizonte_anos)
    estratos = []
    for rotulo, vetor in casos.items():
        for sexo in sexos:
            loci = loci_de_vetor(vetor, parametros, sexo=sexo, horizonte=h)
            if not loci:
                continue
            for idade in idades:
                estratos.append(Estrato(rotulo, sexo, float(idade), loci, previsao_exata(loci, float(idade), h)))
    return estratos


def _dist_verdade(verdade: Verdade, parametros: Parametros, gene: str, sexo: str | None) -> DistribuicaoInicio:
    g = parametros.genes[gene]
    return verdade.inicio[gene].deslocar(g.delta_sexo.get(sexo, 0.0) if sexo else 0.0)


def _candidatos(
    estrato: Estrato, verdade: Verdade, parametros: Parametros, pi: dict, m: int, rng: np.random.Generator
) -> tuple:
    """Sorteia m candidatos por mundo para um estrato, com a penetrância do mundo (compartilhada por todos dele).
    Devolve (idade de início verdadeira, com inf para quem nunca manifesta; índice do lócus do início; máscara dos
    compatíveis com a família: genitor inferido sem sintomas até a idade informada)."""
    from .parentes import SEXO_DO_LADO

    mundos = len(next(iter(pi.values())))
    t = np.full((mundos, m), np.inf)
    qual = np.full((mundos, m), -1)
    ok = np.ones((mundos, m), bool)
    for j, l in enumerate(estrato.loci):
        p = pi[l.gene][:, None]
        inf = l.inferencia
        if inf is None:
            dm, dp = np.full((mundos, m), l.dosagem_mae), np.full((mundos, m), l.dosagem_pai)
        else:  # genitor sem exame: dosagem latente pela evidência de genótipo e fenótipo dele com a π do mundo
            estado = rng.choice(9, size=(mundos, m), p=inf.conjunta.ravel())
            dm, dp = estado // 3, estado % 3
            for nome, dose in (("mae", dm), ("pai", dp)):
                lado = inf.ev.lado(nome)
                if not lado.condiciona:
                    continue
                porta = (dose == 2) if l.recessivo else (dose >= 1)
                manifestou = rng.random((mundos, m)) < porta * p
                inicio = _dist_verdade(verdade, parametros, l.gene, SEXO_DO_LADO[nome]).amostrar(rng, (mundos, m))
                ok &= ~(manifestou & (inicio <= lado.idade))
        dose = (rng.random((mundos, m)) < dm / 2).astype(int) + (rng.random((mundos, m)) < dp / 2).astype(int)
        porta = (dose == 2) if l.recessivo else (dose >= 1)
        manifesta = rng.random((mundos, m)) < porta * p
        inicio = _dist_verdade(verdade, parametros, l.gene, estrato.sexo).amostrar(rng, (mundos, m))
        tj = np.where(manifesta, inicio, np.inf)
        antes = tj < t
        t, qual = np.where(antes, tj, t), np.where(antes, j, qual)
    return t, qual, ok


def coorte_de_mundos(
    estratos: list[Estrato],
    parametros: Parametros,
    verdade: Verdade,
    mundos: int = 200,
    por_estrato: int = 10,
    seed: int = 20261116,
    horizonte: float | None = None,
) -> pd.DataFrame:
    """Coorte sintética com desfecho conhecido. Em cada mundo a penetrância de cada gene é sorteada uma vez e vale
    para todos daquele mundo; em cada estrato nascem `por_estrato` pessoas por mundo e entram na coorte as que chegam
    sem sintomas à idade atual (com genitor inferido, as de famílias compatíveis com a evidência). Cada pessoa recebe a
    previsão do artefato e um desfecho verdadeiro: idade de início ou nenhum até o horizonte.

    Manter todas as pessoas que passam, em vez de um número fixo por mundo, faz cada mundo pesar pelo quanto é
    compatível com o que se observa: é a distribuição que a previsão condicionada supõe, e com verdade = modelo a
    calibração vale sem viés. A semente é própria da coorte, independente da semente das previsões."""
    h = float(horizonte if horizonte is not None else parametros.horizonte_anos)
    rng = np.random.default_rng(seed)
    genes = sorted({l.gene for e in estratos for l in e.loci})
    pi = {g: verdade.sortear_pi(g, mundos, rng) for g in genes}
    partes = []
    for k, e in enumerate(estratos):
        t, qual, ok = _candidatos(e, verdade, parametros, pi, por_estrato, rng)
        ok &= t > e.idade  # a pessoa da coorte está sem sintomas na idade atual
        mundo = np.nonzero(ok)[0]
        t, qual = t[ok], qual[ok]
        evento = t <= h
        gene = np.array([l.gene for l in e.loci] + [""], dtype=object)[np.where(evento, qual, -1)]
        por_gene = e.previsao.get("por_gene") or {}
        partes.append(
            pd.DataFrame(
                {
                    "mundo": mundo,
                    "estrato": k,
                    "cenario": e.cenario,
                    "sexo": e.sexo,
                    "idade_atual": e.idade,
                    "evento": evento,
                    "idade_inicio": np.where(evento, t, np.nan),
                    "tempo": np.where(evento, t - e.idade, h - e.idade),
                    "gene_inicio": gene,
                    "mediana_prevista_gene": [(por_gene.get(g) or (np.nan, np.nan))[0] for g in gene],
                    "piso_erro_gene": [(por_gene.get(g) or (np.nan, np.nan))[1] for g in gene],
                    "p_portador": e.previsao["p_portador"],
                    "risco_10": e.previsao["risco_10"],
                    "risco_20": e.previsao["risco_20"],
                    "risco_horizonte": e.previsao["risco_horizonte"],
                    "mediana_prevista": e.previsao["mediana_inicio"],
                    "piso_erro_idade": e.previsao["piso_erro_idade"],
                }
            )
        )
    coorte = pd.concat(partes, ignore_index=True)
    coorte.attrs.update(verdade=verdade.nome, mundos=mundos, por_estrato=por_estrato, seed=seed, horizonte=h)
    return coorte


def descricao_coorte(estratos: list[Estrato], coorte: pd.DataFrame, verdade: Verdade) -> pd.DataFrame:
    """Composição da coorte por cenário: estratos, pessoas sorteadas, pessoas que entram (sem sintomas na idade atual
    e de família compatível com a evidência), eventos e a faixa das previsões."""
    linhas = []
    for cen, c in coorte.groupby("cenario", sort=False):
        linhas.append(
            {
                "verdade": verdade.rotulo,
                "cenario": cen,
                "estratos": int(c.estrato.nunique()),
                "pessoas_sorteadas": int(c.estrato.nunique() * coorte.attrs["mundos"] * coorte.attrs["por_estrato"]),
                "pessoas": int(len(c)),
                "mundos": int(c.mundo.nunique()),
                "eventos_ate_o_horizonte": int(c.evento.sum()),
                "fracao_que_manifesta": float(c.evento.mean()),
                "risco_previsto_min": float(c.risco_horizonte.min()),
                "risco_previsto_max": float(c.risco_horizonte.max()),
            }
        )
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# Calibração: Brier score e curva por decis
# ---------------------------------------------------------------------------
def _alvos(coorte: pd.DataFrame) -> dict[str, tuple[str, np.ndarray]]:
    """{rótulo: (coluna da previsão, desfecho 0/1)} a 10 e 20 anos a partir da idade atual e até o horizonte."""
    ev, tempo = coorte.evento.to_numpy(), coorte.tempo.to_numpy()
    return {
        "10 anos": ("risco_10", ev & (tempo <= 10)),
        "20 anos": ("risco_20", ev & (tempo <= 20)),
        "até o horizonte": ("risco_horizonte", ev),
    }


def brier(coorte: pd.DataFrame) -> pd.DataFrame:
    """Brier score da previsão a 10 e 20 anos e até o horizonte. `brier_referencia` é o de quem prevê a prevalência
    para todos, p̄(1 − p̄); `habilidade` = 1 − Brier/referência (0 = não melhora a prevalência; 1 = perfeito)."""
    linhas = []
    for rotulo, (col, y) in _alvos(coorte).items():
        p = coorte[col].to_numpy()
        b, prev = float(np.mean((p - y) ** 2)), float(y.mean())
        ref = prev * (1 - prev)
        linhas.append(
            {
                "previsao": rotulo,
                "n": int(len(y)),
                "prevalencia_observada": prev,
                "risco_previsto_medio": float(p.mean()),
                "brier": b,
                "brier_referencia": ref,
                "habilidade": 1 - b / ref if ref > 0 else np.nan,
            }
        )
    return pd.DataFrame(linhas)


def curva_calibracao(coorte: pd.DataFrame, grupos: int = 10) -> pd.DataFrame:
    """Curva de calibração: pessoas ordenadas pelo risco previsto e cortadas em decis; risco previsto médio contra a
    fração observada em cada decil, para 10 anos, 20 anos e até o horizonte."""
    linhas = []
    for rotulo, (col, y) in _alvos(coorte).items():
        p = coorte[col].to_numpy()
        ordem = np.argsort(p, kind="stable")
        for k, idx in enumerate(np.array_split(ordem, grupos), 1):
            if len(idx) == 0:
                continue
            obs = float(y[idx].mean())
            linhas.append(
                {
                    "previsao": rotulo,
                    "decil": k,
                    "n": int(len(idx)),
                    "risco_previsto": float(p[idx].mean()),
                    "fracao_observada": obs,
                    "ep_observado": float(np.sqrt(obs * (1 - obs) / len(idx))),
                    "diferenca": obs - float(p[idx].mean()),
                }
            )
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# Discriminação: C-index de Harrell e AUC dependente do tempo
# ---------------------------------------------------------------------------
def c_index_harrell(tempo, evento, escore) -> float:
    """C-index de Harrell: entre os pares comparáveis (o de menor tempo teve o evento), fração em que quem teve o
    evento antes tinha o maior risco previsto; empate de risco vale meio. NaN sem par comparável."""
    t, e, s = np.asarray(tempo, float), np.asarray(evento, bool), np.asarray(escore, float)
    comparavel = (t[:, None] < t[None, :]) & e[:, None]
    n = int(comparavel.sum())
    if n == 0:
        return float("nan")
    concordante = int((comparavel & (s[:, None] > s[None, :])).sum())
    empate = int((comparavel & (s[:, None] == s[None, :])).sum())
    return (concordante + 0.5 * empate) / n


def auc_mann_whitney(escore_casos, escore_controles) -> float:
    """AUC pela estatística de Mann-Whitney: P(escore do caso > escore do controle) + ½·P(empate)."""
    a, b = np.asarray(escore_casos, float), np.asarray(escore_controles, float)
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    postos = stats.rankdata(np.concatenate([a, b]))
    return float((postos[: len(a)].sum() - len(a) * (len(a) + 1) / 2) / (len(a) * len(b)))


def discriminacao(coorte: pd.DataFrame) -> pd.DataFrame:
    """C-index de Harrell (risco residual previsto contra o tempo até o início verdadeiro, com censura no horizonte)
    e AUC dependente do tempo a 10 e 20 anos (casos: início em (a, a + t]; controles: sem início até a + t).

    O tempo é contado a partir da idade atual de cada pessoa (idade de início verdadeira − idade atual), porque a
    previsão é "daqui em diante". A verdade sintética não tem censura além do horizonte e as idades atuais vão só até
    70 anos, de modo que o estado aos 10 e 20 anos é conhecido para todos: não é preciso ponderar pela censura.
    O C-index compara pares do mesmo mundo (mesma penetrância) e é resumido pela média e pelo desvio entre mundos."""
    por_mundo = [c_index_harrell(c.tempo, c.evento, c.risco_horizonte) for _, c in coorte.groupby("mundo", sort=False)]
    por_mundo = np.array([x for x in por_mundo if np.isfinite(x)])
    linhas = [
        {
            "metrica": "C-index de Harrell (risco residual até o horizonte)",
            "valor": float(por_mundo.mean()) if por_mundo.size else np.nan,
            "dp_entre_mundos": float(por_mundo.std(ddof=1)) if por_mundo.size > 1 else np.nan,
            "mundos": int(por_mundo.size),
            "casos": int(coorte.evento.sum()),
            "controles": int((~coorte.evento).sum()),
        }
    ]
    ev, tempo = coorte.evento.to_numpy(), coorte.tempo.to_numpy()
    for j in JANELAS:
        caso = ev & (tempo <= j)
        aucs = []
        for _, c in coorte.groupby("mundo", sort=False):
            cc = c.evento.to_numpy() & (c.tempo.to_numpy() <= j)
            a = auc_mann_whitney(c[f"risco_{j}"].to_numpy()[cc], c[f"risco_{j}"].to_numpy()[~cc])
            if np.isfinite(a):
                aucs.append(a)
        linhas.append(
            {
                "metrica": f"AUC dependente do tempo, {j} anos (Mann-Whitney)",
                "valor": auc_mann_whitney(
                    coorte[f"risco_{j}"].to_numpy()[caso], coorte[f"risco_{j}"].to_numpy()[~caso]
                ),
                "dp_entre_mundos": float(np.std(aucs, ddof=1)) if len(aucs) > 1 else np.nan,
                "mundos": len(aucs),
                "casos": int(caso.sum()),
                "controles": int((~caso).sum()),
            }
        )
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# Erro da idade de início, por gene, com o piso teórico
# ---------------------------------------------------------------------------
def erro_idade_inicio(coorte: pd.DataFrame) -> pd.DataFrame:
    """Entre quem manifesta: erro absoluto médio entre a idade prevista e a idade de início verdadeira.

    Por gene do início, a idade prevista é a mediana da distribuição de início daquele gene, condicionada à idade
    atual; na linha "combinado" é a mediana condicional do indicador (primeiro início entre os lóci do caso). O piso
    teórico é o desvio absoluto médio da própria distribuição em torno da sua mediana, condicionado à idade atual: um
    modelo perfeito não fica abaixo dele, porque a idade de início é aleatória; sem o piso o erro não é interpretável.
    Nos casos com dois lóci, a distribuição de cada gene é a do início daquele gene quando ele é o primeiro."""
    m = coorte[coorte.evento]
    linhas = []

    def linha(rotulo: str, c: pd.DataFrame, prevista: str, piso: str) -> None:
        c = c[c[prevista].notna()]
        if c.empty:
            return
        desvio = c.idade_inicio - c[prevista]
        linhas.append(
            {
                "gene": rotulo,
                "n_manifestam": int(len(c)),
                "erro_absoluto_medio_anos": float(desvio.abs().mean()),
                "erro_padrao_anos": float(desvio.abs().std(ddof=1) / np.sqrt(len(c))) if len(c) > 1 else np.nan,
                "piso_teorico_anos": float(c[piso].mean()),
                "razao_erro_piso": float(desvio.abs().mean() / c[piso].mean()),
                "vies_medio_anos": float(desvio.mean()),
            }
        )

    for gene, c in m.groupby("gene_inicio", sort=True):
        linha(gene, c, "mediana_prevista_gene", "piso_erro_gene")
    linha("combinado (mediana do indicador)", m, "mediana_prevista", "piso_erro_idade")
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# Cobertura dos intervalos
# ---------------------------------------------------------------------------
def cobertura_monte_carlo(
    casos: dict[str, list[Locus]], n: int = 10_000, repeticoes: int = 200, seed: int = 5000
) -> pd.DataFrame:
    """Em `repeticoes` sementes, fração em que o intervalo de 95 % do Monte Carlo (estimativa ± 1,96 EP) de
    P(portador) e de P(manifesta até o horizonte) contém o valor exato. Esperado: cerca de 95 %."""
    linhas = []
    for rotulo, loci in casos.items():
        dentro_p, dentro_m = np.zeros(len(loci) + 1), np.zeros(len(loci) + 1)
        exato_comb = combinar_independentes(l.p_manifesta_exato for l in loci)
        exato_port = combinar_independentes(l.p_portador_exato for l in loci)
        for r in range(repeticoes):
            res = simular_numpy(loci, n=n, seed=seed + r)
            man = res.manifesta_h
            for j, l in enumerate(loci):
                pc, pm = res.portador[:, j].mean(), man[:, j].mean()
                dentro_p[j] += abs(pc - l.p_portador_exato) <= 1.96 * np.sqrt(pc * (1 - pc) / n)
                dentro_m[j] += abs(pm - l.p_manifesta_exato) <= 1.96 * np.sqrt(pm * (1 - pm) / n)
            pc, pm = res.portador.any(axis=1).mean(), man.any(axis=1).mean()
            dentro_p[-1] += abs(pc - exato_port) <= 1.96 * np.sqrt(pc * (1 - pc) / n)
            dentro_m[-1] += abs(pm - exato_comb) <= 1.96 * np.sqrt(pm * (1 - pm) / n)
        for j, unidade in enumerate([l.rotulo for l in loci] + [sobrevivencia.QUALQUER]):
            if unidade == sobrevivencia.QUALQUER and len(loci) == 1:
                continue
            linhas.append(
                {
                    "cenario": rotulo,
                    "unidade": unidade,
                    "n": n,
                    "sementes": repeticoes,
                    "cobertura_p_portador": dentro_p[j] / repeticoes,
                    "cobertura_p_manifesta": dentro_m[j] / repeticoes,
                    "esperado": 0.95,
                }
            )
    return pd.DataFrame(linhas)


def _f_exata_dos_mundos(loci: list[Locus], verdade: Verdade, parametros: Parametros, pi: dict, sexo, idades) -> tuple:
    """F(t) exata de cada mundo (mundos × idades) para o primeiro início entre os lóci, com a penetrância do mundo, e o
    peso do mundo: a probabilidade de a família ser compatível com a evidência do genitor inferido (1 sem inferência).
    É o limite do F empírico de `_candidatos` quando o número de pessoas do mundo cresce."""
    from .parentes import SEXO_DO_LADO

    mundos = len(next(iter(pi.values())))
    doses = np.arange(3)
    sobrevive, peso = np.ones((mundos, len(idades))), np.ones(mundos)
    for l in loci:
        p = pi[l.gene]
        g = np.array([float(_dist_verdade(verdade, parametros, l.gene, sexo).cdf(t)) for t in idades])
        inf = l.inferencia
        if inf is None:
            q = np.full(mundos, l.p_portador_exato)
        else:  # dosagens do genitor sem exame pesadas pelo fenótipo dele, com a π do mundo
            porta = (doses == 2) if l.recessivo else (doses >= 1)
            post = np.repeat(np.asarray(inf.conjunta, float)[None, :, :], mundos, axis=0)
            for eixo, nome in enumerate(("mae", "pai")):
                lado = inf.ev.lado(nome)
                if not lado.condiciona:
                    continue
                g_lado = float(_dist_verdade(verdade, parametros, l.gene, SEXO_DO_LADO[nome]).cdf(lado.idade))
                fator = 1.0 - porta[None, :] * p[:, None] * g_lado
                post = post * (fator[:, :, None] if eixo == 0 else fator[:, None, :])
            z = post.sum(axis=(1, 2))
            a = doses / 2.0
            filho = a[:, None] * a[None, :] if l.recessivo else 1.0 - (1.0 - a[:, None]) * (1.0 - a[None, :])
            q = (post * filho[None, :, :]).sum(axis=(1, 2)) / z
            peso = peso * z
        sobrevive = sobrevive * (1.0 - (q * p)[:, None] * g[None, :])
    return 1.0 - sobrevive, peso


def cobertura_bandas(
    casos: dict[str, list[Locus]],
    parametros: Parametros,
    verdade: Verdade,
    sexo: str | None = "F",
    mundos: int = 200,
    por_mundo: int = 10_000,
    n_banda: int = 10_000,
    seed_banda: int = 42,
    seed_mundos: int = 20261117,
    idades=IDADES_BANDA,
) -> pd.DataFrame:
    """Fração dos mundos em que o F(t) empírico do mundo (coorte de nascimento com `por_mundo` pessoas e a penetrância
    daquele mundo) cai dentro da banda de 95 % do artefato, aos 50, 60 e 70 anos, para o risco combinado de cada
    cenário. Com verdade = modelo fica perto de 95 % por construção (um pouco abaixo, pelo ruído amostral do F
    empírico); com a verdade alternativa mostra a subcobertura. Com genitor inferido, o F do mundo é o das famílias
    compatíveis com a evidência e cada mundo pesa pelo número delas, como na coorte.

    `cobertura_sem_ruido_amostral` repete a conta com a F exata de cada mundo (o limite do F empírico com infinitas
    pessoas): separa o que é ruído do F empírico do que é erro da banda. O ruído pesa mais onde a banda é estreita."""
    rng = np.random.default_rng(seed_mundos)
    genes = sorted({l.gene for loci in casos.values() for l in loci})
    pi = {g: verdade.sortear_pi(g, mundos, rng) for g in genes}
    linhas = []
    for rotulo, loci in casos.items():
        res = simular_numpy(loci, n=n_banda, seed=seed_banda)
        t, _, ok = _candidatos(Estrato(rotulo, sexo, 0.0, loci), verdade, parametros, pi, por_mundo, rng)
        validos = ok.sum(axis=1)
        f_exata, peso = _f_exata_dos_mundos(loci, verdade, parametros, pi, sexo, idades)
        for i, idade in enumerate(idades):
            f_sorteio = 1 - np.prod(1 - res.risco_por_sorteio(idade), axis=1)
            lo, hi = np.percentile(f_sorteio, [2.5, 97.5])
            f_mundo = ((t <= idade) & ok).sum(axis=1) / np.clip(validos, 1, None)
            linhas.append(
                {
                    "verdade": verdade.rotulo,
                    "cenario": rotulo,
                    "idade": idade,
                    "F_modelo": f_qualquer(idade, [(l.p_manifesta_sem_limite, l.dist) for l in loci]),
                    "banda_q025": float(lo),
                    "banda_q975": float(hi),
                    "F_mundos_media": float(np.average(f_mundo, weights=validos)),
                    "cobertura_da_banda": float(np.average((f_mundo >= lo) & (f_mundo <= hi), weights=validos)),
                    "cobertura_sem_ruido_amostral": float(
                        np.average((f_exata[:, i] >= lo) & (f_exata[:, i] <= hi), weights=peso)
                    ),
                    "mundos": mundos,
                    "pessoas_por_mundo": por_mundo,
                    "esperado_com_verdade_igual_ao_modelo": 0.95,
                }
            )
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# Divergência entre curvas: Kolmogorov-Smirnov e Wasserstein
# ---------------------------------------------------------------------------
def _ks(amostra: np.ndarray, n_total: int, comps, horizonte: float) -> float:
    """sup |F_empírico − F_teórico| em [0, horizonte]; F_empírico = fração de `n_total` com início até t."""
    x = np.sort(amostra[amostra <= horizonte])
    fim = f_qualquer(horizonte, comps)
    if x.size == 0:
        return float(abs(fim))
    ft = f_qualquer_grade(x, comps)
    acima, abaixo = np.arange(1, x.size + 1) / n_total, np.arange(0, x.size) / n_total
    return float(max(np.max(np.abs(acima - ft)), np.max(np.abs(abaixo - ft)), abs(x.size / n_total - fim)))


def divergencia_curvas(
    res: ResultadoSimulacao, loci_teoricos: list[Locus] | None = None, horizonte: float = 90.0, origem: str = ""
) -> pd.DataFrame:
    """Por lócus e combinado: distância de Kolmogorov-Smirnov entre o F(t) empírico dos sorteios e o F(t) teórico em
    [0, horizonte], e distância de Wasserstein (em anos) entre a distribuição empírica da idade de início dos que
    manifestam e a G(t) teórica truncada no horizonte (`scipy.stats.wasserstein_distance`). `loci_teoricos` troca a
    curva teórica (padrão: os lóci do próprio resultado), para confrontar uma verdade alternativa com o modelo."""
    teoricos = loci_teoricos or res.loci
    u = (np.arange(4000) + 0.5) / 4000
    grade = np.linspace(0.0, horizonte, 3601)
    linhas = []
    unidades = [(l.rotulo, [(l.p_manifesta_sem_limite, l.dist)], j) for j, l in enumerate(teoricos)]
    if len(teoricos) > 1:
        unidades.append((sobrevivencia.QUALQUER, [(l.p_manifesta_sem_limite, l.dist) for l in teoricos], None))
    for rotulo, comps, j in unidades:
        idades = res.idade[res.manifesta[:, j], j] if j is not None else res.idade_qualquer[res.manifesta_qualquer]
        idades = idades[idades <= horizonte]
        ks = _ks(idades, res.n, comps, horizonte)
        f = f_qualquer_grade(grade, comps)
        w = np.nan
        if f[-1] > 0 and idades.size:
            teorica = np.interp(u * f[-1], f, grade)  # quantis da idade de início entre quem manifesta até o horizonte
            w = float(stats.wasserstein_distance(idades, teorica))
        linhas.append(
            {
                "origem": origem,
                "unidade": rotulo,
                "n_sorteios": res.n,
                "n_manifestam": int(idades.size),
                "ks_F": ks,
                "ks_referencia_amostral": 1.36 / math.sqrt(res.n),
                "wasserstein_idade_inicio_anos": w,
            }
        )
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# Robustez a erros no VCF
# ---------------------------------------------------------------------------
PERTURBACOES = {
    "registro_removido": ("falso negativo", "registro da variante de risco removido do VCF do genitor portador"),
    "gt_01_para_00": ("falso negativo", "genótipo 0/1 trocado por 0/0 no genitor portador"),
    "gq_abaixo_de_30": ("falso negativo", "GQ abaixo de 30 no registro da variante de risco (registro filtrado)"),
    "variante_inserida": ("falso positivo", "registro de uma variante patogênica da base inserido num genitor"),
    "gt_00_para_01": ("falso positivo", "genótipo 0/0 trocado por 0/1 no genitor que não porta a variante"),
    "genotipo_indeterminado": ("indeterminado", "genótipo ./. no registro da variante de risco do genitor portador"),
}


def _linha_da_variante(linhas: list[str], v) -> int | None:
    for i, l in enumerate(linhas):
        c = l.split("\t")
        if not l.startswith("#") and len(c) > 9 and c[0] == f"chr{v.cromossomo}" and c[1] == str(v.posicao):
            return i
    return None


def _trocar_amostra(linha: str, gt: str | None = None, gq: int | None = None) -> str:
    c = linha.rstrip("\n").split("\t")
    formato, dados = c[8].split(":"), c[9].split(":")
    if gt is not None:
        dados[formato.index("GT")] = gt
    if gq is not None and "GQ" in formato:
        dados[formato.index("GQ")] = str(gq)
    c[9] = ":".join(dados)
    return "\t".join(c)


def _perturbar(texto: str, tipo: str, variante) -> str | None:
    """Aplica a perturbação ao texto de um VCF sintético; None quando ela não se aplica (variante ausente)."""
    linhas = texto.rstrip("\n").split("\n")
    if tipo == "variante_inserida":
        linhas.append(
            f"chr{variante.cromossomo}\t{variante.posicao}\t{variante.rs or '.'}\t{variante.ref}\t{variante.alt}\t99.0\t"
            "PASS\tAC=1;AN=2;DB;SINTETICO\tGT:DP:GQ\t0/1:40:90"
        )
        return "\n".join(linhas) + "\n"
    i = _linha_da_variante(linhas, variante)
    if i is None:
        return None
    if tipo == "registro_removido":
        del linhas[i]
    elif tipo == "gt_01_para_00":
        linhas[i] = _trocar_amostra(linhas[i], gt="0/0")
    elif tipo == "gq_abaixo_de_30":
        linhas[i] = _trocar_amostra(linhas[i], gq=10)
    elif tipo == "gt_00_para_01":
        linhas[i] = _trocar_amostra(linhas[i], gt="0/1")
    elif tipo == "genotipo_indeterminado":
        linhas[i] = _trocar_amostra(linhas[i], gt="./.")
    return "\n".join(linhas) + "\n"


def robustez_vcf(
    dir_cenarios,
    numeros,
    parametros: Parametros,
    tabela: pd.DataFrame,
    dir_tmp,
    sexo: str | None = "F",
) -> pd.DataFrame:
    """Para cada cenário, perturbações controladas num VCF parental e a variação de P(portador de ≥ 1 lócus) e do risco
    vitalício (valores exatos), com o que o artefato reporta em cada caso: falso negativo (registro removido, 0/1 → 0/0,
    GQ abaixo de 30), falso positivo (variante patogênica inserida, 0/0 → 0/1) e genótipo indeterminado (./.), que deve
    descartar o lócus em vez de valer dosagem 0."""
    import warnings

    from . import anotacao, cenarios, genotipo, ingestao
    from .monte_carlo import loci_de_vetor

    dir_cenarios, dir_tmp = Path(dir_cenarios), Path(dir_tmp)
    dir_tmp.mkdir(parents=True, exist_ok=True)
    regioes = ingestao.carregar_regioes()
    todas = [cenarios.SOD1_A5V, cenarios.TARDBP_M337V, cenarios.FUS_R521C, cenarios.SOD1_D91A]

    def avaliar(caminho_mae, caminho_pai, c) -> dict:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            lidos = {
                lado: ingestao.ler_vcf(caminho, regioes, parametros.filtro_qualidade)
                for lado, caminho in (("mae", caminho_mae), ("pai", caminho_pai))
            }
            anot = {lado: anotacao.anotar(df, tabela, parametros.limiar_repeticoes) for lado, df in lidos.items()}
            vetor = genotipo.vetor_dosagem(
                anot["mae"], anot["pai"], parametros, laudo_c9orf72=c.laudo_c9orf72, tabela=tabela
            )
            loci = loci_de_vetor(vetor, parametros, sexo=sexo)
        reprovados = {}
        for df in lidos.values():
            for motivo, k in ingestao.resumo_ingestao(df)["por_motivo"].items():
                reprovados[motivo] = reprovados.get(motivo, 0) + int(k)
        return {
            "p_portador": combinar_independentes(l.p_portador_exato for l in loci),
            "risco": combinar_independentes(l.p_manifesta_exato for l in loci),
            "loci": [l.rotulo for l in loci],
            "descartados": [f"{r.gene} {r.variante}" for r in vetor[vetor.descartado].itertuples()],
            "reprovados": reprovados,
        }

    linhas = []
    for num in numeros:
        c = cenarios.cenario_por_numero(num)
        originais = {lado: (dir_cenarios / f"cenario_{num}_{lado}.vcf") for lado in ("mae", "pai")}
        base = avaliar(originais["mae"], originais["pai"], c)
        portadoras = [(lado, v) for lado in ("mae", "pai") for v in getattr(c, lado) if v.dosagem > 0]
        presentes = {(v.cromossomo, v.posicao) for lado in ("mae", "pai") for v in getattr(c, lado)}
        nova = next(v for v in todas if (v.cromossomo, v.posicao) not in presentes)
        for tipo, (classe, descricao) in PERTURBACOES.items():
            if tipo == "variante_inserida":
                alvo_lado, alvo = "mae", nova
            elif not portadoras:
                alvo_lado, alvo = None, None
            elif tipo == "gt_00_para_01":  # o registro 0/0 da variante de risco só existe no genitor que não a porta
                outro = {"mae": "pai", "pai": "mae"}
                zeradas = [
                    (outro[lado], v)
                    for lado, v in portadoras
                    if not any(
                        (o.cromossomo, o.posicao) == (v.cromossomo, v.posicao) and o.dosagem > 0
                        for o in getattr(c, outro[lado])
                    )
                ]
                alvo_lado, alvo = zeradas[0] if zeradas else (None, None)
            else:
                alvo_lado, alvo = portadoras[0]
            linha = {
                "cenario": f"cenário {num}",
                "perturbacao": tipo,
                "classe": classe,
                "descricao": descricao,
                "genitor": alvo_lado or "",
                "variante": alvo.rotulo if alvo is not None else "",
                "p_portador_original": base["p_portador"],
                "risco_original": base["risco"],
            }
            texto = _perturbar(originais[alvo_lado].read_text(encoding="utf-8"), tipo, alvo) if alvo_lado else None
            if texto is None:
                linha.update(
                    p_portador_perturbado=np.nan,
                    risco_perturbado=np.nan,
                    variacao_p_portador=np.nan,
                    variacao_risco=np.nan,
                    o_que_o_artefato_reporta=(
                        "não se aplica: os dois genitores portam a variante de risco, não há registro 0/0 para trocar"
                        if portadoras
                        else "não se aplica: o cenário não tem variante de risco nos VCFs (a expansão do C9orf72 vem "
                        "do laudo)"
                    ),
                )
                linhas.append(linha)
                continue
            alterado = dir_tmp / f"cenario_{num}_{alvo_lado}_{tipo}.vcf"
            alterado.write_text(texto, encoding="utf-8", newline="\n")
            caminhos = dict(originais)
            caminhos[alvo_lado] = alterado
            novo = avaliar(caminhos["mae"], caminhos["pai"], c)
            alterado.unlink(missing_ok=True)
            perdidos = [x for x in base["loci"] if x not in novo["loci"]]
            ganhos = [x for x in novo["loci"] if x not in base["loci"]]
            if novo["descartados"]:
                relato = (
                    "lócus descartado e declarado no relatório (genótipo não determinado; nunca dosagem 0): "
                    + "; ".join(novo["descartados"])
                )
            elif novo["reprovados"].get("gq_baixo", 0) > base["reprovados"].get("gq_baixo", 0):
                relato = (
                    "registro reprovado no filtro de qualidade (GQ) e contado nas reprovações; o lócus some do cálculo"
                )
            elif perdidos:
                relato = "nenhum aviso: o lócus some do cálculo (falso negativo silencioso): " + "; ".join(perdidos)
            elif ganhos:
                relato = "novo lócus de risco entra no cálculo, sem aviso: " + "; ".join(ganhos)
            elif novo["p_portador"] != base["p_portador"]:
                relato = "a dosagem do genitor muda e o risco é recalculado, sem aviso"
            else:
                relato = "sem efeito no resultado"
            linha.update(
                p_portador_perturbado=novo["p_portador"],
                risco_perturbado=novo["risco"],
                variacao_p_portador=novo["p_portador"] - base["p_portador"],
                variacao_risco=novo["risco"] - base["risco"],
                o_que_o_artefato_reporta=relato,
            )
            linhas.append(linha)
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# Sensibilidade tipo tornado: um parâmetro por vez, toda faixa tirada de fonte
# ---------------------------------------------------------------------------
Z95 = 1.959963984540054


def faixas_tornado(parametros: Parametros, genes: list[str], sexo: str | None = None) -> tuple[list[dict], list[str]]:
    """Faixas de um parâmetro por vez (cada uma com `baixo` e `alto` como argumentos de `loci_de_vetor`) e os genes
    que ficam fora por não terem incerteza publicada. Fontes: IC 95 % da penetrância de cada gene (YAML, bloco
    `genes`) e o bloco `sensibilidade.tornado` do YAML para a idade de início. Nenhuma faixa é inventada."""
    cfg = parametros.sensibilidade.get("tornado") or {}
    faixas, fora = [], []
    for gene in genes:
        g = parametros.genes[gene]
        faixas.append(
            {
                "parametro": f"penetrância do {gene}",
                "gene": gene,
                "base": f"média {g.pen_media:.3f}",
                "baixo": (f"{g.pen_ic95[0]:.3f}", {"penetrancia_fixa": {gene: g.pen_ic95[0]}}),
                "alto": (f"{g.pen_ic95[1]:.3f}", {"penetrancia_fixa": {gene: g.pen_ic95[1]}}),
                "fonte": f"limites do IC 95 %: {g.pen_citacao}",
                "confirmar": g.pen_confirmar,
            }
        )
        ini = (cfg.get(gene) or {}).get("inicio") or {}
        tipo, est = ini.get("tipo"), g.inicio_estatisticas
        z = float(ini.get("z", Z95))
        if tipo == "media" and {"media", "dp"} <= set(est):
            d = z * est["dp"] / math.sqrt(float(ini["n"]))
            lo, hi = (calibracao.weibull_de_momentos(est["media"] + s * d, est["dp"]) for s in (-1, 1))
            faixas.append(
                {
                    "parametro": f"idade de início do {gene} (média)",
                    "gene": gene,
                    "base": f"média {est['media']:g}",
                    "baixo": (f"{est['media'] - d:.2f}", {"distribuicoes": {gene: _weibull(lo)}}),
                    "alto": (f"{est['media'] + d:.2f}", {"distribuicoes": {gene: _weibull(hi)}}),
                    "fonte": ini.get("citacao", ""),
                    "confirmar": bool(ini.get("confirmar", True)),
                }
            )
        elif tipo == "mediana" and {"mediana", "iqr"} <= set(est):
            ep = 1.2533 * (est["iqr"] / 1.349) / math.sqrt(float(ini["n"]))
            lo, hi = (calibracao.weibull_de_quantis(est["mediana"] + s * z * ep, est["iqr"]) for s in (-1, 1))
            faixas.append(
                {
                    "parametro": f"idade de início do {gene} (mediana)",
                    "gene": gene,
                    "base": f"mediana {est['mediana']:g}",
                    "baixo": (f"{est['mediana'] - z * ep:.2f}", {"distribuicoes": {gene: _weibull(lo)}}),
                    "alto": (f"{est['mediana'] + z * ep:.2f}", {"distribuicoes": {gene: _weibull(hi)}}),
                    "fonte": ini.get("citacao", ""),
                    "confirmar": bool(ini.get("confirmar", True)),
                }
            )
        elif tipo == "medianas_publicadas" and ini.get("valores"):
            valores = sorted(ini["valores"], key=lambda x: float(x["mediana"]))
            lo, hi = valores[0], valores[-1]
            atual = g.inicio.mediana
            faixas.append(
                {
                    "parametro": f"idade de início do {gene} (mediana publicada)",
                    "gene": gene,
                    "base": f"mediana ajustada {atual:.1f}",
                    "baixo": (
                        f"{float(lo['mediana']):g} ({lo['fonte']})",
                        {"distribuicoes": {gene: g.inicio.deslocar(float(lo["mediana"]) - atual)}},
                    ),
                    "alto": (
                        f"{float(hi['mediana']):g} ({hi['fonte']})",
                        {"distribuicoes": {gene: g.inicio.deslocar(float(hi["mediana"]) - atual)}},
                    ),
                    "fonte": ini.get("citacao", ""),
                    "confirmar": bool(ini.get("confirmar", True)),
                }
            )
        else:
            fora.append(f"{gene}: {ini.get('motivo', 'sem incerteza publicada para a idade de início')}")
        ds = (cfg.get(gene) or {}).get("delta_sexo")
        atual = g.delta_sexo.get(sexo, 0.0) if sexo else 0.0
        if ds is not None and sexo and atual != float(ds.get("alternativa", 0.0)):
            alt = float(ds.get("alternativa", 0.0))
            sem, com = g.inicio.deslocar(alt - atual), g.inicio
            menor, maior = sorted([(alt, sem), (atual, com)], key=lambda x: x[0])
            faixas.append(
                {
                    "parametro": f"deslocamento por sexo no {gene}",
                    "gene": gene,
                    "base": f"{atual:+g} ano(s) (sexo {sexo})",
                    "baixo": (f"{menor[0]:+g} ano(s)", {"distribuicoes": {gene: menor[1]}}),
                    "alto": (f"{maior[0]:+g} ano(s)", {"distribuicoes": {gene: maior[1]}}),
                    "fonte": ds.get("citacao", g.delta_citacao),
                    "confirmar": g.delta_confirmar,
                }
            )
    alt = "lognormal_truncada" if parametros.distribuicao_penetrancia == "beta" else "beta"
    faixas.append(
        {
            "parametro": f"distribuição da penetrância ({ROTULO_DISTRIBUICAO[alt]} no lugar da em uso)",
            "gene": "todos",
            "base": ROTULO_DISTRIBUICAO[parametros.distribuicao_penetrancia],
            "baixo": (ROTULO_DISTRIBUICAO[parametros.distribuicao_penetrancia], {}),
            "alto": (ROTULO_DISTRIBUICAO[alt], {"priors": parametros.priors_penetrancia(alt)}),
            "fonte": "mesmos ponto e IC 95 % publicados, calibrados na distribuição alternativa",
            "confirmar": False,
        }
    )
    return faixas, fora


def _weibull(ajuste: dict) -> DistribuicaoInicio:
    return DistribuicaoInicio("weibull", k=ajuste["k"], lam=ajuste["lam"])


def tornado(
    vetor: pd.DataFrame,
    parametros: Parametros,
    sexo: str | None = None,
    horizonte: float | None = None,
    idade_atual: float | None = None,
) -> pd.DataFrame:
    """Sensibilidade tipo tornado para um caso (vetor de dosagens): um parâmetro por vez, com a variação do risco
    vitalício combinado (residual, se a idade atual for informada) e da idade mediana de início (valores exatos).
    Ordenado pelo efeito no risco. Os genes sem incerteza publicada ficam em `attrs["fora_do_tornado"]`."""
    from .monte_carlo import loci_de_vetor

    h = float(horizonte if horizonte is not None else parametros.horizonte_anos)
    a = float(idade_atual) if idade_atual else 0.0
    genes = [g for g in dict.fromkeys(vetor.loc[~vetor.descartado.astype(bool), "gene"]) if g in parametros.genes]

    def medir(**kw) -> tuple[float, float | None]:
        loci = loci_de_vetor(vetor, parametros, sexo=sexo, horizonte=h, **kw)
        prev = previsao_exata(loci, a, h)
        return prev["risco_horizonte"], prev["mediana_inicio"]

    base_r, base_m = medir()
    faixas, fora = faixas_tornado(parametros, genes, sexo)
    linhas = []
    for f in faixas:
        (r_lo, m_lo), (r_hi, m_hi) = medir(**f["baixo"][1]), medir(**f["alto"][1])
        linhas.append(
            {
                "parametro": f["parametro"],
                "gene": f["gene"],
                "valor_base": f["base"],
                "valor_baixo": f["baixo"][0],
                "valor_alto": f["alto"][0],
                "risco_base": base_r,
                "risco_baixo": r_lo,
                "risco_alto": r_hi,
                "variacao_risco": abs(r_hi - r_lo),
                "mediana_base": base_m,
                "mediana_baixa": m_lo,
                "mediana_alta": m_hi,
                "variacao_mediana_anos": abs((m_hi or np.nan) - (m_lo or np.nan)),
                "fonte": f["fonte"],
                "provisorio": "sim" if f["confirmar"] else "não",
            }
        )
    df = pd.DataFrame(linhas)
    if not df.empty:
        df = df.sort_values("variacao_risco", ascending=False, kind="stable").reset_index(drop=True)
        numericas = df.select_dtypes("number").columns
        df[numericas] = df[numericas].round(6)
    df.attrs["fora_do_tornado"] = fora
    df.attrs["idade_atual"] = a
    return df
