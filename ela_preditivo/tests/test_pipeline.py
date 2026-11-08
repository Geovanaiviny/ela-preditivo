import json
from pathlib import Path

import pytest

from ela_preditivo import cli, pipeline


def test_executar_cenario_3_completo(dir_cenarios, tmp_path):
    r = pipeline.executar(dir_cenarios / "cenario_3_mae.vcf", dir_cenarios / "cenario_3_pai.vcf", tmp_path / "c3", sexo="F", idade_atual=30,
                          n=1500, seed=5, motor="pymc", rotulo="teste", laudo_c9orf72={"mae": 45}, base_clinvar=False)
    assert r["res"] is not None and len(r["loci"]) == 2
    assert (tmp_path / "c3" / "relatorio.md").exists() and (tmp_path / "c3" / "metadados.json").exists()
    meta = json.loads((tmp_path / "c3" / "metadados.json").read_text(encoding="utf-8"))
    assert meta["seed"] == 5 and meta["n"] == 1500 and "aviso_legal" in meta and len(meta["loci"]) == 2
    assert meta["laudo_c9orf72"] == {"mae": 45} and meta["montagem"] == {"mae": "GRCh38", "pai": "GRCh38"}
    assert meta["base_anotacao"]["base_real"] is None and meta["indicadores_qualidade"]["mae"]["montagem_coerente"] is True
    nomes = {t["nome"] for t in r["tabelas"]}
    assert {"tabela_01_variantes_anotadas", "tabela_01b_vetor_dosagem", "tabela_02_aderencia", "tabela_03_risco_vitalicio", "tabela_04_risco_condicional",
            "tabela_04b_risco_condicional_km", "tabela_07_recuperacao_lifelines", "tabela_10_kaplan_meier"} <= nomes
    assert len(r["figuras"]) == 5 and all(Path(f["png"]).stat().st_size > 10_000 for f in r["figuras"])
    texto = (tmp_path / "c3" / "relatorio.md").read_text(encoding="utf-8")
    assert "AVISO" in texto and "Combinado" in texto and "N = 1.500" in texto and "Qualidade dos dados" in texto and "laudo do C9orf72: mae: 45" in texto


def test_executar_sem_locus_de_risco(dir_cenarios, tmp_path):
    # mãe do cenário 1 × mãe do cenário 1: só variantes 0/0, benigna e não anotadas
    r = pipeline.executar(dir_cenarios / "cenario_1_mae.vcf", dir_cenarios / "cenario_1_mae.vcf", tmp_path / "vazio", n=500, motor="numpy", figuras=False, base_clinvar=False)
    assert r["res"] is None and r["vetor"].empty
    assert "Nenhum lócus de risco" in (tmp_path / "vazio" / "relatorio.md").read_text(encoding="utf-8")


def test_cli_gerar_e_executar(tmp_path, capsys):
    assert cli.main(["gerar-cenarios", "--saida", str(tmp_path / "s"), "--seed", "1"]) == 0
    assert cli.main(["executar", "--vcf-mae", str(tmp_path / "s" / "cenario_4_mae.vcf"), "--vcf-pai", str(tmp_path / "s" / "cenario_4_pai.vcf"),
                     "--saida", str(tmp_path / "c4"), "--n", "800", "--motor", "numpy", "--sem-figuras", "--so-tabela-curada"]) == 0
    out = capsys.readouterr().out
    assert "recessiva" in out and "AVISO" in out
    # laudo do C9orf72 pela CLI, com dois alelos
    assert cli.main(["executar", "--vcf-mae", str(tmp_path / "s" / "cenario_2_mae.vcf"), "--vcf-pai", str(tmp_path / "s" / "cenario_2_pai.vcf"),
                     "--saida", str(tmp_path / "c2"), "--n", "800", "--motor", "numpy", "--sem-figuras", "--so-tabela-curada", "--c9orf72-mae", "2", "45"]) == 0
    assert "C9orf72" in capsys.readouterr().out
    assert json.loads((tmp_path / "c2" / "metadados.json").read_text(encoding="utf-8"))["laudo_c9orf72"] == {"mae": [2, 45]}


def test_avaliar_reduzido(dir_cenarios, tmp_path):
    r = pipeline.avaliar(dir_cenarios, tmp_path / "av", numeros=[4], ns=(500, 1000), repeticoes=3, seed=3, n_coerencia=1500, base_clinvar=False)
    assert set(r["estabilidade"].n) == {500, 1000} and r["pulados"] == []
    assert {"tabela_05_estabilidade", "tabela_06_calibracao", "tabela_07_coerencia", "tabela_08_tempos", "tabela_09_sensibilidade"} <= {t["nome"] for t in r["tabelas"]}
    assert len(r["figuras"]) == 3
    # item B7: a faixa 60–75 só é comparada com o risco combinado, e o relatório diz que não é critério de aprovação
    assert "pico_em_60_75" not in r["coerencia"].columns and (r["coerencia"].variante == "qualquer lócus").sum() == 1
    texto = (tmp_path / "av" / "relatorio.md").read_text(encoding="utf-8")
    assert "não critério de aprovação" in texto and "pico_combinado_na_faixa_60_75" in texto
    # item A5: metadados registram a limpeza da pasta
    assert "saida_limpa" in json.loads((tmp_path / "av" / "metadados.json").read_text(encoding="utf-8"))
