import pytest

from ela_preditivo import anotacao, calibracao, cenarios, ingestao


@pytest.fixture(scope="session")
def parametros():
    return calibracao.carregar_parametros()


@pytest.fixture(scope="session")
def dir_cenarios(tmp_path_factory):
    d = tmp_path_factory.mktemp("sinteticos")
    cenarios.gerar_cenarios(d, seed=2026)
    return d


@pytest.fixture(scope="session")
def anotados(dir_cenarios):
    """{numero: (anotadas_mae, anotadas_pai)} para os 5 cenários."""
    out = {}
    for c in cenarios.CENARIOS:
        mae = anotacao.anotar(ingestao.ler_vcf(dir_cenarios / f"cenario_{c.numero}_mae.vcf"))
        pai = anotacao.anotar(ingestao.ler_vcf(dir_cenarios / f"cenario_{c.numero}_pai.vcf"))
        out[c.numero] = (mae, pai)
    return out
