"""Núcleo estocástico, parte 3: análise de sobrevivência com Lifelines (TCC 4.4.C).

Não há dados individuais reais: a coorte analisada é sintética, construída a partir dos sorteios do Monte Carlo
(idade de início de quem manifesta; censura no horizonte para quem não manifesta). Sobre ela aplicam-se
Kaplan-Meier, Weibull (entre os que manifestam) e um ajustador paramétrico de cura mista
S(t) = 1 − π·(1 − exp(−(t/λ)^ρ)), cuja recuperação dos parâmetros de entrada (π, λ, ρ) é a verificação de
coerência interna do artefato. As curvas analíticas F(t) = P(C)·π·G(t) recebem bandas de credibilidade
a partir dos sorteios de π (prior Beta).
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from autograd import numpy as anp
from lifelines import KaplanMeierFitter, WeibullFitter
from lifelines.exceptions import ApproximationWarning
from lifelines.fitters import ParametricUnivariateFitter

warnings.filterwarnings("ignore", category=ApproximationWarning)

from .exato import combinar_independentes, f_acumulada, hazard, prob_portador_condicional, risco_condicional
from .monte_carlo import Locus, ResultadoSimulacao

QUALQUER = "qualquer lócus"


class MisturaCuraWeibullFitter(ParametricUnivariateFitter):
    """Modelo de cura mista: uma fração π manifesta com idade Weibull(ρ = forma, λ = escala); 1 − π nunca manifesta."""

    _fitted_parameter_names = ["pi_", "lambda_", "rho_"]
    _bounds = [(0.001, 0.999), (1.0, None), (0.1, None)]

    def _create_initial_point(self, Ts, E, *args):
        T = np.asarray(Ts[0] if isinstance(Ts, (tuple, list)) else Ts, dtype=float)  # Lifelines passa (T, None)
        E = np.asarray(E, dtype=bool)
        pi0 = float(np.clip(E.mean() * 1.1 + 0.01, 0.02, 0.95))
        lam0 = float(np.median(T[E])) if E.any() else 60.0
        return anp.array([pi0, max(lam0, 5.0), 4.0])

    def _cumulative_hazard(self, params, times):
        pi, lam, rho = params
        return -anp.log1p(-pi * (1 - anp.exp(-((times / lam) ** rho))))


# ---------------------------------------------------------------------------
# Coorte sintética
# ---------------------------------------------------------------------------
def coorte_sintetica(res: ResultadoSimulacao, horizonte: float = 90.0, apenas_portadores: bool = False) -> pd.DataFrame:
    """Uma linha por fecundação simulada e por unidade (cada lócus e o combinado "qualquer lócus").

    duracao = idade de início se manifesta até o horizonte; senão o horizonte (censura à direita).
    """
    partes = []
    for j, l in enumerate(res.loci):
        man = res.manifesta[:, j] & (res.idade[:, j] <= horizonte)
        dur = np.where(man, res.idade[:, j], horizonte)
        df = pd.DataFrame({"unidade": l.rotulo, "duracao": dur, "evento": man, "portador": res.portador[:, j]})
        partes.append(df[df.portador] if apenas_portadores else df)
    man = res.manifesta_qualquer & (np.nan_to_num(res.idade_qualquer, nan=np.inf) <= horizonte)
    dur = np.where(man, res.idade_qualquer, horizonte)
    df = pd.DataFrame({"unidade": QUALQUER, "duracao": dur, "evento": man, "portador": res.portador.any(axis=1)})
    partes.append(df[df.portador] if apenas_portadores else df)
    return pd.concat(partes, ignore_index=True)


def ajustar_km(coorte: pd.DataFrame, rotulo: str = "") -> KaplanMeierFitter:
    km = KaplanMeierFitter(label=rotulo or None)
    return km.fit(coorte.duracao.values, event_observed=coorte.evento.values.astype(int))


def ajustar_weibull_manifestantes(coorte: pd.DataFrame) -> WeibullFitter | None:
    """Weibull da idade de início entre os que manifestam (todos os eventos observados)."""
    t = coorte.loc[coorte.evento, "duracao"].values
    if len(t) < 10:
        return None
    return WeibullFitter().fit(t, event_observed=np.ones(len(t)))


def ajustar_mistura_cura(coorte: pd.DataFrame) -> MisturaCuraWeibullFitter | None:
    if coorte.evento.sum() < 10 or (~coorte.evento).sum() < 1:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return MisturaCuraWeibullFitter().fit(coorte.duracao.values, event_observed=coorte.evento.values.astype(int))


# ---------------------------------------------------------------------------
# Tabelas derivadas da Lifelines
# ---------------------------------------------------------------------------
def tabela_km(res: ResultadoSimulacao, horizonte: float = 90.0, idades=(40, 50, 60, 70, 80)) -> pd.DataFrame:
    """Sobrevivência (assintomático) estimada por Kaplan-Meier com IC 95% (Greenwood) nas idades pedidas,
    mediana (infinita sob cura mista = "não atingida") e idade em que 90 % do risco vitalício já ocorreu."""
    coorte = coorte_sintetica(res, horizonte)
    linhas = []
    for unidade, c in coorte.groupby("unidade", sort=False):
        km = ajustar_km(c, unidade)
        s = km.survival_function_at_times(idades).values
        ci = km.confidence_interval_
        linha = {
            "unidade": unidade,
            "n": len(c),
            "eventos": int(c.evento.sum()),
            "risco_vitalicio_km": float(1 - km.survival_function_at_times([horizonte]).values[0]),
        }
        for idade, sv in zip(idades, s):
            idx = ci.index[ci.index <= idade]
            lo, hi = ci.loc[idx[-1]].values if len(idx) else (np.nan, np.nan)
            linha[f"S({idade})"] = float(sv)
            linha[f"IC95 S({idade})"] = f"{lo:.3f}–{hi:.3f}"
        med = km.median_survival_time_
        linha["mediana_sobrevivencia"] = "não atingida" if not np.isfinite(med) else round(float(med), 1)
        alvo = 1 - 0.9 * linha["risco_vitalicio_km"]
        p90 = km.percentile(alvo) if linha["risco_vitalicio_km"] > 0 else np.inf
        linha["idade_90pct_do_risco"] = round(float(p90), 1) if np.isfinite(p90) else np.nan
        linhas.append(linha)
    return pd.DataFrame(linhas)


def recuperacao_parametros(res: ResultadoSimulacao, horizonte: float = 90.0) -> pd.DataFrame:
    """Tabela 7: a Lifelines recupera, da coorte sintética de portadores, os parâmetros de entrada π, λ e ρ (= k)?"""
    coorte = coorte_sintetica(res, horizonte, apenas_portadores=True)
    linhas = []
    for j, l in enumerate(res.loci):
        c = coorte[coorte.unidade == l.rotulo]
        linha = {
            "variante": l.rotulo,
            "n_portadores": len(c),
            "eventos": int(c.evento.sum()),
            "pi_entrada": l.pen_media,
            "lambda_entrada": l.dist.params.get("lam", np.nan),
            "rho_entrada": l.dist.params.get("k", np.nan),
            "delta_sexo": l.dist.delta,
        }
        mc = ajustar_mistura_cura(c)
        if mc is not None:
            linha.update(
                {"pi_lifelines": float(mc.pi_), "lambda_lifelines": float(mc.lambda_), "rho_lifelines": float(mc.rho_)}
            )
            linha["erro_rel_pi"] = abs(linha["pi_lifelines"] - l.pen_media) / l.pen_media
            if l.dist.tipo == "weibull":
                # a escala recuperada inclui o deslocamento do sexo, por isso comparar com λ + δ aproximadamente
                linha["erro_rel_lambda"] = (
                    abs(linha["lambda_lifelines"] - (l.dist.params["lam"] + l.dist.delta)) / l.dist.params["lam"]
                )
                linha["erro_rel_rho"] = abs(linha["rho_lifelines"] - l.dist.params["k"]) / l.dist.params["k"]
        wf = ajustar_weibull_manifestantes(c)
        if wf is not None:
            linha.update(
                {
                    "weibull_lambda_manifestantes": float(wf.lambda_),
                    "weibull_rho_manifestantes": float(wf.rho_),
                    "mediana_weibull_manifestantes": float(wf.median_survival_time_),
                }
            )
        linhas.append(linha)
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# Curvas analíticas com bandas de credibilidade
# ---------------------------------------------------------------------------
def curvas_analiticas(res: ResultadoSimulacao, t_max: float = 90.0, passo: float = 0.5) -> pd.DataFrame:
    """F(t), S(t) e h(t) por unidade; banda de 95 % obtida propagando os sorteios de π (coluna por coluna)."""
    t = np.arange(0, t_max + passo, passo)
    linhas = []
    f_por_locus = []
    for j, l in enumerate(res.loci):
        pen = res.penetrancia[:, j][:, None]  # (n, 1)
        f = l.p_portador_exato * pen * l.dist.cdf(t)[None, :]  # (n, T)
        f_por_locus.append(f)
        q = np.percentile(f, [2.5, 50, 97.5], axis=0)
        linhas.append(
            pd.DataFrame(
                {
                    "unidade": l.rotulo,
                    "t": t,
                    "F": f_acumulada(t, l.p_portador_exato, l.pen_media, l.dist),
                    "F_q025": q[0],
                    "F_mediana": q[1],
                    "F_q975": q[2],
                    "h": hazard(t, l.p_portador_exato, l.pen_media, l.dist),
                }
            )
        )
    f_any = 1 - np.prod([1 - f for f in f_por_locus], axis=0)
    q = np.percentile(f_any, [2.5, 50, 97.5], axis=0)
    f_any_media = 1 - np.prod([1 - f_acumulada(t, l.p_portador_exato, l.pen_media, l.dist) for l in res.loci], axis=0)
    s = 1 - f_any_media
    h_any = np.gradient(f_any_media, t) / np.clip(s, 1e-12, None)
    linhas.append(
        pd.DataFrame(
            {
                "unidade": QUALQUER,
                "t": t,
                "F": f_any_media,
                "F_q025": q[0],
                "F_mediana": q[1],
                "F_q975": q[2],
                "h": h_any,
            }
        )
    )
    df = pd.concat(linhas, ignore_index=True)
    df["S"] = 1 - df["F"]
    return df


def tabela_risco_condicional(
    res: ResultadoSimulacao, idades_atuais=(0, 20, 30, 40, 50, 60, 70), janelas=(10, 20), horizonte: float = 90.0
) -> pd.DataFrame:
    """Tabela 4: para cada idade atual sem sintomas, P(portador | assintomático), risco nos próximos 10/20 anos
    e risco vitalício residual, por lócus e combinado, com banda de 95 % pela incerteza de π."""
    linhas = []
    pen_draws = res.penetrancia
    for a in idades_atuais:
        por_locus_media, por_locus_draws = [], []
        for j, l in enumerate(res.loci):
            pen = pen_draws[:, j]
            linha = {
                "unidade": l.rotulo,
                "idade_atual": a,
                "p_portador_condicional": prob_portador_condicional(a, l.p_portador_exato, l.pen_media, l.dist),
            }
            fa = l.p_portador_exato * pen * float(l.dist.cdf(a))
            riscos = {}
            for jan in list(janelas) + [None]:
                t = horizonte if jan is None else a + jan
                r = float(risco_condicional(t, a, l.p_portador_exato, l.pen_media, l.dist))
                ft = l.p_portador_exato * pen * float(l.dist.cdf(t))
                rd = np.clip((ft - fa) / (1 - fa), 0, 1)
                nome = "vitalicio" if jan is None else f"{jan}_anos"
                riscos[nome] = (r, np.percentile(rd, 2.5), np.percentile(rd, 97.5))
                linha[f"risco_{nome}"] = r
                linha[f"risco_{nome}_q025"] = riscos[nome][1]
                linha[f"risco_{nome}_q975"] = riscos[nome][2]
            linhas.append(linha)
            por_locus_media.append(l)
            por_locus_draws.append(pen)
        if len(res.loci) > 1:
            linha = {"unidade": QUALQUER, "idade_atual": a, "p_portador_condicional": np.nan}
            fa_all = [l.p_portador_exato * pen * float(l.dist.cdf(a)) for l, pen in zip(res.loci, por_locus_draws)]
            fa_any = 1 - np.prod([1 - f for f in fa_all], axis=0)
            fa_med = 1 - np.prod([1 - l.p_portador_exato * l.pen_media * float(l.dist.cdf(a)) for l in res.loci])
            for jan in list(janelas) + [None]:
                t = horizonte if jan is None else a + jan
                ft_all = [l.p_portador_exato * pen * float(l.dist.cdf(t)) for l, pen in zip(res.loci, por_locus_draws)]
                ft_any = 1 - np.prod([1 - f for f in ft_all], axis=0)
                ft_med = 1 - np.prod([1 - l.p_portador_exato * l.pen_media * float(l.dist.cdf(t)) for l in res.loci])
                rd = np.clip((ft_any - fa_any) / (1 - fa_any), 0, 1)
                nome = "vitalicio" if jan is None else f"{jan}_anos"
                linha[f"risco_{nome}"] = float(np.clip((ft_med - fa_med) / (1 - fa_med), 0, 1))
                linha[f"risco_{nome}_q025"] = float(np.percentile(rd, 2.5))
                linha[f"risco_{nome}_q975"] = float(np.percentile(rd, 97.5))
            linhas.append(linha)
    return pd.DataFrame(linhas)


def risco_condicional_km(
    res: ResultadoSimulacao, idade_atual: float, horizonte: float = 90.0, idades=(10, 20)
) -> pd.DataFrame:
    """Versão não paramétrica do risco condicional: 1 − S_KM(t)/S_KM(a), por unidade (verificação da Tabela 4)."""
    coorte = coorte_sintetica(res, horizonte)
    linhas = []
    for unidade, c in coorte.groupby("unidade", sort=False):
        km = ajustar_km(c, unidade)
        sa = float(km.survival_function_at_times([idade_atual]).values[0])
        linha = {"unidade": unidade, "idade_atual": idade_atual}
        for jan in idades:
            st = float(km.survival_function_at_times([idade_atual + jan]).values[0])
            linha[f"risco_{jan}_anos_km"] = 1 - st / sa if sa > 0 else np.nan
        st = float(km.survival_function_at_times([horizonte]).values[0])
        linha["risco_vitalicio_km"] = 1 - st / sa if sa > 0 else np.nan
        linhas.append(linha)
    return pd.DataFrame(linhas)
