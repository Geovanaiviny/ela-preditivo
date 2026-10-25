import pandas as pd
import pytest

from ela_preditivo import anotacao, cenarios, genotipo


def test_classificacao_clnsig():
    f = anotacao.classificar_clnsig
    assert f("Pathogenic") == "risco" and f("Likely_pathogenic") == "risco" and f("Pathogenic/Likely_pathogenic") == "risco"
    assert f("Uncertain_significance") == "vus" and f("Conflicting_classifications_of_pathogenicity") == "vus"
    assert f("Benign") == "benigna" and f("Likely_benign") == "benigna" and f("Benign/Likely_benign") == "benigna"
    assert f(None) == "nao_classificada" and f("") == "nao_classificada"


def test_estrelas():
    f = anotacao.estrelas_de_revstat
    assert f("practice_guideline") == 4 and f("reviewed_by_expert_panel") == 3
    assert f("criteria_provided,_multiple_submitters,_no_conflicts") == 2
    assert f("criteria_provided,_single_submitter") == 1 and f("criteria_provided,_conflicting_classifications") == 1
    assert f("no_assertion_criteria_provided") == 0 and f(None) == 0


def test_tabela_curada_integra():
    t = anotacao.carregar_tabela_curada()
    assert len(t) == 6 and set(t.gene) == {"SOD1", "C9orf72", "TARDBP", "FUS"}
    assert (t.conferido_em == "2026-10-24").all()
    assert t.set_index("rs").loc["rs80265967", "heranca"] == "recessiva"


def test_anotacao_cenario_3(anotados):
    mae, pai = anotados[3]
    m = mae.set_index("posicao")
    assert m.loc[27573529, "classe"] == "risco" and m.loc[27573529, "heranca"] == "dominante"
    assert m.loc[31659509, "classe"] == "benigna" and m.loc[31659509, "fonte_anotacao"] == "tabela_curada:posicao_alelos"
    assert m.loc[31185000, "classe"] == "nao_anotada"
    assert m.loc[31659783, "classe"] == "risco" and m.loc[31659783, "dosagem"] == 0
    assert pai.set_index("posicao").loc[31659783, "estrelas"] == 2


def test_anotacao_por_rs_quando_posicao_difere():
    base = pd.DataFrame([{"amostra": "X", "cromossomo": "21", "posicao": 1, "id": "rs121912442", "ref": "C", "alt": "T",
                          "tipo": "snv", "dosagem": 1, "repeticoes": float("nan"), "gene": "SOD1", "aprovado": True}])
    a = anotacao.anotar(base)
    assert a.classe.item() == "risco" and a.fonte_anotacao.item() == "tabela_curada:rs"


@pytest.mark.parametrize("n,classe", [(45, "risco"), (30, "risco"), (27, "intermediaria"), (10, "normal")])
def test_limiar_repeticoes(n, classe):
    base = pd.DataFrame([{"amostra": "X", "cromossomo": "9", "posicao": 27573529, "id": None, "ref": "GGGGCC", "alt": f"<STR{n}>",
                          "tipo": "repeticao", "dosagem": 1, "repeticoes": n, "gene": "C9orf72", "aprovado": True}])
    assert anotacao.anotar(base).classe.item() == classe


def test_variant_summary_carregador(tmp_path):
    cols = ["#AlleleID", "Type", "Name", "GeneID", "GeneSymbol", "HGNC_ID", "GermlineClassification", "ClinSigSimple", "LastEvaluated",
            "RS# (dbSNP)", "nsv/esv (dbVar)", "RCVaccession", "PhenotypeIDS", "PhenotypeList", "Origin", "OriginSimple", "Assembly",
            "ChromosomeAccession", "Chromosome", "Start", "Stop", "ReferenceAllele", "AlternateAllele", "Cytogenetic", "GermlineReviewStatus",
            "NumberSubmitters", "Guidelines", "TestedInGTR", "OtherIDs", "SubmitterCategories", "VariationID", "PositionVCF",
            "ReferenceAlleleVCF", "AlternateAlleleVCF"]
    linhas = [
        ["15", "single nucleotide variant", "NM_000454.5(SOD1):c.14C>T (p.Ala5Val)", "6647", "SOD1", "HGNC:11179", "Pathogenic", "1", "2024-01-01",
         "121912442", "-", "RCV000015885", "", "ALS1", "germline", "germline", "GRCh38", "NC_000021.9", "21", "31659783", "31659783", "C", "T",
         "21q22.11", "criteria provided, multiple submitters, no conflicts", "5", "", "N", "", "2", "13891", "31659783", "C", "T"],
        ["16", "single nucleotide variant", "NM_000454.5(SOD1):c.14C>T (p.Ala5Val)", "6647", "SOD1", "HGNC:11179", "Pathogenic", "1", "2024-01-01",
         "121912442", "-", "RCV000015885", "", "ALS1", "germline", "germline", "GRCh37", "NC_000021.8", "21", "33032096", "33032096", "C", "T",
         "21q22.11", "criteria provided, multiple submitters, no conflicts", "5", "", "N", "", "2", "13891", "33032096", "C", "T"],
        ["99", "Microsatellite", "NM_001256054.3(C9orf72):c.-45+163GGGGCC(>24)", "203228", "C9orf72", "HGNC:28337", "Pathogenic", "1", "2020-01-01",
         "-1", "-", "RCV0001", "", "FTDALS1", "germline", "germline", "GRCh38", "NC_000009.12", "9", "27573529", "27573534", "GGGGCC", "na",
         "9p21.2", "no assertion criteria provided", "1", "", "N", "", "1", "183034", "-1", "na", "na"],
    ]
    p = tmp_path / "variant_summary.txt"
    p.write_text("\t".join(cols) + "\n" + "\n".join("\t".join(l) for l in linhas) + "\n")
    t = anotacao.carregar_variant_summary(p)
    assert len(t) == 1   # só GRCh38 com PositionVCF válido
    r = t.iloc[0]
    assert r.gene == "SOD1" and r.posicao_grch38 == 31659783 and r.rs == "rs121912442" and r.estrelas == 2 and r.classe == "risco"
    assert r.nome_curto == "p.Ala5Val"


def test_desdobrar_frequencias_dbsnp():
    f = anotacao.desdobrar_frequencias("T:0.242812:1216:1000Genomes|T:0.25:5000:ALFA")
    assert f[0]["estudo"] == "1000Genomes" and f[0]["frequencia"] == pytest.approx(0.242812) and f[1]["contagem"] == 5000


@pytest.mark.parametrize("numero", [1, 2, 3, 4, 5])
def test_vetor_dosagem_bate_com_esperado(anotados, parametros, numero):
    mae, pai = anotados[numero]
    v = genotipo.vetor_dosagem(mae, pai, parametros).set_index("gene")
    e = cenarios.cenario_por_numero(numero).esperado.set_index("gene")
    assert set(v.index) == set(e.index)
    for g in e.index:
        assert v.loc[g, "dosagem_mae"] == e.loc[g, "dosagem_mae"]
        assert v.loc[g, "dosagem_pai"] == e.loc[g, "dosagem_pai"]
        assert v.loc[g, "heranca"] == e.loc[g, "heranca"]
        assert v.loc[g, "p_portador_exato"] == pytest.approx(e.loc[g, "p_portador_exato"])


def test_vetor_dosagem_repeticoes_so_no_portador(anotados, parametros):
    mae, pai = anotados[2]
    v = genotipo.vetor_dosagem(mae, pai, parametros).iloc[0]
    assert v.repeticoes_mae == 45 and pd.isna(v.repeticoes_pai)


def test_perfil_variantes(anotados):
    mae, pai = anotados[5]
    p = genotipo.perfil_variantes(mae, pai)
    assert set(p.amostra) == {"MAE", "PAI"} and "benigna" in set(p.classe) and "nao_anotada" in set(p.classe)
