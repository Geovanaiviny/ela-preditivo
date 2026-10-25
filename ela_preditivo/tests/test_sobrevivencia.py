import numpy as np
import pandas as pd
import pytest

from ela_preditivo import genotipo, monte_carlo, sobrevivencia
from ela_preditivo.exato import DistribuicaoInicio


def _res(anotados, parametros, numero, n=20_000, sexo=None, seed=4):
    mae, pai = anotados[numero]
    loci = monte_carlo.loci_de_vetor(genotipo.vetor_dosagem(mae, pai, parametros), parametros, sexo=sexo)
    return monte_carlo.simular_numpy(loci, n=n, seed=seed)


def test_coorte_sintetica_censura(anotados, parametros):
    res = _res(anotados, parametros, 1)
    c = sobrevivencia.coorte_sintetica(res, horizonte=90)
    assert set(c.unidade) == {res.loci[0].rotulo, sobrevivencia.QUALQUER}
    assert (c.duracao <= 90).all() and (c.loc[~c.evento, "duracao"] == 90).all()
    assert c.evento.mean() == pytest.approx(res.loci[0].p_manifesta_exato, abs=0.02)


def test_km_risco_vitalicio_bate_com_exato(anotados, parametros):
    res = _res(anotados, parametros, 3)
    t = sobrevivencia.tabela_km(res).set_index("unidade")
    for l in res.loci:
        assert t.loc[l.rotulo, "risco_vitalicio_km"] == pytest.approx(l.p_manifesta_exato, abs=0.02)
        assert t.loc[l.rotulo, "mediana_sobrevivencia"] == "não atingida"   # risco vitalício < 50 %
    assert t.loc[sobrevivencia.QUALQUER, "risco_vitalicio_km"] == pytest.approx(res.resumo_combinado()["p_manifesta_qualquer_exato"], abs=0.02)
    assert 40 < t.loc[res.loci[0].rotulo, "idade_90pct_do_risco"] < 85


def test_mistura_cura_recupera_parametros():
    # coorte sintética direta: π = 0,4, Weibull(k = 5, λ = 60), censura aos 90
    rng = np.random.default_rng(0)
    n = 30_000
    manif = rng.random(n) < 0.4
    dur = np.where(manif, DistribuicaoInicio("weibull", k=5.0, lam=60.0).amostrar(rng, n), 90.0)
    ev = manif & (dur <= 90)
    dur = np.minimum(dur, 90)
    f = sobrevivencia.MisturaCuraWeibullFitter().fit(dur, event_observed=ev.astype(int))
    assert f.pi_ == pytest.approx(0.4, rel=0.05)
    assert f.lambda_ == pytest.approx(60.0, rel=0.05)
    assert f.rho_ == pytest.approx(5.0, rel=0.10)


def test_recuperacao_parametros_nos_cenarios(anotados, parametros):
    res = _res(anotados, parametros, 5, n=40_000)
    t = sobrevivencia.recuperacao_parametros(res)
    assert len(t) == 2
    assert (t.erro_rel_pi < 0.08).all() and (t.erro_rel_lambda < 0.05).all() and (t.erro_rel_rho < 0.15).all()


def test_curvas_analiticas_coerentes(anotados, parametros):
    res = _res(anotados, parametros, 3, n=5000)
    c = sobrevivencia.curvas_analiticas(res, t_max=90)
    for l in res.loci:
        u = c[c.unidade == l.rotulo]
        assert np.all(np.diff(u.F) >= -1e-12) and u.F.iloc[0] == 0
        assert u.F.iloc[-1] == pytest.approx(l.p_manifesta_exato, abs=0.01)
        assert (u.F_q025 <= u.F_mediana + 1e-12).all() and (u.F_mediana <= u.F_q975 + 1e-12).all()
        assert (u.h >= 0).all()
    q = c[c.unidade == sobrevivencia.QUALQUER]
    assert q.F.iloc[-1] == pytest.approx(res.resumo_combinado()["p_manifesta_qualquer_exato"], abs=0.01)
    assert (q.S + q.F).round(9).eq(1).all()


def test_tabela_risco_condicional(anotados, parametros):
    res = _res(anotados, parametros, 3, n=5000)
    t = sobrevivencia.tabela_risco_condicional(res, idades_atuais=(0, 40, 70))
    l0 = t[(t.unidade == res.loci[0].rotulo)].set_index("idade_atual")
    # em t = 0 o risco vitalício condicional é o incondicional; cai com a idade
    assert l0.loc[0, "risco_vitalicio"] == pytest.approx(res.loci[0].p_manifesta_exato, abs=1e-6)
    assert l0.loc[70, "risco_vitalicio"] < l0.loc[40, "risco_vitalicio"] < l0.loc[0, "risco_vitalicio"]
    assert l0.loc[0, "p_portador_condicional"] == pytest.approx(0.5)
    assert (t.risco_vitalicio_q025 <= t.risco_vitalicio + 1e-9).all() and (t.risco_vitalicio <= t.risco_vitalicio_q975 + 1e-9).all()
    assert sobrevivencia.QUALQUER in set(t.unidade)


def test_risco_condicional_km_aproxima_analitico(anotados, parametros):
    res = _res(anotados, parametros, 1, n=40_000)
    km = sobrevivencia.risco_condicional_km(res, idade_atual=40).set_index("unidade")
    an = sobrevivencia.tabela_risco_condicional(res, idades_atuais=(40,)).set_index("unidade")
    u = res.loci[0].rotulo
    assert km.loc[u, "risco_20_anos_km"] == pytest.approx(an.loc[u, "risco_20_anos"], abs=0.02)
    assert km.loc[u, "risco_vitalicio_km"] == pytest.approx(an.loc[u, "risco_vitalicio"], abs=0.02)
