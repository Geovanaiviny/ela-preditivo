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
