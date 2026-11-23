"""Roteiro de testes da plataforma, pela API: as sete fichas de teste nos três casos de atendimento, o motor padrão,
o número de repetições do laudo do C9orf72 (ausente, com e sem o arquivo anexado, inválido) e o VCF de um só genitor.

Os valores centrais conferidos são exatos (não dependem de N nem do motor); a banda de 95 % vem da simulação e muda
na primeira casa decimal conforme o motor e o N, por isso só a ordem dela é conferida."""

from __future__ import annotations

import itertools
import datetime as _dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ela_preditivo import DIR_DADOS, cenarios
from ela_preditivo import documentos_ficticios as docs
from ela_preditivo.web import analises, demo, pacientes, textos
from ela_preditivo.web.api import criar_app
from ela_preditivo.web.config import Configuracao, gerar_chave
from ela_preditivo.web.seguranca import Cifra

SINT = DIR_DADOS / "sinteticos"
JS = (Path(analises.__file__).parent / "static" / "app.js").read_text(encoding="utf-8")
FICHAS = {f.codigo: f for f in docs.FICHAS_DE_TESTE}
TIPO = {1: "PESSOA", 2: "CASAL", 3: "FAMILIA"}
MOMENTO = {rotulo: chave for chave, rotulo in textos.MOMENTOS.items()}
# data de referência das fichas: as idades do roteiro (32, 36, 27, 50, 45 e 33 anos) valem nesse dia
HOJE = _dt.datetime(2026, 11, 17, 12, 0, 0)
SITUACAO = {"1B": ("FALECIDO_SEM_ELA", 60), "3B": ("VIVO_ASSINTOMATICO", None)}

# valores do roteiro, em % (uma casa) e em anos: herdou ou transmissão, risco (residual na pessoa, vitalício no futuro
# filho), janelas de 10 e 20 anos ou F aos 50, 60 e 70 anos, início (mediana, 25 % e 75 %) e genes de risco
ESPERADO = {
    ("1A", "Beatriz"): (74.6, 38.1, {"10": 5.3, "20": 16.7}, (54, 46, 61), ["C9orf72", "SOD1"]),
    ("1B", "Caio"): (17.2, 8.5, {"10": 2.2, "20": 5.6}, (52, 46, 59), ["SOD1"]),
    ("1C", "Mateus"): (74.5, 25.2, {"10": 2.3, "20": 6.5}, (57, 47, 65), ["FUS", "TARDBP"]),
    ("2A", None): (50.0, 16.6, {"50": 3.6, "60": 9.5, "70": 15.2}, (None, 51, 65), ["C9orf72"]),
    ("2B", None): (25.0, 13.5, {"50": 6.3, "60": 11.0, "70": 13.2}, (None, 43, 58), ["SOD1"]),
    ("3A", "Renata"): (20.0, 7.6, {"10": 5.0}, (57, 54, 62), ["SOD1"]),
    ("3A", "Sérgio"): (21.9, 9.8, {"10": 5.0}, (55, 50, 60), ["SOD1"]),
    ("3B", "Larissa"): (10.2, 5.1, {"10": 1.0, "20": 2.8}, (52, 45, 58), ["SOD1"]),
}


def iso(data: str) -> str:
    d, m, a = data.split("/")
    return f"{a}-{m}-{d}"


@pytest.fixture(scope="module")
def medico(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("fichas")
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
        mp.setattr(pacientes, "agora", lambda: HOJE)  # idades das fichas no dia de referência
        yield cliente
    app.state.analises.encerrar()


_SEQUENCIA_CADASTRO = itertools.count(1)


def cadastrar(medico, codigo: str, numero=None, pdf_laudo=None, vcf=None, parente=True) -> dict:
    """Cadastra a ficha com os arquivos de `data/sinteticos`. `numero` troca o nº de repetições digitado de um lado
    (None = campo vazio); `pdf_laudo` e `vcf` dizem quais lados recebem o arquivo (padrão: os da ficha)."""
    f = FICHAS[codigo]
    pasta = cenarios.pasta_caso(SINT, f.caso)
    numero = numero or {}

    def genitor(lado, g):
        n = numero[lado] if lado in numero else (None if g.repeticoes is None else str(g.repeticoes))
        return {"nome": g.nome, "data_nascimento": iso(g.nascimento), "laudo_c9orf72": n}

    corpo = {
        "tipo": TIPO[f.caso],
        # cada cadastro é um registro novo: o número de prontuário não se repete dentro do mesmo médico, e vários
        # testes cadastram a mesma ficha mais de uma vez para montar cenários diferentes
        "prontuario": f"{f.prontuario}-{next(_SEQUENCIA_CADASTRO)}",
        "momento": MOMENTO[f.momento],
        "mae": genitor("mae", f.mae),
        "pai": genitor("pai", f.pai),
        "descendentes": [
            {"nome": d.nome, "data_nascimento": iso(d.nascimento), "sexo": d.sexo[0]} for d in f.descendentes
        ],
        **({"nome": f.registro} if f.registro else {}),
    }
    r = medico.post("/api/pacientes", json=corpo)
    if r.status_code != 201:
        return {"status": r.status_code, "campos": r.json().get("campos", {})}
    pid = r.json()["id"]
    dids = {d["nome"].split()[0]: d["id"] for d in r.json()["descendentes"]}

    def enviar(caminho, campo, nome, dados=None):
        resposta = medico.post(
            f"/api/pacientes/{pid}/{caminho}", data=dados or {}, files={campo: (nome, (pasta / nome).read_bytes())}
        )
        assert resposta.status_code == 201, (codigo, nome, resposta.text)

    enviar("documentos", "arquivo", f.nome_do_prontuario, {"tipo": "PRONTUARIO"})
    for lado in sorted({lado for lado, _ in f.laudos()} if pdf_laudo is None else pdf_laudo):
        enviar("documentos", "arquivo", f.nome_do_laudo(lado), {"tipo": "LAUDO_C9ORF72", "papel": lado.upper()})
    for lado, g in (("mae", f.mae), ("pai", f.pai)):
        if g.vcf and (vcf is None or lado in vcf):
            enviar(f"genitores/{lado.upper()}/vcf", "vcf", g.vcf)
        if not g.vcf and g.parente and parente:  # genitor sem exame: situação clínica e a mãe dele, testada
            situacao, idade = SITUACAO[codigo]
            r = medico.put(
                f"/api/pacientes/{pid}/genitores/{lado.upper()}/situacao", json={"situacao": situacao, "idade": idade}
            )
            assert r.status_code == 200, r.text
            _, arquivo, repeticoes = g.parente
            dados = {"parentesco": "MAE_DO_GENITOR", "laudo_c9orf72": str(repeticoes)}
            enviar(f"genitores/{lado.upper()}/parentes", "vcf", arquivo, dados)
    for d in f.descendentes:
        if d.vcf:  # filho que já fez o teste
            enviar(f"descendentes/{dids[d.nome.split()[0]]}/vcf", "vcf", d.vcf)
    return {"pid": pid, "dids": dids}


def analisar(medico, pid: int, did: int | None = None, **extra):
    dados = {"paciente_id": str(pid), "n": "300", "cox": "0", **{k: str(v) for k, v in extra.items()}}
    if did is not None:
        dados = {"descendente_id": str(did), "confirma_assintomatico": "1", **dados}
    r = medico.post("/api/analises", data=dados)
    return r.status_code, r.json()


def genes(res: dict) -> list[str]:
    return sorted(x["gene"] for x in res["resumo"])


def pct(x) -> float:
    return round(100 * float(x), 1)


# ---------------------------------------------------------------------------
# Motor padrão
# ---------------------------------------------------------------------------
def test_motor_padrao_da_plataforma_e_o_pymc_e_o_numpy_segue_disponivel():
    assert analises.Execucao().motor == "pymc" and analises.MOTORES == ("pymc", "numpy")
    assert "valores.motor || 'pymc'" in JS and "valores.motor || 'numpy'" not in JS
    seletor = JS[JS.index("nome: 'motor'") :][:600]
    assert seletor.index("['pymc', 'PyMC (motor declarado no TCC") < seletor.index("['numpy', 'NumPy (")
    assert "mais lento" not in seletor  # os dois motores rodam em toda análise, com o mesmo N


# ---------------------------------------------------------------------------
# As sete fichas, nos três casos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("codigo", ["1A", "1B", "1C", "2A", "2B", "3A", "3B"])
def test_ficha_do_roteiro_da_os_valores_esperados_com_o_motor_padrao(medico, codigo):
    c = cadastrar(medico, codigo)
    ficha = FICHAS[codigo]
    for (cod, quem), (herdou, risco, pontos, inicio, genes_esperados) in ESPERADO.items():
        if cod != codigo:
            continue
        extra = {"assumir_nao_portador": "PAI"} if codigo == "2A" else {}  # parceiro sem exame
        status, res = analisar(medico, c["pid"], c["dids"][quem] if quem else None, **extra)
        assert status == 201, res
        p = res["principais"]
        assert res["entrada"]["motor"] == "pymc" and res["entrada"]["tipo"] == TIPO[ficha.caso]
        assert genes(res) == genes_esperados and res["c9orf72_indeterminado"] is False and not res["sem_locus"]
        assert (pct(p["transmissao"]), pct(p["vida"]["valor"])) == (herdou, risco), (codigo, quem)
        assert p["vida"]["q025"] < p["vida"]["valor"] < p["vida"]["q975"]
        assert p["condicionado"] is (quem is not None)  # pessoa: a partir da idade atual; futuro filho: do nascimento
        medidos = p["janelas"] if quem else p["F"]
        assert {k: pct(medidos[k]["valor"]) for k in pontos} == pontos, (codigo, quem)
        for chave, esperado in zip(("mediana", "q25", "q75"), inicio):
            if esperado is not None:  # no futuro filho a mediana vem da amostra; a faixa de 25 % a 75 % é exata
                assert abs(p["inicio"][chave] - esperado) <= 0.5, (codigo, quem, chave)
    if codigo == "2A":
        assert res["entrada"]["suposicoes"] == {"nao_portador": ["PAI"], "laudo_normal_suposto": ["PAI"]}
        status, res = analisar(medico, c["pid"])  # sem a suposição, a análise é recusada
        assert status == 422 and "suposição de não portador" in res["campos"]["vcf_pai"]
        assert res["campos"]["vcf_pai"].startswith("Parceiro (futuro pai) sem VCF anexado")
    if codigo == "1B":
        assert res["parentes"]["loci_inferidos"] and res["limite_inferior"] is False
    if codigo == "3B":  # o filho que já fez o teste é evidência, não pessoa em risco
        status, res = analisar(medico, c["pid"], c["dids"]["Tiago"])
        assert status == 422 and "já fez o teste" in res["campos"]["descendente_id"]


def test_sem_a_confirmacao_de_assintomatico_a_analise_da_pessoa_nao_roda(medico):
    c = cadastrar(medico, "1C")
    r = medico.post("/api/analises", data={"paciente_id": str(c["pid"]), "descendente_id": str(c["dids"]["Mateus"])})
    assert r.status_code == 422 and "confirma_assintomatico" in r.json()["campos"]


# ---------------------------------------------------------------------------
# Laudo do C9orf72: o modelo usa o número digitado; o arquivo é só o documento
# ---------------------------------------------------------------------------
def test_sem_o_numero_de_repeticoes_nao_ha_erro_e_o_c9orf72_fica_indeterminado(medico):
    """Regra do laudo ausente: genitor sem o número é tratado como não testado. A análise roda, o C9orf72 sai do
    cálculo e o aviso diz se o arquivo do laudo está anexado (falta digitar) ou se não há laudo nenhum."""
    com_arquivo = cadastrar(medico, "1A", numero={"mae": None})  # PDF do laudo anexado, número em branco
    ficha = medico.get(f"/api/pacientes/{com_arquivo['pid']}").json()
    mae = ficha["genitores"]["MAE"]
    assert mae["laudo_documento"] and mae["laudo_c9orf72"] is None and mae["laudo_informado"] is False
    status, res = analisar(medico, com_arquivo["pid"], com_arquivo["dids"]["Beatriz"])
    assert status == 201 and res["c9orf72_indeterminado"] is True and genes(res) == ["SOD1"]
    assert res["entrada"]["laudo_sem_numero"] == {"MAE": True} and res["entrada"]["laudo_c9orf72"] == {"pai": 23}
    aviso = res["texto_c9orf72_indeterminado"]
    assert aviso.startswith("Mãe: o arquivo do laudo está anexado, mas o nº de repetições não foi digitado.")
    assert "não é lido" in aviso and "Digite na ficha o nº de repetições" in aviso
    assert pct(res["principais"]["transmissao"]) == 49.3  # só o SOD1 do pai; com o laudo seriam 74,6 %

    sem_arquivo = cadastrar(medico, "1A", numero={"mae": None}, pdf_laudo=["pai"])
    status, res = analisar(medico, sem_arquivo["pid"], sem_arquivo["dids"]["Beatriz"])
    assert (
        status == 201 and res["c9orf72_indeterminado"] is True and res["entrada"]["laudo_sem_numero"] == {"MAE": False}
    )
    assert res["texto_c9orf72_indeterminado"].startswith(
        "Mãe: sem laudo do C9orf72 (nem o nº de repetições, nem o arquivo)."
    )

    # as listas marcam a análise parcial
    lista = medico.get("/api/pacientes/analises").json()
    lista = lista["analises"] if isinstance(lista, dict) else lista
    parciais = {a["paciente_id"] for a in lista if a["c9orf72_indeterminado"]}
    assert {com_arquivo["pid"], sem_arquivo["pid"]} <= parciais


def test_casal_sem_o_numero_nao_mostra_zero_como_ausencia_de_risco(medico):
    """Ficha 2A com o laudo da parceira anexado e o número em branco: nenhum lócus nos VCFs e o C9orf72 fora do
    cálculo. O resultado sai como parcial, com o aviso, e a interface não o apresenta como ausência de risco."""
    c = cadastrar(medico, "2A", numero={"mae": None})
    status, res = analisar(medico, c["pid"], assumir_nao_portador="PAI")
    assert status == 201 and res["sem_locus"] is True and res["c9orf72_indeterminado"] is True
    assert res["entrada"]["laudo_sem_numero"] == {"MAE": True, "PAI": False}
    aviso = res["texto_c9orf72_indeterminado"]
    assert aviso.startswith("Parceira (futura mãe): o arquivo do laudo está anexado") and "Parceiro" not in aviso
    assert "0 % aqui não quer dizer ausência de risco" in JS
    assert "Nenhum lócus de risco nos genes avaliados (C9orf72 não avaliado)" in JS


def test_numero_de_repeticoes_invalido_e_recusado_no_cadastro(medico):
    for texto, mensagem in (("45 repetições", "Informe o nº de repetições"), ("-3", "inteiros entre 0 e 5000")):
        r = cadastrar(medico, "1A", numero={"mae": texto})
        assert r["status"] == 422 and mensagem in r["campos"]["mae.laudo_c9orf72"], texto
    dois_alelos = cadastrar(medico, "1A", numero={"mae": "12,45"})  # os dois alelos: vale o maior
    status, res = analisar(medico, dois_alelos["pid"], dois_alelos["dids"]["Beatriz"])
    assert status == 201 and genes(res) == ["C9orf72", "SOD1"] and pct(res["principais"]["transmissao"]) == 74.6
    intermediario = cadastrar(
        medico, "1A", numero={"mae": "26"}
    )  # faixa intermediária: avaliado, sem ser lócus de risco
    status, res = analisar(medico, intermediario["pid"], intermediario["dids"]["Beatriz"])
    assert status == 201 and genes(res) == ["SOD1"] and res["c9orf72_indeterminado"] is False
    # e o resultado informa o alelo intermediário, mesmo havendo outro lócus de risco no caso
    resultado = next(s["texto"] for s in res["secoes"] if s["titulo"] == "Resultado")
    assert "No laudo do C9orf72: mãe com 26 repetições, faixa intermediária" in resultado
    assert "não contada como risco" in resultado


# ---------------------------------------------------------------------------
# VCF de um só genitor
# ---------------------------------------------------------------------------
def test_vcf_de_um_so_genitor_exige_suposicao_declarada_ou_parente_testado(medico):
    so_mae = cadastrar(medico, "1A", vcf=["mae"])
    did = so_mae["dids"]["Beatriz"]
    status, res = analisar(medico, so_mae["pid"], did)  # sem suposição: recusa com a orientação
    assert status == 422 and list(res["campos"]) == ["vcf_pai"]
    for trecho in ("Pai sem VCF anexado", "adicione um parente testado", "suposição de não portador"):
        assert trecho in res["campos"]["vcf_pai"]
    status, res = analisar(medico, so_mae["pid"], did, assumir_nao_portador="PAI")
    assert status == 201 and genes(res) == ["C9orf72"]  # o SOD1 do pai não entra: ele foi suposto não portador
    assert res["entrada"]["suposicoes"] == {"nao_portador": ["PAI"], "laudo_sem_vcf": ["PAI"]}  # o laudo dele vale
    assert res["entrada"]["laudo_c9orf72"] == {"mae": 45, "pai": 23} and res["c9orf72_indeterminado"] is False

    so_pai = cadastrar(medico, "1A", vcf=["pai"])  # mãe sem VCF, mas com o laudo de 45 repetições digitado
    status, res = analisar(medico, so_pai["pid"], so_pai["dids"]["Beatriz"], assumir_nao_portador="MAE")
    assert status == 201 and genes(res) == ["C9orf72", "SOD1"] and pct(res["principais"]["transmissao"]) == 74.6

    nenhum = cadastrar(medico, "1A", vcf=[])
    status, res = analisar(medico, nenhum["pid"], nenhum["dids"]["Beatriz"], assumir_nao_portador="MAE,PAI")
    assert status == 422 and res["campos"]["assumir_nao_portador"] == "É preciso o VCF de ao menos um genitor."
    status, res = analisar(medico, nenhum["pid"], nenhum["dids"]["Beatriz"])
    assert status == 422 and sorted(res["campos"]) == ["vcf_mae", "vcf_pai"]


def test_suposicao_com_o_arquivo_do_laudo_anexado_e_sem_o_numero_avisa_do_arquivo(medico):
    """Mãe sem VCF, com o PDF do laudo anexado e o número em branco: a suposição de não portador cobre o C9orf72
    (laudo normal suposto) e o texto avisa que o arquivo existe e que o número não foi digitado."""
    c = cadastrar(medico, "1A", vcf=["pai"], numero={"mae": None})
    status, res = analisar(medico, c["pid"], c["dids"]["Beatriz"], assumir_nao_portador="MAE")
    assert status == 201 and genes(res) == ["SOD1"] and res["c9orf72_indeterminado"] is False
    assert res["entrada"]["suposicoes"] == {"nao_portador": ["MAE"], "laudo_normal_suposto": ["MAE"]}
    texto = res["suposicoes_texto"]["laudo_normal_suposto"]
    assert texto.startswith(textos.SUPOSICAO_LAUDO_NORMAL)
    assert texto.endswith("Mãe: o arquivo do laudo está anexado, mas o nº de repetições não foi digitado.")
    # sem o arquivo, só o texto geral
    assert textos.suposicao_laudo_normal({"MAE": False}, "PESSOA", ["MAE"]) == textos.SUPOSICAO_LAUDO_NORMAL


def test_genitor_sem_exame_e_sem_parente_segue_a_mesma_regra(medico):
    c = cadastrar(medico, "1B", parente=False)  # pai sem VCF, sem laudo e sem parente testado
    did = c["dids"]["Caio"]
    status, res = analisar(medico, c["pid"], did)
    assert status == 422 and "Pai sem VCF anexado" in res["campos"]["vcf_pai"]
    status, res = analisar(medico, c["pid"], did, assumir_nao_portador="PAI")
    assert status == 201 and res["sem_locus"] is True and res["c9orf72_indeterminado"] is False
    assert res["entrada"]["suposicoes"] == {"nao_portador": ["PAI"], "laudo_normal_suposto": ["PAI"]}


def test_so_com_os_laudos_a_analise_nao_roda_e_com_um_vcf_o_laudo_do_outro_vale(medico):
    """Só os laudos do C9orf72, sem VCF de nenhum genitor: recusado (o VCF é o que cobre os outros genes). Com o VCF
    de um genitor, o laudo do outro vale, e o resultado pode vir só dos laudos, quando o VCF não traz lócus de risco."""
    r = medico.post(
        "/api/analises", data={"n": "300", "cox": "0", "sexo": "F", "c9orf72_mae": "45", "c9orf72_pai": "23"}
    )
    assert r.status_code == 422  # análise sem registro: os dois VCFs são exigidos
    assert r.json()["campos"] == {"vcf_mae": "Envie o arquivo VCF.", "vcf_pai": "Envie o arquivo VCF."}

    # ficha 2A com a expansão só no laudo do parceiro, que não tem VCF; o VCF da parceira não traz lócus de risco
    c = cadastrar(medico, "2A", numero={"mae": "23", "pai": "45"})
    status, res = analisar(medico, c["pid"], assumir_nao_portador="PAI")
    assert status == 201 and genes(res) == ["C9orf72"] and pct(res["principais"]["transmissao"]) == 50.0
    assert res["entrada"]["laudo_c9orf72"] == {"mae": 23, "pai": 45}
    assert res["entrada"]["suposicoes"] == {"nao_portador": ["PAI"], "laudo_sem_vcf": ["PAI"]}


def test_parente_so_com_laudo_infere_o_c9orf72_do_genitor_sem_exame(medico):
    """Ficha 1B com a avó paterna cadastrada só pelo laudo (45 repetições, sem VCF): o C9orf72 do pai é inferido pelo
    laudo dela e condicionado à situação clínica dele; os outros genes do pai pedem a suposição de não portador."""
    c = cadastrar(medico, "1B", parente=False)
    pid, did = c["pid"], c["dids"]["Caio"]
    r = medico.post(
        f"/api/pacientes/{pid}/genitores/PAI/parentes", data={"parentesco": "MAE_DO_GENITOR", "laudo_c9orf72": "45"}
    )
    assert r.status_code == 201, r.text
    pai = r.json()["genitores"]["PAI"]
    assert pai["inferido_por_parentes"] is False and pai["c9orf72_por_parentes"] == ["Avó paterna"]
    status, res = analisar(medico, pid, did, assumir_nao_portador="PAI")
    assert status == 422 and "situação clínica" in res["campos"]["situacao_pai"]
    r = medico.put(f"/api/pacientes/{pid}/genitores/PAI/situacao", json={"situacao": "FALECIDO_SEM_ELA", "idade": 60})
    assert r.status_code == 200, r.text
    status, res = analisar(medico, pid, did)  # sem VCF do pai nem de parente: falta a suposição para os outros genes
    assert status == 422 and "Pai sem VCF anexado" in res["campos"]["vcf_pai"]
    status, res = analisar(medico, pid, did, assumir_nao_portador="PAI")
    assert status == 201 and genes(res) == ["C9orf72"] and res["c9orf72_indeterminado"] is False
    assert pct(res["principais"]["transmissao"]) == 22.0  # pai portador com 44,3 %, dado que faleceu sem ELA aos 60
    assert res["entrada"]["suposicoes"] == {"nao_portador": ["PAI"]}  # o laudo da avó dispensa o laudo normal suposto
    inferido = res["parentes"]["loci_inferidos"][0]
    assert inferido["genitor_inferido"] == "pai" and inferido["situacao_clinica"] == "falecido sem ELA aos 60 anos"
    assert abs(inferido["p_dosagem_1_condicionada"] - 0.443) < 0.001


def test_ficha_1b_com_o_laudo_da_avo_nao_fica_com_o_c9orf72_indeterminado(medico):
    """Ficha 1B: o pai não tem laudo, mas a avó paterna tem (23 repetições). O C9orf72 dele é inferido pelo laudo dela:
    a ficha diz de quem é o laudo e a análise não sai parcial para o gene."""
    c = cadastrar(medico, "1B")
    pai = medico.get(f"/api/pacientes/{c['pid']}").json()["genitores"]["PAI"]
    assert pai["laudo_c9orf72"] is None and pai["c9orf72_por_parentes"] == ["Avó paterna"]
    status, res = analisar(medico, c["pid"], c["dids"]["Caio"])
    assert status == 201 and res["c9orf72_indeterminado"] is False
    # na tela, o aviso de lócus indeterminado só aparece quando nem o genitor nem um parente dele tem laudo
    estado = JS[JS.index("function estadoLaudo(") : JS.index("function resumoUltimaAnalise(")]
    assert estado.index("g.c9orf72_por_parentes") < estado.index("C9orf72 indeterminado")
    assert "C9orf72 inferido pelo laudo de ${parentes}" in estado


# ---------------------------------------------------------------------------
# Textos da interface
# ---------------------------------------------------------------------------
def test_interface_separa_sem_laudo_de_arquivo_anexado_sem_o_numero():
    assert "estadoLaudo(g, false)" in JS and "estadoLaudo(g, true)" in JS  # ficha e tela de análise
    estado = JS[JS.index("function estadoLaudo(") :][:1800]
    ordem = [
        estado.index(t) for t in ("g.c9orf72_por_parentes", "g.laudo_documento", "Sem laudo: C9orf72 indeterminado")
    ]
    assert ordem == sorted(ordem)  # parentes com laudo, depois arquivo sem o número, depois sem laudo
    for trecho in (
        "Falta o nº de repetições: C9orf72 indeterminado",
        "O arquivo do laudo está anexado, mas o modelo usa o nº de repetições digitado; o arquivo não é lido.",
        "Arquivo do laudo escolhido sem o nº de repetições.",
        'Laudo anexado. Falta digitar o nº de repetições em "Editar dados"',
        "C9orf72 não avaliado",
    ):
        assert trecho in JS, trecho
    assert "nº de repetições" in textos.C9ORF72_INDETERMINADO and "não é lido" in textos.C9ORF72_INDETERMINADO
    assert textos.c9orf72_indeterminado() == textos.C9ORF72_INDETERMINADO  # análise sem registro: só o texto geral
    dois = textos.c9orf72_indeterminado({"MAE": True, "PAI": False}, "CASAL")
    assert dois.index("Parceira (futura mãe): o arquivo") < dois.index("Parceiro (futuro pai): sem laudo")
