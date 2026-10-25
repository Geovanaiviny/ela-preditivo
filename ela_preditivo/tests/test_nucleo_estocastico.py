import numpy as np
import pandas as pd
import pytest

from ela_preditivo import cenarios, exato, genotipo, monte_carlo, rede_bayesiana


def _loci(anotados, parametros, numero, sexo=None):
    mae, pai = anotados[numero]
    return monte_carlo.loci_de_vetor(genotipo.vetor_dosagem(mae, pai, parametros), parametros, sexo=sexo)


@pytest.mark.parametrize("numero", [1, 2, 3, 4, 5])
def test_numpy_adere_ao_exato(anotados, parametros, numero):
    loci = _loci(anotados, parametros, numero)
    res = monte_carlo.simular_numpy(loci, n=20_000, seed=1)
    r = res.resumo()
    for _, l in r.iterrows():
        assert abs(l.p_portador_mc - l.p_portador_exato) < 4 * max(l.ep_portador, 1e-3)
        assert abs(l.p_manifesta_mc - l.p_manifesta_exato) < 4 * max(l.ep_manifesta, 1e-3)
        assert abs(l.idade_mediana_mc - l.idade_mediana_exata) < 2.0
    fg = res.frequencias_genotipo()
    assert (fg.valor_p > 0.001).all()
    comb = res.resumo_combinado()
    assert abs(comb["p_manifesta_qualquer_mc"] - comb["p_manifesta_qualquer_exato"]) < 4 * max(comb["ep_manifesta_qualquer"], 1e-3)


def test_recessiva_so_homozigoto_manifesta(anotados, parametros):
    res = monte_carlo.simular_numpy(_loci(anotados, parametros, 4), n=5000, seed=3)
    assert res.loci[0].recessivo
    assert not res.manifesta[res.dose[:, 0] < 2, 0].any()
    assert res.portador[:, 0].mean() == pytest.approx(0.25, abs=0.03)


def test_reprodutibilidade_por_seed(anotados, parametros):
    loci = _loci(anotados, parametros, 3)
    a = monte_carlo.simular_numpy(loci, n=2000, seed=11); b = monte_carlo.simular_numpy(loci, n=2000, seed=11)
    c = monte_carlo.simular_numpy(loci, n=2000, seed=12)
    assert np.array_equal(a.dose, b.dose) and np.allclose(a.idade, b.idade, equal_nan=True)
    assert not np.array_equal(a.dose, c.dose)


def test_sexo_desloca_idade_c9orf72(anotados, parametros):
    m = monte_carlo.simular_numpy(_loci(anotados, parametros, 2, "M"), n=20_000, seed=5).resumo().iloc[0]
    f = monte_carlo.simular_numpy(_loci(anotados, parametros, 2, "F"), n=20_000, seed=5).resumo().iloc[0]
    assert f.idade_mediana_exata - m.idade_mediana_exata == pytest.approx(2.0)
    assert f.idade_mediana_mc - m.idade_mediana_mc == pytest.approx(2.0, abs=1.5)


def test_condicionar_idade(anotados, parametros):
    loci = _loci(anotados, parametros, 1)
    res = monte_carlo.simular_numpy(loci, n=20_000, seed=9)
    cond = res.condicionar_idade(60)
    assert cond.n < res.n and cond.n_original == res.n and cond.idade_condicionada == 60
    assert not (cond.manifesta & (cond.idade <= 60)).any()
    # P(portador | assintomático aos 60) cai, e bate com a fórmula bayesiana
    l = loci[0]
    esperado = exato.prob_portador_condicional(60, l.p_portador_exato, l.pen_media, l.dist)
    assert cond.portador[:, 0].mean() == pytest.approx(esperado, abs=0.03)


def test_penetrancia_fixa_e_sensibilidade(anotados, parametros):
    mae, pai = anotados[1]
    vetor = genotipo.vetor_dosagem(mae, pai, parametros)
    loci = monte_carlo.loci_de_vetor(vetor, parametros, penetrancia_fixa={"SOD1": 0.9})
    res = monte_carlo.simular_numpy(loci, n=20_000, seed=2)
    assert np.all(res.penetrancia == 0.9)
    assert res.manifesta[:, 0].mean() == pytest.approx(0.45, abs=0.02)


def test_repetir_estabilidade(anotados, parametros):
    loci = _loci(anotados, parametros, 3)
    df = monte_carlo.repetir(loci, n=1000, repeticoes=5, seed_inicial=100)
    assert len(df) == 5 and df.seed.tolist() == [100, 101, 102, 103, 104]
    col = [c for c in df.columns if c.startswith("p_portador[")][0]
    assert df[col].std() < 0.05


@pytest.mark.parametrize("numero", [3, 4])
def test_pymc_adere_ao_exato_e_ao_numpy(anotados, parametros, numero):
    loci = _loci(anotados, parametros, numero, sexo="M")
    res = rede_bayesiana.simular_pymc(loci, n=5000, seed=21)
    assert res.motor == "pymc" and res.dose.shape == (5000, len(loci))
    r = res.resumo()
    for _, l in r.iterrows():
        assert abs(l.p_portador_mc - l.p_portador_exato) < 4 * max(l.ep_portador, 1e-3)
        assert abs(l.p_manifesta_mc - l.p_manifesta_exato) < 4 * max(l.ep_manifesta, 1e-3)
        assert abs(l.idade_mediana_mc - l.idade_mediana_exata) < 3.0
    # penetrância sorteada da Beta: média próxima de α/(α+β)
    for j, l in enumerate(loci):
        assert res.penetrancia[:, j].mean() == pytest.approx(l.pen_media, abs=0.02)
    # idade NaN exatamente onde não manifesta
    assert np.isnan(res.idade[~res.manifesta]).all() and not np.isnan(res.idade[res.manifesta]).any()
    # mesma semântica do NumPy
    rn = monte_carlo.simular_numpy(loci, n=5000, seed=21).resumo()
    assert np.allclose(r.p_manifesta_mc, rn.p_manifesta_mc, atol=0.03)


def test_descrever_dag(anotados, parametros):
    d = rede_bayesiana.descrever_dag(_loci(anotados, parametros, 3))
    assert len(d["loci"]) == 2 and ("Portador", "Manifesta") in d["arestas"]
