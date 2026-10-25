import numpy as np
import pandas as pd
import pytest
import vcf

from ela_preditivo import cenarios, ingestao


def test_gera_dez_vcfs_e_csv(dir_cenarios):
    arquivos = sorted(p.name for p in dir_cenarios.glob("*.vcf"))
    assert len(arquivos) == 10
    assert (dir_cenarios / "cenarios.csv").exists()
    # todos legíveis pelo PyVCF e com uma amostra
    for a in arquivos:
        r = vcf.Reader(filename=str(dir_cenarios / a))
        assert len(r.samples) == 1
        assert sum(1 for _ in r) >= 5


def test_vcfs_sao_reproduziveis(tmp_path):
    cenarios.gerar_cenarios(tmp_path / "a", seed=7)
    cenarios.gerar_cenarios(tmp_path / "b", seed=7)
    for n in range(1, 6):
        for lado in ("mae", "pai"):
            la = [l for l in (tmp_path / "a" / f"cenario_{n}_{lado}.vcf").read_text().splitlines() if not l.startswith("##fileDate")]
            lb = [l for l in (tmp_path / "b" / f"cenario_{n}_{lado}.vcf").read_text().splitlines() if not l.startswith("##fileDate")]
            assert la == lb


def test_normalizacao_cromossomo_e_regioes():
    assert ingestao.normalizar_cromossomo("chr21") == "21"
    assert ingestao.normalizar_cromossomo("MT") == "M"
    reg = ingestao.carregar_regioes()
    assert set(reg.gene) == {"SOD1", "C9orf72", "TARDBP", "FUS"}
    assert ingestao.gene_da_posicao("chr21", 31659783, reg) == "SOD1"
    assert ingestao.gene_da_posicao("21", 31659509, reg) == "SOD1"   # 157 pb acima do gene, dentro do flanco
    assert ingestao.gene_da_posicao("9", 27573529, reg) == "C9orf72"
    assert ingestao.gene_da_posicao("17", 7675088, reg) is None


def test_motivo_repeticao_biopython():
    assert ingestao.mesmo_motivo("GGGGCC", "GGCCCC")   # complemento reverso (as duas grafias do ClinVar)
    assert ingestao.mesmo_motivo("GGGGCC", "CCGGGG")   # rotação do complemento reverso
    assert not ingestao.mesmo_motivo("GGGGCC", "CAGCAG")
    assert ingestao.contar_repeticoes("GGGGCC" * 31) == 31
    assert ingestao.contar_repeticoes("GGCCCC" * 7) == 7


def test_leitura_cenario_3_mae(dir_cenarios):
    df = ingestao.ler_vcf(dir_cenarios / "cenario_3_mae.vcf")
    assert df.amostra.unique().tolist() == ["MAE"]
    assert set(df.cromossomo) <= {"1", "9", "16", "17", "21"}   # sem prefixo chr
    # expansão detectada
    exp = df[df.tipo == "repeticao"].iloc[0]
    assert exp.gene == "C9orf72" and exp.dosagem == 1 and exp.repeticoes == 45 and exp.aprovado
    # multialélico decomposto em duas linhas, GT 0/2 -> dosagens (0, 1)
    multi = df[(df.cromossomo == "1") & (df.posicao == 11020000)].sort_values("indice_alt")
    assert multi.dosagem.tolist() == [0, 1] and multi.n_alt.tolist() == [2, 2]
    # reprovações
    rep = df[~df.aprovado].set_index("posicao")
    assert rep.loc[7675088, "motivo_reprovacao"] == "fora_das_regioes"
    assert set(rep.loc[31663000, "motivo_reprovacao"].split(";")) == {"filtro_nao_pass", "dp_baixo", "gq_baixo"}
    # variante de risco do pai aparece com GT 0/0 e dosagem 0, aprovada
    a5v = df[df.id == "rs121912442"].iloc[0]
    assert a5v.dosagem == 0 and a5v.aprovado
    res = ingestao.resumo_ingestao(df)
    assert res["registros"] == 8 and res["aprovados"] == 6


def test_filtro_configuravel(dir_cenarios):
    df = ingestao.ler_vcf(dir_cenarios / "cenario_1_pai.vcf", filtro={"dp_minimo": 0, "gq_minimo": 0, "exigir_pass": False})
    assert df.loc[df.posicao == 31663000, "aprovado"].item()


def test_esperado_dos_cenarios():
    e = cenarios.cenario_por_numero(4).esperado
    assert e.heranca.tolist() == ["recessiva"] and e.p_portador_exato.tolist() == [0.25]
    e3 = cenarios.cenario_por_numero(3).esperado.set_index("gene")
    assert e3.loc["SOD1", "dosagem_pai"] == 1 and e3.loc["C9orf72", "dosagem_mae"] == 1
    with pytest.raises(KeyError):
        cenarios.cenario_por_numero(9)
