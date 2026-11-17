"""Fórmulas em forma fechada do modelo.

Servem de referência para os testes de aderência do Monte Carlo e para as curvas analíticas.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np
from scipy import optimize, special, stats

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
# Distribuição da penetrância vitalícia π
# ---------------------------------------------------------------------------
class DistribuicaoPenetrancia:
    """Distribuição a priori da penetrância vitalícia π de um gene.

    `tipo` = "beta" (alpha, beta; padrão do artefato) ou "lognormal_truncada" (mu e sigma em escala logarítmica,
    truncada em 1 porque π é uma probabilidade). A fração da log-normal acima de 1, retirada pelo truncamento, fica em
    `massa_truncada` (zero para a Beta).
    """

    def __init__(self, tipo: str = "beta", **params: float):
        self.tipo = tipo
        self.params = {k: float(v) for k, v in params.items()}
        if tipo == "beta":
            self._a, self._b = self.params["alpha"], self.params["beta"]
            self._abaixo_de_1 = 1.0
        elif tipo == "lognormal_truncada":
            self._mu, self._sigma = self.params["mu"], self.params["sigma"]
            self._abaixo_de_1 = float(stats.norm.cdf(-self._mu / self._sigma))  # P(π ≤ 1) antes do truncamento
        else:
            raise ValueError(f"distribuição de penetrância desconhecida: {tipo}")

    @property
    def massa_truncada(self) -> float:
        return 1.0 - self._abaixo_de_1

    def ppf(self, q):
        q = np.asarray(q, dtype=float)
        if self.tipo == "beta":
            return stats.beta.ppf(q, self._a, self._b)
        return np.exp(self._mu + self._sigma * stats.norm.ppf(q * self._abaixo_de_1))

    def cdf(self, x):
        x = np.asarray(x, dtype=float)
        if self.tipo == "beta":
            return stats.beta.cdf(x, self._a, self._b)
        z = (np.log(np.clip(x, 1e-300, 1.0)) - self._mu) / self._sigma
        return np.where(x > 0, stats.norm.cdf(z) / self._abaixo_de_1, 0.0)

    def pdf(self, x):
        x = np.asarray(x, dtype=float)
        if self.tipo == "beta":
            return stats.beta.pdf(x, self._a, self._b)
        dentro = (x > 0) & (x <= 1)
        xs = np.where(dentro, x, 1.0)
        dens = stats.norm.pdf((np.log(xs) - self._mu) / self._sigma) / (xs * self._sigma * self._abaixo_de_1)
        return np.where(dentro, dens, 0.0)

    @property
    def media(self) -> float:
        if self.tipo == "beta":
            return self._a / (self._a + self._b)
        # E[X | X ≤ 1] da log-normal: exp(μ + σ²/2) · Φ((−μ − σ²)/σ) / Φ(−μ/σ)
        s2 = self._sigma**2
        return float(math.exp(self._mu + s2 / 2) * stats.norm.cdf((-self._mu - s2) / self._sigma) / self._abaixo_de_1)

    @property
    def mediana(self) -> float:
        return float(self.ppf(0.5))

    def amostrar(self, rng: np.random.Generator, tamanho) -> np.ndarray:
        if self.tipo == "beta":
            return rng.beta(self._a, self._b, tamanho)
        return self.ppf(rng.random(tamanho))

    def quadratura(self, n: int | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Nós e pesos (somam 1) para integrar g(π) na distribuição: Gauss-Jacobi na Beta (exata para polinômios de
        grau até 2n − 1) e Gauss-Legendre na escala da probabilidade acumulada para a log-normal truncada."""
        if self.tipo == "beta":
            x, w = special.roots_jacobi(n or 48, self._b - 1.0, self._a - 1.0)
            return (x + 1.0) / 2.0, w / w.sum()
        u, w = np.polynomial.legendre.leggauss(n or 400)
        return self.ppf((u + 1.0) / 2.0), w / w.sum()

    def descricao(self) -> str:
        if self.tipo == "beta":
            return f"Beta({self._a:.2f}, {self._b:.2f})"
        return f"log-normal truncada em 1 (μ = {self._mu:.3f}, σ = {self._sigma:.3f})"


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
# Modelo de cura mista e condicionamento à idade
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


def f_qualquer(t: float, componentes) -> float:
    """F(t) do primeiro início entre lóci independentes: 1 − ∏_j (1 − k_j · G_j(t)), com k_j = P(portador_j) · E[π_j]."""
    prod = 1.0
    for k, dist in componentes:
        prod *= 1.0 - float(k) * float(dist.cdf(t))
    return 1.0 - prod


def f_qualquer_grade(t, componentes) -> np.ndarray:
    """`f_qualquer` avaliada de uma vez numa grade de idades."""
    t = np.asarray(t, dtype=float)
    prod = np.ones_like(t)
    for k, dist in componentes:
        prod = prod * (1.0 - float(k) * dist.cdf(t))
    return 1.0 - prod


def quantil_inicio_condicional(q: float, idade_atual: float, horizonte: float, componentes) -> float | None:
    """Idade t tal que P(T ≤ t | idade_atual < T ≤ horizonte) = q, para o primeiro início entre lóci independentes.

    É a idade de início entre quem vai manifestar até o horizonte, condicionada a ainda não ter manifestado na idade
    atual. `componentes`: pares (k_j, G_j), com F_j(t) = k_j · G_j(t). None quando não resta risco entre a idade atual
    e o horizonte.
    """
    comps = [(float(k), d) for k, d in componentes]
    if not comps or not horizonte > idade_atual:
        return None
    fa, fh = f_qualquer(idade_atual, comps), f_qualquer(horizonte, comps)
    if fh - fa <= 1e-12:
        return None
    alvo = fa + float(q) * (fh - fa)
    return float(optimize.brentq(lambda t: f_qualquer(t, comps) - alvo, idade_atual, horizonte, xtol=1e-8))


def desvio_absoluto_inicio_condicional(idade_atual: float, horizonte: float, componentes, passos: int = 4000) -> float:
    """Desvio absoluto médio da idade de início em torno da sua mediana, entre quem manifesta em (idade atual,
    horizonte]: E|T − mediana| sob a distribuição condicional do primeiro início. NaN quando não resta risco."""
    comps = [(float(k), d) for k, d in componentes]
    med = quantil_inicio_condicional(0.5, idade_atual, horizonte, comps)
    if med is None:
        return float("nan")
    t = np.linspace(idade_atual, horizonte, passos + 1)
    f = f_qualquer_grade(t, comps)
    massa = np.diff(f)
    meio = (t[:-1] + t[1:]) / 2.0
    return float(np.sum(massa * np.abs(meio - med)) / np.sum(massa))


def inicio_por_causa(idade_atual: float, horizonte: float, componentes, passos: int = 4000) -> list[tuple]:
    """Por lócus j, entre quem manifesta em (idade atual, horizonte] tendo o lócus j como primeiro início: (mediana da
    idade de início, desvio absoluto médio em torno dela).

    A massa do lócus j em cada idade é k_j · dG_j(t) · ∏_{i≠j} (1 − k_i · G_i(t)): o lócus j inicia em t e nenhum outro
    iniciou antes. Com um só lócus é a própria G_j condicionada ao intervalo. (NaN, NaN) quando não resta risco.
    """
    comps = [(float(k), d) for k, d in componentes]
    t = np.linspace(idade_atual, horizonte, passos + 1)
    meio = (t[:-1] + t[1:]) / 2.0
    saida = []
    for j, (k, dist) in enumerate(comps):
        massa = k * np.diff(dist.cdf(t))
        for i, (ki, di) in enumerate(comps):
            if i != j:
                massa = massa * (1.0 - ki * di.cdf(meio))
        total = float(massa.sum())
        if not total > 1e-12:
            saida.append((float("nan"), float("nan")))
            continue
        acumulada = np.concatenate([[0.0], np.cumsum(massa)]) / total
        med = float(np.interp(0.5, acumulada, t))
        saida.append((med, float(np.sum(massa * np.abs(meio - med)) / total)))
    return saida
