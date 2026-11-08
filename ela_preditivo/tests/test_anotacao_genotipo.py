import numpy as np
import pandas as pd
import pytest

from ela_preditivo import anotacao, cenarios, genotipo, ingestao


def test_classificacao_clnsig():
    f = anotacao.classificar_clnsig
    assert f("Pathogenic") == "risco" and f("Likely_pathogenic") == "risco" and f("Pathogenic/Likely_pathogenic") == "risco"
    assert f("Uncertain_significance") == "vus" and f("Conflicting_classifications_of_pathogenicity") == "conflitante"
    assert f("Conflicting classifications of pathogenicity") == "conflitante"       # grafia do variant_summary (com espaços); classe própria (Quadro 15)
    assert f("Benign") == "benigna" and f("Likely_benign") == "benigna" and f("Benign/Likely_benign") == "benigna"
    assert f(None) == "nao_classificada" and f("") == "nao_classificada" and f("-") == "nao_classificada"


def test_estrelas():
    f = anotacao.estrelas_de_revstat
    assert f("practice_guideline") == 4 and f("reviewed_by_expert_panel") == 3
    assert f("criteria_provided,_multiple_submitters,_no_conflicts") == 2
    assert f("criteria provided, multiple submitters, no conflicts") == 2
    assert f("criteria_provided,_single_submitter") == 1 and f("criteria_provided,_conflicting_classifications") == 1
    assert f("no_assertion_criteria_provided") == 0 and f(None) == 0


def test_tabela_curada_integra():
    t = anotacao.carregar_tabela_curada()
    assert len(t) == 6 and set(t.gene) == {"SOD1", "C9orf72", "TARDBP", "FUS"}
    assert (t.conferido_em == "2026-10-24").all() and (t.fonte == "tabela_curada").all()
    assert t.set_index("rs").loc["rs80265967", "heranca"] == "recessiva"


def test_anotacao_cenario_3(anotados):
    mae, pai = anotados[3]
    m = mae.set_index("posicao")
    assert m.loc[31659509, "classe"] == "benigna" and m.loc[31659509, "fonte_anotacao"] == "tabela_curada:posicao_alelos"
    assert m.loc[31185000, "classe"] == "nao_anotada"
    assert m.loc[31659783, "classe"] == "risco" and m.loc[31659783, "dosagem"] == 0
    assert pai.set_index("posicao").loc[31659783, "estrelas"] == 2
    assert mae.attrs["vcf"]["montagem"] == "GRCh38"      # metadados do VCF sobrevivem à anotação


def test_anotacao_por_rs_quando_posicao_difere(curada):
    base = pd.DataFrame([{"amostra": "X", "cromossomo": "21", "posicao": 1, "id": "rs121912442", "ref": "C", "alt": "T",
                          "tipo": "snv", "dosagem": 1, "repeticoes": float("nan"), "gene": "SOD1", "aprovado": True}])
    a = anotacao.anotar(base, curada)
    assert a.classe.item() == "risco" and a.fonte_anotacao.item() == "tabela_curada:rs"


def test_rs_ambiguo_nao_anota(curada):
    """Um rs que cobre vários alelos (ex.: FUS p.Arg521Cys/Gly/Ser no ClinVar) só anota pela chave de coordenadas."""
    t = pd.concat([curada, curada[curada.rs == "rs121909668"].assign(alt="G", nome_curto="p.Arg521Gly")], ignore_index=True)
    base = pd.DataFrame([{"amostra": "X", "cromossomo": "16", "posicao": 5, "id": "rs121909668", "ref": "C", "alt": "A",
                          "tipo": "snv", "dosagem": 1, "repeticoes": float("nan"), "gene": "FUS", "aprovado": True}])
    a = anotacao.anotar(base, t)
    assert a.classe.item() == "nao_anotada" and a.fonte_anotacao.item() == "rs_ambiguo:2_alelos"
    base["posicao"] = 31191418
    assert anotacao.anotar(base.assign(alt="G"), t).nome_curto.item() == "p.Arg521Gly"


@pytest.mark.parametrize("n,classe", [(45, "risco"), (30, "risco"), (27, "intermediaria"), (10, "normal")])
def test_limiar_repeticoes(n, classe, curada):
    base = pd.DataFrame([{"amostra": "X", "cromossomo": "9", "posicao": 27573529, "id": None, "ref": "GGGGCC", "alt": f"<STR{n}>",
                          "tipo": "repeticao", "dosagem": 1, "repeticoes": n, "gene": "C9orf72", "aprovado": True}])
    assert anotacao.anotar(base, curada).classe.item() == classe
    assert anotacao.classe_por_repeticoes(n, 30, 24) == classe


COLS_VS = ["#AlleleID", "Type", "Name", "GeneID", "GeneSymbol", "HGNC_ID", "ClinicalSignificance", "ClinSigSimple", "LastEvaluated",
           "RS# (dbSNP)", "nsv/esv (dbVar)", "RCVaccession", "PhenotypeIDS", "PhenotypeList", "Origin", "OriginSimple", "Assembly",
           "ChromosomeAccession", "Chromosome", "Start", "Stop", "ReferenceAllele", "AlternateAllele", "Cytogenetic", "ReviewStatus",
           "NumberSubmitters", "Guidelines", "TestedInGTR", "OtherIDs", "SubmitterCategories", "VariationID", "PositionVCF",
           "ReferenceAlleleVCF", "AlternateAlleleVCF"]
LINHAS_VS = [
    ["15", "single nucleotide variant", "NM_000454.5(SOD1):c.14C>T (p.Ala5Val)", "6647", "SOD1", "HGNC:11179", "Pathogenic", "1", "2024-01-01",
     "121912442", "-", "RCV000015885", "", "ALS1", "germline", "germline", "GRCh38", "NC_000021.9", "21", "31659783", "31659783", "C", "T",
     "21q22.11", "criteria provided, multiple submitters, no conflicts", "5", "", "N", "", "2", "13891", "31659783", "C", "T"],
    ["16", "single nucleotide variant", "NM_000454.5(SOD1):c.14C>T (p.Ala5Val)", "6647", "SOD1", "HGNC:11179", "Pathogenic", "1", "2024-01-01",
     "121912442", "-", "RCV000015885", "", "ALS1", "germline", "germline", "GRCh37", "NC_000021.8", "21", "33032096", "33032096", "C", "T",
     "21q22.11", "criteria provided, multiple submitters, no conflicts", "5", "", "N", "", "2", "13891", "33032096", "C", "T"],
    ["99", "Microsatellite", "NM_001256054.3(C9orf72):c.-45+163GGGGCC(>24)", "203228", "C9orf72", "HGNC:28337", "Pathogenic", "1", "2020-01-01",
     "-1", "-", "RCV0001", "", "FTDALS1", "germline", "germline", "GRCh38", "NC_000009.12", "9", "27573529", "27573534", "GGGGCC", "na",
     "9p21.2", "no assertion criteria provided", "1", "", "N", "", "1", "183034", "-1", "na", "na"],
    ["17", "single nucleotide variant", "NM_000454.5(SOD1):c.272A>C (p.Asp91Ala)", "6647", "SOD1", "HGNC:11179", "Conflicting classifications of pathogenicity", "1",
     "2025-01-01", "80265967", "-", "RCV000015888", "", "ALS1", "germline", "germline", "GRCh38", "NC_000021.9", "21", "31667290", "31667290", "A", "C",
     "21q22.11", "criteria provided, conflicting classifications", "9", "", "N", "", "3", "13894", "31667290", "A", "C"],
    ["18", "single nucleotide variant", "NM_007375.4(TARDBP):c.1A>G (p.Met1Val)", "23435", "MASP2;TARDBP", "HGNC:11571", "Uncertain significance", "0",
     "2025-01-01", "-1", "-", "RCV9", "", "ALS10", "germline", "germline", "GRCh38", "NC_000001.11", "1", "11012700", "11012700", "A", "G",
     "1p36.22", "criteria provided, single submitter", "1", "", "N", "", "1", "9999", "11012700", "A", "G"],
]


@pytest.fixture
def variant_summary_falso(tmp_path):
    p = tmp_path / "variant_summary.txt"
    p.write_text("\t".join(COLS_VS) + "\n" + "\n".join("\t".join(l) for l in LINHAS_VS) + "\n")
    return p


def test_variant_summary_carregador(variant_summary_falso):
    t = anotacao.carregar_variant_summary(variant_summary_falso)
    assert len(t) == 3                       # só GRCh38 com PositionVCF válido; a microssatélite fica de fora
    r = t.set_index("rs").loc["rs121912442"]
    assert r.gene == "SOD1" and r.posicao_grch38 == 31659783 and r.estrelas == 2 and r.classe == "risco" and r.nome_curto == "p.Ala5Val"
    assert r.allele_id == "15" and r.revstat.startswith("criteria provided, multiple") and r.n_submissores == 5 and r.fonte == "clinvar_variant_summary"
    assert t[t.posicao_grch38 == 11012700].gene.item() == "TARDBP"      # GeneSymbol "MASP2;TARDBP" → gene-alvo
    # a mesma tabela em CSV (clinvar_ela_4genes.csv) é lida igual
    csv = variant_summary_falso.with_suffix(".csv")
    pd.read_csv(variant_summary_falso, sep="\t", dtype=str, keep_default_na=False).to_csv(csv, index=False)
    assert len(anotacao.carregar_variant_summary(csv)) == 3


def test_tabela_anotacao_mescla_clinvar_e_curada(variant_summary_falso):
    with pytest.warns(UserWarning, match="prevalece o ClinVar"):
        t = anotacao.tabela_anotacao(base_real=variant_summary_falso)
    assert t.attrs["fontes"]["base_real"] == "clinvar_variant_summary" and t.attrs["fontes"]["n_real"] == 3
    # expansão do C9orf72 (sem posição em VCF no ClinVar) vem da tabela curada; variantes curadas ausentes do ClinVar falso também
    assert (t[t.tipo == "repeticao"].fonte == "tabela_curada").all()
    assert set(t[t.fonte == "tabela_curada"].nome_curto) >= {"M337V", "R521C"}
    # D91A: ClinVar conflitante prevalece (classe conflitante); herança recessiva e divergência registradas
    d = t[(t.posicao_grch38 == 31667290)].iloc[0]
    assert d.classe == "conflitante" and d.heranca == "recessiva" and d.clnsig_curada == "Pathogenic" and "prevalece o ClinVar" in d.divergencia_curada
    # A5V: concordante, sem divergência, herança vinda da curada
    a = t[(t.posicao_grch38 == 31659783)].iloc[0]
    assert a.classe == "risco" and a.heranca == "dominante" and pd.isna(a.divergencia_curada) and a.fonte == "clinvar_variant_summary"
    # sem base real: só a curada
    assert anotacao.tabela_anotacao(base_real=False).attrs["fontes"]["base_real"] is None


def test_clinvar_vcf_carregador(tmp_path):
    p = tmp_path / "clinvar_x.vcf"
    p.write_text("\n".join([
        "##fileformat=VCFv4.1", "##reference=GRCh38", "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
        "21\t31659783\t13891\tC\tT\t.\t.\tALLELEID=15;CLNREVSTAT=criteria_provided,_multiple_submitters,_no_conflicts;CLNSIG=Pathogenic;CLNSIGSCV=SCV1|SCV2;CLNVC=single_nucleotide_variant;GENEINFO=SOD1:6647;RS=121912442;AF_TGP=0.00001",
        "21\t31668167\t14786\tC\t.\t.\t.\tCLNSIG=Pathogenic;GENEINFO=SOD1:6647",                      # sem ALT: ignorada
        "17\t7675088\t1\tC\tT\t.\t.\tCLNSIG=Pathogenic;GENEINFO=TP53:7157",                          # fora dos genes-alvo
    ]) + "\n")
    t = anotacao.carregar_clinvar_vcf(p)
    assert len(t) == 1 and t.iloc[0].rs == "rs121912442" and t.iloc[0].estrelas == 2 and t.iloc[0].n_submissores == 2 and t.iloc[0].fonte == "clinvar_vcf"
    assert anotacao.carregar_base_real(p).equals(t)


def test_desdobrar_frequencias_dbsnp():
    f = anotacao.desdobrar_frequencias("T:0.242812:1216:1000Genomes|T:0.25:5000:ALFA")
    assert f[0]["estudo"] == "1000Genomes" and f[0]["frequencia"] == pytest.approx(0.242812) and f[1]["contagem"] == 5000


def test_indicadores_qualidade(anotados):
    mae, _ = anotados[3]
    ind = anotacao.indicadores_qualidade(mae)
    assert ind["registros"] == 7 and ind["aprovados"] == 5 and ind["anotadas"] == 2 and ind["por_estrelas"] == {1: 1, 2: 1}
    assert ind["n_risco"] == 1 and ind["n_vus"] == 0 and ind["montagem"] == "GRCh38" and ind["montagem_coerente"] is True
    assert ind["risco_com_frequencia_acima_1pct"] == 0


# ---------------------------------------------------------------------------
# Vetor de dosagem: VCF + laudo do C9orf72
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("numero", [1, 2, 3, 4, 5])
def test_vetor_dosagem_bate_com_esperado(anotados, parametros, curada, numero):
    mae, pai = anotados[numero]
    c = cenarios.cenario_por_numero(numero)
    v = genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72=c.laudo_c9orf72, tabela=curada).set_index("gene")
    e = c.esperado.set_index("gene")
    assert set(v.index) == set(e.index)
    for g in e.index:
        assert v.loc[g, "dosagem_mae"] == e.loc[g, "dosagem_mae"]
        assert v.loc[g, "dosagem_pai"] == e.loc[g, "dosagem_pai"]
        assert v.loc[g, "heranca"] == e.loc[g, "heranca"]
        assert v.loc[g, "p_portador_exato"] == pytest.approx(e.loc[g, "p_portador_exato"])
    if "C9orf72" in v.index:
        assert v.loc["C9orf72", "fonte"] == "laudo"


def test_vetor_dosagem_laudo(anotados, parametros, curada):
    mae, pai = anotados[1]      # VCFs sem C9orf72
    v = genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": 45}, tabela=curada).set_index("gene")
    assert v.loc["C9orf72", "dosagem_mae"] == 1 and v.loc["C9orf72", "dosagem_pai"] == 0 and v.loc["C9orf72", "repeticoes_mae"] == 45
    assert pd.isna(v.loc["C9orf72", "repeticoes_pai"]) and v.loc["C9orf72", "heranca"] == "dominante" and v.loc["C9orf72", "clnsig"] == "Pathogenic"
    # dois alelos informados; pai homozigoto expandido
    v2 = genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": (2, 45), "pai": (40, 60)}, tabela=curada).set_index("gene")
    assert v2.loc["C9orf72", "dosagem_mae"] == 1 and v2.loc["C9orf72", "dosagem_pai"] == 2 and v2.loc["C9orf72", "repeticoes_pai"] == 60
    # laudo normal nos dois: nenhum lócus do C9orf72; faixa intermediária gera aviso e não conta como risco
    assert "C9orf72" not in genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": 8, "pai": 2}, tabela=curada).gene.tolist()
    with pytest.warns(UserWarning, match="intermediária"):
        v3 = genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": 27}, tabela=curada)
    assert "C9orf72" not in v3.gene.tolist()


def test_laudo_prevalece_sobre_vcf(tmp_path, parametros, curada):
    rng = np.random.default_rng(3)
    mae = anotacao.anotar(ingestao.ler_vcf(cenarios.escrever_vcf(tmp_path / "m.vcf", "MAE", [cenarios.c9orf72_expansao(45)], rng, incluir_ruido=False)), curada)
    pai = anotacao.anotar(ingestao.ler_vcf(cenarios.escrever_vcf(tmp_path / "p.vcf", "PAI", [cenarios.c9orf72_expansao(45, dosagem=0)], rng, incluir_ruido=False)), curada)
    sem = genotipo.vetor_dosagem(mae, pai, parametros, tabela=curada).iloc[0]            # só VCF: caminho secundário
    assert sem.fonte == "vcf" and sem.dosagem_mae == 1 and "caminho secundário" in sem.observacao
    com = genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": 45}, tabela=curada).iloc[0]
    assert com.fonte == "laudo+vcf" and com.dosagem_mae == 1
    with pytest.warns(UserWarning, match="divergem"):
        div = genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": 45, "pai": 50}, tabela=curada).iloc[0]
    assert div.dosagem_pai == 1 and "prevalece o laudo" in div.observacao
    with pytest.warns(UserWarning, match="prevalece o laudo"):
        assert genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": 10, "pai": 10}, tabela=curada).empty


def test_perfil_variantes(anotados):
    mae, pai = anotados[5]
    p = genotipo.perfil_variantes(mae, pai)
    assert set(p.amostra) == {"MAE", "PAI"} and "benigna" in set(p.classe) and "nao_anotada" in set(p.classe)
