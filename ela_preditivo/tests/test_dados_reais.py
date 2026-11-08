"""Testes com o subconjunto real do ClinVar dos quatro genes (TCC 4.2.2). Rodam só quando os arquivos estão na máquina
(`ELA_DADOS_BRUTOS` ou `dados_reais/` na raiz do repositório); caso contrário são pulados (fixture `base_real`)."""
import pandas as pd
import pytest

from ela_preditivo import anotacao, cenarios, genotipo, ingestao, pipeline


@pytest.fixture(scope="module")
def base(base_real):
    return anotacao.carregar_base_real(base_real)


def test_base_real_carrega_os_quatro_genes(base, base_real):
    assert set(base.gene) == {"SOD1", "C9orf72", "TARDBP", "FUS"} and len(base) > 1000
    assert (base.classe == "conflitante").sum() > 0 and base.attrs["base"]["sha256"]       # conflitantes contadas à parte; versão identificada
    assert base.fonte.iloc[0] in {"clinvar_base_consolidada", "clinvar_variant_summary", "clinvar_vcf"}
    assert not base.duplicated(["cromossomo", "posicao_grch38", "ref", "alt"]).any()
    assert base.classe.isin(anotacao.CLASSES).all() and (base.classe == "risco").sum() > 100
    assert base.estrelas.between(0, 4).all()
    # o VCF do ClinVar, quando está ao lado, lê o mesmo recorte
    vcf = base_real.with_name("clinvar_ela_4genes.vcf")
    if vcf.exists():
        v = anotacao.carregar_clinvar_vcf(vcf)
        assert set(v.gene) == set(base.gene) and abs(len(v) - len(base)) < 150


def test_variantes_curadas_batem_com_o_clinvar(base):
    b = base.set_index(["cromossomo", "posicao_grch38", "ref", "alt"])
    a5v = b.loc[("21", 31659783, "C", "T")]
    assert a5v.classe == "risco" and a5v.estrelas == 2 and a5v.rs == "rs121912442" and a5v.nome_curto == "p.Ala5Val"
    assert b.loc[("1", 11022418, "A", "G")].classe == "risco"           # TARDBP p.Met337Val
    assert b.loc[("16", 31191418, "C", "T")].classe == "risco"          # FUS p.Arg521Cys
    assert b.loc[("21", 31659509, "G", "T")].classe == "benigna"        # rs17883296 (exemplo do TCC)
    assert b.loc[("21", 31667290, "A", "C")].classe == "conflitante"    # SOD1 p.Asp91Ala: conflitante no ClinVar (classe própria, Quadro 15)
    # um rs, três alelos no FUS: a chave de coordenadas distingue
    assert len(base[base.rs == "rs121909668"]) >= 2


def test_tabela_mesclada_e_divergencia_d91a(base_real):
    with pytest.warns(UserWarning, match="D91A"):
        t = anotacao.tabela_anotacao(base_real=base_real)
    assert t.attrs["fontes"]["n_curada_extra"] == 1          # só a expansão do C9orf72 vem da curada
    d = t[(t.posicao_grch38 == 31667290) & (t.alt == "C")].iloc[0]
    assert d.classe == "conflitante" and d.heranca == "recessiva" and d.clnsig_curada == "Pathogenic"
    assert t[t.posicao_grch38 == 31659783].iloc[0].heranca == "dominante"


def test_cenarios_sinteticos_contra_base_real(dir_cenarios, parametros, base_real):
    t = anotacao.tabela_anotacao(base_real=base_real)
    esperado_fonte = t.attrs["fontes"]["base_real"]
    for c in cenarios.CENARIOS:
        mae = anotacao.anotar(ingestao.ler_vcf(dir_cenarios / f"cenario_{c.numero}_mae.vcf"), t)
        pai = anotacao.anotar(ingestao.ler_vcf(dir_cenarios / f"cenario_{c.numero}_pai.vcf"), t)
        v = genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72=c.laudo_c9orf72, tabela=t)
        e = c.esperado
        if c.numero == 4:
            assert v.empty                                     # D91A conflitante no ClinVar → não sustenta risco (TCC 4.2.2)
            assert (mae[mae.posicao == 31667290].classe == "conflitante").all()
            continue
        assert set(v.gene) == set(e.gene)
        assert (mae.loc[mae.anotada.fillna(False) & (mae.tipo != "repeticao"), "fonte_anotacao"].str.startswith(esperado_fonte)).all()
        ind = anotacao.indicadores_qualidade(mae)
        assert ind["montagem_coerente"] is True and ind["risco_com_frequencia_acima_1pct"] == 0


def test_pipeline_cenario_3_com_base_real(dir_cenarios, tmp_path, base_real):
    r = pipeline.executar(dir_cenarios / "cenario_3_mae.vcf", dir_cenarios / "cenario_3_pai.vcf", tmp_path / "c3r", sexo="M", n=800, motor="numpy",
                          figuras=False, laudo_c9orf72={"mae": 45}, base_clinvar=base_real)
    assert len(r["loci"]) == 2
    texto = (tmp_path / "c3r" / "relatorio.md").read_text(encoding="utf-8")
    assert "clinvar_" in texto and "p.Ala5Val" in texto
    r4 = pipeline.executar(dir_cenarios / "cenario_4_mae.vcf", dir_cenarios / "cenario_4_pai.vcf", tmp_path / "c4r", n=300, motor="numpy", figuras=False, base_clinvar=base_real)
    assert r4["res"] is None and "Conflicting" in (tmp_path / "c4r" / "relatorio.md").read_text(encoding="utf-8")
