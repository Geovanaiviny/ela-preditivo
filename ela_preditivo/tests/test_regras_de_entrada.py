"""Regras de entrada da análise a partir de um registro, pela API: o que cada genitor precisa trazer (VCF próprio,
parente com VCF, filho já testado com variante de risco ou suposição declarada de não portador), a situação clínica do
genitor sem exame e os cenários A a J descritos no README ("Regras de entrada da análise").

Os valores conferidos são os centrais, exatos: não dependem de N nem do motor. O avaliado dos casos de pessoa é um
homem de 36 anos na data de referência; na família, o irmão avaliado tem 33 anos."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from ela_preditivo import DIR_DADOS, cenarios, cli
from ela_preditivo.web import demo, pacientes, textos
from ela_preditivo.web.api import criar_app
from ela_preditivo.web.config import Configuracao, gerar_chave
from ela_preditivo.web.modelos import Auditoria
from ela_preditivo.web.seguranca import Cifra

SINT = DIR_DADOS / "sinteticos"
CASO_1 = SINT / "caso_1_pessoa_com_historico"
CASO_2 = SINT / "caso_2_casal_ou_futuro_filho"
CASO_3 = SINT / "caso_3_familia_com_variante"
PORTADOR = CASO_1 / "parentes_1_avo_paterna.vcf"  # heterozigoto para a SOD1 p.Ala5Val
SEM_VARIANTE_1 = CASO_1 / "parentes_1_mae.vcf"  # sem variante de risco
SEM_VARIANTE_3 = CASO_3 / "parentes_2_mae.vcf"
FILHO_NEGATIVO = CASO_3 / "parentes_2_filho_testado.vcf"  # filho testado, sem variante de risco
PARCEIRA = CASO_2 / "casal_1_mae.vcf"
HOJE = _dt.datetime(2026, 11, 17, 12, 0, 0)  # as idades valem neste dia
SEM_VCF = (
    "sem VCF anexado: anexe o arquivo na ficha, adicione um parente testado ou marque a suposição de não portador."
)
AO_MENOS_UM = "É preciso o VCF de ao menos um genitor."
AVALIADO = ("Avaliado Fictício Regra", "1990-02-10", "M")  # 36 anos
IRMAOS = (("Filho Testado Regra", "1988-01-05", "M"), ("Irmão Avaliado Regra", "1993-01-26", "M"))  # o avaliado: 33


@pytest.fixture(scope="module")
def medico(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("regras")
    cfg = Configuracao(
        chave=gerar_chave().encode(), bd=pasta / "bd.sqlite3", dir_vcfs=pasta / "vcfs", demonstracao=True
    )
    app = criar_app(cfg)
    with app.state.sessoes() as bd:
        cred = {c["email"]: c for c in demo.popular(bd, Cifra(cfg.chave), cfg, analisar=False)["credenciais"]}
    cliente = TestClient(app)
    r = cliente.post(
        "/api/contas/login", json={"email": "medico@demo.local", "senha": cred["medico@demo.local"]["senha"]}
    )
    cliente.headers["X-CSRF-Token"] = r.json()["csrf"]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pacientes, "agora", lambda: HOJE)
        yield cliente
    app.state.analises.encerrar()


_seq = iter(range(1, 10_000))


def registro(medico, tipo="PESSOA", filhos=(AVALIADO,), laudo_mae=None, laudo_pai=None, pai_nasc="1958-05-04"):
    """Registro sem nenhum arquivo: mãe de 64 anos e pai de 68 (ou o parceiro, com a data dada). Devolve (id, filhos)."""
    n = next(_seq)
    corpo = {
        "tipo": tipo,
        "prontuario": f"REGRA-{n:03d}",
        "mae": {"nome": "Mãe Fictícia Regra", "data_nascimento": "1962-07-30", "laudo_c9orf72": laudo_mae},
        "pai": {"nome": "Pai Fictício Regra", "data_nascimento": pai_nasc, "laudo_c9orf72": laudo_pai},
        "descendentes": [{"nome": a, "data_nascimento": b, "sexo": c} for a, b, c in filhos],
        **({} if tipo == "PESSOA" else {"nome": f"Registro Fictício Regra {n}"}),
    }
    r = medico.post("/api/pacientes", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()["id"], [d["id"] for d in r.json()["descendentes"]]


def vcf_do_genitor(medico, pid, papel, arquivo):
    r = medico.post(f"/api/pacientes/{pid}/genitores/{papel}/vcf", files={"vcf": (arquivo.name, arquivo.read_bytes())})
    assert r.status_code == 201, r.text


def parente(medico, pid, papel, parentesco, arquivo=None, laudo=None):
    dados = {"parentesco": parentesco, **({"laudo_c9orf72": str(laudo)} if laudo is not None else {})}
    arquivos = {"vcf": (arquivo.name, arquivo.read_bytes())} if arquivo else None
    r = medico.post(f"/api/pacientes/{pid}/genitores/{papel}/parentes", data=dados, files=arquivos)
    assert r.status_code == 201, r.text
    return r.json()


def situacao(medico, pid, papel, valor, idade=None):
    r = medico.put(f"/api/pacientes/{pid}/genitores/{papel}/situacao", json={"situacao": valor, "idade": idade})
    assert r.status_code == 200, r.text


def enviar_teste_proprio(medico, pid, did, arquivo):
    return medico.post(
        f"/api/pacientes/{pid}/descendentes/{did}/vcf", files={"vcf": (arquivo.name, arquivo.read_bytes())}
    )


def analisar(medico, pid, did=None, **extra):
    dados = {"paciente_id": str(pid), "n": "300", "cox": "0", **{k: str(v) for k, v in extra.items()}}
    if did is not None:
        dados = {"descendente_id": str(did), "confirma_assintomatico": "1", **dados}
    r = medico.post("/api/analises", data=dados)
    return r.status_code, r.json()


def valores(res: dict) -> tuple[float, float]:
    """(herdou ou transmissão, risco da resposta 2), em %, com duas casas."""
    p = res["principais"]
    return round(100 * p["transmissao"], 2), round(100 * p["vida"]["valor"], 2)


def recusada_por(res: dict) -> dict:
    assert res["erro"] == "validacao", res
    return res["campos"]


# ---------------------------------------------------------------------------
# Caso 1 (pessoa): cada genitor precisa de VCF, de parente com VCF ou da suposição declarada
# ---------------------------------------------------------------------------
def test_cenarios_a_b_c_nenhum_genitor_com_vcf_e_cada_um_coberto_por_um_parente(medico):
    pid, (did,) = registro(medico)
    # A: nenhum genitor com VCF, nenhum parente
    status, res = analisar(medico, pid, did)
    assert status == 422 and recusada_por(res) == {"vcf_mae": f"Mãe {SEM_VCF}", "vcf_pai": f"Pai {SEM_VCF}"}
    # B: avó paterna e avó materna testadas, sem a situação clínica dos genitores
    parente(medico, pid, "PAI", "MAE_DO_GENITOR", PORTADOR, laudo=23)
    parente(medico, pid, "MAE", "MAE_DO_GENITOR", SEM_VARIANTE_1)
    status, res = analisar(medico, pid, did)
    campos = recusada_por(res)
    assert status == 422 and sorted(campos) == ["situacao_mae", "situacao_pai"]
    assert (
        campos["situacao_pai"] == "Informe na ficha a situação clínica de Pai (genitor sem exame com parente testado)."
    )
    # C: "situação desconhecida" é resposta válida; dois genitores sem VCF, cada um coberto por um parente, rodam
    situacao(medico, pid, "PAI", "FALECIDO_SEM_ELA", 60)
    situacao(medico, pid, "MAE", "DESCONHECIDA")
    status, res = analisar(medico, pid, did)
    assert status == 201 and valores(res) == (17.15, 8.50)
    assert res["entrada"]["suposicoes"] == {} and res["limite_inferior"] is False and not res["sem_locus"]
    assert {x["genitor_inferido"] for x in res["parentes"]["loci_inferidos"]} == {"mãe", "pai"}


def test_cenario_d_um_genitor_por_parente_e_o_outro_pela_suposicao(medico):
    pid, (did,) = registro(medico)
    parente(medico, pid, "PAI", "MAE_DO_GENITOR", PORTADOR, laudo=23)
    situacao(medico, pid, "PAI", "FALECIDO_SEM_ELA", 60)
    status, res = analisar(medico, pid, did)  # a mãe não tem VCF, parente nem suposição
    assert status == 422 and recusada_por(res) == {"vcf_mae": f"Mãe {SEM_VCF}"}
    status, res = analisar(medico, pid, did, assumir_nao_portador="MAE")
    assert status == 201 and valores(res) == (17.15, 8.50)
    assert res["entrada"]["suposicoes"] == {"nao_portador": ["MAE"], "laudo_normal_suposto": ["MAE"]}


def test_cenario_e_parente_so_com_laudo_nao_dispensa_o_vcf(medico):
    """O laudo do parente informa só o C9orf72 do genitor; para SOD1, TARDBP e FUS continua faltando dado genético.
    Sem VCF de ninguém, nem as duas suposições bastam."""
    pid, (did,) = registro(medico)
    parente(medico, pid, "PAI", "MAE_DO_GENITOR", laudo=45)
    situacao(medico, pid, "PAI", "FALECIDO_SEM_ELA", 60)
    status, res = analisar(medico, pid, did)
    assert status == 422 and recusada_por(res) == {"vcf_mae": f"Mãe {SEM_VCF}", "vcf_pai": f"Pai {SEM_VCF}"}
    status, res = analisar(medico, pid, did, assumir_nao_portador="MAE,PAI")
    assert status == 422 and recusada_por(res) == {"assumir_nao_portador": AO_MENOS_UM}


def test_cenario_f_so_o_tio_testado(medico):
    """Tio portador, avós sem exame (variáveis latentes), pai vivo sem sintomas aos 68 e suposição para a mãe."""
    pid, (did,) = registro(medico)
    parente(medico, pid, "PAI", "IRMAO_DO_GENITOR", PORTADOR)
    situacao(medico, pid, "PAI", "VIVO_ASSINTOMATICO")
    status, res = analisar(medico, pid, did, assumir_nao_portador="MAE")
    assert status == 201 and valores(res) == (15.50, 7.58)
    assert res["parentes"]["genitores"]["pai"]["idade"] == 68


def test_cenario_h_teste_proprio_so_no_caso_de_familia(medico):
    pid, (did,) = registro(medico)
    r = enviar_teste_proprio(medico, pid, did, PORTADOR)
    assert r.status_code == 422 and "só se aplica ao caso 3" in r.json()["campos"]["vcf"]


# ---------------------------------------------------------------------------
# Caso 2 (casal): a mesma regra, com a parceira e o parceiro
# ---------------------------------------------------------------------------
def test_cenario_g_casal_com_o_parceiro_inferido_pela_mae_dele(medico):
    pid, _ = registro(medico, "CASAL", filhos=(), pai_nasc="1991-12-01")  # parceiro de 34 anos
    vcf_do_genitor(medico, pid, "MAE", PARCEIRA)
    parente(medico, pid, "PAI", "MAE_DO_GENITOR", PORTADOR)
    status, res = analisar(medico, pid)
    assert status == 422 and "situacao_pai" in recusada_por(res)
    situacao(medico, pid, "PAI", "VIVO_ASSINTOMATICO")
    status, res = analisar(medico, pid)
    assert status == 201 and valores(res) == (24.49, 13.17) and res["principais"]["condicionado"] is False
    assert res["aviso_parceiro_inferido"] == textos.AVISO_PARCEIRO_INFERIDO  # revela a chance de o parceiro portar


# ---------------------------------------------------------------------------
# Caso 3 (família): o filho já testado
# ---------------------------------------------------------------------------
def test_cenario_i_filho_testado_com_variante_de_risco_basta_para_inferir_os_genitores(medico):
    """O filho positivo prova que um dos genitores porta a variante: sem VCF dos genitores e sem parentes, a análise
    do irmão roda. O filho testado não é analisado como pessoa em risco."""
    pid, (testado, irmao) = registro(medico, "FAMILIA", filhos=IRMAOS)
    assert enviar_teste_proprio(medico, pid, testado, PORTADOR).status_code == 201
    status, res = analisar(medico, pid, irmao)
    assert status == 422 and sorted(recusada_por(res)) == ["situacao_mae", "situacao_pai"]
    situacao(medico, pid, "MAE", "DESCONHECIDA")
    situacao(medico, pid, "PAI", "DESCONHECIDA")
    status, res = analisar(medico, pid, irmao)
    assert status == 201 and valores(res) == (49.14, 25.67)
    assert res["entrada"]["suposicoes"] == {} and res["entrada"]["parentes"]["filhos_testados"] == 1
    status, res = analisar(medico, pid, testado)
    assert status == 422 and "já fez o teste" in recusada_por(res)["descendente_id"]


def test_cenario_j_filho_testado_sem_variante_de_risco_nao_basta_sozinho(medico):
    """Sem VCF dos genitores e sem parentes, o único dado é um filho sem variante de risco: isso não diz qual é o
    genótipo dos genitores. A análise é recusada como em qualquer registro sem dado genético; antes ela rodava e
    devolvia 0 % sem suposição declarada."""
    pid, (testado, irmao) = registro(medico, "FAMILIA", filhos=IRMAOS)
    assert enviar_teste_proprio(medico, pid, testado, FILHO_NEGATIVO).status_code == 201
    situacao(medico, pid, "MAE", "DESCONHECIDA")
    situacao(medico, pid, "PAI", "DESCONHECIDA")
    status, res = analisar(medico, pid, irmao)
    assert status == 422 and recusada_por(res) == {"vcf_mae": f"Mãe {SEM_VCF}", "vcf_pai": f"Pai {SEM_VCF}"}
    status, res = analisar(medico, pid, irmao, assumir_nao_portador="MAE")
    assert status == 422 and recusada_por(res) == {"vcf_pai": f"Pai {SEM_VCF}"}
    status, res = analisar(medico, pid, irmao, assumir_nao_portador="MAE,PAI")
    assert status == 422 and recusada_por(res) == {"assumir_nao_portador": AO_MENOS_UM}


def test_ficha_diz_o_mesmo_que_a_analise_quando_o_unico_dado_e_um_filho_sem_variante_de_risco(medico):
    """Sem VCF dos genitores, sem parentes e com um filho testado negativo, a ficha mostra os genitores sem exame, com
    a mensagem da recusa, e não libera a análise. A conta é feita ao abrir a ficha, com a base de anotação em uso: o VCF
    do filho é lido só em memória, sem gravar arquivo e sem contar como acesso ao VCF na auditoria."""
    app = medico.app
    cfg = app.state.config
    pid, (testado, irmao) = registro(medico, "FAMILIA", filhos=IRMAOS)
    assert enviar_teste_proprio(medico, pid, testado, FILHO_NEGATIVO).status_code == 201

    def arquivos():
        return sorted(str(x.relative_to(cfg.dir_vcfs.parent)) for x in cfg.dir_vcfs.parent.rglob("*"))

    def auditoria():
        with app.state.sessoes() as bd:
            return [a.acao for a in bd.execute(select(Auditoria).order_by(Auditoria.id)).scalars()]

    antes_arquivos, antes_auditoria = arquivos(), auditoria()
    ficha = medico.get(f"/api/pacientes/{pid}").json()
    lista = medico.get("/api/pacientes").json()["pacientes"]
    assert arquivos() == antes_arquivos  # nada gravado: nem VCF decifrado, nem pasta temporária
    novas = auditoria()[len(antes_auditoria) :]
    assert novas and not [a for a in novas if "vcf" in a or "pacote" in a or "documento" in a]
    for papel, rotulo in (("MAE", "Mãe"), ("PAI", "Pai")):
        g = ficha["genitores"][papel]
        assert g["sem_exame"] is True and g["inferido_por_parentes"] is False
        assert g["falta_exame"] == f"{rotulo} {SEM_VCF}" == textos.GENITOR_SEM_VCF.format(rotulo=rotulo)
    assert ficha["pode_analisar"] is False and ficha["genitores_inferidos"] == []
    na_lista = next(x for x in lista if x["id"] == pid)
    assert na_lista["pode_analisar"] is False and na_lista["genitores_inferidos"] == []
    # a análise devolve exatamente o que a ficha já mostrava
    status, res = analisar(medico, pid, irmao)
    assert status == 422 and recusada_por(res) == {
        "vcf_mae": ficha["genitores"]["MAE"]["falta_exame"],
        "vcf_pai": ficha["genitores"]["PAI"]["falta_exame"],
    }

    # com o filho testado positivo, a ficha marca os genitores como inferidos e libera a análise
    pid2, (testado2, _) = registro(medico, "FAMILIA", filhos=IRMAOS)
    assert enviar_teste_proprio(medico, pid2, testado2, PORTADOR).status_code == 201
    ficha2 = medico.get(f"/api/pacientes/{pid2}").json()
    assert ficha2["pode_analisar"] is True and sorted(ficha2["genitores_inferidos"]) == ["MAE", "PAI"]
    assert all(g["sem_exame"] is False and g["falta_exame"] is None for g in ficha2["genitores"].values())

    # mãe com VCF e pai sem nada, com o filho negativo: dá para analisar com a suposição, e a ficha avisa do pai
    pid3, (testado3, _) = registro(medico, "FAMILIA", filhos=IRMAOS)
    vcf_do_genitor(medico, pid3, "MAE", SEM_VARIANTE_3)
    assert enviar_teste_proprio(medico, pid3, testado3, FILHO_NEGATIVO).status_code == 201
    ficha3 = medico.get(f"/api/pacientes/{pid3}").json()
    assert ficha3["pode_analisar"] is True and ficha3["genitores_inferidos"] == []
    assert ficha3["genitores"]["MAE"]["falta_exame"] is None
    assert (
        ficha3["genitores"]["PAI"]["sem_exame"] is True
        and ficha3["genitores"]["PAI"]["falta_exame"] == f"Pai {SEM_VCF}"
    )

    # na tela: o cartão do genitor mostra a mensagem, e os botões de análise desativados repetem o mesmo texto
    js = (Path(pacientes.__file__).parent / "static" / "app.js").read_text(encoding="utf-8")
    assert "g.falta_exame" in js and "'Sem exame'" in js and "function desativarAnalise(" in js
    assert "p.genitores[g].falta_exame" in js


def test_filho_negativo_e_evidencia_quando_ha_outro_dado_genetico(medico):
    """Mãe com VCF, pai sem nada e um filho testado sem variante de risco: o pai continua precisando de parente com VCF
    ou da suposição. Com a suposição declarada, o resultado sem lócus de risco sai marcado como tal, com a suposição."""
    pid, (testado, irmao) = registro(medico, "FAMILIA", filhos=IRMAOS, laudo_mae="23")
    vcf_do_genitor(medico, pid, "MAE", SEM_VARIANTE_3)
    assert enviar_teste_proprio(medico, pid, testado, FILHO_NEGATIVO).status_code == 201
    status, res = analisar(medico, pid, irmao)
    assert status == 422 and recusada_por(res) == {"vcf_pai": f"Pai {SEM_VCF}"}
    status, res = analisar(medico, pid, irmao, assumir_nao_portador="PAI")
    assert status == 201 and res["sem_locus"] is True and res["resumo"] == []
    assert res["entrada"]["suposicoes"] == {"nao_portador": ["PAI"], "laudo_normal_suposto": ["PAI"]}
    # com a avó paterna portadora no lugar da suposição, o teste negativo do filho entra como evidência sobre o pai
    parente(medico, pid, "PAI", "MAE_DO_GENITOR", CASO_3 / "parentes_2_avo_paterna.vcf", laudo=23)
    situacao(medico, pid, "PAI", "VIVO_ASSINTOMATICO")
    status, res = analisar(medico, pid, irmao)
    assert status == 201 and not res["sem_locus"] and res["entrada"]["parentes"]["filhos_testados"] == 1
    assert res["entrada"]["suposicoes"] == {} and 0 < res["principais"]["transmissao"] < 0.25


# ---------------------------------------------------------------------------
# Análise sem registro: sempre os VCFs dos dois genitores
# ---------------------------------------------------------------------------
def test_analise_sem_registro_exige_os_dois_vcfs_e_nao_aceita_suposicao(medico):
    arquivos = {"vcf_mae": (PARCEIRA.name, PARCEIRA.read_bytes())}
    dados = {"n": "300", "cox": "0", "sexo": "M", "assumir_nao_portador": "PAI"}
    r = medico.post("/api/analises", data=dados, files=arquivos)
    assert r.status_code == 422 and r.json()["campos"] == {"vcf_pai": "Envie o arquivo VCF."}


# ---------------------------------------------------------------------------
# Resultado sem lócus de risco: nunca um zero apresentado como risco
# ---------------------------------------------------------------------------
def test_csv_do_pesquisador_nao_escreve_zero_para_analise_sem_locus_de_risco():
    from ela_preditivo.web import pesquisa

    sem_locus = {
        "sem_locus": True,
        "executado_em": "2026-11",
        "modo": "vcf",
        "motor": "pymc",
        "n": 300,
        "hipoteses": False,
        "suposicoes": {"nao_portador": ["PAI"]},
        "genes_de_risco": [],
        "herancas": [],
        "p_portador_desde_nascimento": 0.0,
        "risco_vitalicio": 0.0,
        "risco_vitalicio_q025": 0.0,
        "risco_vitalicio_q975": 0.0,
        "F_desde_nascimento": {"50": 0.0, "60": 0.0, "70": 0.0},
        "condicionado": True,
        "faixa_idade_referencia": "30-39",
        "p_portador": 0.0,
        "risco_residual": 0.0,
        "janelas": {"10": {"valor": 0.0}, "20": {"valor": 0.0}},
        "inicio": {},
    }
    com_locus = {
        **sem_locus,
        "sem_locus": False,
        "genes_de_risco": ["SOD1"],
        "herancas": ["dominante"],
        "p_portador_desde_nascimento": 0.5,
        "risco_vitalicio": 0.25,
        "p_portador": 0.4,
    }
    pessoa = lambda i, a: {"indice": i, "sexo": "M", "faixa_etaria": "30-39", "analise": a}  # noqa: E731
    caso = {
        "codigo": "abc123",
        "tipo": "FAMILIA",
        "momento": None,
        "futuro_filho": None,
        "descendentes": [pessoa(1, sem_locus), pessoa(2, com_locus), pessoa(3, None)],
    }
    cabecalho, *linhas = pesquisa.csv_casos([caso]).splitlines()
    sem, com, nada = (dict(zip(cabecalho.split(";"), linha.split(";"))) for linha in linhas)
    probabilidades = [c for c in cabecalho.split(";") if c.startswith(("p_", "risco_", "F_", "inicio_"))]
    assert sem["genes_de_risco"] == "nenhum lócus de risco encontrado" == pesquisa.SEM_LOCUS_NO_CSV
    assert len(probabilidades) == 19 and all(sem[c] == "" for c in probabilidades)  # nenhum zero escrito como risco
    assert (sem["motor"], sem["suposicao_nao_portador"], sem["faixa_idade_referencia"]) == ("pymc", "PAI", "30-39")
    assert com["genes_de_risco"] == "SOD1" and com["p_transmissao"] == "0,5000" and com["risco_vitalicio"] == "0,2500"
    assert com["p_portador_sem_sintomas"] == "0,4000" and com["risco_10_anos"] == "0,0000"
    assert nada["genes_de_risco"] == "" and nada["motor"] == ""  # pessoa sem análise: linha vazia, sem o texto


SEM_VARIANTE_NOS_GENES = "lido como genitor sem variante nos genes avaliados (o C9orf72 vem do laudo)"
TEXTO_SEM_REGISTRO = {  # um texto por situação, com a montagem e as contagens lidas (N) e dentro dos genes (M)
    "cabecalho": f"montagem GRCh38 (coerente); nenhum registro no arquivo; {SEM_VARIANTE_NOS_GENES}",
    "fora": f"montagem GRCh38 (coerente); 1 registro lido, fora dos genes avaliados; {SEM_VARIANTE_NOS_GENES}",
    "qualidade": "montagem GRCh38 (coerente); nenhum registro aprovado no filtro de qualidade (1 lido, 1 no gene "
    f"avaliado); {SEM_VARIANTE_NOS_GENES}",
}


@pytest.fixture
def vcfs_sem_registros_aproveitaveis(tmp_path):
    rng = np.random.default_rng(1)
    arquivos = {
        "cabecalho": cenarios.escrever_vcf(tmp_path / "cabecalho.vcf", "CAB", [], rng, incluir_ruido=False),
        "fora": cenarios.escrever_vcf_sem_variantes(tmp_path / "fora.vcf", "FORA"),
    }
    pai = CASO_1 / "cenario_1_pai.vcf"
    linhas = pai.read_text(encoding="utf-8").splitlines()
    for linha in linhas:
        if "\trs121912442\t" in linha:
            campos = linha.split("\t")
            campos[6] = "LowQual"
            arquivos["qualidade"] = tmp_path / "qualidade.vcf"
            arquivos["qualidade"].write_text(
                "\n".join([*(l for l in linhas if l.startswith("#")), "\t".join(campos)]) + "\n",
                encoding="utf-8",
            )
            break
    return arquivos


@pytest.mark.parametrize("caso", ["cabecalho", "fora", "qualidade"])
def test_cli_genitor_sem_registros_aproveitaveis(caso, vcfs_sem_registros_aproveitaveis, tmp_path):
    saida = tmp_path / "resultado"
    assert (
        cli.main(
            [
                "executar",
                "--vcf-mae",
                str(vcfs_sem_registros_aproveitaveis[caso]),
                "--vcf-pai",
                str(CASO_1 / "cenario_1_pai.vcf"),
                "--saida",
                str(saida),
                "--c9orf72-mae",
                "23",
                "--c9orf72-pai",
                "23",
                "--n",
                "300",
                "--sem-figuras",
            ]
        )
        == 0
    )
    meta = json.loads((saida / "metadados.json").read_text(encoding="utf-8"))
    assert meta["loci"]
    assert set(meta["tempo_motores_s"]) == {"pymc", "numpy"}
    assert all(tempo > 0 for tempo in meta["tempo_motores_s"].values())
    texto = (saida / "relatorio.md").read_text(encoding="utf-8")
    assert f"- Mãe: {TEXTO_SEM_REGISTRO[caso]}." in texto
    assert "- Pai: montagem GRCh38 (coerente); " in texto and "registros aprovados" in texto.split("- Pai: ")[1]


def test_analise_avulsa_genitor_sem_registros_aproveitaveis(medico, vcfs_sem_registros_aproveitaveis):
    pai = CASO_1 / "cenario_1_pai.vcf"
    dados = {"n": "300", "cox": "0", "sexo": "M", "c9orf72_mae": "23", "c9orf72_pai": "23"}
    referencia = CASO_1 / "cenario_1_mae.vcf"
    resultados = {}
    for caso, mae in {"referencia": referencia, **vcfs_sem_registros_aproveitaveis}.items():
        arquivos = {"vcf_mae": (mae.name, mae.read_bytes()), "vcf_pai": (pai.name, pai.read_bytes())}
        r = medico.post("/api/analises", data=dados, files=arquivos)
        assert r.status_code == 201, r.text
        resultado = r.json()
        assert not resultado["sem_locus"]
        principais = resultado["principais"]
        resultados[caso] = (principais["transmissao"], principais["vida"]["valor"])
        if caso != "referencia":
            assert resultado["avisos_qualidade_vcf"] == {"mae": TEXTO_SEM_REGISTRO[caso]}
    assert all(v == resultados["referencia"] for v in resultados.values())
    vazio = vcfs_sem_registros_aproveitaveis["cabecalho"]
    arquivos = {lado: (vazio.name, vazio.read_bytes()) for lado in ("vcf_mae", "vcf_pai")}
    r = medico.post("/api/analises", data=dados, files=arquivos)
    assert r.status_code == 201, r.text
    assert r.json()["sem_locus"]
    assert r.json()["metadados"]["tempo_motores_s"] == {"pymc": None, "numpy": None}


def test_ficha_mostra_aviso_do_vcf_apenas_com_cabecalho(medico, vcfs_sem_registros_aproveitaveis):
    painel = "/api/pacientes/painel"
    total = medico.get(painel).json()["totais"]["pendencias_analise"]
    pid, [did] = registro(medico, laudo_mae="23", laudo_pai="23")
    assert medico.get(painel).json()["totais"]["pendencias_analise"] == total + 1
    vcf_do_genitor(medico, pid, "MAE", vcfs_sem_registros_aproveitaveis["cabecalho"])
    pendencias = medico.get(painel).json()
    assert pendencias["totais"]["pendencias_analise"] == total
    assert all(p["id"] != pid for p in pendencias["pendencias"]["sem_dados_para_analise"])
    vcf_do_genitor(medico, pid, "PAI", CASO_1 / "cenario_1_pai.vcf")
    status, resultado = analisar(medico, pid, did)
    assert status == 201, resultado
    assert not resultado["sem_locus"]
    ficha = medico.get(f"/api/pacientes/{pid}").json()
    assert ficha["genitores"]["MAE"]["aviso_qualidade"] == TEXTO_SEM_REGISTRO["cabecalho"]
    assert "aviso_qualidade" not in ficha["genitores"]["PAI"] or not ficha["genitores"]["PAI"]["aviso_qualidade"]


def test_analise_avulsa_cita_nome_do_vcf_enviado(medico):
    dados = {"n": "300", "cox": "0", "sexo": "M"}
    pai = CASO_1 / "cenario_1_pai.vcf"
    grch37 = b"##fileformat=VCFv4.2\n##reference=GRCh37\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tM\n"
    r = medico.post(
        "/api/analises",
        data=dados,
        files={
            "vcf_mae": ("amostra-original.vcf", grch37),
            "vcf_pai": (pai.name, pai.read_bytes()),
        },
    )
    assert r.status_code == 422, r.text
    assert "amostra-original.vcf" in r.text


# ---------------------------------------------------------------------------
# Aviso de qualidade só para genitor com VCF próprio; genitor assumido ou inferido não tem arquivo a avisar
# ---------------------------------------------------------------------------


def linha_da_qualidade(res: dict, rotulo: str) -> str:
    secao = next(s for s in res["secoes"] if s["titulo"].startswith("Qualidade dos dados"))
    return next(l for l in secao["texto"].splitlines() if l.startswith(f"- {rotulo}:"))


def test_genitor_assumido_sem_vcf_nao_mostra_registros_nem_aviso(medico):
    pid, (did,) = registro(medico, laudo_mae="23", laudo_pai="23")
    vcf_do_genitor(medico, pid, "PAI", CASO_1 / "cenario_1_pai.vcf")
    status, res = analisar(medico, pid, did, assumir_nao_portador="MAE")
    assert status == 201, res
    assert res["entrada"]["suposicoes"]["nao_portador"] == ["MAE"]
    mae = linha_da_qualidade(res, "Mãe")
    assert mae == "- Mãe: sem VCF; genitor assumido sem variante de risco (limite inferior)."
    assert "registro" not in mae and "regiões" not in mae
    assert "registros aprovados" in linha_da_qualidade(res, "Pai")  # quem tem VCF continua com a leitura completa
    assert res["avisos_qualidade_vcf"] == {}
    ficha = medico.get(f"/api/pacientes/{pid}").json()
    assert not ficha["genitores"]["MAE"].get("aviso_qualidade")
    assert not ficha["genitores"]["PAI"].get("aviso_qualidade")


def test_genitor_inferido_por_parente_nao_mostra_registros_nem_aviso(medico):
    pid, (did,) = registro(medico, laudo_mae="23", laudo_pai="23")
    vcf_do_genitor(medico, pid, "MAE", SEM_VARIANTE_1)
    parente(medico, pid, "PAI", "MAE_DO_GENITOR", PORTADOR, laudo=23)
    situacao(medico, pid, "PAI", "FALECIDO_SEM_ELA", 60)
    status, res = analisar(medico, pid, did)
    assert status == 201, res
    pai = linha_da_qualidade(res, "Pai")
    assert pai == "- Pai: sem VCF próprio; dosagem inferida a partir de parente testado."
    assert "registro" not in pai
    assert res["avisos_qualidade_vcf"] == {}
    assert not medico.get(f"/api/pacientes/{pid}").json()["genitores"]["PAI"].get("aviso_qualidade")


def test_vcf_so_com_cabecalho_no_genitor_assumido_continua_gerando_o_aviso(medico, vcfs_sem_registros_aproveitaveis):
    """Mesmo genitor do teste do assumido, agora com um arquivo que só tem cabeçalho: o aviso do arquivo aparece."""
    pid, (did,) = registro(medico, laudo_mae="23", laudo_pai="23")
    vcf_do_genitor(medico, pid, "MAE", vcfs_sem_registros_aproveitaveis["cabecalho"])
    vcf_do_genitor(medico, pid, "PAI", CASO_1 / "cenario_1_pai.vcf")
    status, res = analisar(medico, pid, did)
    assert status == 201, res
    assert res["avisos_qualidade_vcf"] == {"mae": TEXTO_SEM_REGISTRO["cabecalho"]}
    assert linha_da_qualidade(res, "Mãe") == f"- Mãe: {TEXTO_SEM_REGISTRO['cabecalho']}."


# ---------------------------------------------------------------------------
# Campos que a tela usa, painel de pendências e a lista de situações da ficha
# ---------------------------------------------------------------------------


def test_painel_conta_pendencias_inferidos_e_lista_so_o_que_falta(medico):
    painel = "/api/pacientes/painel"
    antes = medico.get(painel).json()["totais"]
    sem_dados, _ = registro(medico)  # nenhum dado genético
    um_vcf, _ = registro(medico)
    vcf_do_genitor(medico, um_vcf, "MAE", SEM_VARIANTE_1)
    inferido, _ = registro(medico)
    parente(medico, inferido, "PAI", "MAE_DO_GENITOR", PORTADOR, laudo=23)
    situacao(medico, inferido, "PAI", "FALECIDO_SEM_ELA", 60)
    vcf_do_genitor(medico, inferido, "MAE", SEM_VARIANTE_1)
    d = medico.get(painel).json()
    assert d["totais"]["pendencias_analise"] == antes["pendencias_analise"] + 1
    assert d["totais"]["com_genitor_inferido"] == antes["com_genitor_inferido"] + 1
    sem = [p["id"] for p in d["pendencias"]["sem_dados_para_analise"]]
    assert sem_dados in sem and um_vcf not in sem and inferido not in sem
    assert not medico.get(f"/api/pacientes/{sem_dados}").json()["pode_analisar"]
    assert medico.get(f"/api/pacientes/{um_vcf}").json()["pode_analisar"] is True  # o outro genitor pode ser assumido
    assert medico.get(f"/api/pacientes/{inferido}").json()["genitores_inferidos"] == ["PAI"]


def test_ficha_e_painel_devolvem_os_campos_de_risco_que_a_tela_usa(medico):
    pid, (did,) = registro(medico, laudo_mae="23", laudo_pai="23")
    vcf_do_genitor(medico, pid, "MAE", CASO_1 / "cenario_1_mae.vcf")
    vcf_do_genitor(medico, pid, "PAI", CASO_1 / "cenario_1_pai.vcf")
    status, res = analisar(medico, pid, did)
    assert status == 201, res
    ficha = medico.get(f"/api/pacientes/{pid}").json()
    campos = ("condicionado", "idade_referencia", "p_manifesta", "risco_vitalicio")
    assert ficha["ultima_analise"] and all(c in ficha["ultima_analise"] for c in campos)
    assert ficha["ultimas_por_descendente"] and all(
        all(c in u for c in campos) for u in ficha["ultimas_por_descendente"].values()
    )
    assert ficha["ultima_analise"]["condicionado"] is True  # o avaliado tem 36 anos e está sem sintomas
    recentes = medico.get("/api/pacientes/painel").json()["analises_recentes"]
    assert recentes and all(c in recentes[0] for c in campos)


def test_situacao_clinica_comeca_vazia_e_desabilitada_e_a_regra_do_servidor_nao_mudou(medico):
    js = (Path(pacientes.__file__).parent / "static" / "app.js").read_text(encoding="utf-8")
    assert "opcao.disabled = def.placeholderVazio && valor === ''" in js  # a opção vazia não pode ser reescolhida
    assert "placeholderVazio: true" in js
    pid, (did,) = registro(medico)
    parente(medico, pid, "PAI", "MAE_DO_GENITOR", PORTADOR, laudo=23)
    parente(medico, pid, "MAE", "MAE_DO_GENITOR", SEM_VARIANTE_1)
    status, res = analisar(medico, pid, did)  # parente testado sem a situação clínica: continua recusado
    assert status == 422 and sorted(recusada_por(res)) == ["situacao_mae", "situacao_pai"]
    situacao(medico, pid, "PAI", "DESCONHECIDA")  # "Situação desconhecida" é uma resposta aceita pelo servidor
    situacao(medico, pid, "MAE", "DESCONHECIDA")
    assert analisar(medico, pid, did)[0] == 201
