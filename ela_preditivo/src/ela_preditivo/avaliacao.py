"""Avaliação do artefato (TCC, seções 3.4 e 4.5): aderência teórica, estabilidade numérica, coerência das curvas,
tempo de processamento e análises de sensibilidade."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from . import sobrevivencia
from .calibracao import Parametros
from .exato import DistribuicaoInicio, combinar_independentes
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


FAIXA_INCIDENCIA = (
    60.0,
    75.0,
)  # pico de incidência populacional da ELA (FELDMAN et al., 2022): referência, não critério de aprovação


def _idade_pico(curvas: pd.DataFrame, unidade: str) -> float:
    c = curvas[curvas.unidade == unidade]
    return float(c.t.iloc[int(np.argmax(c.h.values))])


def coerencia(res: ResultadoSimulacao, horizonte: float = 90.0) -> pd.DataFrame:
    """Coerência das curvas (TCC 4.5): F(∞) exato vs Kaplan-Meier, medianas de início (exata, Weibull da Lifelines),
    parâmetros recuperados pelo modelo de cura mista e idade do pico de h(t), por lócus e para o risco combinado.

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
                "F_inf_exato": l.p_manifesta_exato,
                "risco_vitalicio_km": km.loc[l.rotulo, "risco_vitalicio_km"],
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
            "F_inf_exato": comb["p_manifesta_qualquer_exato"],
            "risco_vitalicio_km": km.loc[q, "risco_vitalicio_km"],
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
    """Tabela 9: risco vitalício e idade mediana sob (a) calibração pela literatura, (b) parâmetros do exemplo do
    orientador, (c) C9orf72 com penetrância de coorte familiar (0,90)."""
    from .monte_carlo import loci_de_vetor

    cenarios = {"literatura (Douglas & Baralle 2024; Murphy 2017)": {}}
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
