"""Fórmulas em forma fechada do modelo (docs/02_modelo_matematico.md, §1 e §3).

Servem de referência para os testes de aderência do Monte Carlo e para as curvas analíticas.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np
from scipy import stats

HERANCAS = ("dominante", "recessiva")


def cpt_segregacao(dose_materna: int, dose_paterna: int) -> np.ndarray:
    """P(D = 0, 1, 2 | dosagens dos pais): convolução de duas Bernoulli(d/2)."""
    for d in (dose_materna, dose_paterna):
        if d not in (0, 1, 2):
            raise ValueError(f"dosagem inválida: {d}")
    pm, pf = dose_materna / 2.0, dose_paterna / 2.0
    return np.array([(1 - pm) * (1 - pf), pm * (1 - pf) + (1 - pm) * pf, pm * pf])


def prob_portador(dose_materna: int, dose_paterna: int, heranca: str = "dominante") -> float:
    """P(C = 1): descendente em risco genético (dominante: D >= 1; recessiva: D = 2)."""
    if heranca not in HERANCAS:
        raise ValueError(f"herança desconhecida: {heranca}")
    cpt = cpt_segregacao(dose_materna, dose_paterna)
    return float(cpt[2]) if heranca == "recessiva" else float(cpt[1] + cpt[2])


def media_beta(alpha: float, beta: float) -> float:
    return alpha / (alpha + beta)


def intervalo_beta(alpha: float, beta: float, nivel: float = 0.95) -> tuple[float, float]:
    q = (1 - nivel) / 2
    return tuple(stats.beta.ppf([q, 1 - q], alpha, beta))


def prob_manifestacao(p_portador: float, alpha: float, beta: float) -> float:
    """P(M = 1) = P(C = 1) · E[π]."""
    return p_portador * media_beta(alpha, beta)


def combinar_independentes(probabilidades: Iterable[float]) -> float:
    """P(pelo menos um evento) sob independência: 1 − ∏(1 − p_g)."""
    prod = 1.0
    for p in probabilidades:
        prod *= 1.0 - p
    return 1.0 - prod


# ---------------------------------------------------------------------------
# Distribuição de idade de início G(t) com deslocamento por sexo
# ---------------------------------------------------------------------------
class DistribuicaoInicio:
    """G(t): fração acumulada, entre os que manifestam, com início até a idade t.

    `tipo` = "weibull" (k = forma, lam = escala) ou "lognormal" (mu, sigma, em anos).
    `delta` desloca a idade (ex.: sexo). Idades abaixo de `delta` têm G = 0.
    """

    def __init__(self, tipo: str, delta: float = 0.0, **params: float):
        self.tipo = tipo
        self.delta = float(delta)
        self.params = {k: float(v) for k, v in params.items()}
        if tipo == "weibull":
            self._dist = stats.weibull_min(c=self.params["k"], scale=self.params["lam"])
        elif tipo == "lognormal":
            self._dist = stats.lognorm(s=self.params["sigma"], scale=math.exp(self.params["mu"]))
        else:
            raise ValueError(f"distribuição desconhecida: {tipo}")

    def deslocar(self, delta: float) -> "DistribuicaoInicio":
        return DistribuicaoInicio(self.tipo, delta=self.delta + delta, **self.params)

    def cdf(self, t):
        t = np.asarray(t, dtype=float) - self.delta
        return np.where(t > 0, self._dist.cdf(np.clip(t, 0, None)), 0.0)

    def pdf(self, t):
        t = np.asarray(t, dtype=float) - self.delta
        return np.where(t > 0, self._dist.pdf(np.clip(t, 1e-12, None)), 0.0)

    def ppf(self, q):
        return self._dist.ppf(q) + self.delta

    def amostrar(self, rng: np.random.Generator, tamanho) -> np.ndarray:
        return self._dist.rvs(size=tamanho, random_state=rng) + self.delta

    @property
    def mediana(self) -> float:
        return float(self._dist.median() + self.delta)

    @property
    def media(self) -> float:
        return float(self._dist.mean() + self.delta)


def weibull_mediana(k: float, lam: float, delta: float = 0.0) -> float:
    return lam * math.log(2) ** (1.0 / k) + delta


def weibull_media(k: float, lam: float, delta: float = 0.0) -> float:
    return lam * math.gamma(1.0 + 1.0 / k) + delta


# ---------------------------------------------------------------------------
# Modelo de cura mista e condicionamento à idade (docs/02, §3)
# ---------------------------------------------------------------------------
def f_acumulada(t, p_portador: float, penetrancia: float, dist: DistribuicaoInicio):
    """F(t) = P(C) · π · G(t): probabilidade de manifestação até a idade t."""
    return p_portador * penetrancia * dist.cdf(t)


def risco_condicional(t, idade_atual: float, p_portador: float, penetrancia: float, dist: DistribuicaoInicio):
    """P(T <= t | assintomático na idade a) = (F(t) − F(a)) / (1 − F(a)), com F = q·π·G."""
    fa = f_acumulada(idade_atual, p_portador, penetrancia, dist)
    ft = f_acumulada(t, p_portador, penetrancia, dist)
    return np.clip((ft - fa) / (1.0 - fa), 0.0, 1.0)


def prob_portador_condicional(
    idade_atual: float, p_portador: float, penetrancia: float, dist: DistribuicaoInicio
) -> float:
    """Atualização bayesiana: P(C = 1 | assintomático na idade a) = q(1 − πG(a)) / (1 − qπG(a))."""
    g = float(dist.cdf(idade_atual))
    return p_portador * (1.0 - penetrancia * g) / (1.0 - p_portador * penetrancia * g)


def hazard(t, p_portador: float, penetrancia: float, dist: DistribuicaoInicio):
    """h(t) = f(t) / S(t), com f = dF/dt."""
    f = p_portador * penetrancia * dist.pdf(t)
    s = 1.0 - f_acumulada(t, p_portador, penetrancia, dist)
    return f / np.clip(s, 1e-12, None)
