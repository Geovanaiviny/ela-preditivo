"""Genótipo de parentes para o genitor sem exame: inferência exata com penetrância compartilhada, evidência de tio e
de filho testado, Monte Carlo (NumPy e PyMC) contra o exato, regras do C9orf72, pipeline, relatório e linha de comando.
"""

import json

import numpy as np
import pandas as pd
import pytest

from ela_preditivo import avaliacao, cenarios, cli, comparacao, genotipo, monte_carlo, parentes, pipeline, sobrevivencia
from ela_preditivo.parentes import EvidenciaLado, EvidenciaLocus, Familia, InferenciaLocus, LadoFamilia


def _inferencia(parametros, gene="SOD1", heranca="dominante", mae=None, pai=None, filhos=(), **kw):
    g = parametros.genes[gene]
    ev = EvidenciaLocus(
        heranca, mae or EvidenciaLado("mae", observado=0), pai or EvidenciaLado("pai"), filhos
    ).resolver()
    dists = {n: g.distribuicao_sexo(parentes.SEXO_DO_LADO[n]) for n in parentes.LADOS}
    return ev, InferenciaLocus(ev, kw.get("prior", g.penetrancia), kw.get("pen_fixa"), dists)


# ---------------------------------------------------------------------------
# Valores esperados: avó paterna heterozigota para SOD1 p.Ala5Val, avô suposto não portador, mãe negativa
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "situacao, idade, p_portador, risco",
    [
        ("desconhecido", None, 0.2500, 0.1347),
        ("vivo_assintomatico", 40, 0.2380, 0.1277),
        ("vivo_assintomatico", 50, 0.2139, 0.1137),
        ("vivo_assintomatico", 60, 0.1792, 0.0935),
        ("vivo_assintomatico", 70, 0.1602, 0.0824),
        ("falecido_sem_ela", 60, 0.1792, 0.0935),  # mesma verossimilhança, na idade do falecimento
        ("afetado", 60, 0.2500, 0.1347),  # afetado não condiciona
    ],
)
def test_avo_portadora_com_penetrancia_compartilhada(parametros, situacao, idade, p_portador, risco):
    pai = EvidenciaLado("pai", avos=(None, 1), situacao=situacao, idade=idade)
    ev, inf = _inferencia(parametros, pai=pai)
    assert ev.marginal("pai") == pytest.approx([0.5, 0.5, 0.0])  # antes da situação clínica
    assert inf.p_portador == pytest.approx(p_portador, abs=5e-5)
    assert inf.p_manifesta_sem_limite == pytest.approx(risco, abs=5e-5)
    # com o horizonte de 90 anos a diferença é desprezível para o SOD1
    g90 = float(parametros.genes["SOD1"].distribuicao_sexo(None).cdf(90))
    assert inf.p_manifesta_sem_limite * g90 == pytest.approx(risco, abs=1e-4)
    assert inf.p_portador * inf.pen_media == pytest.approx(inf.p_manifesta_sem_limite)


def test_penetrancia_separada_por_pessoa_daria_resultado_errado(parametros):
    pai = EvidenciaLado("pai", avos=(None, 1), situacao="vivo_assintomatico", idade=60)
    _, inf = _inferencia(parametros, pai=pai)
    separado = inf.p_portador * parametros.genes["SOD1"].pen_media  # E[π] para cada pessoa em separado
    assert separado == pytest.approx(0.0966, abs=5e-5) and inf.p_manifesta_sem_limite == pytest.approx(0.0935, abs=5e-5)
    # o genitor sem sintomas torna menos prováveis a variante nele e os valores altos de π
    assert inf.pen_media_posterior < parametros.genes["SOD1"].pen_media and inf.pen_media < inf.pen_media_posterior
    assert inf.dosagem_genitor("pai")[1] == pytest.approx(0.3585, abs=5e-4)
    assert inf.dosagem_genitor("pai", condicionada=False) == pytest.approx([0.5, 0.5, 0.0])
    # com penetrância fixa não há o que aprender sobre π: produto simples
    _, fixa = _inferencia(parametros, pai=pai, pen_fixa=0.5)
    assert fixa.pen_media == pytest.approx(0.5) and fixa.quantis_penetrancia() == (0.5, 0.5)
    # P(portador | π) decresce com π: quanto maior a penetrância, menos provável o genitor assintomático portar
    q = inf.q_portador(np.array([0.2, 0.5, 0.8]))
    assert q[0] > q[1] > q[2] and inf.q_portador(0.0) == pytest.approx(0.25)
    lo, hi = inf.quantis_manifesta_sem_limite()
    assert lo < inf.p_manifesta_sem_limite < hi and inf.cpt_descendente().sum() == pytest.approx(1.0)
    assert inf.cpt_descendente()[1] == pytest.approx(inf.p_portador)


def test_log_normal_truncada_entra_na_integracao(parametros):
    pai = EvidenciaLado("pai", avos=(None, 1), situacao="vivo_assintomatico", idade=60)
    prior = parametros.genes["SOD1"].prior_penetrancia("lognormal_truncada")
    _, inf = _inferencia(parametros, pai=pai, prior=prior)
    _, beta = _inferencia(parametros, pai=pai)
    assert inf.p_manifesta_sem_limite != pytest.approx(beta.p_manifesta_sem_limite, abs=1e-4)
    # conferência por Monte Carlo direto na log-normal
    pi = prior.amostrar(np.random.default_rng(0), 400_000)
    g60 = float(parametros.genes["SOD1"].distribuicao_sexo("M").cdf(60))
    z, nc = 0.5 + 0.5 * (1 - pi * g60), 0.5 * (1 - pi * g60) * 0.5
    assert inf.p_portador == pytest.approx(nc.mean() / z.mean(), abs=2e-4)
    assert inf.p_manifesta_sem_limite == pytest.approx((pi * nc).mean() / z.mean(), abs=3e-4)


# ---------------------------------------------------------------------------
# Tio, filho já testado, Hardy-Weinberg e evidência incompatível
# ---------------------------------------------------------------------------
def test_tio_portador_com_avos_sem_exame(parametros):
    # sem frequência na base: um avô heterozigoto e o outro não portador ⇒ P(pai portador) = 0,5 antes da idade
    ev, _ = _inferencia(parametros, pai=EvidenciaLado("pai", irmaos=(1,)))
    assert ev.marginal("pai")[1:].sum() == pytest.approx(0.5) and ev.exige_variante["pai"] is True
    cond = ev.condicional_avos["pai"]  # P(a1, a2 | d_G): (1, 0) ou (0, 1), meio a meio
    assert cond[1, 1, 0] == pytest.approx(0.5) and cond[1, 0, 1] == pytest.approx(0.5)
    # com frequência, a inferência bayesiana completa (prior de Hardy-Weinberg) fica muito perto desse limite
    hw = EvidenciaLado("pai", irmaos=(1,), modo_prior="hardy_weinberg", freq=1e-4)
    ev_hw, _ = _inferencia(parametros, pai=hw)
    p = ev_hw.marginal("pai")[1:].sum()
    assert 0.5 < p < 0.5002
    # frequência alta: mais chance de os dois avós portarem
    ev_alta, _ = _inferencia(parametros, pai=EvidenciaLado("pai", irmaos=(1,), modo_prior="hardy_weinberg", freq=0.1))
    assert ev_alta.marginal("pai")[1:].sum() > p
    # tio sem a variante e nada que a exija: avós supostos não portadores
    ev0, _ = _inferencia(parametros, mae=EvidenciaLado("mae", observado=1), pai=EvidenciaLado("pai", irmaos=(0,)))
    assert ev0.marginal("pai") == pytest.approx([1.0, 0.0, 0.0]) and ev0.exige_variante["pai"] is False
    # tio homozigoto: os dois avós heterozigotos na configuração mínima
    ev2, _ = _inferencia(parametros, pai=EvidenciaLado("pai", irmaos=(2,)))
    assert ev2.marginal("pai") == pytest.approx([0.25, 0.5, 0.25])


def test_filho_ja_testado_e_evidencia_sobre_o_genitor(parametros):
    # filho positivo e outro genitor negativo ⇒ G portador com probabilidade 1
    ev, inf = _inferencia(parametros, pai=EvidenciaLado("pai"), filhos=(1,))
    assert ev.marginal("pai")[1:].sum() == pytest.approx(1.0) and inf.p_portador == pytest.approx(0.5)
    # avó portadora, filho negativo e outro genitor negativo ⇒ P(G portador) = 1/3, sem idade
    ev, inf = _inferencia(parametros, pai=EvidenciaLado("pai", avos=(None, 1)), filhos=(0,))
    assert ev.marginal("pai")[1] == pytest.approx(1 / 3) and inf.p_portador == pytest.approx(1 / 6)
    # dois filhos negativos reduzem mais: 1/5
    ev, _ = _inferencia(parametros, pai=EvidenciaLado("pai", avos=(None, 1)), filhos=(0, 0))
    assert ev.marginal("pai")[1] == pytest.approx(1 / 5)
    # com os dois genitores testados o filho não acrescenta nada
    ev, _ = _inferencia(parametros, pai=EvidenciaLado("pai", observado=1), filhos=(0,))
    assert ev.lados_inferidos == [] and ev.conjunta[0, 1] == pytest.approx(1.0)
    # incompatível com a segregação: avós negativos, mãe negativa e filho positivo
    ev = EvidenciaLocus(
        "dominante", EvidenciaLado("mae", observado=0), EvidenciaLado("pai", avos=(0, 0)), (1,)
    ).resolver()
    assert ev.compativel is False and ev.conjunta is None


def test_heranca_recessiva_e_dois_genitores_inferidos(parametros):
    # recessiva: mãe heterozigota; pai sem exame com a mãe dele heterozigota ⇒ P(pai het) = 0,5 e P(filho homozigoto) = 1/8
    pai = EvidenciaLado("pai", avos=(None, 1), situacao="vivo_assintomatico", idade=70)
    ev, inf = _inferencia(parametros, heranca="recessiva", mae=EvidenciaLado("mae", observado=1), pai=pai)
    assert inf.p_portador == pytest.approx(0.125)  # heterozigoto não manifesta: a idade do pai não informa nada
    assert inf.dosagem_genitor("pai") == pytest.approx([0.5, 0.5, 0.0])
    # os dois genitores sem exame, cada um com um dos pais heterozigoto
    mae = EvidenciaLado("mae", avos=(1, None), situacao="vivo_assintomatico", idade=60)
    pai = EvidenciaLado("pai", avos=(None, 1), situacao="vivo_assintomatico", idade=60)
    ev, inf = _inferencia(parametros, mae=mae, pai=pai)
    assert ev.lados_inferidos == ["mae", "pai"] and ev.conjunta[1, 1] == pytest.approx(0.25)
    sem = _inferencia(parametros, mae=EvidenciaLado("mae", avos=(1, None)), pai=EvidenciaLado("pai", avos=(None, 1)))[1]
    assert sem.p_portador == pytest.approx(1 - 0.75 * 0.75) and inf.p_portador < sem.p_portador


def test_validacao_da_entrada():
    with pytest.raises(ValueError, match="exige a idade"):
        LadoFamilia(situacao="vivo_assintomatico")
    with pytest.raises(ValueError, match="situação clínica"):
        LadoFamilia(situacao="doente")
    with pytest.raises(ValueError, match="prior dos avós"):
        LadoFamilia(prior_avos="uniforme")
    assert LadoFamilia(situacao="desconhecida").situacao == "desconhecido"
    assert Familia.de(None) is None and Familia.de({}) is None and Familia.de({"pai": {}}) is None
    f = Familia.de({"pai": {"situacao": "afetado", "mae": "avo.vcf", "irmaos": {"vcf": "tio.vcf"}}, "filhos": "f.vcf"})
    assert f.pai.mae.vcf == "avo.vcf" and len(f.pai.irmaos) == 1 and len(f.filhos_testados) == 1
    assert f.tem_parente_com_vcf("pai") and f.tem_parente_com_vcf("mae")  # o filho testado vale para os dois lados
    assert not f.tem_parente_com_laudo("pai")


# ---------------------------------------------------------------------------
# Monte Carlo (NumPy e PyMC) contra o exato
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def caso_parentes(tmp_path_factory, parametros, curada):
    """Cenário de parentes 1: pai sem exame, falecido sem ELA aos 60; avó paterna heterozigota; mãe negativa."""
    d = tmp_path_factory.mktemp("parentes")
    caso = cenarios.gerar_cenarios_parentes(d)[0]
    regioes = pipeline.ingestao.carregar_regioes()
    mae = pipeline.anotacao.anotar(
        pipeline.ingestao.ler_vcf(caso["vcf_mae"], regioes, parametros.filtro_qualidade), curada
    )
    vazio = cenarios.escrever_vcf_sem_variantes(d / "pai_sem_exame.vcf", "PAI_SEM_EXAME")
    pai = pipeline.anotacao.anotar(pipeline.ingestao.ler_vcf(vazio, regioes, parametros.filtro_qualidade), curada)
    familia = Familia.de(caso["parentes"])
    pessoas = parentes.ler_familia(familia, parametros, curada, regioes)
    vetor = parentes.vetor_familia(
        mae, pai, parametros, caso["laudo_c9orf72"], curada, familia, pessoas, {"mae": True, "pai": False}
    )
    return {"caso": caso, "vetor": vetor, "dir": d, "mae": mae, "pai": pai, "familia": familia, "pessoas": pessoas}


def test_vetor_da_familia_e_locus_inferido(caso_parentes, parametros):
    vetor = caso_parentes["vetor"]
    assert len(vetor) == 1 and vetor.gene.tolist() == ["SOD1"]  # C9orf72: laudos normais, sem lócus
    l = vetor.iloc[0]
    assert l.dosagem_mae == 0 and pd.isna(l.dosagem_pai) and l.genitor_inferido == "pai" and not l.descartado
    assert l.p_dosagem_pai == "0: 0.5000; 1: 0.5000; 2: 0.0000" and "inferida por parentes" in l.observacao
    assert l.p_portador_exato == pytest.approx(0.1792, abs=5e-5)
    loci = monte_carlo.loci_de_vetor(vetor, parametros, sexo="F")
    assert loci[0].inferencia is not None and loci[0].dosagem_pai is None and loci[0].dosagem_mae == 0
    assert loci[0].p_portador_exato == pytest.approx(0.1792, abs=5e-5)
    assert loci[0].p_manifesta_exato == pytest.approx(0.0935, abs=1e-4)
    # cenário de sensibilidade troca a distribuição de π: a inferência é refeita com ela
    alt = monte_carlo.loci_de_vetor(
        vetor, parametros, sexo="F", priors=parametros.priors_penetrancia("lognormal_truncada")
    )
    assert alt[0].inferencia.prior.tipo == "lognormal_truncada"
    assert alt[0].p_manifesta_exato != pytest.approx(loci[0].p_manifesta_exato, abs=1e-4)
    fixa = monte_carlo.loci_de_vetor(vetor, parametros, sexo="F", penetrancia_fixa={"SOD1": 0.9})
    assert fixa[0].inferencia.pen_fixa == 0.9 and fixa[0].pen_media == pytest.approx(0.9)


def test_numpy_e_pymc_aderem_ao_exato_com_genitor_inferido(caso_parentes, parametros):
    loci = monte_carlo.loci_de_vetor(caso_parentes["vetor"], parametros, sexo="F")
    exato_p, exato_m = loci[0].p_portador_exato, loci[0].p_manifesta_exato
    rn = monte_carlo.simular_numpy(loci, n=80_000, seed=7)
    rp = pipeline.simular_pymc(loci, n=5000, seed=7)
    for r in (rn, rp):
        assert r.n == len(r.dose) and r.sorteados > r.n and r.dose_pai is not None  # rejeição pela situação do pai
        s = r.resumo().iloc[0]
        assert abs(s.p_portador_mc - exato_p) < 4 * s.ep_portador
        assert abs(s.p_manifesta_mc - exato_m) < 4 * s.ep_manifesta
        assert (r.dose_mae == 0).all() and set(np.unique(r.dose_pai)) <= {0, 1}
        assert (r.frequencias_genotipo().valor_p > 0.001).all()
    # entre os sorteios aceitos, a dosagem do pai e a penetrância seguem o posterior
    inf = loci[0].inferencia
    assert rn.dose_pai[:, 0].mean() == pytest.approx(inf.dosagem_genitor("pai")[1], abs=0.01)
    assert rn.penetrancia[:, 0].mean() == pytest.approx(inf.pen_media_posterior, abs=0.004)
    assert rn.penetrancia[rn.portador[:, 0], 0].mean() == pytest.approx(inf.pen_media, abs=0.01)
    assert rn.sorteados / rn.n == pytest.approx(1 / inf.verossimilhanca, rel=0.05)
    # mesma semente, mesmo resultado
    rn2 = monte_carlo.simular_numpy(loci, n=80_000, seed=7)
    assert np.array_equal(rn.dose, rn2.dose) and np.allclose(rn.idade, rn2.idade, equal_nan=True)
    # atendido assintomático na idade atual: rejeição no mesmo sorteio contra a conta exata
    ind = sobrevivencia.indicadores_condicionados(rn, 45, 90.0)
    c = rn.condicionar_idade(45)
    ep = np.sqrt(0.25 / c.n)
    assert abs(c.portador[:, 0].mean() - ind["p_portador"]) < 4 * ep
    assert abs(c.manifesta_qualquer_h.mean() - ind["risco_residual"]["valor"]) < 4 * ep
    assert ind["p_portador"] < exato_p and c.dose_pai is not None and len(c.dose_pai) == c.n
    # bandas e curvas usam P(portador | π) de cada sorteio
    curvas = sobrevivencia.curvas_analiticas(monte_carlo.simular_numpy(loci, n=4000, seed=1), 90.0)
    u = curvas[curvas.unidade == loci[0].rotulo]
    assert u.F.iloc[-1] == pytest.approx(exato_m, abs=1e-9) and u.F_q025.iloc[-1] < exato_m < u.F_q975.iloc[-1]


def test_demais_analises_funcionam_com_genitor_inferido(caso_parentes, parametros):
    vetor = caso_parentes["vetor"]
    s = avaliacao.sensibilidade(vetor, parametros, "F", n=3000, seed=1)
    assert s.conjunto_de_parametros.nunique() >= 3 and s.p_manifesta_exato.notna().all()
    res = monte_carlo.simular_numpy(monte_carlo.loci_de_vetor(vetor, parametros, sexo="F"), n=6000, seed=3)
    res.sexo = "F"
    cox = comparacao.comparar(res, parametros, 90.0)
    assert len(cox["tabela"]) == 1 and "cox" in cox["tabela"].columns
    co = avaliacao.coerencia(res, 90.0)
    assert co.risco_vitalicio_km.iloc[0] == pytest.approx(co.risco_vitalicio_exato.iloc[0], abs=0.02)


# ---------------------------------------------------------------------------
# C9orf72: o laudo é a única fonte, também para os parentes
# ---------------------------------------------------------------------------
def test_c9orf72_com_parentes_segue_o_laudo(caso_parentes, parametros, curada):
    mae, pai, d = caso_parentes["mae"], caso_parentes["pai"], caso_parentes["dir"]
    avo_vcf = caso_parentes["caso"]["parentes"]["pai"]["mae"]["vcf"]

    def vetor(laudo, lado_pai):
        fam = Familia.de({"pai": lado_pai})
        pessoas = parentes.ler_familia(fam, parametros, curada)
        return parentes.vetor_familia(mae, pai, parametros, laudo, curada, fam, pessoas, {"mae": True, "pai": False})

    normal = cenarios.LAUDO_NORMAL
    # avó com expansão (45 repetições) no laudo, pai sem laudo: o C9orf72 do pai é inferido
    v = vetor(
        {"mae": normal}, {"situacao": "vivo_assintomatico", "idade": 58, "mae": {"vcf": avo_vcf, "laudo_c9orf72": 45}}
    )
    c9 = v[v.gene == "C9orf72"].iloc[0]
    assert not c9.descartado and c9.genitor_inferido == "pai" and c9.dosagem_mae == 0 and pd.isna(c9.dosagem_pai)
    assert 0 < c9.p_portador_exato < 0.25  # 0,25 sem a idade; menor porque o pai chegou aos 58 sem sintomas
    assert set(v.gene) == {"SOD1", "C9orf72"}
    # nenhum laudo entre os parentes e nenhum do pai: o lócus continua indeterminado
    with pytest.warns(UserWarning, match="não informado"):
        v = vetor({"mae": normal}, {"situacao": "desconhecido", "mae": {"vcf": avo_vcf}})
    c9 = v[v.gene == "C9orf72"].iloc[0]
    assert c9.descartado and "indeterminado" in c9.observacao and not v[v.gene == "SOD1"].iloc[0].descartado
    # pai com laudo próprio: observado para o C9orf72, inferido só para as variantes do VCF
    v = vetor(
        {"mae": normal, "pai": 45}, {"situacao": "desconhecido", "mae": {"vcf": avo_vcf, "laudo_c9orf72": normal}}
    )
    c9 = v[v.gene == "C9orf72"].iloc[0]
    assert c9.dosagem_pai == 1 and c9.genitor_inferido == "" and c9.p_portador_exato == pytest.approx(0.5)
    loci = monte_carlo.loci_de_vetor(v, parametros, sexo="M")
    por_gene = {l.gene: l for l in loci}
    assert por_gene["C9orf72"].inferencia is None and por_gene["SOD1"].inferencia is not None
    # tio com expansão e avós sem laudo: configuração mínima, P(pai com expansão) = 0,5
    tio = cenarios.escrever_vcf(d / "tio.vcf", "TIO", [cenarios.SOD1_A5V.com_dosagem(0)], np.random.default_rng(3))
    v = vetor({"mae": normal}, {"situacao": "desconhecido", "irmaos": [{"vcf": tio, "laudo_c9orf72": 45}]})
    c9 = v[v.gene == "C9orf72"].iloc[0]
    assert c9.p_portador_exato == pytest.approx(0.25) and c9.p_dosagem_pai.startswith("0: 0.5000; 1: 0.5000")
    assert any("configuração mínima" in s for s in v.attrs["parentes"]["suposicoes"])
    assert any("suposta herdada" in s for s in v.attrs["parentes"]["suposicoes"])


def test_genotipo_indeterminado_em_parente_descarta_o_locus(caso_parentes, parametros, curada):
    d = caso_parentes["dir"]
    texto = (
        open(caso_parentes["caso"]["parentes"]["pai"]["mae"]["vcf"], encoding="utf-8")
        .read()
        .replace("\t0/1:", "\t./.:")
    )
    indet = d / "avo_indeterminada.vcf"
    indet.write_text(texto, encoding="utf-8")
    fam = Familia.de(
        {"pai": {"situacao": "desconhecido", "mae": {"vcf": indet, "laudo_c9orf72": cenarios.LAUDO_NORMAL}}}
    )
    pessoas = parentes.ler_familia(fam, parametros, curada)
    with pytest.warns(UserWarning):
        v = parentes.vetor_familia(
            caso_parentes["mae"],
            caso_parentes["pai"],
            parametros,
            caso_parentes["caso"]["laudo_c9orf72"],
            curada,
            fam,
            pessoas,
            {"mae": True, "pai": False},
        )
    sod1 = v[v.gene == "SOD1"].iloc[0]
    assert sod1.descartado and "avó paterna" in sod1.observacao and "sem atribuir dosagem 0" in sod1.observacao
    assert monte_carlo.loci_de_vetor(v, parametros) == []


# ---------------------------------------------------------------------------
# Pipeline, relatório, metadados e linha de comando
# ---------------------------------------------------------------------------
def test_pipeline_com_parentes_grava_secao_tabela_1d_e_metadados(caso_parentes, tmp_path):
    caso = caso_parentes["caso"]
    r = pipeline.executar(
        caso["vcf_mae"],
        None,
        tmp_path / "p1",
        sexo="F",
        idade_atual=35,
        n=1500,
        seed=4,
        motor="numpy",
        laudo_c9orf72=caso["laudo_c9orf72"],
        parentes=caso["parentes"],
        base_clinvar=False,
        figuras=False,
    )
    assert r["resumo"].p_portador_exato.iloc[0] == pytest.approx(0.1792, abs=5e-5)
    assert r["resumo"].p_manifesta_exato.iloc[0] == pytest.approx(0.0935, abs=1e-4)
    assert r["condicionado"]["p_portador"] < 0.1792 and r["limite_inferior"] is False
    nomes = {t["nome"] for t in r["tabelas"]}
    assert "tabela_01d_genitor_inferido" in nomes
    t1d = pd.read_csv(tmp_path / "p1" / "tabelas" / "tabela_01d_genitor_inferido.csv").iloc[0]
    assert t1d.genitor_inferido == "pai" and "avó paterna: 1" in t1d.parentes_e_dosagens
    assert t1d.p_genitor_portador_genotipos == pytest.approx(0.5)
    assert t1d.p_genitor_portador_condicionada == pytest.approx(0.3585, abs=5e-4)
    assert t1d.penetrancia_media_a_posteriori < t1d.penetrancia_media_a_priori
    t1 = pd.read_csv(tmp_path / "p1" / "tabelas" / "tabela_01_variantes_anotadas.csv")
    assert "avó paterna" in set(t1.amostra)
    texto = (tmp_path / "p1" / "relatorio.md").read_text(encoding="utf-8")
    assert "## Genitor inferido por parentes" in texto and "falecido sem ELA aos 60 anos" in texto
    assert "sem exame (genótipo inferido por parentes)" in texto and "suposto(s) não portador(es)" in texto
    assert "dosagens mãe/pai 0/inferida" in texto and "vale para toda a família" in texto
    meta = json.loads((tmp_path / "p1" / "metadados.json").read_text(encoding="utf-8"))
    assert meta["vcf_pai"] is None and meta["parentes"]["penetrancia_compartilhada"] is True
    assert meta["parentes"]["genitores"]["pai"] == {
        "situacao": "falecido_sem_ela",
        "idade": 60.0,
        "prior_avos": "nao_portador",
        "limite_inferior": False,
    }
    assert meta["parentes"]["pessoas"][0]["parente"] == "avó paterna" and meta["parentes"]["suposicoes"]
    assert meta["sorteios_rejeitados"] > 0 and not list((tmp_path / "p1").glob("_*sem_exame.vcf"))
    # genitor afetado: sem condicionamento, resultado rotulado como limite inferior
    afetado = {"pai": {**caso["parentes"]["pai"], "situacao": "afetado", "idade": None}}
    r2 = pipeline.executar(
        caso["vcf_mae"],
        None,
        tmp_path / "p1b",
        sexo="F",
        n=800,
        motor="numpy",
        laudo_c9orf72=caso["laudo_c9orf72"],
        parentes=afetado,
        base_clinvar=False,
        figuras=False,
    )
    assert r2["limite_inferior"] is True and r2["resumo"].p_portador_exato.iloc[0] == pytest.approx(0.25)
    assert "limite inferior: o fenótipo do genitor não é modelado" in (tmp_path / "p1b" / "relatorio.md").read_text(
        encoding="utf-8"
    )


def test_sem_parentes_o_resultado_e_identico(dir_cenarios, tmp_path):
    comum = dict(
        sexo="F",
        idade_atual=40,
        n=1000,
        seed=9,
        motor="numpy",
        laudo_c9orf72={"mae": 45, "pai": cenarios.LAUDO_NORMAL},
        base_clinvar=False,
        figuras=False,
    )
    mae, pai = dir_cenarios / "cenario_3_mae.vcf", dir_cenarios / "cenario_3_pai.vcf"
    a = pipeline.executar(mae, pai, tmp_path / "a", **comum)
    b = pipeline.executar(mae, pai, tmp_path / "b", parentes={}, **comum)
    c = pipeline.executar(mae, pai, tmp_path / "c", parentes={"pai": {"situacao": "desconhecido"}}, **comum)
    for r in (b, c):
        assert r["parentes"] is None and all(l.inferencia is None for l in r["loci"])
        assert np.array_equal(a["res"].dose, r["res"].dose) and np.array_equal(
            a["res"].penetrancia, r["res"].penetrancia
        )
        pd.testing.assert_frame_equal(a["vetor"], r["vetor"])
    for nome in ("tabela_01b_vetor_dosagem", "tabela_03_risco_vitalicio", "tabela_04_risco_condicional"):
        assert (tmp_path / "a" / "tabelas" / f"{nome}.csv").read_bytes() == (
            tmp_path / "b" / "tabelas" / f"{nome}.csv"
        ).read_bytes()
    assert "Genitor inferido" not in (tmp_path / "b" / "relatorio.md").read_text(encoding="utf-8")
    # sem VCF e sem parente com VCF: falha com o motivo
    with pytest.raises(ValueError, match="VCF do pai não informado"):
        pipeline.executar(mae, None, tmp_path / "d", **comum)
    with pytest.raises(ValueError, match="VCF do pai não informado"):
        pipeline.executar(mae, None, tmp_path / "e", parentes={"pai": {"situacao": "desconhecido"}}, **comum)


def test_filho_testado_pelo_pipeline(tmp_path):
    caso = cenarios.gerar_cenarios_parentes(tmp_path / "vcfs")[1]
    r = pipeline.executar(
        caso["vcf_mae"],
        None,
        tmp_path / "p2",
        sexo="M",
        n=800,
        motor="numpy",
        laudo_c9orf72=caso["laudo_c9orf72"],
        parentes=caso["parentes"],
        base_clinvar=False,
        figuras=False,
    )
    t1d = pd.read_csv(tmp_path / "p2" / "tabelas" / "tabela_01d_genitor_inferido.csv").iloc[0]
    assert t1d.p_genitor_portador_genotipos == pytest.approx(1 / 3)  # avó portadora, filho e mãe negativos
    assert t1d.p_genitor_portador_condicionada < 1 / 3 and "filho(a) já testado(a): 0" in t1d.parentes_e_dosagens
    assert r["resumo"].p_portador_exato.iloc[0] == pytest.approx(t1d.p_genitor_portador_condicionada / 2, abs=1e-6)
    assert "suposta herdada" in (tmp_path / "p2" / "relatorio.md").read_text(encoding="utf-8")


def test_cli_com_parentes(tmp_path, capsys):
    assert cli.main(["gerar-cenarios", "--saida", str(tmp_path / "s"), "--seed", "2026"]) == 0
    saida = capsys.readouterr().out
    assert "cenário de parentes 1" in saida and len(list((tmp_path / "s").glob("parentes_*.vcf"))) == 5
    # os cinco cenários padrão continuam os mesmos arquivos (o gerador dos parentes é independente)
    for p in sorted((tmp_path / "s").glob("cenario_*.vcf")):
        assert p.read_bytes() == (cli_dados() / p.name).read_bytes(), p.name
    args = [
        "executar",
        "--vcf-mae",
        str(tmp_path / "s" / "parentes_1_mae.vcf"),
        "--c9orf72-mae",
        str(cenarios.LAUDO_NORMAL),
        "--vcf-mae-do-pai",
        str(tmp_path / "s" / "parentes_1_avo_paterna.vcf"),
        "--c9orf72-mae-do-pai",
        str(cenarios.LAUDO_NORMAL),
        "--situacao-pai",
        "falecido_sem_ela",
        "--idade-pai",
        "60",
        "--sexo",
        "F",
        "--n",
        "600",
        "--motor",
        "numpy",
        "--sem-figuras",
        "--so-tabela-curada",
        "--saida",
        str(tmp_path / "exec"),
    ]
    assert cli.main(args) == 0
    meta = json.loads((tmp_path / "exec" / "metadados.json").read_text(encoding="utf-8"))
    assert meta["parentes"]["genitores"]["pai"]["situacao"] == "falecido_sem_ela" and meta["vcf_pai"] is None
    assert meta["parentes"]["loci_inferidos"][0]["p_descendente_portador"] == pytest.approx(0.1792, abs=5e-5)
    # as opções viram o dicionário `parentes` do pipeline
    ns = cli.construir_parser().parse_args(
        ["executar", "--vcf-mae", "m.vcf", "--saida", "x", "--vcf-irmao-do-pai", "t1.vcf", "t2.vcf"]
        + ["--c9orf72-irmao-do-pai", "45", "--vcf-filho-testado", "f.vcf", "--prior-avos", "hardy_weinberg"]
    )
    p = cli._parentes(ns)
    assert p["pai"]["irmaos"] == [{"vcf": "t1.vcf", "laudo_c9orf72": 45}, {"vcf": "t2.vcf", "laudo_c9orf72": None}]
    assert p["pai"]["prior_avos"] == "hardy_weinberg" and p["filhos_testados"] == [{"vcf": "f.vcf"}] and "mae" not in p
    assert (
        cli._parentes(
            cli.construir_parser().parse_args(["executar", "--vcf-mae", "m", "--vcf-pai", "p", "--saida", "x"])
        )
        is None
    )


def cli_dados():
    from ela_preditivo import DIR_DADOS

    return DIR_DADOS / "sinteticos"


def test_vcfs_dos_cenarios_de_parentes_sao_reprodutiveis(tmp_path):
    a = cenarios.gerar_cenarios_parentes(tmp_path / "a", seed=2026)
    cenarios.gerar_cenarios_parentes(tmp_path / "b", seed=2026)
    arquivos = sorted((tmp_path / "a").glob("parentes_*.vcf"))
    assert len(arquivos) == 5 and len(a) == len(cenarios.CENARIOS_PARENTES) == 2
    for p in arquivos:
        assert p.read_bytes() == (tmp_path / "b" / p.name).read_bytes()
        assert p.read_bytes() == (cli_dados() / p.name).read_bytes(), p.name  # os versionados são os do gerador
    assert a[0]["vcf_pai"] is None and a[0]["parentes"]["pai"]["situacao"] == "falecido_sem_ela"
    assert cenarios.cenario_parentes_por_numero(2).filhos_testados and a[1]["parentes"]["filhos_testados"]
    with pytest.raises(KeyError):
        cenarios.cenario_parentes_por_numero(9)
