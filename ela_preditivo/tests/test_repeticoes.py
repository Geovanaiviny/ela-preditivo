"""Transmissão do C9orf72 por repetições (extensão experimental)."""

import json

import numpy as np
import pandas as pd
import pytest

from ela_preditivo import cenarios, cli, genotipo, pipeline, repeticoes
from ela_preditivo.monte_carlo import loci_de_vetor


def _executar(dir_cenarios, saida, **kw):
    return pipeline.executar(
        dir_cenarios / "cenario_3_mae.vcf",
        dir_cenarios / "cenario_3_pai.vcf",
        saida,
        sexo="F",
        idade_atual=30,
        n=1500,
        seed=11,
        motor="numpy",
        figuras=False,
        base_clinvar=False,
        **kw,
    )


def test_hipoteses_zeradas_nao_mudam_nada(dir_cenarios, tmp_path):
    base = _executar(dir_cenarios, tmp_path / "base", laudo_c9orf72={"mae": 45, "pai": cenarios.LAUDO_NORMAL})
    zero = _executar(
        dir_cenarios,
        tmp_path / "zero",
        laudo_c9orf72={"mae": 45, "pai": cenarios.LAUDO_NORMAL},
        hipoteses_c9orf72={"delta_mae": 0, "delta_pai": 0, "antecipacao": 0},
    )
    pd.testing.assert_frame_equal(base["resumo"], zero["resumo"])
    pd.testing.assert_frame_equal(base["curvas"], zero["curvas"])
    assert base["combinado"]["p_manifesta_qualquer_mc"] == zero["combinado"]["p_manifesta_qualquer_mc"]
    # sem hipóteses o pipeline nem instancia a extensão
    assert base["transmissao_c9orf72"] is None and "tabela_01c_transmissao_c9orf72" not in {
        t["nome"] for t in base["tabelas"]
    }
    assert zero["transmissao_c9orf72"] is not None and zero["transmissao_c9orf72"].p_portador == 0.5


def test_enumeracao_e_dosagem_efetiva(parametros, curada):
    tr = repeticoes.transmissao_c9orf72(
        {"mae": (28, 45), "pai": 27}, {"delta_mae": 3, "delta_pai": 4, "antecipacao": 0}, parametros, curada
    )
    assert len(tr.genotipos) == 4 and tr.genotipos.probabilidade.sum() == pytest.approx(1.0)
    # 28 + 3 = 31 e 45 + 3 = 48 cruzam ou mantêm o limiar (dosagem efetiva 2); pai 27 + 4 = 31 (1); alelo normal 2 fica 2
    assert (tr.dosagem_laudo_mae, tr.dosagem_laudo_pai) == (1, 0)
    assert (tr.dosagem_efetiva_mae, tr.dosagem_efetiva_pai) == (2, 1)
    assert tr.p_portador == 1.0 and tr.p_portador_sem_hipotese == 0.5
    assert set(tr.genotipos.classe_descendente) == {"risco"}
    assert tr.genotipos.alelo_paterno_transmitido.tolist() == [2, 31, 2, 31]
    # P(portador) por enumeração coincide com a fórmula de dosagem do núcleo
    frac = tr.genotipos.loc[tr.genotipos.classe_descendente == "risco", "probabilidade"].sum()
    assert frac == pytest.approx(tr.p_portador)


def test_delta_so_afeta_alelos_instaveis_e_pode_contrair(parametros, curada):
    mais = repeticoes.transmissao_c9orf72(
        {"mae": 45, "pai": cenarios.LAUDO_NORMAL}, {"delta_mae": 10}, parametros, curada
    )
    assert mais.alelos_mae == (2, 45) and mais.genotipos.alelo_materno_transmitido.tolist() == [2, 2, 55, 55]
    assert mais.p_portador == 0.5  # o alelo normal (2) não muda; o expandido continua expandido
    menos = repeticoes.transmissao_c9orf72(
        {"mae": 45, "pai": cenarios.LAUDO_NORMAL}, {"delta_mae": -20}, parametros, curada
    )
    assert menos.dosagem_efetiva_mae == 0 and menos.p_portador == 0.0 and menos.p_intermediario == pytest.approx(0.5)
    assert repeticoes.transmissao_c9orf72(None, {"delta_mae": 3}, parametros, curada) is None


def test_aplicar_ao_vetor_cria_e_remove_linha(anotados, parametros, curada):
    mae, pai = anotados[1]  # cenário 1: só SOD1 no pai
    # mãe com alelo intermediário (28): sem hipótese não há lócus do C9orf72; com +3 ele é criado
    vetor = genotipo.vetor_dosagem(
        mae, pai, parametros, laudo_c9orf72={"mae": 28, "pai": cenarios.LAUDO_NORMAL}, tabela=curada
    )
    assert (vetor.gene == "C9orf72").sum() == 0
    tr = repeticoes.transmissao_c9orf72({"mae": 28, "pai": cenarios.LAUDO_NORMAL}, {"delta_mae": 3}, parametros, curada)
    v2 = repeticoes.aplicar_ao_vetor(vetor, tr, parametros, curada)
    linha = v2[v2.gene == "C9orf72"].iloc[0]
    assert (linha.dosagem_mae, linha.dosagem_pai, linha.p_portador_exato) == (1, 0, 0.5)
    assert "hipótese" in linha.observacao and linha.clnsig == "Pathogenic"
    # o contrário: lócus existente some quando a contração leva a dosagem efetiva a zero
    vetor = genotipo.vetor_dosagem(
        mae, pai, parametros, laudo_c9orf72={"mae": 45, "pai": cenarios.LAUDO_NORMAL}, tabela=curada
    )
    assert (vetor.gene == "C9orf72").sum() == 1
    tr = repeticoes.transmissao_c9orf72(
        {"mae": 45, "pai": cenarios.LAUDO_NORMAL}, {"delta_mae": -20}, parametros, curada
    )
    v3 = repeticoes.aplicar_ao_vetor(vetor, tr, parametros, curada)
    assert (v3.gene == "C9orf72").sum() == 0 and (v3.gene == "SOD1").sum() == 1


def test_antecipacao_desloca_so_o_c9orf72(anotados, parametros, curada):
    mae, pai = anotados[3]
    vetor = genotipo.vetor_dosagem(
        mae, pai, parametros, laudo_c9orf72={"mae": 45, "pai": cenarios.LAUDO_NORMAL}, tabela=curada
    )
    loci = loci_de_vetor(vetor, parametros, sexo="F")
    novos = repeticoes.aplicar_antecipacao(loci, 5.0)
    for antes, depois in zip(loci, novos):
        if antes.gene == "C9orf72":
            assert depois.dist.mediana == pytest.approx(antes.dist.mediana - 5.0)
        else:
            assert depois is antes
    assert repeticoes.aplicar_antecipacao(loci, 0) == loci


def test_pipeline_com_hipoteses_grava_tabela_1c_relatorio_e_metadados(dir_cenarios, tmp_path):
    r = _executar(
        dir_cenarios,
        tmp_path / "hip",
        laudo_c9orf72={"mae": (28, 45), "pai": 27},
        hipoteses_c9orf72={"delta_mae": 3, "delta_pai": 4, "antecipacao": 5},
    )
    c9 = r["resumo"][r["resumo"].gene == "C9orf72"].iloc[0]
    assert (c9.dosagem_mae, c9.dosagem_pai, c9.p_portador_exato) == (2, 1, 1.0)
    assert "tabela_01c_transmissao_c9orf72" in {t["nome"] for t in r["tabelas"]}
    texto = (tmp_path / "hip" / "relatorio.md").read_text(encoding="utf-8")
    assert "hipótese experimental" in texto and "Δ materno +3" in texto and "deslocada em −5 anos" in texto
    meta = json.loads((tmp_path / "hip" / "metadados.json").read_text(encoding="utf-8"))
    assert meta["hipoteses_c9orf72"] == {"delta_mae": 3, "delta_pai": 4, "antecipacao": 5.0}
    assert meta["transmissao_c9orf72"]["dosagem_efetiva"] == {"mae": 2, "pai": 1}
    assert meta["transmissao_c9orf72"]["rotulo"] == repeticoes.ROTULO_EXPERIMENTAL


def test_cli_hipoteses(tmp_path):
    assert cli.main(["gerar-cenarios", "--saida", str(tmp_path / "s"), "--seed", "1"]) == 0
    args = [
        "executar",
        "--vcf-mae",
        str(tmp_path / "s" / "cenario_2_mae.vcf"),
        "--vcf-pai",
        str(tmp_path / "s" / "cenario_2_pai.vcf"),
        "--saida",
        str(tmp_path / "c2"),
        "--n",
        "500",
        "--motor",
        "numpy",
        "--sem-figuras",
        "--so-tabela-curada",
        "--c9orf72-mae",
        "45",
        "--c9-delta-mae",
        "-20",
        "--c9-antecipacao",
        "2",
    ]
    assert cli.main(args) == 0
    meta = json.loads((tmp_path / "c2" / "metadados.json").read_text(encoding="utf-8"))
    assert meta["hipoteses_c9orf72"] == {"delta_mae": -20, "delta_pai": 0, "antecipacao": 2.0}
    assert meta["loci"] == 0  # a contração tirou o único lócus de risco
    assert np.isnan(float("nan"))  # sanidade do import numpy
