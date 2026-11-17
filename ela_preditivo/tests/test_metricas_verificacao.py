"""Métricas de verificação com famílias sintéticas de desfecho conhecido: coorte de mundos, Brier e calibração,
discriminação, erro da idade de início com o piso teórico, cobertura, divergência entre curvas, robustez a erros no
VCF e tornado; e a integração no comando `avaliar`, na linha de comando e na opção da análise de um caso.

Com dados sintéticos gerados pelo próprio modelo estas métricas medem verificação, não validação. Cada uma é testada
em dois mundos: verdade = modelo (deve sair certa) e verdade alternativa (deve degradar).
"""

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from ela_preditivo import anotacao, avaliacao, cenarios, cli, exato, genotipo, ingestao, monte_carlo, parentes, pipeline

MUNDOS, POR_ESTRATO, SEMENTE_COORTE = 80, 12, 11
ROTULO_PARENTES = "cenário de parentes 1"


# ---------------------------------------------------------------------------
# Casos: os cinco cenários e o cenário de parentes 1 (pai sem exame, avó paterna heterozigota)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def vetores(anotados, parametros, curada, tmp_path_factory):
    out = {}
    for c in cenarios.CENARIOS:
        mae, pai = anotados[c.numero]
        out[f"cenário {c.numero}"] = genotipo.vetor_dosagem(
            mae, pai, parametros, laudo_c9orf72=c.laudo_c9orf72, tabela=curada
        )
    d = tmp_path_factory.mktemp("parentes_metricas")
    caso = cenarios.gerar_cenarios_parentes(d)[0]
    regioes = ingestao.carregar_regioes()
    mae = anotacao.anotar(ingestao.ler_vcf(caso["vcf_mae"], regioes, parametros.filtro_qualidade), curada)
    vazio = cenarios.escrever_vcf_sem_variantes(d / "pai_sem_exame.vcf", "PAI_SEM_EXAME")
    pai = anotacao.anotar(ingestao.ler_vcf(vazio, regioes, parametros.filtro_qualidade), curada)
    familia = parentes.Familia.de(caso["parentes"])
    out[ROTULO_PARENTES] = parentes.vetor_familia(
        mae,
        pai,
        parametros,
        caso["laudo_c9orf72"],
        curada,
        familia,
        parentes.ler_familia(familia, parametros, curada, regioes),
        {"mae": True, "pai": False},
    )
    return out


@pytest.fixture(scope="module")
def loci_f(vetores, parametros):
    return {k: monte_carlo.loci_de_vetor(v, parametros, sexo="F") for k, v in vetores.items()}


@pytest.fixture(scope="module")
def estratos(vetores, parametros):
    return avaliacao.montar_estratos(vetores, parametros)


@pytest.fixture(scope="module")
def verdades(parametros):
    return {v.nome: v for v in avaliacao.verdades(parametros)}


@pytest.fixture(scope="module")
def coortes(estratos, parametros, verdades):
    return {
        nome: avaliacao.coorte_de_mundos(
            estratos, parametros, v, mundos=MUNDOS, por_estrato=POR_ESTRATO, seed=SEMENTE_COORTE
        )
        for nome, v in verdades.items()
    }


# ---------------------------------------------------------------------------
# Enquadramento e coorte
# ---------------------------------------------------------------------------
def test_enquadramento_e_verdades(parametros, verdades):
    assert (
        "verificação" in avaliacao.ENQUADRAMENTO and "não validação contra pacientes reais" in avaliacao.ENQUADRAMENTO
    )
    assert list(verdades) == ["modelo", "exemplo_orientador", "penetrancia_alternativa"]
    # as verdades alternativas só usam o que o YAML já traz
    ex = parametros.sensibilidade["exemplo_professor"]["genes"]
    assert verdades["exemplo_orientador"].penetrancia["SOD1"] == pytest.approx(ex["SOD1"]["penetrancia"])
    assert verdades["exemplo_orientador"].inicio["FUS"].params["lam"] == pytest.approx(ex["FUS"]["weibull_lam"])
    assert verdades["penetrancia_alternativa"].penetrancia["SOD1"].tipo == "lognormal_truncada"
    assert verdades["modelo"].penetrancia["SOD1"].tipo == parametros.distribuicao_penetrancia == "beta"
    # penetrância sorteada uma vez por mundo: distribuição no modelo, valor fixo no exemplo do orientador
    rng = np.random.default_rng(1)
    assert len(set(verdades["modelo"].sortear_pi("SOD1", 50, rng).round(6))) == 50
    assert set(verdades["exemplo_orientador"].sortear_pi("SOD1", 50, rng)) == {0.9}


@pytest.mark.parametrize(
    "cenario, sexo, idade, p_portador, risco",
    [
        ("cenário 1", "F", 55, 0.3930, 0.1130),
        ("cenário 2", "M", 42, 0.4930, 0.1547),
        ("cenário 5", "F", 55, 0.7120, 0.1542),
    ],
)
def test_previsao_da_coorte_e_a_dos_indicadores_condicionados(
    vetores, parametros, cenario, sexo, idade, p_portador, risco
):
    loci = monte_carlo.loci_de_vetor(vetores[cenario], parametros, sexo=sexo)
    prev = avaliacao.previsao_exata(loci, float(idade), 90.0)
    assert prev["p_portador"] == pytest.approx(p_portador, abs=5e-5)
    assert prev["risco_horizonte"] == pytest.approx(risco, abs=5e-5)
    assert 0 < prev["risco_10"] < prev["risco_20"] <= prev["risco_horizonte"]
    assert idade < prev["mediana_inicio"] < 90 and prev["piso_erro_idade"] > 0


def test_coorte_mistura_cenarios_sexos_e_idades_com_semente_propria(estratos, coortes, parametros, verdades):
    assert len(estratos) == 6 * 2 * len(avaliacao.IDADES_COORTE)
    assert {e.idade for e in estratos} == {float(i) for i in range(0, 71, 5)} and {e.sexo for e in estratos} == {
        "F",
        "M",
    }
    co = coortes["modelo"]
    assert co.attrs["seed"] == SEMENTE_COORTE and co.mundo.nunique() == MUNDOS and co.cenario.nunique() == 6
    # todos sem sintomas na idade atual; evento = início até o horizonte; tempo contado da idade atual
    ev = co[co.evento]
    assert (ev.idade_inicio > ev.idade_atual).all() and (ev.idade_inicio <= 90).all()
    assert co[~co.evento].idade_inicio.isna().all()
    assert np.allclose(co[~co.evento].tempo, 90 - co[~co.evento].idade_atual)
    assert np.allclose(ev.tempo, ev.idade_inicio - ev.idade_atual)
    # dentro de um estrato todos têm a mesma previsão: a heterogeneidade vem da mistura
    assert (co.groupby("estrato").risco_horizonte.nunique() == 1).all() and co.risco_horizonte.nunique() > 50
    # entra quem chega sem sintomas à idade atual: nunca mais gente do que a sorteada, e menos nas idades altas
    por_estrato = co.groupby(["estrato", "mundo"]).size()
    assert por_estrato.max() <= POR_ESTRATO
    c1 = co[(co.cenario == "cenário 1") & (co.sexo == "F")]
    assert len(c1[c1.idade_atual == 0]) == MUNDOS * POR_ESTRATO > len(c1[c1.idade_atual == 70])
    # o cenário de parentes perde também as famílias incompatíveis com o pai sem sintomas aos 60 anos
    cp = co[(co.cenario == ROTULO_PARENTES) & (co.idade_atual == 0)]
    assert len(cp) < 2 * MUNDOS * POR_ESTRATO
    # reprodutível com a mesma semente e diferente com outra
    de_novo = avaliacao.coorte_de_mundos(
        estratos, parametros, verdades["modelo"], mundos=MUNDOS, por_estrato=POR_ESTRATO, seed=SEMENTE_COORTE
    )
    pd.testing.assert_frame_equal(co, de_novo)
    outra = avaliacao.coorte_de_mundos(
        estratos, parametros, verdades["modelo"], mundos=MUNDOS, por_estrato=POR_ESTRATO, seed=12
    )
    assert len(outra) != len(co) or not np.array_equal(outra.evento.to_numpy(), co.evento.to_numpy())
    desc = avaliacao.descricao_coorte(estratos, co, verdades["modelo"])
    assert desc.pessoas.sum() == len(co) and (desc.pessoas <= desc.pessoas_sorteadas).all()
    assert (desc.estratos == 30).all()


# ---------------------------------------------------------------------------
# Calibração
# ---------------------------------------------------------------------------
def test_brier_e_calibracao_com_verdade_igual_ao_modelo(coortes):
    b = avaliacao.brier(coortes["modelo"]).set_index("previsao")
    assert list(b.index) == ["10 anos", "20 anos", "até o horizonte"]
    assert (b.prevalencia_observada - b.risco_previsto_medio).abs().max() < 0.012
    assert (b.brier < b.brier_referencia).all() and (b.habilidade > 0).all()
    cal = avaliacao.curva_calibracao(coortes["modelo"])
    assert set(cal.decil) == set(range(1, 11)) and len(cal) == 30
    assert cal.diferenca.abs().max() < 0.03
    # o risco previsto cresce com o decil
    for _, c in cal.groupby("previsao"):
        assert c.sort_values("decil").risco_previsto.is_monotonic_increasing


def test_calibracao_degrada_com_a_verdade_alternativa(coortes):
    modelo = avaliacao.brier(coortes["modelo"]).set_index("previsao")
    alt = avaliacao.brier(coortes["exemplo_orientador"]).set_index("previsao")
    # o mundo do exemplo do orientador tem penetrância bem maior: o modelo subestima
    assert (alt.prevalencia_observada - alt.risco_previsto_medio).loc["até o horizonte"] > 0.08
    assert (alt.brier > modelo.brier).all()
    cal = avaliacao.curva_calibracao(coortes["exemplo_orientador"])
    assert cal[cal.previsao == "até o horizonte"].diferenca.max() > 0.15
    # a penetrância log-normal com os mesmos intervalos publicados afasta pouco
    ln = avaliacao.brier(coortes["penetrancia_alternativa"]).set_index("previsao")
    assert (ln.prevalencia_observada - ln.risco_previsto_medio).abs().max() < 0.02


# ---------------------------------------------------------------------------
# Discriminação
# ---------------------------------------------------------------------------
def test_c_index_e_auc_em_exemplos_feitos_a_mao():
    assert avaliacao.c_index_harrell([1, 2, 3], [True, True, False], [0.9, 0.5, 0.1]) == 1.0
    assert avaliacao.c_index_harrell([1, 2, 3], [True, True, False], [0.1, 0.5, 0.9]) == 0.0
    assert avaliacao.c_index_harrell([1, 2, 3], [True, True, False], [0.4, 0.4, 0.4]) == 0.5
    # censurado antes do evento do outro: par não comparável
    assert np.isnan(avaliacao.c_index_harrell([1, 2], [False, True], [0.9, 0.1]))
    assert avaliacao.c_index_harrell([1, 2, 3], [False, True, False], [0.1, 0.9, 0.2]) == 1.0
    assert avaliacao.auc_mann_whitney([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert avaliacao.auc_mann_whitney([0.1], [0.9, 0.8]) == 0.0
    assert avaliacao.auc_mann_whitney([0.5, 0.5], [0.5]) == 0.5
    assert np.isnan(avaliacao.auc_mann_whitney([], [0.5]))
    rng = np.random.default_rng(3)
    a, b = rng.random(40), rng.random(60) * 0.9
    bruto = np.mean([(x > y) + 0.5 * (x == y) for x in a for y in b])
    assert avaliacao.auc_mann_whitney(a, b) == pytest.approx(bruto)


def test_discriminacao_existe_pela_mistura_e_some_dentro_de_um_estrato(coortes):
    d = avaliacao.discriminacao(coortes["modelo"])
    assert len(d) == 3 and d.metrica.str.contains("C-index de Harrell").iloc[0]
    assert d.metrica.str.contains("10 anos").iloc[1] and d.metrica.str.contains("20 anos").iloc[2]
    assert 0.58 < d.valor.iloc[0] < 0.70 and (d.valor.iloc[1:] > 0.70).all() and (d.mundos == MUNDOS).all()
    # casos: início em (a, a + t]; controles: sem início até a + t
    co = coortes["modelo"]
    assert d.casos.iloc[1] == int((co.evento & (co.tempo <= 10)).sum()) and d.casos.iloc[1] + d.controles.iloc[
        1
    ] == len(co)
    # dentro de um só cenário, sexo e idade todos têm a mesma previsão: não há discriminação a medir
    um = co[(co.cenario == "cenário 1") & (co.sexo == "F") & (co.idade_atual == 50)]
    assert um.estrato.nunique() == 1 and um.risco_10.nunique() == 1
    d1 = avaliacao.discriminacao(um)
    assert d1.valor.iloc[0] == pytest.approx(0.5) and d1.valor.iloc[1] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Erro da idade de início com o piso teórico
# ---------------------------------------------------------------------------
def test_inicio_por_causa_confere_com_um_locus_e_com_sorteios(parametros):
    sod1, c9 = parametros.genes["SOD1"].inicio, parametros.genes["C9orf72"].inicio
    um = [(0.27, sod1)]
    ((med, piso),) = exato.inicio_por_causa(40.0, 90.0, um)
    assert med == pytest.approx(exato.quantil_inicio_condicional(0.5, 40.0, 90.0, um), abs=0.02)
    assert piso == pytest.approx(exato.desvio_absoluto_inicio_condicional(40.0, 90.0, um), abs=0.02)
    # dois lóci: o início de um gene quando ele é o primeiro tende a ser mais cedo do que o do gene sozinho
    comps = [(0.45, sod1), (0.30, c9)]
    causa = exato.inicio_por_causa(40.0, 90.0, comps)
    ((so_c9, _),) = exato.inicio_por_causa(40.0, 90.0, [comps[1]])
    assert causa[1][0] < so_c9
    rng = np.random.default_rng(5)
    n = 400_000
    t = np.column_stack([np.where(rng.random(n) < k, d.amostrar(rng, n), np.inf) for k, d in comps])
    primeiro, qual = t.min(axis=1), t.argmin(axis=1)
    for j, (mediana, desvio) in enumerate(causa):
        x = primeiro[(qual == j) & (primeiro > 40) & (primeiro <= 90)]
        assert np.median(x) == pytest.approx(mediana, abs=0.15)
        assert np.abs(x - mediana).mean() == pytest.approx(desvio, abs=0.1)
    assert all(np.isnan(v) for v in exato.inicio_por_causa(89.99, 90.0, [(0.0, sod1)])[0])


def test_erro_da_idade_de_inicio_fica_no_piso_com_verdade_igual_ao_modelo(coortes):
    e = avaliacao.erro_idade_inicio(coortes["modelo"]).set_index("gene")
    assert set(e.index) == {"SOD1", "C9orf72", "TARDBP", "FUS", "combinado (mediana do indicador)"}
    assert e.n_manifestam.iloc[:-1].sum() == e.n_manifestam.iloc[-1] == int(coortes["modelo"].evento.sum())
    # um modelo perfeito fica no piso: razão 1, a menos da flutuação amostral
    assert ((e.razao_erro_piso - 1).abs() < 0.06).all()
    assert ((e.erro_absoluto_medio_anos - e.piso_teorico_anos).abs() < 4 * e.erro_padrao_anos).all()
    alt = avaliacao.erro_idade_inicio(coortes["exemplo_orientador"]).set_index("gene")
    assert alt.loc["combinado (mediana do indicador)", "razao_erro_piso"] > 1.10
    assert alt.loc["combinado (mediana do indicador)", "vies_medio_anos"] < -2


# ---------------------------------------------------------------------------
# Cobertura dos intervalos
# ---------------------------------------------------------------------------
def test_cobertura_dos_intervalos_do_monte_carlo(loci_f):
    casos = {k: loci_f[k] for k in ("cenário 1", "cenário 3", ROTULO_PARENTES)}
    c = avaliacao.cobertura_monte_carlo(casos, n=2000, repeticoes=120, seed=7)
    assert list(c.cenario) == ["cenário 1", "cenário 3", "cenário 3", "cenário 3", ROTULO_PARENTES]
    assert c.unidade.iloc[3] == "qualquer lócus" and (c.esperado == 0.95).all() and (c.sementes == 120).all()
    assert c.cobertura_p_portador.between(0.88, 1.0).all() and c.cobertura_p_manifesta.between(0.88, 1.0).all()


def test_cobertura_das_bandas_com_verdade_igual_ao_modelo_e_subcobertura_com_a_alternativa(
    loci_f, parametros, verdades
):
    casos = {k: loci_f[k] for k in ("cenário 1", "cenário 3", ROTULO_PARENTES)}
    kw = dict(sexo="F", mundos=150, por_mundo=4000, n_banda=6000, seed_banda=3, seed_mundos=5)
    m = avaliacao.cobertura_bandas(casos, parametros, verdades["modelo"], **kw)
    assert (
        set(m.idade) == {50, 60, 70}
        and len(m) == 9
        and (m.banda_q025 < m.F_modelo).all()
        and (m.F_modelo < m.banda_q975).all()
    )
    # por construção: perto de 95 % quando o F do mundo não tem ruído amostral
    assert m.cobertura_sem_ruido_amostral.between(0.90, 1.0).all()
    assert (m.F_mundos_media - m.F_modelo).abs().max() < 0.01
    sem_inferencia = m[m.cenario != ROTULO_PARENTES]
    assert sem_inferencia.cobertura_da_banda.between(0.88, 1.0).all()
    # com genitor inferido a banda é estreita e o ruído do F empírico pesa mais: cobertura empírica menor
    inferido = m[m.cenario == ROTULO_PARENTES]
    assert (inferido.cobertura_da_banda < inferido.cobertura_sem_ruido_amostral).all()
    a = avaliacao.cobertura_bandas(casos, parametros, verdades["exemplo_orientador"], **kw)
    fora = a[a.cenario != ROTULO_PARENTES]
    assert (fora.cobertura_da_banda < 0.05).all() and (fora.cobertura_sem_ruido_amostral < 0.05).all()
    assert (fora.F_mundos_media > fora.banda_q975).all()


# ---------------------------------------------------------------------------
# Divergência entre curvas
# ---------------------------------------------------------------------------
def test_ks_e_wasserstein_pequenos_com_o_modelo_e_grandes_com_a_verdade_alternativa(
    vetores, loci_f, parametros, verdades
):
    loci = loci_f["cenário 3"]
    res = monte_carlo.simular_numpy(loci, n=20_000, seed=5)
    d = avaliacao.divergencia_curvas(res, None, 90.0, "sorteios do artefato")
    assert list(d.unidade) == [loci[0].rotulo, loci[1].rotulo, "qualquer lócus"]
    assert np.allclose(d.ks_referencia_amostral, 1.36 / np.sqrt(20_000), atol=1e-6)
    assert (d.ks_F < 1.5 * d.ks_referencia_amostral).all() and (d.wasserstein_idade_inicio_anos < 0.6).all()
    assert (d.n_manifestam > 3000).all() and (d.n_sorteios == 20_000).all()
    alt_loci = avaliacao.loci_da_verdade(vetores["cenário 3"], parametros, verdades["exemplo_orientador"], "F", 90.0)
    assert alt_loci[0].pen_media == pytest.approx(0.9)
    alt = monte_carlo.simular_numpy(alt_loci, n=20_000, seed=6)
    da = avaliacao.divergencia_curvas(alt, loci, 90.0, "verdade alternativa")
    assert (da.ks_F > 0.08).all() and (da.wasserstein_idade_inicio_anos > 2.0).all()


# ---------------------------------------------------------------------------
# Robustez a erros no VCF
# ---------------------------------------------------------------------------
def test_robustez_a_erros_no_vcf(dir_cenarios, parametros, curada, tmp_path):
    antes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dir_cenarios.glob("cenario_*.vcf"))}
    r = avaliacao.robustez_vcf(dir_cenarios, [1, 2, 4], parametros, curada, tmp_path / "tmp", "F")
    assert antes == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dir_cenarios.glob("cenario_*.vcf"))
    }
    assert list((tmp_path / "tmp").iterdir()) == []  # os VCFs perturbados não ficam no disco
    assert len(r) == 3 * len(avaliacao.PERTURBACOES)
    assert set(r.classe) == {"falso negativo", "falso positivo", "indeterminado"}
    c1 = r[r.cenario == "cenário 1"].set_index("perturbacao")
    assert (c1.p_portador_original == 0.5).all()
    # falso negativo: o lócus some e nada avisa, salvo o filtro de qualidade, que conta a reprovação
    for tipo in ("registro_removido", "gt_01_para_00", "gq_abaixo_de_30"):
        assert c1.loc[tipo, "p_portador_perturbado"] == 0 and c1.loc[tipo, "variacao_risco"] < -0.2
    assert "nenhum aviso" in c1.loc["registro_removido", "o_que_o_artefato_reporta"]
    assert "falso negativo silencioso" in c1.loc["gt_01_para_00", "o_que_o_artefato_reporta"]
    assert "filtro de qualidade (GQ)" in c1.loc["gq_abaixo_de_30", "o_que_o_artefato_reporta"]
    # falso positivo: outro lócus entra, ou o segundo genitor passa a portar
    assert c1.loc["variante_inserida", "p_portador_perturbado"] == pytest.approx(0.75)
    assert "novo lócus de risco" in c1.loc["variante_inserida", "o_que_o_artefato_reporta"]
    assert (
        c1.loc["gt_00_para_01", "p_portador_perturbado"] == pytest.approx(0.75)
        and c1.loc["gt_00_para_01", "genitor"] == "mae"
    )
    # genótipo indeterminado: o lócus é descartado e declarado, nunca tratado como dosagem 0
    assert "descartado e declarado" in c1.loc["genotipo_indeterminado", "o_que_o_artefato_reporta"]
    assert "nunca dosagem 0" in c1.loc["genotipo_indeterminado", "o_que_o_artefato_reporta"]
    # cenário 2: a expansão vem do laudo, não do VCF; só a variante inserida se aplica
    c2 = r[r.cenario == "cenário 2"].set_index("perturbacao")
    assert c2.drop("variante_inserida").p_portador_perturbado.isna().all()
    assert c2.drop("variante_inserida").o_que_o_artefato_reporta.str.contains("vem do laudo").all()
    assert c2.loc["variante_inserida", "variacao_p_portador"] == pytest.approx(0.25)
    # cenário 4: os dois genitores portam a variante recessiva, não há registro 0/0 para trocar
    c4 = r[r.cenario == "cenário 4"].set_index("perturbacao")
    assert "os dois genitores portam" in c4.loc["gt_00_para_01", "o_que_o_artefato_reporta"]
    assert (
        c4.loc["gt_01_para_00", "p_portador_perturbado"] == 0 and c4.loc["gt_01_para_00", "p_portador_original"] == 0.25
    )


# ---------------------------------------------------------------------------
# Tornado
# ---------------------------------------------------------------------------
def test_tornado_so_usa_faixas_publicadas(vetores, parametros):
    t1 = avaliacao.tornado(vetores["cenário 1"], parametros, "F")
    assert t1.variacao_risco.is_monotonic_decreasing and t1.parametro.iloc[0] == "penetrância do SOD1"
    assert (t1.fonte.str.len() > 10).all() and t1.attrs["fora_do_tornado"] == []
    pen = t1.set_index("parametro").loc["penetrância do SOD1"]
    lo, hi = parametros.genes["SOD1"].pen_ic95
    assert float(pen.valor_baixo) == pytest.approx(lo) and float(pen.valor_alto) == pytest.approx(hi)
    assert "DOUGLAS; BARALLE, 2024" in pen.fonte and pen.variacao_mediana_anos == 0
    assert pen.risco_baixo < pen.risco_base < pen.risco_alto
    # início do SOD1: média ± 1,96·dp/√n, com média 50,2, dp 10,6 e n = 64
    ini = t1.set_index("parametro").loc["idade de início do SOD1 (média)"]
    meia = avaliacao.Z95 * 10.6 / np.sqrt(64)
    assert float(ini.valor_baixo) == pytest.approx(50.2 - meia, abs=0.006) and float(ini.valor_alto) == pytest.approx(
        50.2 + meia, abs=0.006
    )
    assert (
        "BERDYŃSKI" in ini.fonte
        and ini.variacao_mediana_anos == pytest.approx(2 * meia, abs=0.2)
        and ini.variacao_risco < 1e-3
    )
    # C9orf72: faixa entre as medianas publicadas e deslocamento por sexo de 0 contra ±1 ano
    t2 = avaliacao.tornado(vetores["cenário 2"], parametros, "F").set_index("parametro")
    c9 = t2.loc["idade de início do C9orf72 (mediana publicada)"]
    assert c9.valor_baixo.startswith("57") and c9.valor_alto.startswith("62.9")
    assert t2.loc["deslocamento por sexo no C9orf72", "variacao_mediana_anos"] == pytest.approx(1.0, abs=0.01)
    # TARDBP: mediana ± 1,96·EP com EP ≈ 1,2533·(IQR/1,349)/√n; FUS fica fora da idade de início e isso é reportado
    t5 = avaliacao.tornado(vetores["cenário 5"], parametros, "F")
    tar = t5.set_index("parametro").loc["idade de início do TARDBP (mediana)"]
    ep = 1.2533 * (16.23 / 1.349) / np.sqrt(64)
    assert float(tar.valor_alto) - float(tar.valor_baixo) == pytest.approx(2 * avaliacao.Z95 * ep, abs=0.02)
    assert "aproxima" in tar.fonte
    assert not t5.parametro.str.contains("idade de início do FUS").any() and "penetrância do FUS" in set(t5.parametro)
    assert len(t5.attrs["fora_do_tornado"]) == 1 and "FUS" in t5.attrs["fora_do_tornado"][0]
    # com idade atual o risco é o residual, o mesmo dos indicadores condicionados
    t55 = avaliacao.tornado(vetores["cenário 1"], parametros, "F", idade_atual=55)
    assert t55.risco_base.iloc[0] == pytest.approx(0.1130, abs=5e-5) and t55.attrs["idade_atual"] == 55
    # genitor inferido: o tornado refaz a inferência com cada valor
    tp = avaliacao.tornado(vetores[ROTULO_PARENTES], parametros, "F")
    assert tp.risco_base.iloc[0] == pytest.approx(0.0935, abs=1e-4) and len(tp) == 3


def test_tornado_como_opcao_da_execucao(dir_cenarios, tmp_path):
    comum = dict(sexo="F", idade_atual=40, n=600, motor="numpy", base_clinvar=False)
    c = cenarios.cenario_por_numero(3)
    vcfs = (dir_cenarios / "cenario_3_mae.vcf", dir_cenarios / "cenario_3_pai.vcf")
    sem = pipeline.executar(*vcfs, tmp_path / "sem", laudo_c9orf72=c.laudo_c9orf72, figuras=False, **comum)
    assert sem["tornado"] is None and not (tmp_path / "sem" / "tabelas" / "tabela_20_tornado.csv").exists()
    assert json.loads((tmp_path / "sem" / "metadados.json").read_text(encoding="utf-8"))["tornado"] is False
    com = pipeline.executar(*vcfs, tmp_path / "com", laudo_c9orf72=c.laudo_c9orf72, tornado=True, **comum)
    assert len(com["tornado"]) == 6 and "tabela_20_tornado" in {t["nome"] for t in com["tabelas"]}
    assert (tmp_path / "com" / "figuras" / "figura_12_tornado.png").stat().st_size > 10_000
    texto = (tmp_path / "com" / "relatorio.md").read_text(encoding="utf-8")
    assert "## Sensibilidade tipo tornado" in texto and "risco vitalício residual" in texto
    assert json.loads((tmp_path / "com" / "metadados.json").read_text(encoding="utf-8"))["tornado"] is True
    # o tornado não muda o resultado da análise
    sem_tempo = lambda d: {k: v for k, v in d.items() if k != "tempo_s"}  # noqa: E731
    assert sem_tempo(com["combinado"]) == sem_tempo(sem["combinado"]) and com["condicionado"] == sem["condicionado"]


# ---------------------------------------------------------------------------
# Comando `avaliar` e linha de comando
# ---------------------------------------------------------------------------
TABELAS_VERIFICACAO = {
    "tabela_12_coorte_verificacao",
    "tabela_13_brier",
    "tabela_14_calibracao_decis",
    "tabela_15_discriminacao",
    "tabela_16_erro_idade_inicio",
    "tabela_17_cobertura_monte_carlo",
    "tabela_17b_cobertura_bandas",
    "tabela_18_divergencia_curvas",
    "tabela_19_robustez_vcf",
    "tabela_20_tornado",
}


def test_avaliar_grava_as_metricas_de_verificacao(dir_cenarios, tmp_path):
    kw = dict(numeros=[1, 5], ns=(300,), repeticoes=2, seed=3, n_coerencia=1500, base_clinvar=False)
    r = pipeline.avaliar(dir_cenarios, tmp_path / "av", mundos=12, por_estrato=4, seed_coorte=99, **kw)
    nomes = {t["nome"] for t in r["tabelas"]}
    assert TABELAS_VERIFICACAO <= nomes and {"tabela_05_estabilidade", "tabela_09_sensibilidade"} <= nomes
    for nome in TABELAS_VERIFICACAO:
        assert (tmp_path / "av" / "tabelas" / f"{nome}.csv").stat().st_size > 100
    figuras = {p.name for p in (tmp_path / "av" / "figuras").iterdir()}
    assert {"figura_10_calibracao.png", "figura_11_robustez_vcf.png", "figura_12_tornado.png"} <= figuras
    assert len(r["figuras"]) == 6 and not (tmp_path / "av" / "_verificacao_tmp").exists()
    v = r["verificacao"]
    assert (
        set(v["coorte"].cenario) == {"cenário 1", "cenário 5", ROTULO_PARENTES} and v["coorte"].verdade.nunique() == 3
    )
    assert set(v["brier"].verdade) == set(v["cobertura_bandas"].verdade) == set(v["coorte"].verdade)
    assert set(v["robustez"].cenario) == set(v["tornado"].cenario) == {"cenário 1", "cenário 5"}
    assert v["divergencia"].origem.nunique() == 3 and (v["cobertura_mc"].sementes == 12).all()
    texto = (tmp_path / "av" / "relatorio.md").read_text(encoding="utf-8")
    assert "## Verificação com famílias sintéticas de desfecho conhecido" in texto
    assert "não validação contra pacientes reais" in texto and "verdade alternativa" in texto
    assert "Tabela 12 —" in texto and "Tabela 20 —" in texto and "Figura 10 —" in texto and "Figura 12 —" in texto
    assert "Fora do tornado, por não haver incerteza publicada" in texto and "FUS" in texto
    assert "não precisa de ponderação pela censura" in texto  # nota da AUC dependente do tempo
    meta = json.loads((tmp_path / "av" / "metadados.json").read_text(encoding="utf-8"))["verificacao"]
    assert meta["seed_coorte"] == 99 and meta["seed_previsoes"] == 3 and meta["mundos"] == 12
    assert meta["pessoas_por_estrato"] == 4 and ROTULO_PARENTES in meta["cenarios_na_coorte"]
    assert [x["nome"] for x in meta["verdades"]] == ["modelo", "exemplo_orientador", "penetrancia_alternativa"]
    assert len(meta["fora_do_tornado"]) == 1 and "verificação" in meta["enquadramento"]
    # a semente da coorte é própria: mudar a das previsões não muda a coorte
    kw2 = dict(kw, seed=4)
    r2 = pipeline.avaliar(dir_cenarios, tmp_path / "av2", mundos=12, por_estrato=4, seed_coorte=99, **kw2)
    pd.testing.assert_frame_equal(r2["verificacao"]["coorte"], v["coorte"])
    pd.testing.assert_frame_equal(r2["verificacao"]["brier"], v["brier"])


def test_avaliar_sem_metricas_e_semente_padrao_da_coorte(dir_cenarios, tmp_path):
    kw = dict(numeros=[4], ns=(300,), repeticoes=2, seed=3, n_coerencia=600, base_clinvar=False)
    sem = pipeline.avaliar(dir_cenarios, tmp_path / "sem", metricas=False, **kw)
    assert sem["verificacao"] is None and not (TABELAS_VERIFICACAO & {t["nome"] for t in sem["tabelas"]})
    assert json.loads((tmp_path / "sem" / "metadados.json").read_text(encoding="utf-8"))["verificacao"] is None
    assert "Verificação com famílias sintéticas" not in (tmp_path / "sem" / "relatorio.md").read_text(encoding="utf-8")
    com = pipeline.avaliar(dir_cenarios, tmp_path / "com", mundos=6, por_estrato=3, **kw)
    meta = json.loads((tmp_path / "com" / "metadados.json").read_text(encoding="utf-8"))["verificacao"]
    assert meta["seed_coorte"] != meta["seed_previsoes"] == 3


def test_cli_avaliar_com_as_opcoes_de_verificacao(dir_cenarios, tmp_path, capsys):
    comum = ["avaliar", "--dir-cenarios", str(dir_cenarios), "--cenarios", "1", "--n", "300", "--repeticoes", "2"]
    comum += ["--n-coerencia", "600", "--so-tabela-curada"]
    assert (
        cli.main(comum + ["--saida", str(tmp_path / "a"), "--mundos", "6", "--por-estrato", "3", "--seed-coorte", "7"])
        == 0
    )
    meta = json.loads((tmp_path / "a" / "metadados.json").read_text(encoding="utf-8"))["verificacao"]
    assert meta["mundos"] == 6 and meta["pessoas_por_estrato"] == 3 and meta["seed_coorte"] == 7
    assert (tmp_path / "a" / "tabelas" / "tabela_13_brier.csv").exists()
    assert cli.main(comum + ["--saida", str(tmp_path / "b"), "--sem-metricas"]) == 0
    assert not (tmp_path / "b" / "tabelas" / "tabela_13_brier.csv").exists()
    capsys.readouterr()


def test_cli_executar_com_tornado(dir_cenarios, tmp_path, capsys):
    args = [
        "executar",
        "--vcf-mae",
        str(dir_cenarios / "cenario_1_mae.vcf"),
        "--vcf-pai",
        str(dir_cenarios / "cenario_1_pai.vcf"),
    ]
    args += [
        "--saida",
        str(tmp_path / "t"),
        "--n",
        "500",
        "--motor",
        "numpy",
        "--sem-figuras",
        "--so-tabela-curada",
        "--tornado",
    ]
    assert cli.main(args) == 0
    tab = pd.read_csv(tmp_path / "t" / "tabelas" / "tabela_20_tornado.csv")
    assert list(tab.parametro)[0] == "penetrância do SOD1" and tab.fonte.notna().all()
    capsys.readouterr()
