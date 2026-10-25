import numpy as np
import pytest

from ela_preditivo import exato


@pytest.mark.parametrize("dm,df", [(0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (2, 1), (2, 2)])
def test_cpt_soma_um(dm, df):
    assert exato.cpt_segregacao(dm, df).sum() == pytest.approx(1.0)


def test_cpt_valores_mendelianos():
    assert exato.cpt_segregacao(1, 0).tolist() == pytest.approx([0.5, 0.5, 0.0])
    assert exato.cpt_segregacao(1, 1).tolist() == pytest.approx([0.25, 0.5, 0.25])
    assert exato.cpt_segregacao(2, 0).tolist() == pytest.approx([0.0, 1.0, 0.0])
    assert exato.cpt_segregacao(2, 2).tolist() == pytest.approx([0.0, 0.0, 1.0])


def test_prob_portador_dominante_e_recessiva():
    assert exato.prob_portador(1, 0, "dominante") == pytest.approx(0.5)
    assert exato.prob_portador(1, 1, "dominante") == pytest.approx(0.75)
    assert exato.prob_portador(1, 1, "recessiva") == pytest.approx(0.25)
    assert exato.prob_portador(1, 0, "recessiva") == pytest.approx(0.0)
    assert exato.prob_portador(0, 0, "dominante") == pytest.approx(0.0)
    assert exato.prob_portador(2, 0, "dominante") == pytest.approx(1.0)


def test_dosagem_invalida():
    with pytest.raises(ValueError):
        exato.cpt_segregacao(3, 0)
    with pytest.raises(ValueError):
        exato.prob_portador(1, 0, "ligada_ao_x")


def test_combinar_independentes():
    assert exato.combinar_independentes([0.5, 0.5]) == pytest.approx(0.75)
    assert exato.combinar_independentes([]) == pytest.approx(0.0)


def test_weibull_mediana_e_media_batem_com_distribuicao():
    d = exato.DistribuicaoInicio("weibull", k=5.0, lam=60.0, delta=-1.0)
    assert d.mediana == pytest.approx(exato.weibull_mediana(5.0, 60.0, -1.0))
    assert d.media == pytest.approx(exato.weibull_media(5.0, 60.0, -1.0))
    assert float(d.cdf(d.mediana)) == pytest.approx(0.5)
    assert float(d.cdf(-5)) == 0.0


def test_cura_mista_e_condicionamento():
    d = exato.DistribuicaoInicio("weibull", k=5.0, lam=60.0)
    q, pen = 0.5, 0.4
    f_inf = exato.f_acumulada(500, q, pen, d)
    assert float(f_inf) == pytest.approx(q * pen, abs=1e-9)
    # risco condicional cresce com t, fica em [0, 1] e é menor que o incondicional no limite
    t = np.array([40, 50, 60, 70, 90])
    rc = exato.risco_condicional(t, 40, q, pen, d)
    assert np.all(np.diff(rc) >= 0) and rc.min() >= 0 and rc.max() <= 1
    assert rc[-1] <= q * pen / (1 - 0) + 1e-9
    # atualização bayesiana: assintomático na idade a reduz P(portador); em t = 0 não muda nada
    assert exato.prob_portador_condicional(0, q, pen, d) == pytest.approx(q)
    assert exato.prob_portador_condicional(80, q, pen, d) < q
    # risco residual com G(a) = 1: tudo que ia manifestar já manifestou
    assert float(exato.risco_condicional(200, 150, q, pen, d)) == pytest.approx(0.0, abs=1e-6)


def test_hazard_positivo():
    d = exato.DistribuicaoInicio("weibull", k=5.0, lam=60.0)
    h = exato.hazard(np.array([30.0, 60.0, 75.0]), 0.5, 0.4, d)
    assert np.all(h >= 0)
