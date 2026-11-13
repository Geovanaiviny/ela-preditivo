"""Calibração das priors a partir da literatura (docs/02_modelo_matematico.md, §2).

- `ajustar_beta`: Beta(α, β) por ajuste de quantis ao ponto e ao IC 95% de penetrância.
- `ajustar_weibull` / `ajustar_lognormal`: forma da distribuição de idade de início G(t) a partir
  de pontos de Kaplan-Meier ou de faixas etárias.
- `weibull_de_momentos` / `weibull_de_quantis` (e as log-normais correspondentes): G(t) em forma fechada a partir das
  estatísticas publicadas — média e desvio padrão (ex.: BERDYŃSKI et al., 2022) ou mediana e IQR (ex.: McFARLANE et al., 2025).
- `carregar_parametros`: lê `config/parametros_literatura.yaml` e devolve os parâmetros calibrados.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy import optimize, special, stats

from . import DIR_CONFIG, GENES
from .exato import DistribuicaoInicio

CAMINHO_PADRAO = DIR_CONFIG / "parametros_literatura.yaml"


# ---------------------------------------------------------------------------
# Beta a partir de ponto + IC 95%
# ---------------------------------------------------------------------------
def ajustar_beta(ponto: float, ic95: tuple[float, float], peso_ponto: float = 0.5) -> dict[str, float]:
    """Ajusta Beta(α, β) minimizando o erro nos quantis 2,5% e 97,5% e tratando o ponto como mediana."""
    lo, hi = float(ic95[0]), float(ic95[1])
    if not (0 < lo < ponto < hi < 1):
        raise ValueError(f"ponto/IC inconsistentes: {ponto}, {ic95}")

    def perda(theta: np.ndarray) -> float:
        a, b = np.exp(theta)
        return (
            (stats.beta.cdf(lo, a, b) - 0.025) ** 2
            + (stats.beta.cdf(hi, a, b) - 0.975) ** 2
            + peso_ponto * (stats.beta.cdf(ponto, a, b) - 0.5) ** 2
        )

    # chute inicial pelo método dos momentos (desvio ≈ largura do IC / 3,92)
    m, s = ponto, (hi - lo) / 3.92
    comum = m * (1 - m) / (s * s) - 1
    a0, b0 = max(m * comum, 0.5), max((1 - m) * comum, 0.5)
    res = optimize.minimize(
        perda, np.log([a0, b0]), method="Nelder-Mead", options={"xatol": 1e-9, "fatol": 1e-14, "maxiter": 10000}
    )
    a, b = np.exp(res.x)
    q025, q975 = stats.beta.ppf([0.025, 0.975], a, b)
    return {
        "alpha": float(a),
        "beta": float(b),
        "media": float(a / (a + b)),
        "mediana": float(stats.beta.median(a, b)),
        "q025": float(q025),
        "q975": float(q975),
        "erro_ic": float(max(abs(q025 - lo), abs(q975 - hi))),
        "erro_ponto": float(abs(stats.beta.median(a, b) - ponto)),
    }


# ---------------------------------------------------------------------------
# Distribuição de idade de início a partir de pontos (t, fração acumulada)
# ---------------------------------------------------------------------------
def _preparar_pontos(pontos, plato: float | None):
    pts = np.asarray(pontos, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) < 2:
        raise ValueError("pontos devem ser uma lista [[idade, fração], ...] com pelo menos 2 itens")
    t, g = pts[:, 0], pts[:, 1]
    if plato:
        g = np.clip(g / float(plato), 0, 1)
    if np.any(t <= 0) or np.any(g < 0) or np.any(g > 1):
        raise ValueError("idades devem ser > 0 e frações em [0, 1]")
    return t, g


def ajustar_weibull(pontos, plato: float | None = None) -> dict[str, Any]:
    """Weibull(k, λ) por mínimos quadrados sobre G(t_i) − g_i, com chute pela linearização ln(−ln(1−g))."""
    t, g = _preparar_pontos(pontos, plato)
    uteis = (g > 0.001) & (g < 0.999)
    if uteis.sum() >= 2:
        y = np.log(-np.log(1 - g[uteis]))
        k0, c0 = np.polyfit(np.log(t[uteis]), y, 1)
        lam0 = float(np.exp(-c0 / k0))
    else:
        k0, lam0 = 5.0, float(np.median(t))
    k0 = float(np.clip(k0, 0.5, 40))
    lam0 = float(np.clip(lam0, 5, 150))

    def residuos(p):
        return 1 - np.exp(-((t / p[1]) ** p[0])) - g

    res = optimize.least_squares(residuos, x0=[k0, lam0], bounds=([0.2, 1.0], [60.0, 200.0]))
    k, lam = res.x
    return {
        "tipo": "weibull",
        "k": float(k),
        "lam": float(lam),
        "rss": float(np.sum(res.fun**2)),
        "metodo": "pontos",
        "pontos_t": t.tolist(),
        "pontos_g": g.tolist(),
    }


def ajustar_lognormal(pontos, plato: float | None = None) -> dict[str, Any]:
    """Log-normal(μ, σ) por mínimos quadrados, com chute pela linearização Φ⁻¹(g) = (ln t − μ)/σ."""
    t, g = _preparar_pontos(pontos, plato)
    uteis = (g > 0.001) & (g < 0.999)
    if uteis.sum() >= 2:
        inv_sigma, c0 = np.polyfit(np.log(t[uteis]), stats.norm.ppf(g[uteis]), 1)
        sigma0 = 1.0 / max(inv_sigma, 1e-3)
        mu0 = -c0 * sigma0
    else:
        mu0, sigma0 = float(np.log(np.median(t))), 0.3

    def residuos(p):
        return stats.norm.cdf((np.log(t) - p[0]) / p[1]) - g

    res = optimize.least_squares(residuos, x0=[mu0, max(sigma0, 0.05)], bounds=([0.0, 0.01], [6.0, 3.0]))
    mu, sigma = res.x
    return {
        "tipo": "lognormal",
        "mu": float(mu),
        "sigma": float(sigma),
        "rss": float(np.sum(res.fun**2)),
        "metodo": "pontos",
        "pontos_t": t.tolist(),
        "pontos_g": g.tolist(),
    }


# ---------------------------------------------------------------------------
# Distribuição de idade de início a partir de estatísticas publicadas (forma fechada)
# ---------------------------------------------------------------------------
_Z75 = float(stats.norm.ppf(0.75))


def weibull_de_momentos(media: float, dp: float) -> dict[str, Any]:
    """Weibull(k, λ) com a média e o desvio padrão publicados (ex.: BERDYŃSKI et al., 2022, idade de início do SOD1).

    CV² = Γ(1 + 2/k)/Γ(1 + 1/k)² − 1 depende só de k e decresce com k: k sai por bissecção (brentq) e λ = média/Γ(1 + 1/k).
    """
    media, dp = float(media), float(dp)
    if media <= 0 or dp <= 0:
        raise ValueError(f"média e desvio padrão devem ser positivos: {media}, {dp}")
    cv2 = (dp / media) ** 2

    def g(k):
        return math.exp(special.gammaln(1 + 2 / k) - 2 * special.gammaln(1 + 1 / k)) - 1 - cv2

    k = float(optimize.brentq(g, 0.1, 500.0, xtol=1e-12))
    return {
        "tipo": "weibull",
        "k": k,
        "lam": float(media / math.gamma(1 + 1 / k)),
        "rss": float("nan"),
        "metodo": "momentos",
        "estatisticas": {"media": media, "dp": dp},
        "pontos_t": [],
        "pontos_g": [],
    }


def weibull_de_quantis(mediana: float, iqr: float) -> dict[str, Any]:
    """Weibull(k, λ) com a mediana e o intervalo interquartil (Q3 − Q1) publicados (ex.: McFARLANE et al., 2025).

    Com Q(p) = λ(−ln(1 − p))^{1/k}: IQR/mediana = [(ln 4)^{1/k} − (ln 4/3)^{1/k}]/(ln 2)^{1/k} depende só de k e decresce
    com k; k sai por bissecção e λ = mediana/(ln 2)^{1/k} (casamento de quantis).
    """
    mediana, iqr = float(mediana), float(iqr)
    if mediana <= 0 or iqr <= 0:
        raise ValueError(f"mediana e IQR devem ser positivos: {mediana}, {iqr}")
    razao = iqr / mediana
    a, b, c = math.log(4), math.log(4 / 3), math.log(2)

    def g(k):
        return (a ** (1 / k) - b ** (1 / k)) / c ** (1 / k) - razao

    k = float(optimize.brentq(g, 0.1, 500.0, xtol=1e-12))
    return {
        "tipo": "weibull",
        "k": k,
        "lam": float(mediana / c ** (1 / k)),
        "rss": float("nan"),
        "metodo": "quantis",
        "estatisticas": {"mediana": mediana, "iqr": iqr},
        "pontos_t": [],
        "pontos_g": [],
    }


def lognormal_de_momentos(media: float, dp: float) -> dict[str, Any]:
    """Log-normal(μ, σ) com média e desvio padrão: σ² = ln(1 + CV²), μ = ln(média) − σ²/2 (alternativa da Tabela 6)."""
    media, dp = float(media), float(dp)
    if media <= 0 or dp <= 0:
        raise ValueError(f"média e desvio padrão devem ser positivos: {media}, {dp}")
    sigma2 = math.log(1 + (dp / media) ** 2)
    return {
        "tipo": "lognormal",
        "mu": math.log(media) - sigma2 / 2,
        "sigma": math.sqrt(sigma2),
        "rss": float("nan"),
        "metodo": "momentos",
        "estatisticas": {"media": media, "dp": dp},
        "pontos_t": [],
        "pontos_g": [],
    }


def lognormal_de_quantis(mediana: float, iqr: float) -> dict[str, Any]:
    """Log-normal(μ, σ) com mediana e IQR: μ = ln(mediana); IQR = 2·mediana·senh(z₇₅·σ) ⇒ σ = asenh(IQR/(2·mediana))/z₇₅."""
    mediana, iqr = float(mediana), float(iqr)
    if mediana <= 0 or iqr <= 0:
        raise ValueError(f"mediana e IQR devem ser positivos: {mediana}, {iqr}")
    return {
        "tipo": "lognormal",
        "mu": math.log(mediana),
        "sigma": math.asinh(iqr / (2 * mediana)) / _Z75,
        "rss": float("nan"),
        "metodo": "quantis",
        "estatisticas": {"mediana": mediana, "iqr": iqr},
        "pontos_t": [],
        "pontos_g": [],
    }


def ajustar_estatisticas(estatisticas: dict) -> tuple[dict, dict]:
    """(Weibull, log-normal) em forma fechada a partir de `{media, dp}` (momentos) ou `{mediana, iqr}` (quantis)."""
    e = {str(k).lower(): v for k, v in dict(estatisticas).items()}
    if {"media", "dp"} <= set(e):
        return weibull_de_momentos(e["media"], e["dp"]), lognormal_de_momentos(e["media"], e["dp"])
    if {"mediana", "iqr"} <= set(e):
        return weibull_de_quantis(e["mediana"], e["iqr"]), lognormal_de_quantis(e["mediana"], e["iqr"])
    raise ValueError(f"`estatisticas` deve trazer {{media, dp}} ou {{mediana, iqr}}; recebido: {sorted(e)}")


def ajustar_inicio(
    pontos=None, distribuicao: str = "weibull", plato: float | None = None, estatisticas: dict | None = None
) -> tuple[DistribuicaoInicio, dict]:
    """Ajusta a distribuição pedida e, para a tabela de calibração, também a alternativa.

    Entrada: `pontos` [[idade, fração], ...] (curva de Kaplan-Meier ou faixas etárias; mínimos quadrados) **ou**
    `estatisticas` {media, dp} / {mediana, iqr} (forma fechada) — exatamente um dos dois.
    """
    pontos = pontos if pontos else None
    if (pontos is None) == (estatisticas is None):
        raise ValueError("informe `pontos` ou `estatisticas` (exatamente um dos dois) para a distribuição de início")
    if estatisticas is not None:
        w, ln = ajustar_estatisticas(estatisticas)
    else:
        w, ln = ajustar_weibull(pontos, plato), ajustar_lognormal(pontos, plato)
    escolhido = w if distribuicao == "weibull" else ln
    alternativa = ln if distribuicao == "weibull" else w
    if escolhido["tipo"] == "weibull":
        dist = DistribuicaoInicio("weibull", k=escolhido["k"], lam=escolhido["lam"])
    else:
        dist = DistribuicaoInicio("lognormal", mu=escolhido["mu"], sigma=escolhido["sigma"])
    return dist, {"escolhido": escolhido, "alternativa": alternativa}


# ---------------------------------------------------------------------------
# Parâmetros carregados do YAML
# ---------------------------------------------------------------------------
@dataclass
class ParametrosGene:
    nome: str
    cromossomo: str
    heranca: str
    tipo_variante: str
    pen_valor: float
    pen_ic95: tuple[float, float]
    alpha: float
    beta: float
    pen_citacao: str
    pen_confirmar: bool
    inicio: DistribuicaoInicio
    inicio_ajuste: dict
    inicio_pontos: list
    inicio_citacao: str
    inicio_confirmar: bool
    delta_sexo: dict[str, float]
    delta_citacao: str
    delta_confirmar: bool
    inicio_estatisticas: dict = field(
        default_factory=dict
    )  # {media, dp} ou {mediana, iqr} quando G(t) vem de estatísticas
    extras: dict = field(default_factory=dict)

    def distribuicao_sexo(self, sexo: str | None) -> DistribuicaoInicio:
        """G(t) deslocada pelo efeito do sexo ("M", "F" ou None = sem deslocamento)."""
        return self.inicio.deslocar(self.delta_sexo.get(sexo, 0.0) if sexo else 0.0)

    @property
    def pen_media(self) -> float:
        return self.alpha / (self.alpha + self.beta)


@dataclass
class Parametros:
    versao: int
    data: str
    horizonte_anos: float
    multiplicador_homozigoto: float
    filtro_qualidade: dict
    limiar_repeticoes: dict
    sensibilidade: dict
    genes: dict[str, ParametrosGene]
    caminho: Path

    def tabela_calibracao(self) -> pd.DataFrame:
        """Tabela 6 do relatório: priors Beta e distribuições de início calibradas, com flags de confirmação."""
        linhas = []
        for g in self.genes.values():
            esc = g.inicio_ajuste["escolhido"]
            alt = g.inicio_ajuste["alternativa"]
            linhas.append(
                {
                    "gene": g.nome,
                    "heranca": g.heranca,
                    "penetrancia_publicada": g.pen_valor,
                    "ic95_publicado": f"{g.pen_ic95[0]:.3f}–{g.pen_ic95[1]:.3f}",
                    "alpha": round(g.alpha, 3),
                    "beta": round(g.beta, 3),
                    "media_beta": round(g.pen_media, 3),
                    "mediana_beta": round(stats.beta.median(g.alpha, g.beta), 3),
                    "ic95_beta": f"{stats.beta.ppf(0.025, g.alpha, g.beta):.3f}–{stats.beta.ppf(0.975, g.alpha, g.beta):.3f}",
                    "distribuicao_inicio": g.inicio.tipo,
                    "metodo_inicio": esc.get("metodo", "pontos"),
                    "parametros_inicio": ", ".join(f"{k}={v:.2f}" for k, v in g.inicio.params.items()),
                    "mediana_inicio_anos": round(g.inicio.mediana, 1),
                    "rss_escolhida": round(esc["rss"], 5),
                    "rss_alternativa": round(alt["rss"], 5),
                    "delta_sexo": f"M {g.delta_sexo.get('M', 0):+.1f} / F {g.delta_sexo.get('F', 0):+.1f}",
                    "erro_ic_beta": round(
                        max(
                            abs(stats.beta.ppf(0.025, g.alpha, g.beta) - g.pen_ic95[0]),
                            abs(stats.beta.ppf(0.975, g.alpha, g.beta) - g.pen_ic95[1]),
                        ),
                        3,
                    ),
                    "valor_provisorio": "sim" if (g.pen_confirmar or g.inicio_confirmar) else "não",
                    "citacao_penetrancia": g.pen_citacao,
                    "citacao_inicio": g.inicio_citacao,
                }
            )
        return pd.DataFrame(linhas)


def carregar_parametros(caminho: str | Path | None = None) -> Parametros:
    caminho = Path(caminho) if caminho else CAMINHO_PADRAO
    with open(caminho, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    peso_ponto = float(cfg.get("calibracao_beta", {}).get("peso_ponto", 1.0))
    genes: dict[str, ParametrosGene] = {}
    for nome, g in cfg["genes"].items():
        pen = g["penetrancia"]
        beta_fit = ajustar_beta(pen["valor"], tuple(pen["ic95"]), peso_ponto=peso_ponto)
        ini = g["inicio"]
        dist, ajuste = ajustar_inicio(
            ini.get("pontos"),
            ini.get("distribuicao", "weibull"),
            ini.get("plato"),
            estatisticas=ini.get("estatisticas"),
        )
        ds = g.get("delta_sexo", {})
        extras = {
            k: v
            for k, v in g.items()
            if k not in {"cromossomo", "heranca", "tipo_variante", "penetrancia", "inicio", "delta_sexo"}
        }
        genes[nome] = ParametrosGene(
            nome=nome,
            cromossomo=str(g["cromossomo"]),
            heranca=g["heranca"],
            tipo_variante=g.get("tipo_variante", "snv"),
            pen_valor=float(pen["valor"]),
            pen_ic95=(float(pen["ic95"][0]), float(pen["ic95"][1])),
            alpha=beta_fit["alpha"],
            beta=beta_fit["beta"],
            pen_citacao=pen.get("citacao", ""),
            pen_confirmar=bool(pen.get("confirmar", True)),
            inicio=dist,
            inicio_ajuste=ajuste,
            inicio_pontos=list(ini.get("pontos") or []),
            inicio_estatisticas=dict(ini.get("estatisticas") or {}),
            inicio_citacao=ini.get("citacao", ""),
            inicio_confirmar=bool(ini.get("confirmar", True)),
            delta_sexo={"M": float(ds.get("M", 0.0)), "F": float(ds.get("F", 0.0))},
            delta_citacao=ds.get("citacao", ""),
            delta_confirmar=bool(ds.get("confirmar", True)),
            extras=extras,
        )
    faltam = set(GENES) - set(genes)
    if faltam:
        raise ValueError(f"genes ausentes no YAML: {sorted(faltam)}")
    return Parametros(
        versao=int(cfg.get("versao", 1)),
        data=str(cfg.get("data", "")),
        horizonte_anos=float(cfg.get("horizonte_anos", 90)),
        multiplicador_homozigoto=float(cfg.get("multiplicador_homozigoto", 1.0)),
        filtro_qualidade=cfg.get("filtro_qualidade", {}),
        limiar_repeticoes=cfg.get("limiar_repeticoes_c9orf72", {"patogenico": 30, "intermediario": 24}),
        sensibilidade=cfg.get("sensibilidade", {}),
        genes=genes,
        caminho=caminho,
    )
