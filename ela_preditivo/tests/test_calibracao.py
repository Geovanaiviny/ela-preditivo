import numpy as np
import pytest

from ela_preditivo import avaliacao, calibracao, cenarios, genotipo, monte_carlo, rede_bayesiana
from ela_preditivo.exato import DistribuicaoInicio, DistribuicaoPenetrancia

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
    with pytest.raises(ValueError):
        calibracao.ajustar_lognormal_truncada(0.5, (0.6, 0.9))


@pytest.mark.parametrize("gene", list(PUBLICADOS))
def test_lognormal_truncada_reproduz_mediana_e_limites(gene):
    ponto, ic = PUBLICADOS[gene]
    r = calibracao.ajustar_lognormal_truncada(ponto, ic)
    # mediana e limites de 2,5 % e 97,5 % da distribuição já truncada reproduzem os publicados
    assert abs(r["mediana"] - ponto) < 0.005 and abs(r["q025"] - ic[0]) < 0.005 and abs(r["q975"] - ic[1]) < 0.005
    assert r["erro_max"] < 0.005
    # ponto de partida: mediana no valor publicado e desvio em escala log tirado do intervalo
    assert r["mu_inicial"] == pytest.approx(np.log(ponto))
    assert r["sigma_inicial"] == pytest.approx((np.log(ic[1]) - np.log(ic[0])) / (2 * 1.959964), rel=1e-6)
    assert abs(r["mu"] - r["mu_inicial"]) < 0.02 and abs(r["sigma"] - r["sigma_inicial"]) < 0.02
    assert 0 <= r["massa_truncada"] < 0.02  # massa acima de 1, retirada pelo truncamento, reportada
    d = DistribuicaoPenetrancia("lognormal_truncada", mu=r["mu"], sigma=r["sigma"])
    assert d.massa_truncada == r["massa_truncada"] and d.mediana == pytest.approx(r["mediana"])
    assert float(d.cdf(d.ppf(0.3))) == pytest.approx(0.3, abs=1e-9) and float(d.cdf(1.0)) == pytest.approx(1.0)
    assert float(d.pdf(1.5)) == 0.0 and float(d.cdf(2.0)) == pytest.approx(1.0)
    x = d.amostrar(np.random.default_rng(0), 200_000)
    assert 0 < x.min() and x.max() <= 1.0 and x.mean() == pytest.approx(d.media, abs=0.002)
    assert np.quantile(x, [0.025, 0.5, 0.975]) == pytest.approx([r["q025"], r["mediana"], r["q975"]], abs=0.004)
    nos, pesos = d.quadratura()
    assert pesos.sum() == pytest.approx(1.0) and float(np.sum(pesos * nos)) == pytest.approx(d.media, abs=1e-5)


def test_beta_quadratura_integra_polinomios():
    d = DistribuicaoPenetrancia("beta", alpha=5.3, beta=4.6)
    nos, pesos = d.quadratura()
    assert float(np.sum(pesos * nos)) == pytest.approx(d.media, abs=1e-12)
    segundo = 5.3 * 6.3 / (9.9 * 10.9)  # E[π²] da Beta
    assert float(np.sum(pesos * nos**2)) == pytest.approx(segundo, abs=1e-12)
    with pytest.raises(ValueError):
        DistribuicaoPenetrancia("gama", a=1.0)


def test_padrao_continua_beta_e_a_lognormal_e_escolha_do_yaml(tmp_path, parametros):
    assert parametros.distribuicao_penetrancia == "beta"
    assert all(g.penetrancia.tipo == "beta" and g.pen_distribuicao == "beta" for g in parametros.genes.values())
    tab = parametros.tabela_calibracao().set_index("gene")
    assert {
        "distribuicao_penetrancia_em_uso",
        "ic95_lognormal",
        "massa_truncada_lognormal",
        "erro_max_lognormal",
    } <= set(tab.columns)
    assert (tab.distribuicao_penetrancia_em_uso == "beta").all() and (tab.erro_max_lognormal < 0.005).all()
    assert tab.loc["SOD1", "massa_truncada_lognormal"] > 0.005 > tab.loc["FUS", "massa_truncada_lognormal"] >= 0
    # o limite superior da Beta fica abaixo do publicado (0,886); o da log-normal truncada o reproduz
    sod1 = parametros.genes["SOD1"]
    assert float(sod1.penetrancia.ppf(0.975)) == pytest.approx(0.744, abs=0.005)
    assert float(sod1.prior_penetrancia("lognormal_truncada").ppf(0.975)) == pytest.approx(0.886, abs=0.005)
    texto = calibracao.CAMINHO_PADRAO.read_text(encoding="utf-8")
    assert texto.count("  distribuicao: beta\n") == 1
    alt = tmp_path / "lognormal.yaml"
    alt.write_text(texto.replace("  distribuicao: beta\n", "  distribuicao: lognormal_truncada\n"), encoding="utf-8")
    p_alt = calibracao.carregar_parametros(alt)
    assert p_alt.distribuicao_penetrancia == "lognormal_truncada"
    assert p_alt.genes["SOD1"].penetrancia.tipo == "lognormal_truncada"
    assert p_alt.genes["SOD1"].pen_media == pytest.approx(p_alt.genes["SOD1"].penetrancia.media) != sod1.pen_media
    assert (p_alt.tabela_calibracao().distribuicao_penetrancia_em_uso == "lognormal_truncada").all()
    ruim = tmp_path / "ruim.yaml"
    ruim.write_text(texto.replace("  distribuicao: beta\n", "  distribuicao: gama\n"), encoding="utf-8")
    with pytest.raises(ValueError, match="calibracao_penetrancia"):
        calibracao.carregar_parametros(ruim)


def test_motores_sorteiam_da_lognormal_truncada_e_tabela_9_traz_o_cenario(anotados, parametros, curada):
    mae, pai = anotados[1]
    vetor = genotipo.vetor_dosagem(
        mae, pai, parametros, laudo_c9orf72=cenarios.cenario_por_numero(1).laudo_c9orf72, tabela=curada
    )
    priors = parametros.priors_penetrancia("lognormal_truncada")
    loci = monte_carlo.loci_de_vetor(vetor, parametros, priors=priors)
    assert loci[0].prior.tipo == "lognormal_truncada" and loci[0].pen_media == pytest.approx(priors["SOD1"].media)
    assert monte_carlo.loci_de_vetor(vetor, parametros)[0].prior.tipo == "beta"  # sem pedir, continua Beta
    rn = monte_carlo.simular_numpy(loci, n=40_000, seed=1)
    rp = rede_bayesiana.simular_pymc(loci, n=6000, seed=1)
    for r, tol in ((rn, 0.004), (rp, 0.012)):
        pen = r.penetrancia[:, 0]
        assert pen.max() <= 1.0 and pen.mean() == pytest.approx(priors["SOD1"].media, abs=tol)
        assert np.quantile(pen, 0.975) == pytest.approx(0.886, abs=0.02)
    res = rn.resumo().iloc[0]
    assert abs(res.p_manifesta_mc - res.p_manifesta_exato) < 4 * res.ep_manifesta
    assert res.p_manifesta_q975 == pytest.approx(0.5 * float(priors["SOD1"].ppf(0.975)) * loci[0].g_horizonte)
    s = avaliacao.sensibilidade(vetor, parametros, "F", n=3000, seed=1)
    nomes = list(s.conjunto_de_parametros.unique())
    assert any("log-normal truncada" in x for x in nomes) and any(x.startswith("literatura") for x in nomes)
    alt = s[s.conjunto_de_parametros.str.contains("log-normal") & s.variante.str.startswith("SOD1")].iloc[0]
    lit = s[s.conjunto_de_parametros.str.startswith("literatura") & s.variante.str.startswith("SOD1")].iloc[0]
    assert alt.penetrancia_media == pytest.approx(priors["SOD1"].media) != lit.penetrancia_media


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
