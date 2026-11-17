"""Núcleo estocástico, parte 1: simulação de Monte Carlo em NumPy (TCC 4.4.B).

Cada sorteio é uma fecundação hipotética: alelos transmitidos por cada genitor, dosagem do descendente,
status de portador segundo a herança, penetrância π sorteada da prior Beta, manifestação e idade de início.
O amostrador NumPy tem a mesma semântica do modelo PyMC (`rede_bayesiana.py`) e serve para as execuções
repetidas de estabilidade (N = 1e3, 1e4, 1e5 × 30 sementes) e como verificação cruzada.

"Risco vitalício" tem um só significado em todo o artefato: probabilidade de manifestar até o horizonte
(`horizonte_anos` do YAML). A fração que manifesta em algum momento, sem limite de idade, F(∞) = P(portador)·E[π],
continua calculada em coluna própria e serve às verificações de coerência.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd
from scipy import stats

from .calibracao import Parametros
from .exato import (
    DistribuicaoInicio,
    DistribuicaoPenetrancia,
    combinar_independentes,
    cpt_segregacao,
    prob_portador,
)


@dataclass
class Locus:
    """Entrada do núcleo estocástico: um lócus de risco com as dosagens parentais e os parâmetros do gene."""

    gene: str
    rotulo: str
    dosagem_mae: int | None  # None quando a dosagem do genitor é inferida por parentes (`inferencia`)
    dosagem_pai: int | None
    heranca: str
    alpha: float
    beta: float
    dist: DistribuicaoInicio  # já deslocada pelo efeito do sexo
    pen_fixa: float | None = None  # análise de sensibilidade: penetrância fixa em vez de Beta
    rs: str | None = None
    horizonte: float = 90.0  # idade-limite do risco vitalício (`horizonte_anos` do YAML)
    prior_pen: DistribuicaoPenetrancia | None = None  # None = Beta(alpha, beta); alternativa: log-normal truncada
    inferencia: object | None = None  # genitor sem exame inferido por parentes (`parentes.InferenciaLocus`)

    @property
    def recessivo(self) -> bool:
        return self.heranca == "recessiva"

    @property
    def prior(self) -> DistribuicaoPenetrancia:
        """Distribuição a priori da penetrância π do gene."""
        return self.prior_pen or DistribuicaoPenetrancia("beta", alpha=self.alpha, beta=self.beta)

    @property
    def p_portador_exato(self) -> float:
        if self.inferencia is not None:
            return self.inferencia.p_portador
        return prob_portador(self.dosagem_mae, self.dosagem_pai, self.heranca)

    @property
    def pen_media(self) -> float:
        """E[π] entre os portadores. Com genitor inferido por parentes, é a média a posteriori que faz
        P(portador) · pen_media = P(portador e manifesta), porque π é compartilhada pela família."""
        if self.inferencia is not None:
            return self.inferencia.pen_media
        return self.pen_fixa if self.pen_fixa is not None else self.prior.media

    @property
    def g_horizonte(self) -> float:
        """G(horizonte): fração dos que manifestam cujo início ocorre até o horizonte."""
        return float(self.dist.cdf(self.horizonte))

    @property
    def p_manifesta_sem_limite(self) -> float:
        """F(∞) = P(portador) · E[π]: fração que manifesta em algum momento, sem limite de idade."""
        return self.p_portador_exato * self.pen_media

    @property
    def p_manifesta_exato(self) -> float:
        """Risco vitalício: probabilidade de manifestar até o horizonte, P(portador) · E[π] · G(horizonte)."""
        return self.p_manifesta_sem_limite * self.g_horizonte

    def quantis_penetrancia(self, q=(0.025, 0.975)) -> tuple[float, float]:
        if self.inferencia is not None:
            return self.inferencia.quantis_penetrancia(q)
        if self.pen_fixa is not None:
            return (self.pen_fixa, self.pen_fixa)
        return tuple(self.prior.ppf(q))

    def quantis_manifesta(self, q=(0.025, 0.975)) -> tuple[float, float]:
        """Quantis do risco vitalício (até o horizonte) pela incerteza da penetrância."""
        if self.inferencia is not None:
            lo, hi = self.inferencia.quantis_manifesta_sem_limite(q)
            return (lo * self.g_horizonte, hi * self.g_horizonte)
        lo, hi = self.quantis_penetrancia(q)
        return (self.p_portador_exato * lo * self.g_horizonte, self.p_portador_exato * hi * self.g_horizonte)

    def q_dado_pi(self, pen):
        """P(portador | π): constante no modelo de dois genitores testados; com genitor inferido por parentes depende
        de π, porque a situação clínica do genitor informa ao mesmo tempo a dosagem dele e a penetrância."""
        if self.inferencia is not None:
            return self.inferencia.q_portador(pen)
        return self.p_portador_exato

    def cpt_descendente(self) -> np.ndarray:
        """P(D = 0, 1, 2) do descendente, para o teste de aderência do genótipo simulado."""
        if self.inferencia is not None:
            return self.inferencia.cpt_descendente()
        return cpt_segregacao(self.dosagem_mae, self.dosagem_pai)


def loci_de_vetor(
    vetor: pd.DataFrame,
    parametros: Parametros,
    sexo: str | None = None,
    penetrancia_fixa: dict[str, float] | None = None,
    distribuicoes: dict[str, DistribuicaoInicio] | None = None,
    horizonte: float | None = None,
    priors: dict[str, DistribuicaoPenetrancia] | None = None,
) -> list[Locus]:
    """Monta os lóci a partir do vetor de dosagens (genotipo.vetor_dosagem) e dos parâmetros calibrados.

    `penetrancia_fixa`, `distribuicoes` e `priors` permitem análises de sensibilidade (ex.: parâmetros do exemplo do
    orientador; penetrância log-normal truncada). `horizonte` é a idade-limite do risco vitalício (padrão:
    `horizonte_anos` do YAML).
    """
    h = float(horizonte if horizonte is not None else parametros.horizonte_anos)
    loci = []
    for _, v in vetor.iterrows():
        if bool(v.get("descartado", False)):  # genótipo não determinado num genitor: lócus fora do cálculo (TCC 4.3)
            continue
        g = parametros.genes[v.gene]
        dist = (distribuicoes or {}).get(v.gene, g.inicio).deslocar(g.delta_sexo.get(sexo, 0.0) if sexo else 0.0)
        prior = (priors or {}).get(v.gene) or (g.penetrancia if g.penetrancia.tipo != "beta" else None)
        loci.append(
            Locus(
                gene=v.gene,
                rotulo=f"{v.gene} {v.variante}",
                dosagem_mae=None if pd.isna(v.dosagem_mae) else int(v.dosagem_mae),
                dosagem_pai=None if pd.isna(v.dosagem_pai) else int(v.dosagem_pai),
                heranca=v.heranca,
                alpha=g.alpha,
                beta=g.beta,
                dist=dist,
                pen_fixa=(penetrancia_fixa or {}).get(v.gene),
                rs=v.rs if isinstance(v.rs, str) else None,
                horizonte=h,
                prior_pen=prior,
            )
        )
    if (vetor.attrs.get("parentes") or {}).get("evidencias"):  # genitor sem exame inferido por parentes
        from .parentes import anexar_inferencias

        loci = anexar_inferencias(loci, vetor, parametros, distribuicoes)
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
    dose_mae: np.ndarray | None = None  # (n, L) int: dosagem sorteada do genitor inferido por parentes (senão None)
    dose_pai: np.ndarray | None = None
    sorteados: int | None = None  # sorteios feitos antes da rejeição pela evidência dos parentes (senão None)

    @property
    def horizonte(self) -> float:
        return float(self.loci[0].horizonte) if self.loci else 90.0

    @property
    def manifesta_h(self) -> np.ndarray:
        """(n, L) bool: manifestou com início até o horizonte. É o evento do risco vitalício."""
        h = np.array([l.horizonte for l in self.loci], float)
        with np.errstate(invalid="ignore"):
            return self.manifesta & (self.idade <= h[None, :])

    @property
    def manifesta_qualquer_h(self) -> np.ndarray:
        return self.manifesta_h.any(axis=1)

    @property
    def manifesta_qualquer(self) -> np.ndarray:
        """Manifestou em algum lócus em algum momento (sem limite de idade)."""
        return self.manifesta.any(axis=1)

    @property
    def idade_qualquer(self) -> np.ndarray:
        with np.errstate(all="ignore"):
            minimo = np.nanmin(np.where(self.manifesta, self.idade, np.nan), axis=1, initial=np.inf)
        return np.where(np.isfinite(minimo), minimo, np.nan)

    def resumo(self) -> pd.DataFrame:
        """Uma linha por lócus: P(portador) e risco vitalício (P de manifestar até o horizonte) exatos e simulados,
        erro padrão de MC, IC 95% de credibilidade (incerteza da penetrância), a fração que manifesta em algum
        momento, sem limite de idade (`p_manifesta_sem_limite`), e a idade de início (mediana e percentis 10/90) entre
        os que manifestam.
        """
        linhas = []
        man_h = self.manifesta_h
        for j, l in enumerate(self.loci):
            pc = self.portador[:, j].mean()
            pm_ = man_h[:, j].mean()
            qlo, qhi = l.quantis_penetrancia()
            mlo, mhi = l.quantis_manifesta()
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
                    "p_manifesta_q025": mlo,
                    "p_manifesta_q975": mhi,
                    "p_manifesta_sem_limite": l.p_manifesta_sem_limite,
                    "idade_mediana_exata": l.dist.mediana,
                    "idade_mediana_mc": float(np.median(idades)) if idades.size else np.nan,
                    "idade_p10_mc": float(np.percentile(idades, 10)) if idades.size else np.nan,
                    "idade_p90_mc": float(np.percentile(idades, 90)) if idades.size else np.nan,
                    "n_manifesta": int(man_h[:, j].sum()),
                    "n": self.n,
                }
            )
        return pd.DataFrame(linhas)

    def risco_por_sorteio(self, t: float | None = None) -> np.ndarray:
        """(n, L): P(manifestar o lócus j até a idade t) em cada sorteio de π, P(C_j | π_ij) · π_ij · G_j(t).
        `t = None` usa o horizonte de cada lócus (risco vitalício)."""
        cols = []
        for j, l in enumerate(self.loci):
            pen = self.penetrancia[:, j]
            g = l.g_horizonte if t is None else float(l.dist.cdf(t))
            cols.append(np.broadcast_to(l.q_dado_pi(pen) * pen * g, pen.shape))
        return np.column_stack(cols) if cols else np.empty((self.n, 0))

    def risco_combinado_por_sorteio(self) -> np.ndarray:
        """Risco vitalício de ≥ 1 lócus em cada sorteio de π: 1 − ∏_j (1 − P(C_j)·π_ij·G_j(horizonte)). É a mesma
        propagação usada por `sobrevivencia.curvas_analiticas` no horizonte, de modo que a banda da Tabela 3 e a da
        Figura 4 coincidem."""
        return 1 - np.prod(1 - self.risco_por_sorteio(), axis=1)

    def resumo_combinado(self) -> dict:
        """Risco combinado (qualquer lócus) sob independência: exato, simulado, banda de 95 % pelo percentil dos sorteios
        de π (não pela combinação dos quantis de cada lócus, que alarga a banda) e idade do primeiro início. O risco
        vitalício vai até o horizonte; `p_manifesta_qualquer_sem_limite` é a fração que manifesta em algum momento."""
        pq = self.manifesta_qualquer_h.mean()
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
            "p_manifesta_qualquer_sem_limite": combinar_independentes(l.p_manifesta_sem_limite for l in self.loci),
            "horizonte": self.horizonte,
            "idade_mediana_primeiro_inicio": float(np.median(idades)) if idades.size else np.nan,
            "tempo_s": self.tempo_s,
            "idade_condicionada": self.idade_condicionada,
        }

    def frequencias_genotipo(self) -> pd.DataFrame:
        """Frequências simuladas de D ∈ {0,1,2} por lócus vs CPT exata, com teste qui-quadrado (aderência)."""
        linhas = []
        for j, l in enumerate(self.loci):
            obs = np.bincount(self.dose[:, j], minlength=3)[:3]
            esp = l.cpt_descendente() * self.n
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
        return replace(
            self,
            n=int(manteve.sum()),
            alelo_mae=self.alelo_mae[manteve],
            alelo_pai=self.alelo_pai[manteve],
            dose=self.dose[manteve],
            portador=self.portador[manteve],
            penetrancia=self.penetrancia[manteve],
            manifesta=self.manifesta[manteve],
            idade=self.idade[manteve],
            idade_condicionada=float(idade_atual),
            n_original=self.n,
            dose_mae=None if self.dose_mae is None else self.dose_mae[manteve],
            dose_pai=None if self.dose_pai is None else self.dose_pai[manteve],
        )


def simular_numpy(loci: list[Locus], n: int = 10_000, seed: int = 42) -> ResultadoSimulacao:
    """Amostrador vetorizado com a mesma semântica do DAG em PyMC."""
    if any(l.inferencia is not None for l in loci):  # genitor sem exame inferido por parentes: amostrador próprio
        from .parentes import simular_numpy_parentes

        return simular_numpy_parentes(loci, n=n, seed=seed)
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
        pen[:, j] = l.pen_fixa if l.pen_fixa is not None else l.prior.amostrar(rng, n)
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
            linha[f"p_manifesta[{l.rotulo}]"] = res.manifesta_h[:, j].mean()
        linhas.append(linha)
    return pd.DataFrame(linhas)
