import numpy as np
import pytest

from ela_preditivo import calibracao
from ela_preditivo.exato import DistribuicaoInicio

PUBLICADOS = {  # Douglas & Baralle (2024), ponto e IC 95%
    "C9orf72": (0.33, (0.209, 0.532)),
    "SOD1": (0.54, (0.327, 0.886)),
    "TARDBP": (0.38, (0.211, 0.698)),
    "FUS": (0.19, (0.130, 0.284)),
}


@pytest.mark.parametrize("gene", list(PUBLICADOS))
def test_beta_reproduz_ponto_e_ic(gene):
    ponto, ic = PUBLICADOS[gene]
    r = calibracao.ajustar_beta(ponto, ic, peso_ponto=1.0)
    assert r["alpha"] > 0 and r["beta"] > 0
    assert r["erro_ponto"] < 0.01, r  # mediana = ponto publicado
    assert r["q025"] == pytest.approx(ic[0], abs=0.01)  # limite inferior reproduzido
    assert r["erro_ic"] < 0.15, r  # limite superior aproximado (IC publicado é log-simétrico)
    r0 = calibracao.ajustar_beta(ponto, ic, peso_ponto=0.0)
    assert r0["erro_ic"] < 0.005, r0  # com peso 0 a Beta reproduz o IC exatamente


def test_beta_rejeita_ic_inconsistente():
    with pytest.raises(ValueError):
        calibracao.ajustar_beta(0.5, (0.6, 0.9))


def test_weibull_recupera_parametros_conhecidos():
    verdadeiro = DistribuicaoInicio("weibull", k=5.4, lam=62.0)
    t = np.array([35, 45, 58, 70, 80])
    pontos = list(zip(t.tolist(), verdadeiro.cdf(t).tolist()))
    r = calibracao.ajustar_weibull(pontos)
    assert r["k"] == pytest.approx(5.4, rel=0.02)
    assert r["lam"] == pytest.approx(62.0, rel=0.02)
    assert r["rss"] < 1e-6


def test_weibull_murphy_mediana_58():
    r = calibracao.ajustar_weibull([[35, 0.0], [45, 0.10], [58, 0.5], [70, 0.90], [80, 0.98]])
    d = DistribuicaoInicio("weibull", k=r["k"], lam=r["lam"])
    assert d.mediana == pytest.approx(58, abs=1.5)
    assert float(d.cdf(80)) >= 0.95
    assert float(d.cdf(35)) < 0.06
    assert 3 < r["k"] < 12  # curva em S plausível, não degenerada


def test_lognormal_recupera_parametros_conhecidos():
    verdadeiro = DistribuicaoInicio("lognormal", mu=np.log(55.0), sigma=0.25)
    t = np.array([30, 40, 50, 60, 70, 80])
    pontos = list(zip(t.tolist(), verdadeiro.cdf(t).tolist()))
    r = calibracao.ajustar_lognormal(pontos)
    assert r["mu"] == pytest.approx(np.log(55.0), abs=0.02)
    assert r["sigma"] == pytest.approx(0.25, abs=0.02)


def test_plato_normaliza():
    r = calibracao.ajustar_weibull([[40, 0.1], [58, 0.165], [80, 0.33]], plato=0.33)
    assert r["pontos_g"][-1] == pytest.approx(1.0)


def test_carregar_parametros_yaml_padrao():
    p = calibracao.carregar_parametros()
    assert set(p.genes) == {"SOD1", "C9orf72", "TARDBP", "FUS"}
    c9 = p.genes["C9orf72"]
    assert c9.heranca == "dominante" and c9.tipo_variante == "repeticao"
    assert c9.delta_sexo == {"M": -1.0, "F": 1.0}
    assert c9.distribuicao_sexo("M").mediana == pytest.approx(c9.inicio.mediana - 1.0)
    assert c9.distribuicao_sexo("F").mediana == pytest.approx(c9.inicio.mediana + 1.0)
    # estado da calibração de G(t): SOD1 pelas estatísticas de Berdyński (2022) e FUS pelos quartis publicados de
    # Grassano (2022) já estão fechados; C9orf72 (dois pontos lidos da figura de Murphy) e TARDBP (mediana e IQR a
    # conferir no artigo) seguem marcados para confirmação
    sod1, fus = p.genes["SOD1"], p.genes["FUS"]
    assert sod1.inicio_estatisticas == {"media": 50.2, "dp": 10.6} and sod1.inicio_confirmar is False
    assert sod1.inicio.mediana == pytest.approx(50.9, abs=0.2)  # mediana publicada: 51,0
    assert fus.inicio_confirmar is False and fus.inicio.mediana == pytest.approx(48.0, abs=1.5)
    assert p.genes["TARDBP"].inicio_estatisticas == {"mediana": 58.30, "iqr": 16.23}
    assert p.genes["TARDBP"].inicio_confirmar is True and c9.inicio_confirmar is True
    tab = p.tabela_calibracao()
    assert len(tab) == 4 and "valor_provisorio" in tab.columns
    assert p.limiar_repeticoes["patogenico"] == 30
