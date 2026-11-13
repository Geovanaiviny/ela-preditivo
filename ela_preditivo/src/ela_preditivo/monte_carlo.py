"""Núcleo estocástico, parte 1: simulação de Monte Carlo em NumPy (TCC 4.4.B).

Cada sorteio é uma fecundação hipotética: alelos transmitidos por cada genitor, dosagem do descendente,
status de portador segundo a herança, penetrância π sorteada da prior Beta, manifestação e idade de início.
O amostrador NumPy tem a mesma semântica do modelo PyMC (`rede_bayesiana.py`) e serve para as execuções
repetidas de estabilidade (N = 1e3, 1e4, 1e5 × 30 sementes) e como verificação cruzada.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from .calibracao import Parametros
from .exato import DistribuicaoInicio, combinar_independentes, cpt_segregacao, media_beta, prob_portador


@dataclass
class Locus:
    """Entrada do núcleo estocástico: um lócus de risco com as dosagens parentais e os parâmetros do gene."""

    gene: str
    rotulo: str
    dosagem_mae: int
    dosagem_pai: int
    heranca: str
    alpha: float
    beta: float
    dist: DistribuicaoInicio  # já deslocada pelo efeito do sexo
    pen_fixa: float | None = None  # análise de sensibilidade: penetrância fixa em vez de Beta
    rs: str | None = None

    @property
    def recessivo(self) -> bool:
        return self.heranca == "recessiva"

    @property
    def p_portador_exato(self) -> float:
        return prob_portador(self.dosagem_mae, self.dosagem_pai, self.heranca)

    @property
    def pen_media(self) -> float:
        return self.pen_fixa if self.pen_fixa is not None else media_beta(self.alpha, self.beta)

    @property
    def p_manifesta_exato(self) -> float:
        return self.p_portador_exato * self.pen_media

    def quantis_penetrancia(self, q=(0.025, 0.975)) -> tuple[float, float]:
        if self.pen_fixa is not None:
            return (self.pen_fixa, self.pen_fixa)
        return tuple(stats.beta.ppf(q, self.alpha, self.beta))


def loci_de_vetor(
    vetor: pd.DataFrame,
    parametros: Parametros,
    sexo: str | None = None,
    penetrancia_fixa: dict[str, float] | None = None,
    distribuicoes: dict[str, DistribuicaoInicio] | None = None,
) -> list[Locus]:
    """Monta os lóci a partir do vetor de dosagens (genotipo.vetor_dosagem) e dos parâmetros calibrados.

    `penetrancia_fixa` e `distribuicoes` permitem análises de sensibilidade (ex.: parâmetros do exemplo do orientador).
    """
    loci = []
    for _, v in vetor.iterrows():
        if bool(v.get("descartado", False)):  # genótipo não determinado num genitor: lócus fora do cálculo (TCC 4.3)
            continue
        g = parametros.genes[v.gene]
        dist = (distribuicoes or {}).get(v.gene, g.inicio).deslocar(g.delta_sexo.get(sexo, 0.0) if sexo else 0.0)
        loci.append(
            Locus(
                gene=v.gene,
                rotulo=f"{v.gene} {v.variante}",
                dosagem_mae=int(v.dosagem_mae),
                dosagem_pai=int(v.dosagem_pai),
                heranca=v.heranca,
                alpha=g.alpha,
                beta=g.beta,
                dist=dist,
                pen_fixa=(penetrancia_fixa or {}).get(v.gene),
                rs=v.rs if isinstance(v.rs, str) else None,
            )
        )
    return loci


@dataclass
class ResultadoSimulacao:
    motor: str
    n: int
    seed: int
    sexo: str | None
    loci: list[Locus]
    alelo_mae: np.ndarray  # (n, L) bool
    alelo_pai: np.ndarray
    dose: np.ndarray  # (n, L) int
    portador: np.ndarray  # (n, L) bool
    penetrancia: np.ndarray  # (n, L) float
    manifesta: np.ndarray  # (n, L) bool
    idade: np.ndarray  # (n, L) float, NaN quando não manifesta
    tempo_s: float = 0.0
    idade_condicionada: float | None = None
    n_original: int | None = None

    @property
    def manifesta_qualquer(self) -> np.ndarray:
        return self.manifesta.any(axis=1)

    @property
    def idade_qualquer(self) -> np.ndarray:
        with np.errstate(all="ignore"):
            minimo = np.nanmin(np.where(self.manifesta, self.idade, np.nan), axis=1, initial=np.inf)
        return np.where(np.isfinite(minimo), minimo, np.nan)

    def resumo(self) -> pd.DataFrame:
        """Uma linha por lócus: P(portador) e P(manifesta) exatas e simuladas, erro padrão de MC, IC 95% de
        credibilidade (incerteza da penetrância) e idade de início (mediana e percentis 10/90) entre os que manifestam.
        """
        linhas = []
        for j, l in enumerate(self.loci):
            pc = self.portador[:, j].mean()
            pm_ = self.manifesta[:, j].mean()
            qlo, qhi = l.quantis_penetrancia()
            idades = self.idade[self.manifesta[:, j], j]
            linhas.append(
                {
                    "gene": l.gene,
                    "variante": l.rotulo,
                    "heranca": l.heranca,
                    "dosagem_mae": l.dosagem_mae,
                    "dosagem_pai": l.dosagem_pai,
                    "p_portador_exato": l.p_portador_exato,
                    "p_portador_mc": pc,
                    "ep_portador": np.sqrt(pc * (1 - pc) / self.n),
                    "penetrancia_media": l.pen_media,
                    "penetrancia_q025": qlo,
                    "penetrancia_q975": qhi,
                    "p_manifesta_exato": l.p_manifesta_exato,
                    "p_manifesta_mc": pm_,
                    "ep_manifesta": np.sqrt(pm_ * (1 - pm_) / self.n),
                    "p_manifesta_q025": l.p_portador_exato * qlo,
                    "p_manifesta_q975": l.p_portador_exato * qhi,
                    "idade_mediana_exata": l.dist.mediana,
                    "idade_mediana_mc": float(np.median(idades)) if idades.size else np.nan,
                    "idade_p10_mc": float(np.percentile(idades, 10)) if idades.size else np.nan,
                    "idade_p90_mc": float(np.percentile(idades, 90)) if idades.size else np.nan,
                    "n_manifesta": int(self.manifesta[:, j].sum()),
                    "n": self.n,
                }
            )
        return pd.DataFrame(linhas)

    def risco_combinado_por_sorteio(self) -> np.ndarray:
        """P(manifestação de ≥ 1 lócus) em cada sorteio de π: 1 − ∏_j (1 − P(C_j)·π_ij). É a mesma propagação usada por
        `sobrevivencia.curvas_analiticas` (em t → ∞), de modo que a banda da Tabela 3 e a da Figura 4 coincidem."""
        pp = np.array([l.p_portador_exato for l in self.loci], float)
        return 1 - np.prod(1 - pp[None, :] * self.penetrancia, axis=1)

    def resumo_combinado(self) -> dict:
        """Risco combinado (qualquer lócus) sob independência: exato, simulado, banda de 95 % pelo percentil dos sorteios
        de π (não pela combinação dos quantis de cada lócus, que alarga a banda) e idade do primeiro início."""
        pq = self.manifesta_qualquer.mean()
        idades = self.idade_qualquer[self.manifesta_qualquer]
        f_any = self.risco_combinado_por_sorteio()
        qlo, qhi = (
            (float(np.percentile(f_any, 2.5)), float(np.percentile(f_any, 97.5))) if f_any.size else (np.nan, np.nan)
        )
        return {
            "motor": self.motor,
            "n": self.n,
            "seed": self.seed,
            "sexo": self.sexo,
            "n_loci": len(self.loci),
            "p_portador_qualquer_mc": float(self.portador.any(axis=1).mean()),
            "p_portador_qualquer_exato": combinar_independentes(l.p_portador_exato for l in self.loci),
            "p_manifesta_qualquer_mc": float(pq),
            "ep_manifesta_qualquer": float(np.sqrt(pq * (1 - pq) / self.n)),
            "p_manifesta_qualquer_exato": combinar_independentes(l.p_manifesta_exato for l in self.loci),
            "p_manifesta_qualquer_q025": qlo,
            "p_manifesta_qualquer_q975": qhi,
            "idade_mediana_primeiro_inicio": float(np.median(idades)) if idades.size else np.nan,
            "tempo_s": self.tempo_s,
            "idade_condicionada": self.idade_condicionada,
        }

    def frequencias_genotipo(self) -> pd.DataFrame:
        """Frequências simuladas de D ∈ {0,1,2} por lócus vs CPT exata, com teste qui-quadrado (aderência)."""
        linhas = []
        for j, l in enumerate(self.loci):
            obs = np.bincount(self.dose[:, j], minlength=3)[:3]
            esp = cpt_segregacao(l.dosagem_mae, l.dosagem_pai) * self.n
            mask = esp > 0
            chi2, p = stats.chisquare(obs[mask], esp[mask]) if mask.sum() > 1 else (0.0, 1.0)
            linhas.append(
                {
                    "variante": l.rotulo,
                    "freq_0_mc": obs[0] / self.n,
                    "freq_1_mc": obs[1] / self.n,
                    "freq_2_mc": obs[2] / self.n,
                    "freq_0_exata": esp[0] / self.n,
                    "freq_1_exata": esp[1] / self.n,
                    "freq_2_exata": esp[2] / self.n,
                    "qui_quadrado": float(chi2),
                    "valor_p": float(p),
                    "n": self.n,
                }
            )
        return pd.DataFrame(linhas)

    def condicionar_idade(self, idade_atual: float) -> "ResultadoSimulacao":
        """Condicionamento por rejeição: mantém as fecundações em que nenhum lócus manifestou até `idade_atual`."""
        manteve = ~(self.manifesta & (self.idade <= idade_atual)).any(axis=1)
        return ResultadoSimulacao(
            self.motor,
            int(manteve.sum()),
            self.seed,
            self.sexo,
            self.loci,
            self.alelo_mae[manteve],
            self.alelo_pai[manteve],
            self.dose[manteve],
            self.portador[manteve],
            self.penetrancia[manteve],
            self.manifesta[manteve],
            self.idade[manteve],
            self.tempo_s,
            idade_condicionada=float(idade_atual),
            n_original=self.n,
        )


def simular_numpy(loci: list[Locus], n: int = 10_000, seed: int = 42) -> ResultadoSimulacao:
    """Amostrador vetorizado com a mesma semântica do DAG em PyMC."""
    t0 = time.perf_counter()
    rng = np.random.default_rng(seed)
    L = len(loci)
    dm = np.array([l.dosagem_mae for l in loci], float) / 2
    dp = np.array([l.dosagem_pai for l in loci], float) / 2
    rec = np.array([l.recessivo for l in loci])
    alelo_mae = rng.random((n, L)) < dm
    alelo_pai = rng.random((n, L)) < dp
    dose = alelo_mae.astype(int) + alelo_pai.astype(int)
    portador = np.where(rec, dose == 2, dose >= 1)
    pen = np.empty((n, L))
    idade = np.full((n, L), np.nan)
    for j, l in enumerate(loci):
        pen[:, j] = l.pen_fixa if l.pen_fixa is not None else rng.beta(l.alpha, l.beta, n)
    manifesta = rng.random((n, L)) < portador * pen
    for j, l in enumerate(loci):
        k = int(manifesta[:, j].sum())
        if k:
            idade[manifesta[:, j], j] = l.dist.amostrar(rng, k)
    return ResultadoSimulacao(
        "numpy",
        n,
        seed,
        None,
        loci,
        alelo_mae,
        alelo_pai,
        dose,
        portador,
        pen,
        manifesta,
        idade,
        tempo_s=time.perf_counter() - t0,
    )


def repetir(
    loci: list[Locus], n: int, repeticoes: int = 30, seed_inicial: int = 1000, motor: str = "numpy"
) -> pd.DataFrame:
    """Execuções sucessivas para a avaliação de estabilidade numérica (TCC 4.5). Uma linha por execução."""
    if motor == "pymc":
        from .rede_bayesiana import simular_pymc as simular
    else:
        simular = simular_numpy
    linhas = []
    for r in range(repeticoes):
        res = simular(loci, n=n, seed=seed_inicial + r)
        comb = res.resumo_combinado()
        linha = {
            "motor": motor,
            "n": n,
            "repeticao": r,
            "seed": seed_inicial + r,
            "tempo_s": res.tempo_s,
            "p_manifesta_qualquer": comb["p_manifesta_qualquer_mc"],
            "idade_mediana_primeiro_inicio": comb["idade_mediana_primeiro_inicio"],
        }
        for j, l in enumerate(res.loci):
            linha[f"p_portador[{l.rotulo}]"] = res.portador[:, j].mean()
            linha[f"p_manifesta[{l.rotulo}]"] = res.manifesta[:, j].mean()
        linhas.append(linha)
    return pd.DataFrame(linhas)
