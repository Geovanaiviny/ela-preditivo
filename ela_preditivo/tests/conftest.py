import pytest

from ela_preditivo import anotacao, calibracao, cenarios, ingestao


@pytest.fixture(scope="session")
def parametros():
    return calibracao.carregar_parametros()


@pytest.fixture(scope="session")
def curada():
    """Tabela curada sozinha: os testes unitários não dependem de a base real estar na máquina."""
    return anotacao.tabela_anotacao(base_real=False)


@pytest.fixture(scope="session")
def dir_cenarios(tmp_path_factory):
    d = tmp_path_factory.mktemp("sinteticos")
    cenarios.gerar_cenarios(d, seed=2026)
    return d


@pytest.fixture(scope="session")
def anotados(dir_cenarios, curada):
    """{numero: (anotadas_mae, anotadas_pai)} para os 5 cenários, anotados com a tabela curada."""
    out = {}
    for c in cenarios.CENARIOS:
        mae = anotacao.anotar(ingestao.ler_vcf(dir_cenarios / f"cenario_{c.numero}_mae.vcf"), curada)
        pai = anotacao.anotar(ingestao.ler_vcf(dir_cenarios / f"cenario_{c.numero}_pai.vcf"), curada)
        out[c.numero] = (mae, pai)
    return out


@pytest.fixture(scope="session")
def base_real():
    """Base real do ClinVar (dados_reais/ ou ELA_DADOS_BRUTOS); pula o teste se não estiver nesta máquina."""
    p = anotacao.localizar_base_real()
    if p is None:
        pytest.skip("base real do ClinVar não encontrada (ELA_DADOS_BRUTOS / dados_reais/)")
    return p


# ---------------------------------------------------------------------------
# Construtores de arquivos mínimos usados pelos testes das correções da revisão (08/11/2026) e do atualizacao.py
# ---------------------------------------------------------------------------
from pathlib import Path  # noqa: E402

COLS_VS = ["#AlleleID", "Type", "Name", "GeneID", "GeneSymbol", "HGNC_ID", "ClinicalSignificance", "ClinSigSimple", "LastEvaluated",
           "RS# (dbSNP)", "nsv/esv (dbVar)", "RCVaccession", "PhenotypeIDS", "PhenotypeList", "Origin", "OriginSimple", "Assembly",
           "ChromosomeAccession", "Chromosome", "Start", "Stop", "ReferenceAllele", "AlternateAllele", "Cytogenetic", "ReviewStatus",
           "NumberSubmitters", "Guidelines", "TestedInGTR", "OtherIDs", "SubmitterCategories", "VariationID", "PositionVCF",
           "ReferenceAlleleVCF", "AlternateAlleleVCF"]
CABECALHO_VCF = ["##fileformat=VCFv4.2", "##reference=GRCh38",
                 '##INFO=<ID=AC,Number=A,Type=Integer,Description="x">', '##INFO=<ID=AN,Number=1,Type=Integer,Description="x">',
                 '##INFO=<ID=DB,Number=0,Type=Flag,Description="x">', '##FORMAT=<ID=GT,Number=1,Type=String,Description="x">',
                 '##FORMAT=<ID=DP,Number=1,Type=Integer,Description="x">', '##FORMAT=<ID=GQ,Number=1,Type=Integer,Description="x">']


def _linha_vs(allele_id, gene, nome, clnsig, revstat, rs, crom, pos, ref, alt, vid):
    """Uma linha de `variant_summary.txt` (GRCh38) com os campos que o carregador usa."""
    return [str(allele_id), "single nucleotide variant", nome, "1", gene, "HGNC:1", clnsig, "1", "2025-01-01", str(rs), "-", "RCV1", "", "ALS",
            "germline", "germline", "GRCh38", "NC_1", str(crom), str(pos), str(pos), ref, alt, "x", revstat, "1", "", "N", "", "1", str(vid), str(pos), ref, alt]


def _variant_summary_fake(caminho, linhas):
    caminho = Path(caminho)
    caminho.write_text("\t".join(COLS_VS) + "\n" + "\n".join("\t".join(l) for l in linhas) + "\n", encoding="utf-8")
    return caminho


def _vcf_minimo(caminho, amostra, registros):
    """registros: [(cromossomo, posicao, id, ref, alt, gt[, dp, gq]), ...] → VCF 4.2 mono-amostra, GRCh38, FILTER PASS."""
    linhas = list(CABECALHO_VCF) + [f"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t{amostra}"]
    for r in registros:
        crom, pos, rid, ref, alt, gt = r[:6]
        dp, gq = (r[6], r[7]) if len(r) > 6 else (40, 90)
        alelos = [a for a in gt.replace("|", "/").split("/") if a != "."]
        linhas.append(f"chr{crom}\t{pos}\t{rid}\t{ref}\t{alt}\t99\tPASS\tAC={alelos.count('1')};AN={len(alelos)}\tGT:DP:GQ\t{gt}:{dp}:{gq}")
    caminho = Path(caminho)
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


@pytest.fixture
def linha_vs():
    return _linha_vs


@pytest.fixture
def variant_summary_fake():
    return _variant_summary_fake


@pytest.fixture
def vcf_minimo():
    return _vcf_minimo
