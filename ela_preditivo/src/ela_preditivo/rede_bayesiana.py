"""Núcleo estocástico, parte 2: Rede Bayesiana em PyMC (TCC 4.4.A).

O grafo acíclico dirigido é declarado explicitamente: Dose materna/paterna → Alelo transmitido → Dose do
descendente → Portador (segundo a herança) → Manifestação (com penetrância π ~ Beta) → Idade de início
(Weibull ou log-normal, deslocada pelo sexo). A simulação de Monte Carlo é a amostragem preditiva a priori
(`pm.sample_prior_predictive`), em que cada sorteio é uma fecundação hipotética.
"""
from __future__ import annotations

import logging
import os
import time

os.environ.setdefault("PYTENSOR_FLAGS", "cxx=")  # máquina sem g++: PyTensor em modo Python (docs/04, D7)

import numpy as np
import pymc as pm
import pytensor.tensor as pt

logging.getLogger("pymc").setLevel(logging.WARNING)   # após o import: pymc/__init__ fixa INFO; silencia "Sampling: [...]"

from .monte_carlo import Locus, ResultadoSimulacao


def construir_modelo(loci: list[Locus]) -> pm.Model:
    rotulos = [l.rotulo for l in loci]
    with pm.Model(coords={"locus": rotulos}) as modelo:
        dose_m = pm.Data("dose_materna", np.array([l.dosagem_mae for l in loci], dtype=float), dims="locus")
        dose_p = pm.Data("dose_paterna", np.array([l.dosagem_pai for l in loci], dtype=float), dims="locus")
        recessivo = pm.Data("recessivo", np.array([l.recessivo for l in loci], dtype=float), dims="locus")
        alelo_m = pm.Bernoulli("alelo_materno", p=dose_m / 2.0, dims="locus")
        alelo_p = pm.Bernoulli("alelo_paterno", p=dose_p / 2.0, dims="locus")
        dose = pm.Deterministic("dose_descendente", alelo_m + alelo_p, dims="locus")
        portador = pm.Deterministic("portador", pt.switch(pt.eq(recessivo, 1.0), pt.eq(dose, 2), pt.ge(dose, 1)), dims="locus")
        pens, idades = [], []
        for i, l in enumerate(loci):
            if l.pen_fixa is not None:
                pens.append(pt.constant(float(l.pen_fixa)))
            else:
                pens.append(pm.Beta(f"penetrancia_{i}", alpha=l.alpha, beta=l.beta))
            if l.dist.tipo == "weibull":
                lat = pm.Weibull(f"idade_latente_{i}", alpha=l.dist.params["k"], beta=l.dist.params["lam"])
            else:
                lat = pm.LogNormal(f"idade_latente_{i}", mu=l.dist.params["mu"], sigma=l.dist.params["sigma"])
            idades.append(lat + l.dist.delta)
        pen = pm.Deterministic("penetrancia", pt.stack(pens), dims="locus")
        manifesta = pm.Bernoulli("manifesta", p=portador * pen, dims="locus")
        pm.Deterministic("idade_inicio", pt.stack(idades), dims="locus")
        pm.Deterministic("manifesta_qualquer", pt.max(manifesta))
    return modelo


def simular_pymc(loci: list[Locus], n: int = 10_000, seed: int = 42) -> ResultadoSimulacao:
    """Monte Carlo sobre a Rede Bayesiana: N sorteios conjuntos do DAG (fecundações hipotéticas)."""
    t0 = time.perf_counter()
    modelo = construir_modelo(loci)
    with modelo:
        idata = pm.sample_prior_predictive(draws=n, random_seed=seed, var_names=[
            "alelo_materno", "alelo_paterno", "dose_descendente", "portador", "penetrancia", "manifesta", "idade_inicio"])
    pr = idata.prior
    v = lambda nome: np.asarray(pr[nome].values[0])  # noqa: E731  (cadeia única)
    manifesta = v("manifesta").astype(bool)
    idade = np.where(manifesta, v("idade_inicio"), np.nan)
    return ResultadoSimulacao("pymc", n, seed, None, loci, v("alelo_materno").astype(bool), v("alelo_paterno").astype(bool),
                              v("dose_descendente").astype(int), v("portador").astype(bool), v("penetrancia").astype(float),
                              manifesta, idade, tempo_s=time.perf_counter() - t0)


def descrever_dag(loci: list[Locus]) -> dict:
    """Nós e arestas do DAG para a Figura 1 e para a documentação."""
    nos = ["Dose materna (0/1/2)", "Dose paterna (0/1/2)", "Alelo materno", "Alelo paterno", "Dose do descendente",
           "Herança (dom./rec.)", "Portador", "Penetrância π ~ Beta(α, β)", "Manifesta", "Sexo", "Idade de início G(t)"]
    arestas = [("Dose materna (0/1/2)", "Alelo materno"), ("Dose paterna (0/1/2)", "Alelo paterno"),
               ("Alelo materno", "Dose do descendente"), ("Alelo paterno", "Dose do descendente"),
               ("Dose do descendente", "Portador"), ("Herança (dom./rec.)", "Portador"),
               ("Portador", "Manifesta"), ("Penetrância π ~ Beta(α, β)", "Manifesta"),
               ("Manifesta", "Idade de início G(t)"), ("Sexo", "Idade de início G(t)")]
    return {"nos": nos, "arestas": arestas, "loci": [l.rotulo for l in loci]}
