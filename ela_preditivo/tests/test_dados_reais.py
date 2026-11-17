"""Testes com o subconjunto real do ClinVar dos quatro genes (TCC 4.2.2). Rodam só quando os arquivos estão na máquina
(`ELA_DADOS_BRUTOS` ou `dados_reais/` na raiz do repositório); caso contrário são pulados (fixture `base_real`)."""

import warnings

import pandas as pd
import pytest

from ela_preditivo import anotacao, cenarios, genotipo, ingestao, pipeline

D91A = ("21", 31667290, "A", "C")  # SOD1 p.Asp91Ala (rs80265967)


@pytest.fixture(scope="module")
def base(base_real):
    return anotacao.carregar_base_real(base_real)


def test_base_real_carrega_os_quatro_genes(base, base_real):
    assert set(base.gene) == {"SOD1", "C9orf72", "TARDBP", "FUS"} and len(base) > 1000
    assert (base.classe == "conflitante").sum() > 0 and base.attrs["base"][
        "sha256"
    ]  # conflitantes contadas à parte; versão identificada
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
    assert b.loc[("1", 11022418, "A", "G")].classe == "risco"  # TARDBP p.Met337Val
    assert b.loc[("16", 31191418, "C", "T")].classe == "risco"  # FUS p.Arg521Cys
    assert b.loc[("21", 31659509, "G", "T")].classe == "benigna"  # rs17883296 (exemplo do TCC)
    # SOD1 p.Asp91Ala: conflitante no ClinVar, aceita pela regra qualificada (maioria patogênica + herança declarada)
    d = b.loc[D91A]
    assert d.classe == "risco" and bool(d.regra_qualificada) and d.proporcao_patogenica > 0.5
    assert d.heranca_declarada == "recessiva" and "Conflicting" in d.clnsig
    # um rs, três alelos no FUS: a chave de coordenadas distingue
    assert len(base[base.rs == "rs121909668"]) >= 2


def test_impacto_da_regra_qualificada_na_base_real(base, base_real):
    """Números esperados para a base real. Se a base discordar, este teste falha e o caso é reportado antes de seguir."""
    bruto = pd.read_csv(base_real, dtype=str, keep_default_na=False, encoding="utf-8-sig", low_memory=False)
    col = {c.lower().lstrip("#"): c for c in bruto.columns}
    sig = col.get("germlineclassification") or col.get("clinicalsignificance")
    assert len(bruto) == 1463  # variantes na base consolidada (as 1.458 com posição em VCF entram na anotação)
    assert int(bruto[sig].str.contains("Conflicting", case=False).sum()) == 73
    conflitantes = base[base.clnsig.fillna("").str.contains("onflicting")]
    assert int((conflitantes.proporcao_patogenica > 0.5).sum()) == 8  # maioria patogênica
    aceitas = base[base.regra_qualificada.astype(bool)]
    assert len(aceitas) == 1 and tuple(aceitas.iloc[0][["cromossomo", "posicao_grch38", "ref", "alt"]]) == D91A
    assert aceitas.iloc[0].classe == "risco" and aceitas.iloc[0].heranca_declarada == "recessiva"
    assert int((conflitantes.classe == "conflitante").sum()) == 72  # as demais continuam conflitantes


def test_tabela_mesclada_d91a_sem_divergencia(base_real):
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        t = anotacao.tabela_anotacao(base_real=base_real)
    assert not [a for a in avisos if "D91A" in str(a.message)]  # classe final risco = tabela curada: sem divergência
    assert t.attrs["fontes"]["n_curada_extra"] == 1  # só a expansão do C9orf72 vem da curada
    d = t[(t.posicao_grch38 == 31667290) & (t.alt == "C")].iloc[0]
    assert d.classe == "risco" and bool(d.regra_qualificada) and d.heranca == "recessiva" and pd.isna(d.clnsig_curada)
    assert t[t.posicao_grch38 == 31659783].iloc[0].heranca == "dominante"


def test_cenarios_sinteticos_contra_base_real(dir_cenarios, parametros, base_real):
    t = anotacao.tabela_anotacao(base_real=base_real)
    esperado_fonte = t.attrs["fontes"]["base_real"]
    for c in cenarios.CENARIOS:
        mae = anotacao.anotar(ingestao.ler_vcf(dir_cenarios / f"cenario_{c.numero}_mae.vcf"), t)
        pai = anotacao.anotar(ingestao.ler_vcf(dir_cenarios / f"cenario_{c.numero}_pai.vcf"), t)
        v = genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72=c.laudo_c9orf72, tabela=t)
        e = c.esperado
        if c.numero == 4:  # D91A entra pela regra qualificada: herança recessiva, P(portador) 0,25
            assert (mae[mae.posicao == 31667290].classe == "risco").all()
            assert v.iloc[0].heranca == "recessiva" and v.iloc[0].p_portador_exato == pytest.approx(0.25)
        assert set(v.gene) == set(e.gene)
        assert (
            mae.loc[mae.anotada.fillna(False) & (mae.tipo != "repeticao"), "fonte_anotacao"].str.startswith(
                esperado_fonte
            )
        ).all()
        ind = anotacao.indicadores_qualidade(mae)
        assert ind["montagem_coerente"] is True and ind["risco_com_frequencia_acima_1pct"] == 0


def test_pipeline_cenario_3_com_base_real(dir_cenarios, tmp_path, base_real):
    r = pipeline.executar(
        dir_cenarios / "cenario_3_mae.vcf",
        dir_cenarios / "cenario_3_pai.vcf",
        tmp_path / "c3r",
        sexo="M",
        n=800,
        motor="numpy",
        figuras=False,
        laudo_c9orf72={"mae": 45, "pai": cenarios.LAUDO_NORMAL},
        base_clinvar=base_real,
    )
    assert len(r["loci"]) == 2
    texto = (tmp_path / "c3r" / "relatorio.md").read_text(encoding="utf-8")
    assert "clinvar_" in texto and "p.Ala5Val" in texto
    r4 = pipeline.executar(
        dir_cenarios / "cenario_4_mae.vcf",
        dir_cenarios / "cenario_4_pai.vcf",
        tmp_path / "c4r",
        n=300,
        motor="numpy",
        figuras=False,
        base_clinvar=base_real,
        laudo_c9orf72=cenarios.cenario_por_numero(4).laudo_c9orf72,
    )
    texto4 = (tmp_path / "c4r" / "relatorio.md").read_text(encoding="utf-8")
    assert r4["res"] is not None and r4["loci"][0].heranca == "recessiva"
    assert "regra qualificada" in texto4 and "Conflicting" in texto4 and "Aproximação de penetrância" in texto4


def test_avaliar_com_base_real_nao_pula_cenarios(dir_cenarios, tmp_path, base_real):
    av = pipeline.avaliar(
        dir_cenarios,
        tmp_path / "av",
        ns=(200,),
        repeticoes=2,
        n_coerencia=300,
        base_clinvar=base_real,
        mundos=6,
        por_estrato=3,
    )
    assert av["pulados"] == [] and set(av["estabilidade"].cenario) == {f"cenário {n}" for n in range(1, 6)}
    # métricas de verificação com a base real: os cinco cenários e o de parentes entram na coorte
    assert set(av["verificacao"]["coorte"].cenario) == {f"cenário {n}" for n in range(1, 6)} | {"cenário de parentes 1"}
    assert set(av["verificacao"]["robustez"].cenario) == {f"cenário {n}" for n in range(1, 6)}
