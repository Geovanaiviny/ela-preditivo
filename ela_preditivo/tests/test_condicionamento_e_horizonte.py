"""Indicadores condicionados à idade atual (pessoa sem sintomas) e significado único de "risco vitalício": a
probabilidade de manifestar até o horizonte, igual nas Tabelas 3 e 4, nas curvas e nos indicadores."""

import json

import numpy as np
import pandas as pd
import pytest

from ela_preditivo import cenarios, exato, genotipo, monte_carlo, pipeline, sobrevivencia


def _res(anotados, parametros, curada, numero, sexo, n=4000, seed=7, horizonte=None):
    mae, pai = anotados[numero]
    vetor = genotipo.vetor_dosagem(
        mae, pai, parametros, laudo_c9orf72=cenarios.cenario_por_numero(numero).laudo_c9orf72, tabela=curada
    )
    loci = monte_carlo.loci_de_vetor(vetor, parametros, sexo=sexo, horizonte=horizonte)
    return monte_carlo.simular_numpy(loci, n=n, seed=seed)


# ---------------------------------------------------------------------------
# Indicadores condicionados à idade atual
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "numero, sexo, idade, p_portador, residual",
    [(2, "M", 42, 0.4930, 0.1547), (5, "F", 55, 0.7120, 0.1542), (1, "F", 55, 0.3930, 0.1130)],
)
def test_indicadores_condicionados_valores_exatos(
    anotados, parametros, curada, numero, sexo, idade, p_portador, residual
):
    res = _res(anotados, parametros, curada, numero, sexo)
    ind = sobrevivencia.indicadores_condicionados(res, idade, parametros.horizonte_anos)
    assert ind["idade_referencia"] == idade and ind["horizonte"] == 90
    assert ind["p_portador"] == pytest.approx(p_portador, abs=5e-5)
    rr = ind["risco_residual"]
    assert rr["valor"] == pytest.approx(residual, abs=5e-5)
    # banda pelos sorteios da penetrância; janelas de 10 e 20 anos crescentes e dentro do risco residual
    assert rr["q025"] < rr["valor"] < rr["q975"]
    assert 0 < ind["janelas"]["10"]["valor"] < ind["janelas"]["20"]["valor"] <= rr["valor"]
    assert ind["janelas"]["10"]["ate"] == idade + 10 and ind["janelas"]["20"]["ate"] == idade + 20
    # idade provável de início entre quem vai manifestar: depois da idade atual e antes do horizonte
    ini = ind["inicio"]
    assert idade < ini["q25"] < ini["mediana"] < ini["q75"] < 90
    # é a mesma conta exata da Tabela 4, na idade do atendido
    tab = sobrevivencia.tabela_risco_condicional(res, idades_atuais=(idade,), horizonte=90.0)
    linha = tab[tab.unidade == ind["unidade"]].iloc[0]
    assert linha.p_portador_condicional == ind["p_portador"] and linha.risco_residual == rr["valor"]


def test_condicionado_bate_com_a_rejeicao_do_monte_carlo(anotados, parametros, curada):
    res = _res(anotados, parametros, curada, 5, "F", n=60_000, seed=3)
    ind = sobrevivencia.indicadores_condicionados(res, 55, 90.0)
    c = res.condicionar_idade(55)
    ep = np.sqrt(0.25 / c.n)
    assert abs(c.portador.any(axis=1).mean() - ind["p_portador"]) < 4 * ep
    assert abs(c.manifesta_qualquer_h.mean() - ind["risco_residual"]["valor"]) < 4 * ep
    # mediana condicional do início: a dos sorteios que manifestam depois dos 55 e até os 90 anos
    idades = c.idade_qualquer[c.manifesta_qualquer_h]
    assert np.median(idades) == pytest.approx(ind["inicio"]["mediana"], abs=1.0)
    assert np.percentile(idades, 25) == pytest.approx(ind["inicio"]["q25"], abs=1.0)


def test_linha_combinada_da_tabela_4_tem_p_portador_condicional(anotados, parametros, curada):
    res = _res(anotados, parametros, curada, 5, "F")
    tab = sobrevivencia.tabela_risco_condicional(res, idades_atuais=(0, 55), horizonte=90.0).set_index(
        ["unidade", "idade_atual"]
    )
    por_locus = [tab.loc[(l.rotulo, 55), "p_portador_condicional"] for l in res.loci]
    comb = tab.loc[(sobrevivencia.QUALQUER, 55), "p_portador_condicional"]
    assert comb == pytest.approx(1 - np.prod([1 - p for p in por_locus])) and comb == pytest.approx(0.7120, abs=5e-5)
    assert tab.loc[(sobrevivencia.QUALQUER, 0), "p_portador_condicional"] == pytest.approx(0.75)


def test_idade_alem_do_horizonte_nao_deixa_risco(anotados, parametros, curada):
    res = _res(anotados, parametros, curada, 1, "F")
    ind = sobrevivencia.indicadores_condicionados(res, 95, 90.0)
    assert ind["risco_residual"]["valor"] == 0 and ind["janelas"]["10"]["valor"] == 0
    assert ind["inicio"] == {"q25": None, "mediana": None, "q75": None}
    # janela limitada ao horizonte: aos 85 anos, "próximos 20 anos" vai só até os 90
    j = sobrevivencia.indicadores_condicionados(res, 85, 90.0)["janelas"]
    assert j["20"]["ate"] == 90 and j["20"]["valor"] == pytest.approx(j["10"]["valor"])


def test_quantil_inicio_condicional_e_desvio_absoluto():
    d = exato.DistribuicaoInicio("weibull", k=5.0, lam=60.0)
    comps = [(0.25, d)]
    # sem condicionamento e com horizonte longo, a mediana é a da própria distribuição de início
    assert exato.quantil_inicio_condicional(0.5, 0.0, 400.0, comps) == pytest.approx(d.mediana, abs=1e-4)
    med = exato.quantil_inicio_condicional(0.5, 55.0, 90.0, comps)
    assert 55 < med < 90 and med > d.mediana
    # a fração acumulada condicional no quantil devolvido é o próprio q
    fa, fh = exato.f_qualquer(55.0, comps), exato.f_qualquer(90.0, comps)
    assert (exato.f_qualquer(med, comps) - fa) / (fh - fa) == pytest.approx(0.5, abs=1e-7)
    assert exato.quantil_inicio_condicional(0.5, 90.0, 90.0, comps) is None
    dam = exato.desvio_absoluto_inicio_condicional(55.0, 90.0, comps)
    assert 0 < dam < 35 and np.isnan(exato.desvio_absoluto_inicio_condicional(95.0, 90.0, comps))


def test_pipeline_poe_a_idade_do_atendido_na_tabela_4_e_no_relatorio(dir_cenarios, tmp_path):
    args = dict(
        sexo="M",
        n=1200,
        seed=5,
        motor="numpy",
        laudo_c9orf72={"mae": 45, "pai": cenarios.LAUDO_NORMAL},
        base_clinvar=False,
        figuras=False,
    )
    mae, pai = cenarios.vcf_cenario(dir_cenarios, 2, "mae"), cenarios.vcf_cenario(dir_cenarios, 2, "pai")
    r = pipeline.executar(mae, pai, tmp_path / "c2", idade_atual=42, **args)
    cond = r["condicionado"]
    assert cond["p_portador"] == pytest.approx(0.4930, abs=5e-5)
    assert cond["risco_residual"]["valor"] == pytest.approx(0.1547, abs=5e-5)
    t4 = pd.read_csv(tmp_path / "c2" / "tabelas" / "tabela_04_risco_condicional.csv")
    assert sorted(t4.idade_atual.unique()) == [0, 20, 30, 40, 42, 50, 60, 70]
    linha = t4[t4.idade_atual == 42].iloc[0]
    assert linha.p_portador_condicional == pytest.approx(cond["p_portador"])
    assert linha.risco_residual == pytest.approx(cond["risco_residual"]["valor"])
    # o texto do relatório usa os mesmos números dos indicadores
    texto = (tmp_path / "c2" / "relatorio.md").read_text(encoding="utf-8")
    assert "assintomático aos 42 anos" in texto and "para 49.3%" in texto and "é 15.5%" in texto
    meta = json.loads((tmp_path / "c2" / "metadados.json").read_text(encoding="utf-8"))
    assert meta["indicadores_condicionados"]["idade_referencia"] == 42
    # sem idade (futuro filho) não há condicionamento e a Tabela 4 fica com as idades padrão
    r0 = pipeline.executar(mae, pai, tmp_path / "c2b", idade_atual=None, **args)
    assert r0["condicionado"] is None
    t4b = pd.read_csv(tmp_path / "c2b" / "tabelas" / "tabela_04_risco_condicional.csv")
    assert sorted(t4b.idade_atual.unique()) == list(pipeline.IDADES_TABELA_4)
    assert pipeline._idades_tabela_4(0) == pipeline.IDADES_TABELA_4 == pipeline._idades_tabela_4(40)
    assert pipeline._idades_tabela_4(42.5) == (0, 20, 30, 40, 42.5, 50, 60, 70)


# ---------------------------------------------------------------------------
# Um só significado para "risco vitalício": risco até o horizonte
# ---------------------------------------------------------------------------
def test_fus_cenario_5_risco_ate_o_horizonte_nas_tabelas_e_nas_curvas(anotados, parametros, curada):
    res = _res(anotados, parametros, curada, 5, "F", n=5000)
    j = next(i for i, l in enumerate(res.loci) if l.gene == "FUS")
    l = res.loci[j]
    assert l.horizonte == parametros.horizonte_anos == res.horizonte
    assert l.p_manifesta_exato == pytest.approx(0.0918, abs=5e-5)  # Tabela 3
    assert l.p_manifesta_sem_limite == pytest.approx(0.0960, abs=5e-5)  # F(∞), coluna própria
    assert res.resumo().iloc[j].p_manifesta_exato == l.p_manifesta_exato
    t4 = sobrevivencia.tabela_risco_condicional(res, idades_atuais=(0,), horizonte=90.0).set_index("unidade")
    assert t4.loc[l.rotulo, "risco_residual"] == pytest.approx(l.p_manifesta_exato, abs=1e-12)  # Tabela 4, idade 0
    curvas = sobrevivencia.curvas_analiticas(res, 90.0)
    assert curvas[curvas.unidade == l.rotulo].F.iloc[-1] == pytest.approx(l.p_manifesta_exato, abs=1e-12)
    # combinado: mesmo número na Tabela 3, na Tabela 4 (idade 0) e na curva; a banda é a da curva no horizonte
    comb = res.resumo_combinado()
    q = curvas[curvas.unidade == sobrevivencia.QUALQUER]
    assert comb["p_manifesta_qualquer_exato"] == pytest.approx(
        t4.loc[sobrevivencia.QUALQUER, "risco_residual"], abs=1e-12
    )
    assert comb["p_manifesta_qualquer_exato"] == pytest.approx(q.F.iloc[-1], abs=1e-12)
    assert comb["p_manifesta_qualquer_q025"] == pytest.approx(q.F_q025.iloc[-1], abs=1e-12)
    assert comb["p_manifesta_qualquer_q975"] == pytest.approx(q.F_q975.iloc[-1], abs=1e-12)
    assert comb["p_manifesta_qualquer_sem_limite"] > comb["p_manifesta_qualquer_exato"] and comb["horizonte"] == 90


def test_monte_carlo_conta_so_inicios_ate_o_horizonte(anotados, parametros, curada):
    res = _res(anotados, parametros, curada, 5, "F", n=300_000, seed=11)
    j = next(i for i, l in enumerate(res.loci) if l.gene == "FUS")
    r = res.resumo().iloc[j]
    assert abs(r.p_manifesta_mc - 0.0918) < 4 * r.ep_manifesta
    assert abs(r.p_manifesta_mc - 0.0960) > 4 * r.ep_manifesta  # sem o horizonte a simulação daria F(∞)
    assert r.p_manifesta_mc == pytest.approx(res.manifesta_h[:, j].mean())
    assert res.manifesta[:, j].mean() > res.manifesta_h[:, j].mean()  # inícios depois dos 90 anos existem no FUS
    comb = res.resumo_combinado()
    assert abs(comb["p_manifesta_qualquer_mc"] - comb["p_manifesta_qualquer_exato"]) < 4 * comb["ep_manifesta_qualquer"]


def test_horizonte_menor_reduz_o_risco_vitalicio(anotados, parametros, curada):
    r90 = _res(anotados, parametros, curada, 5, "F")
    r70 = _res(anotados, parametros, curada, 5, "F", horizonte=70)
    assert r70.horizonte == 70 and all(l.horizonte == 70 for l in r70.loci)
    for a, b in zip(r70.loci, r90.loci):
        assert a.p_manifesta_exato < b.p_manifesta_exato and a.p_manifesta_sem_limite == b.p_manifesta_sem_limite
    assert r70.resumo_combinado()["p_manifesta_qualquer_exato"] < r90.resumo_combinado()["p_manifesta_qualquer_exato"]


def test_tabela_3_tem_coluna_propria_para_a_fracao_sem_limite(dir_cenarios, tmp_path):
    r = pipeline.executar(
        cenarios.vcf_cenario(dir_cenarios, 5, "mae"),
        cenarios.vcf_cenario(dir_cenarios, 5, "pai"),
        tmp_path / "c5",
        sexo="F",
        n=1200,
        seed=2,
        motor="numpy",
        laudo_c9orf72=cenarios.cenario_por_numero(5).laudo_c9orf72,
        base_clinvar=False,
        figuras=False,
    )
    col = pipeline.COLUNA_SEM_LIMITE
    assert col == "fração que manifesta em algum momento (sem limite de idade)" and r["horizonte"] == 90
    t3 = pd.read_csv(tmp_path / "c5" / "tabelas" / "tabela_03_risco_vitalicio.csv")
    t4 = pd.read_csv(tmp_path / "c5" / "tabelas" / "tabela_04_risco_condicional.csv")
    fus = t3[t3.variante.str.startswith("FUS")].iloc[0]
    assert fus.p_manifesta_exato == pytest.approx(0.0918, abs=5e-5) and fus[col] == pytest.approx(0.0960, abs=5e-5)
    na_t4 = t4[(t4.unidade == fus.variante) & (t4.idade_atual == 0)].risco_residual.item()
    assert na_t4 == pytest.approx(fus.p_manifesta_exato, abs=1e-9)
    comb3 = t3[t3.variante == sobrevivencia.QUALQUER].iloc[0]
    comb4 = t4[(t4.unidade == sobrevivencia.QUALQUER) & (t4.idade_atual == 0)].iloc[0]
    assert (
        comb3.p_manifesta_exato == pytest.approx(comb4.risco_residual, abs=1e-9)
        and comb3[col] > comb3.p_manifesta_exato
    )
    texto = (tmp_path / "c5" / "relatorio.md").read_text(encoding="utf-8")
    assert "risco vitalício (até os 90 anos)" in texto and col in texto
