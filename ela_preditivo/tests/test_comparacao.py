"""Comparação com o modelo de Cox (extensão)."""

import numpy as np
import pandas as pd
import pytest

from ela_preditivo import cenarios, comparacao, genotipo, pipeline
from ela_preditivo.monte_carlo import loci_de_vetor, simular_numpy
from ela_preditivo.sobrevivencia import QUALQUER


@pytest.fixture(scope="module")
def res_cenario_3(anotados, parametros, curada):
    mae, pai = anotados[3]
    vetor = genotipo.vetor_dosagem(
        mae, pai, parametros, laudo_c9orf72={"mae": 45, "pai": cenarios.LAUDO_NORMAL}, tabela=curada
    )
    res = simular_numpy(loci_de_vetor(vetor, parametros, sexo="F"), n=4000, seed=5)
    res.sexo = "F"
    return res


def test_coorte_so_portadores_nos_dois_sexos(res_cenario_3, parametros):
    c = comparacao.coorte_cox(res_cenario_3, parametros, 90.0)
    assert set(c.sexo_masculino.unique()) == {0, 1}
    assert set(c.unidade) == {l.rotulo for l in res_cenario_3.loci} | {QUALQUER}
    # unidade de lócus: só portadores (≈ metade das fecundações por sexo); combinada: indicadores por lócus
    por_locus = c[c.unidade != QUALQUER].groupby("unidade").size()
    assert ((por_locus > 0.4 * 2 * 4000) & (por_locus < 0.6 * 2 * 4000)).all()
    comb = c[c.unidade == QUALQUER]
    assert (comb[["portador_0", "portador_1"]].sum(axis=1) >= 1).all()
    assert c.duracao.between(0, 90).all() and c.evento.dtype == bool


def test_coortes_dos_dois_sexos_sao_amostras_independentes(res_cenario_3, parametros):
    c = comparacao.coorte_cox(res_cenario_3, parametros, 90.0)
    sod1 = next(u for u in c.unidade.unique() if u.startswith("SOD1"))
    f = c[(c.unidade == sod1) & (c.sexo_masculino == 0)].duracao.to_numpy()
    m = c[(c.unidade == sod1) & (c.sexo_masculino == 1)].duracao.to_numpy()
    # no SOD1, sem efeito do sexo, as duas coortes eram idênticas linha a linha quando a semente era a mesma
    assert len(f) != len(m) or not np.array_equal(f, m)
    sementes = comparacao.sementes_por_sexo(res_cenario_3.seed)
    assert set(sementes) == {"F", "M"} and sementes["F"] != sementes["M"]
    assert sementes == comparacao.sementes_por_sexo(res_cenario_3.seed) != comparacao.sementes_por_sexo(6)
    # mesma semente da execução, mesma coorte e mesmo resultado
    pd.testing.assert_frame_equal(c, comparacao.coorte_cox(res_cenario_3, parametros, 90.0))
    tab = comparacao.comparar(res_cenario_3, parametros, 90.0)["tabela"].set_index("unidade")
    tab2 = comparacao.comparar(res_cenario_3, parametros, 90.0)["tabela"].set_index("unidade")
    hr, p = tab.loc[sod1, "HR[sexo masculino]"], tab.loc[sod1, "p[sexo masculino]"]
    assert hr == tab2.loc[sod1, "HR[sexo masculino]"] and p == tab2.loc[sod1, "p[sexo masculino]"]
    # razão de riscos perto de 1, mas não 1 com p = 1 por construção
    assert 0.8 < hr < 1.25 and abs(hr - 1.0) > 1e-6 and 0.0 < p < 0.999


def test_loci_por_sexo_desloca_so_o_c9orf72(res_cenario_3, parametros):
    por_sexo = comparacao.loci_por_sexo(res_cenario_3, parametros)
    for lf, lm, orig in zip(por_sexo["F"], por_sexo["M"], res_cenario_3.loci):
        if orig.gene == "C9orf72":
            assert lf.dist.mediana == pytest.approx(orig.dist.mediana)  # res já está em F
            assert lm.dist.mediana == pytest.approx(orig.dist.mediana - 2.0)  # M = −1, F = +1
        else:
            assert lf is orig and lm is orig


def test_cox_reproduz_km_e_fracao_de_cura(res_cenario_3, parametros):
    out = comparacao.comparar(res_cenario_3, parametros, 90.0)
    tab = out["tabela"].set_index("unidade")
    assert (tab.cox == "ajustado").all() and out["curvas"] is not None and out["mensagens"] == []
    for u in tab.index:
        assert tab.loc[u, "dif_max_cox_km"] < 0.01
        assert tab.loc[u, "dif_max_cox_cura_mista"] < 0.03
        assert abs(tab.loc[u, "S_cox(horizonte)"] - tab.loc[u, "fracao_cura_lifelines"]) < 0.02
        assert 0 < tab.loc[u, "S_cox(60)"] < 1 and 0 < tab.loc[u, "S_analitico(60)"] < 1
    # SOD1 não tem efeito do sexo: HR ≈ 1 e IC contém 1; combinado traz HR por lócus
    sod1 = next(u for u in tab.index if u.startswith("SOD1"))
    lo, hi = (float(x) for x in tab.loc[sod1, "IC95 HR[sexo masculino]"].split("–"))
    assert lo <= 1.0 <= hi and tab.loc[sod1, "pi_entrada"] == pytest.approx(0.5387, abs=1e-3)
    assert tab.loc[QUALQUER, "HR[portador " + sod1 + "]"] > 1.5  # SOD1 (π 0,54) manifesta mais que C9orf72 (π 0,33)
    assert "Cox" in out["texto"] and "cura" in out["texto"]


def test_poucos_eventos_nao_ajusta_sem_quebrar(parametros, curada, anotados):
    mae, pai = anotados[1]
    vetor = genotipo.vetor_dosagem(mae, pai, parametros, tabela=curada)
    res = simular_numpy(loci_de_vetor(vetor, parametros, sexo="F"), n=12, seed=1)
    res.sexo = "F"
    out = comparacao.comparar(res, parametros, 90.0)
    assert out["tabela"].cox.str.startswith("não ajustado").all() and out["mensagens"]
    assert out["curvas"] is None and "não ajustado" in out["texto"]


def test_pipeline_com_cox_grava_tabela_11_e_figura_9(dir_cenarios, tmp_path):
    r = pipeline.executar(
        dir_cenarios / "cenario_2_mae.vcf",
        dir_cenarios / "cenario_2_pai.vcf",
        tmp_path / "c2",
        sexo="M",
        n=1500,
        seed=2,
        motor="numpy",
        laudo_c9orf72={"mae": 45, "pai": cenarios.LAUDO_NORMAL},
        base_clinvar=False,
        comparar_cox=True,
    )
    nomes = {t["nome"] for t in r["tabelas"]}
    assert "tabela_11_cox_vs_cura_mista" in nomes and r["cox"]["tabela"].iloc[0]["cox"] == "ajustado"
    assert any(f["png"].endswith("figura_09_cox_vs_cura_mista.png") for f in r["figuras"])
    texto = (tmp_path / "c2" / "relatorio.md").read_text(encoding="utf-8")
    assert "Comparação com o modelo de Cox" in texto and "CoxPHFitter" in texto
    # sem o flag nada disso aparece
    r0 = pipeline.executar(
        dir_cenarios / "cenario_2_mae.vcf",
        dir_cenarios / "cenario_2_pai.vcf",
        tmp_path / "c2b",
        n=500,
        seed=2,
        motor="numpy",
        laudo_c9orf72={"mae": 45, "pai": cenarios.LAUDO_NORMAL},
        base_clinvar=False,
        figuras=False,
    )
    assert r0["cox"] is None and "tabela_11_cox_vs_cura_mista" not in {t["nome"] for t in r0["tabelas"]}
    assert np.isfinite(r0["combinado"]["p_manifesta_qualquer_mc"])
