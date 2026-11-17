"""Plataforma web: contas, RBAC com negação por padrão, auditoria encadeada, registros dos três casos (pessoa, casal,
família), genitores com VCF cifrado, descendentes, consentimentos, análises com resumo guardado, filtros, casos
pseudonimizados para pesquisa e LGPD.

Cada teste cobre um critério de aceite das revisões de 15/11/2026. Autentica antes de chamar a API.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from ela_preditivo import DIR_DADOS, cenarios
from ela_preditivo.web import auditoria, demo, permissoes, textos
from ela_preditivo.web.api import COOKIE_SESSAO, criar_app, exigencia_da_rota, rotas_api
from ela_preditivo.web.config import Configuracao, gerar_chave
from ela_preditivo.web import pacientes as mod_pacientes
from ela_preditivo.web import pesquisa as mod_pesquisa
from ela_preditivo.web.modelos import AnalisePaciente, Consentimento, Paciente, Parente, Sessao, Usuario
from ela_preditivo.web.seguranca import Cifra, hash_token, mascarar_cpf, validar_cpf

DIR_STATIC = Path(__file__).resolve().parents[1] / "src" / "ela_preditivo" / "web" / "static"
CPFS_VALIDOS = ["529.982.247-25", "111.444.777-35", "935.411.347-80", "390.533.447-05", "123.456.789-09"]
CPF = demo._cpf_valido  # CPFs sintáticos válidos a partir de uma semente (100 em diante, para não colidir com a demo)
NOMES_FICTICIOS = demo.NOMES_FICTICIOS
DADOS_PACIENTES = demo.DADOS_IDENTIFICAVEIS  # nomes, prontuários e nascimentos de atendidos e genitores
SINT = DIR_DADOS / "sinteticos"
VERSAO_TERMO = textos.VERSAO_TERMO_CONSENTIMENTO_PESQUISA


def genitor(nome: str, nasc: str, laudo: str | None = None) -> dict:
    return {"nome": nome, "data_nascimento": nasc, "laudo_c9orf72": laudo}


def registro_pessoa(nome="Pessoa de Teste", nasc="1990-01-01", sexo="F", prontuario="T-1", **extra) -> dict:
    d = {
        "tipo": "PESSOA",
        "prontuario": prontuario,
        "mae": genitor("Mãe de Teste", "1960-02-02"),
        "pai": genitor("Pai de Teste", "1958-03-03"),
        "descendentes": [{"nome": nome, "data_nascimento": nasc, "sexo": sexo}],
    }
    d.update(extra)
    return d


def anexar_cenario(cliente, pid: int, papel: str, numero: int, lado: str | None = None):
    lado = lado or ("mae" if papel == "MAE" else "pai")
    with open(SINT / f"cenario_{numero}_{lado}.vcf", "rb") as f:
        return cliente.post(
            f"/api/pacientes/{pid}/genitores/{papel}/vcf", files={"vcf": ("Nome Pessoal.vcf", f, "text/plain")}
        )


# ---------------------------------------------------------------------------
# Infraestrutura
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def plataforma(tmp_path_factory):
    d = tmp_path_factory.mktemp("web")
    cfg = Configuracao(
        chave=gerar_chave().encode(),
        bd=d / "ela_web.sqlite3",
        dir_vcfs=d / "vcfs",
        demonstracao=True,
        tentativas_login=3,
        bloqueio_minutos=15,
    )
    app = criar_app(cfg)
    with app.state.sessoes() as bd:
        cred = demo.popular(bd, Cifra(cfg.chave), cfg, analisar=False)["credenciais"]
    return {"app": app, "cfg": cfg, "cred": {c["email"]: c for c in cred}}


def entrar(plataforma, email: str, senha: str | None = None) -> TestClient:
    c = TestClient(plataforma["app"])
    senha = senha or plataforma["cred"][email]["senha"]
    r = c.post("/api/contas/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c


@pytest.fixture
def medico(plataforma):
    return entrar(plataforma, "medico@demo.local")


@pytest.fixture
def pesquisador(plataforma):
    return entrar(plataforma, "pesquisador@demo.local")


@pytest.fixture
def admin(plataforma):
    return entrar(plataforma, "admin@demo.local")


@pytest.fixture
def pendente(plataforma):
    return entrar(plataforma, "medico.pendente@demo.local")


def cadastro_valido(email: str, cpf: str, papel: str = "MEDICO", **extra) -> dict:
    d = {
        "nome": "Pessoa de Teste",
        "cpf": cpf,
        "email": email,
        "senha": "senha-segura-123",
        "papel_pretendido": papel,
        "aceite_privacidade": True,
        "aceite_termo_uso": True,
        "versao_privacidade": textos.VERSAO_AVISO_PRIVACIDADE,
        "versao_termo_uso": textos.VERSAO_TERMO_USO,
        "medico": {"tipo": "CRM", "crm": "54321", "uf": "RJ"},
        "pesquisador": {"tipo": "INDEPENDENTE", "cargo": "Pesquisador", "linha_pesquisa": "ELA"},
    }
    d.update(extra)
    return d


def novo_medico_verificado(plataforma, admin, email: str, cpf: str) -> TestClient:
    anon = TestClient(plataforma["app"])
    assert anon.post("/api/contas/cadastro", json=cadastro_valido(email, cpf)).status_code == 201
    uid = next(u["id"] for u in admin.get("/api/admin/cadastros/pendentes").json()["cadastros"] if u["email"] == email)
    assert admin.post(f"/api/admin/usuarios/{uid}/aprovar").status_code == 200
    return entrar(plataforma, email, "senha-segura-123")


def paciente_do(medico) -> dict:
    return medico.get("/api/pacientes").json()["pacientes"][0]


def acoes_auditadas(plataforma) -> list[dict]:
    with plataforma["app"].state.sessoes() as bd:
        return [
            auditoria.serializar(r)
            for r in bd.execute(select(auditoria.Auditoria).order_by(auditoria.Auditoria.sequencia)).scalars()
        ]


# ---------------------------------------------------------------------------
# RBAC: negação por padrão e matriz
# ---------------------------------------------------------------------------
def test_toda_rota_api_fora_da_lista_publica_devolve_401_sem_sessao(plataforma):
    """Percorre as rotas registradas: uma rota nova sem `exigir` ou fora de ROTAS_PUBLICAS faz este teste falhar."""
    app = plataforma["app"]
    anon = TestClient(app)
    rotas = rotas_api(app)
    assert len(rotas) >= 35
    publicas = set(permissoes.ROTAS_PUBLICAS)
    assert publicas == {
        ("GET", "/api/sistema"),
        ("GET", "/api/privacidade"),
        ("GET", "/api/ajuda"),
        ("POST", "/api/contas/cadastro"),
        ("POST", "/api/contas/login"),
    }
    for rota in rotas:
        metodo = sorted(rota.methods)[0]
        caminho = re.sub(r"\{[^}]+\}", "1", rota.path)
        if (metodo, rota.path) in publicas:
            assert exigencia_da_rota(rota) is None
            continue
        assert exigencia_da_rota(rota) is not None, f"{metodo} {rota.path} não passa por permissoes.exigir"
        r = anon.request(metodo, caminho, json={} if metodo in ("POST", "PUT", "DELETE") else None)
        assert r.status_code == 401, f"{metodo} {rota.path}: {r.status_code}"
        assert r.json()["erro"] == "nao_autenticado"
    # a negação sem sessão vai para a auditoria
    assert any(a["acao"] == "acesso_negado" and a["usuario_id"] is None for a in acoes_auditadas(plataforma))


MATRIZ_NAO = {
    "PESQUISADOR": [
        ("GET", "/api/pacientes"),
        ("POST", "/api/pacientes"),
        ("GET", "/api/pacientes/1"),
        ("GET", "/api/pacientes/1/consentimentos"),
        ("GET", "/api/cenarios"),
        ("POST", "/api/analises"),
        ("GET", "/api/analises/x/pacote.zip"),
        ("GET", "/api/admin/cadastros/pendentes"),
        ("GET", "/api/admin/usuarios"),
        ("GET", "/api/admin/auditoria"),
    ],
    "ADMIN": [
        ("GET", "/api/pacientes"),
        ("GET", "/api/pacientes/1"),
        ("POST", "/api/analises"),
        ("GET", "/api/analises/x/pacote.zip"),
        ("GET", "/api/parametros"),
        ("GET", "/api/cenarios"),
        ("GET", "/api/pesquisa/casos"),
    ],
    "MEDICO": [
        ("GET", "/api/admin/cadastros/pendentes"),
        ("POST", "/api/admin/usuarios/1/aprovar"),
        ("GET", "/api/admin/usuarios"),
        ("GET", "/api/admin/auditoria"),
        ("GET", "/api/pesquisa/casos"),
    ],
}


def test_cada_nao_da_matriz_devolve_403(plataforma, medico, pesquisador, admin):
    clientes = {"MEDICO": medico, "PESQUISADOR": pesquisador, "ADMIN": admin}
    for papel, rotas in MATRIZ_NAO.items():
        for metodo, caminho in rotas:
            r = clientes[papel].request(metodo, caminho, json={} if metodo == "POST" else None)
            assert r.status_code == 403, f"{papel} {metodo} {caminho}: {r.status_code}"
            assert r.json()["mensagem"] == permissoes.MENSAGEM_403
    # cada negação foi auditada, com o papel
    negadas = [a for a in acoes_auditadas(plataforma) if a["acao"] == "acesso_negado" and a["resultado"] == "NEGADO"]
    assert {a["papel"] for a in negadas} >= {"MEDICO", "PESQUISADOR", "ADMIN"}
    # os "Sim" da matriz respondem 200
    assert medico.get("/api/parametros").status_code == 200 and pesquisador.get("/api/parametros").status_code == 200
    assert medico.get("/api/pacientes").status_code == 200 and pesquisador.get("/api/pesquisa/casos").status_code == 200
    assert admin.get("/api/admin/usuarios").status_code == 200 and admin.get("/api/admin/auditoria").status_code == 200
    for c in (medico, pesquisador, admin):
        assert c.get("/api/contas/minha/auditoria").status_code == 200 and c.get("/api/contas/minha").status_code == 200


def test_quem_sou_eu_devolve_permissoes_da_matriz(medico, pesquisador, admin):
    for c, papel in ((medico, "MEDICO"), (pesquisador, "PESQUISADOR"), (admin, "ADMIN")):
        eu = c.get("/api/contas/quem-sou-eu").json()
        assert set(eu["permissoes"]) == permissoes.MATRIZ[papel] and eu["verificado"] is True and eu["csrf"]
        assert "cpf" not in eu["usuario"] and eu["usuario"]["cpf_mascarado"].startswith("***.")


def test_conta_nao_verificada_so_acessa_situacao_e_conta(plataforma, pendente):
    eu = pendente.get("/api/contas/quem-sou-eu").json()
    assert eu["verificado"] is False and eu["usuario"]["situacao"] == "PENDENTE"
    assert pendente.get("/api/contas/situacao").status_code == 200
    assert pendente.get("/api/contas/minha").status_code == 200
    for metodo, caminho in (
        ("GET", "/api/pacientes"),
        ("GET", "/api/parametros"),
        ("GET", "/api/cenarios"),
        ("POST", "/api/analises"),
        ("GET", "/api/contas/minha/auditoria"),
    ):
        r = pendente.request(metodo, caminho, json={} if metodo == "POST" else None)
        assert r.status_code == 403 and r.json()["mensagem"] == permissoes.MENSAGEM_NAO_VERIFICADO, (metodo, caminho)
    assert any(
        a["acao"] == "acesso_negado" and "conta_nao_verificada" in (a["detalhe"] or "")
        for a in acoes_auditadas(plataforma)
    )


def test_ninguem_vira_admin_nem_muda_o_proprio_papel(plataforma, medico):
    anon = TestClient(plataforma["app"])
    r = anon.post(
        "/api/contas/cadastro", json=cadastro_valido("quer.admin@teste.local", CPFS_VALIDOS[1], papel="ADMIN")
    )
    assert r.status_code == 422 and "papel_pretendido" in r.json()["campos"]
    corpo = cadastro_valido("extra@teste.local", CPFS_VALIDOS[1])
    corpo.update({"papel": "ADMIN", "situacao": "VERIFICADO", "id": 999})  # campos extras são ignorados
    r = anon.post("/api/contas/cadastro", json=corpo)
    assert r.status_code == 201
    c = entrar(plataforma, "extra@teste.local", "senha-segura-123")
    eu = c.get("/api/contas/quem-sou-eu").json()["usuario"]
    assert eu["papel"] == "MEDICO" and eu["situacao"] == "PENDENTE"
    r = c.put("/api/contas/minha", json={"nome": "Nome Alterado", "papel": "ADMIN", "situacao": "VERIFICADO"})
    assert r.status_code == 200 and r.json()["papel"] == "MEDICO" and r.json()["situacao"] == "PENDENTE"
    r = medico.put("/api/contas/minha", json={"papel": "ADMIN", "situacao": "DESATIVADO"})
    assert r.status_code == 200 and r.json()["papel"] == "MEDICO" and r.json()["situacao"] == "VERIFICADO"
    assert not any(
        rota.path.startswith("/api/admin/usuarios") and "papel" in rota.path for rota in rotas_api(plataforma["app"])
    )


# ---------------------------------------------------------------------------
# Pacientes: isolamento, dados sensíveis, consentimentos, exclusão
# ---------------------------------------------------------------------------
def test_medico_a_nao_acessa_pacientes_do_medico_b(plataforma, medico, admin):
    p = paciente_do(medico)
    b = novo_medico_verificado(plataforma, admin, "medico.b@teste.local", CPFS_VALIDOS[2])
    assert b.get("/api/pacientes").json()["total"] == 0
    assert b.post("/api/pacientes/busca", json={"texto": p["nome"][:4]}).json()["total"] == 0
    for metodo, caminho, corpo in (
        ("GET", f"/api/pacientes/{p['id']}", None),
        ("PUT", f"/api/pacientes/{p['id']}", registro_pessoa()),
        ("POST", f"/api/pacientes/{p['id']}/exportar", {}),
        ("DELETE", f"/api/pacientes/{p['id']}", {"confirmacao_nome": p["nome"]}),
        ("GET", f"/api/pacientes/{p['id']}/consentimentos", None),
        (
            "POST",
            f"/api/pacientes/{p['id']}/consentimentos",
            {"titular": "MAE", "confirmado": True, "versao_termo": VERSAO_TERMO},
        ),
        ("PUT", f"/api/pacientes/{p['id']}/genitores/MAE", genitor("X Y Z", "1960-01-01")),
        ("DELETE", f"/api/pacientes/{p['id']}/genitores/MAE/vcf", None),
        (
            "POST",
            f"/api/pacientes/{p['id']}/descendentes",
            {"nome": "X Y Z", "data_nascimento": "2000-01-01", "sexo": "F"},
        ),
        (
            "PUT",
            f"/api/pacientes/{p['id']}/descendentes/{p['descendentes'][0]['id']}",
            {"nome": "X Y Z", "data_nascimento": "2000-01-01", "sexo": "F"},
        ),
        ("DELETE", f"/api/pacientes/{p['id']}/descendentes/{p['descendentes'][0]['id']}", None),
    ):
        r = b.request(metodo, caminho, json=corpo)
        assert r.status_code == 404, (metodo, caminho, r.status_code)
    assert anexar_cenario(b, p["id"], "MAE", 1).status_code == 404
    fd = {"modo": "cenario", "cenario": "1", "n": "200", "motor": "numpy", "cox": "0", "paciente_id": str(p["id"])}
    assert b.post("/api/analises", data=fd).status_code == 404
    assert medico.get(f"/api/pacientes/{p['id']}").status_code == 200  # o dono continua vendo


def test_respostas_de_pesquisador_e_admin_nao_contem_dados_de_paciente(plataforma, pesquisador, admin, medico):
    medico.get(f"/api/pacientes/{paciente_do(medico)['id']}")  # gera auditoria com alvo
    textos_resp = []
    for c, caminhos in (
        (
            pesquisador,
            [
                "/api/contas/quem-sou-eu",
                "/api/contas/minha",
                "/api/pesquisa/casos",
                "/api/parametros",
                "/api/contas/minha/auditoria",
                "/api/sistema",
                "/api/privacidade",
            ],
        ),
        (
            admin,
            [
                "/api/contas/quem-sou-eu",
                "/api/admin/cadastros/pendentes",
                "/api/admin/usuarios",
                "/api/admin/auditoria?por_pagina=500",
                "/api/admin/auditoria/verificacao",
                "/api/contas/minha/auditoria",
            ],
        ),
    ):
        for caminho in caminhos:
            r = c.get(caminho)
            assert r.status_code == 200, caminho
            textos_resp.append(r.text)
    textos_resp.append(pesquisador.post("/api/pesquisa/casos/busca", json={"genes": ["SOD1"]}).text)
    textos_resp.append(pesquisador.post("/api/pesquisa/casos/exportar", json={}).text)
    todos = "\n".join(textos_resp)
    for dado in DADOS_PACIENTES:
        assert dado not in todos, dado
    assert "codigo_pesquisa" not in todos and "medico_id" not in todos


def test_arquivo_do_banco_nao_contem_nome_de_paciente_em_claro(plataforma, medico):
    paciente_do(medico)
    conteudo = plataforma["cfg"].bd.read_bytes()
    for dado in DADOS_PACIENTES:
        assert dado.encode("utf-8") not in conteudo, dado
    for c in plataforma["cred"].values():  # senhas nunca em claro
        assert c["senha"].encode() not in conteudo
    # VCFs: cifrados em disco, com nome aleatório, sem o cabeçalho em claro
    arquivos = list(plataforma["cfg"].dir_vcfs.glob("*.bin"))
    assert arquivos and all(b"##fileformat" not in a.read_bytes() and "Ficticia" not in a.name for a in arquivos)
    assert not list(plataforma["cfg"].dir_vcfs.glob("*.vcf"))
    # e os CPFs dos usuários também não (só HMAC e Fernet)
    with plataforma["app"].state.sessoes() as bd:
        cifra = Cifra(plataforma["cfg"].chave)
        for u in bd.execute(select(Usuario)).scalars():
            assert cifra.decifrar(u.cpf_cifrado).encode() not in conteudo


def test_consentimento_nunca_pre_marcado_revogavel_e_menor_exige_responsavel(plataforma, medico):
    novo = medico.post("/api/pacientes", json=registro_pessoa("Pessoa Menor de Teste", "2012-05-05", "F", "MENOR-1"))
    assert novo.status_code == 201, novo.text
    pacientes = medico.get("/api/pacientes").json()["pacientes"]
    menor = next(p for p in pacientes if p["id"] == novo.json()["id"])
    adulto = next(p for p in pacientes if p["nome"].startswith("Ana"))
    casal = next(p for p in pacientes if p["nome"].startswith("Fernanda"))
    ficha = medico.get(f"/api/pacientes/{menor['id']}").json()
    did = ficha["descendentes"][0]["id"]
    assert ficha["descendentes"][0]["menor_de_idade"]
    assert [(e["titular"], e["descendente_id"]) for e in ficha["pesquisa"]["exigidos"]] == [
        ("MAE", None),
        ("PAI", None),
        ("RESPONSAVEL", did),
    ]
    assert not any(e["consentido"] for e in ficha["pesquisa"]["exigidos"])  # nada pré-marcado
    # casal: só os dois parceiros consentem
    fc = medico.get(f"/api/pacientes/{casal['id']}").json()
    assert [e["titular"] for e in fc["pesquisa"]["exigidos"]] == ["MAE", "PAI"] and fc["pesquisa"]["liberado"]
    r = medico.post(
        f"/api/pacientes/{casal['id']}/consentimentos",
        json={"titular": "DESCENDENTE", "confirmado": True, "versao_termo": VERSAO_TERMO},
    )
    assert r.status_code == 422 and "titular" in r.json()["campos"]
    # sem a marcação explícita, recusa
    r = medico.post(
        f"/api/pacientes/{adulto['id']}/consentimentos",
        json={
            "titular": "DESCENDENTE",
            "descendente_id": adulto["descendentes"][0]["id"],
            "versao_termo": VERSAO_TERMO,
        },
    )
    assert r.status_code == 422 and "confirmado" in r.json()["campos"]
    # menor: em nome do próprio, recusa; responsável sem nome, recusa; responsável identificado, aceita
    r = medico.post(
        f"/api/pacientes/{menor['id']}/consentimentos",
        json={"titular": "DESCENDENTE", "descendente_id": did, "confirmado": True, "versao_termo": VERSAO_TERMO},
    )
    assert r.status_code == 422 and "art. 14" in r.json()["campos"]["titular"]
    r = medico.post(
        f"/api/pacientes/{menor['id']}/consentimentos",
        json={"titular": "RESPONSAVEL", "descendente_id": did, "confirmado": True, "versao_termo": VERSAO_TERMO},
    )
    assert r.status_code == 422 and "nome_titular" in r.json()["campos"]
    r = medico.post(
        f"/api/pacientes/{menor['id']}/consentimentos",
        json={
            "titular": "RESPONSAVEL",
            "confirmado": True,
            "versao_termo": VERSAO_TERMO,
            "nome_titular": "Luísa Fictícia Prado",
        },
    )
    assert r.status_code == 422 and "descendente_id" in r.json()["campos"]
    r = medico.post(
        f"/api/pacientes/{menor['id']}/consentimentos",
        json={
            "titular": "RESPONSAVEL",
            "descendente_id": did,
            "nome_titular": "Luísa Fictícia Prado",
            "confirmado": True,
            "versao_termo": VERSAO_TERMO,
        },
    )
    assert (
        r.status_code == 201
        and r.json()["pesquisa"]["liberado"] is False
        and r.json()["pesquisa_situacao"] == "PENDENTE"
    )
    for t in ("MAE", "PAI"):
        r = medico.post(
            f"/api/pacientes/{menor['id']}/consentimentos",
            json={"titular": t, "confirmado": True, "versao_termo": VERSAO_TERMO},
        )
        assert r.status_code == 201
    assert r.json()["liberado_para_pesquisa"] is True and "codigo_pesquisa" not in r.text
    with plataforma["app"].state.sessoes() as bd:
        p = bd.get(Paciente, menor["id"])
        assert p.codigo_pesquisa and len(p.codigo_pesquisa) == 32 and p.codigo_pesquisa not in r.text
        for dado in (menor["nome"], "MENOR-1", "2012-05-05"):
            assert dado not in p.codigo_pesquisa
    # duplicado ativo é recusado; revogar na mesma tela, com efeito imediato
    r = medico.post(
        f"/api/pacientes/{menor['id']}/consentimentos",
        json={"titular": "MAE", "confirmado": True, "versao_termo": VERSAO_TERMO},
    )
    assert r.status_code == 409
    cid = next(
        c["id"] for c in medico.get(f"/api/pacientes/{menor['id']}").json()["consentimentos"] if c["titular"] == "MAE"
    )
    r = medico.post(f"/api/pacientes/{menor['id']}/consentimentos/{cid}/revogar")
    assert r.status_code == 200 and r.json()["liberado_para_pesquisa"] is False
    assert next(c for c in r.json()["consentimentos"] if c["id"] == cid)["revogado_em"]
    assert medico.post(f"/api/pacientes/{menor['id']}/consentimentos/{cid}/revogar").status_code == 409
    # família: cada filho (adulto) consente por si; incluir um filho novo retira a liberação até ele consentir
    fam = next(p for p in pacientes if "Ramos" in p["nome"])
    for e in medico.get(f"/api/pacientes/{fam['id']}").json()["pesquisa"]["exigidos"]:
        corpo = {
            "titular": e["titular"],
            "descendente_id": e["descendente_id"],
            "confirmado": True,
            "versao_termo": VERSAO_TERMO,
        }
        r = medico.post(f"/api/pacientes/{fam['id']}/consentimentos", json=corpo)
        assert r.status_code == 201, r.text
    assert r.json()["liberado_para_pesquisa"] is True
    r = medico.post(
        f"/api/pacientes/{fam['id']}/descendentes",
        json={"nome": "Filho Novo Ramos", "data_nascimento": "1980-01-01", "sexo": "M"},
    )
    assert r.status_code == 201 and r.json()["liberado_para_pesquisa"] is False and len(r.json()["descendentes"]) == 3
    novo = r.json()["descendentes"][-1]["id"]
    r = medico.post(
        f"/api/pacientes/{fam['id']}/consentimentos",
        json={"titular": "DESCENDENTE", "descendente_id": novo, "confirmado": True, "versao_termo": VERSAO_TERMO},
    )
    assert r.status_code == 201 and r.json()["liberado_para_pesquisa"] is True
    assert medico.request("DELETE", f"/api/pacientes/{fam['id']}/descendentes/{novo}").status_code == 200
    acoes = {a["acao"] for a in acoes_auditadas(plataforma)}
    assert {
        "consentimento_registrado",
        "consentimento_revogado",
        "caso_liberado_pesquisa",
        "caso_retirado_pesquisa",
        "descendente_editado",
    } <= acoes


def test_excluir_paciente_remove_identificadores_e_consentimentos_mantendo_auditoria(plataforma, medico):
    r = medico.post("/api/pacientes", json=registro_pessoa("Paciente Para Excluir", "1980-05-05", "M", "EXC-1"))
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert anexar_cenario(medico, pid, "MAE", 1).status_code == 201
    arquivo = next(a for a in plataforma["cfg"].dir_vcfs.glob("*.bin"))  # algum arquivo existe
    with plataforma["app"].state.sessoes() as bd:
        nome_arquivo = bd.get(Paciente, pid).genitor("MAE").vcf_arquivo
    assert (plataforma["cfg"].dir_vcfs / nome_arquivo).exists()
    assert (
        medico.post(
            f"/api/pacientes/{pid}/consentimentos",
            json={"titular": "MAE", "confirmado": True, "versao_termo": VERSAO_TERMO},
        ).status_code
        == 201
    )
    r = medico.request("DELETE", f"/api/pacientes/{pid}", json={"confirmacao_nome": "nome errado"})
    assert r.status_code == 422 and "confirmacao_nome" in r.json()["campos"]
    r = medico.request("DELETE", f"/api/pacientes/{pid}", json={"confirmacao_nome": "paciente para excluir"})
    assert r.status_code == 200
    assert medico.get(f"/api/pacientes/{pid}").status_code == 404
    assert not (plataforma["cfg"].dir_vcfs / nome_arquivo).exists()  # o VCF cifrado foi apagado com o registro
    with plataforma["app"].state.sessoes() as bd:
        assert bd.get(Paciente, pid) is None
        assert bd.execute(select(Consentimento).where(Consentimento.paciente_id == pid)).first() is None
        assert bd.execute(select(AnalisePaciente).where(AnalisePaciente.paciente_id == pid)).first() is None
        assert bd.execute(text("SELECT count(*) FROM genitores WHERE paciente_id = :p"), {"p": pid}).scalar_one() == 0
        assert (
            bd.execute(text("SELECT count(*) FROM descendentes WHERE paciente_id = :p"), {"p": pid}).scalar_one() == 0
        )
    reg = [a for a in acoes_auditadas(plataforma) if a["acao"] == "paciente_excluido" and a["alvo_id"] == str(pid)]
    assert reg and "Excluir" not in (reg[0]["detalhe"] or "") and "EXC-1" not in (reg[0]["detalhe"] or "")
    del arquivo


def test_cpf_invalido_ou_duplicado_e_email_duplicado_sao_recusados(plataforma):
    anon = TestClient(plataforma["app"])
    assert validar_cpf("529.982.247-25") and not validar_cpf("529.982.247-26") and not validar_cpf("111.111.111-11")
    assert mascarar_cpf("52998224725") == "***.982.247-**"
    r = anon.post("/api/contas/cadastro", json=cadastro_valido("cpf.ruim@teste.local", "529.982.247-26"))
    assert r.status_code == 422 and r.json()["campos"]["cpf"] == "CPF inválido: confira os dígitos."
    r = anon.post(
        "/api/contas/cadastro", json=cadastro_valido("senha.fraca@teste.local", CPFS_VALIDOS[3], senha="curta")
    )
    assert r.status_code == 422 and "senha" in r.json()["campos"]
    assert (
        anon.post("/api/contas/cadastro", json=cadastro_valido("primeiro@teste.local", CPFS_VALIDOS[3])).status_code
        == 201
    )
    r = anon.post("/api/contas/cadastro", json=cadastro_valido("segundo@teste.local", CPFS_VALIDOS[3]))
    assert r.status_code == 409 and r.json()["campos"] == {"cpf": "Já existe um cadastro com este CPF."}
    r = anon.post("/api/contas/cadastro", json=cadastro_valido("primeiro@teste.local", CPFS_VALIDOS[4]))
    assert r.status_code == 409 and r.json()["campos"] == {"email": "Já existe um cadastro com este e-mail."}
    r = anon.post(
        "/api/contas/cadastro",
        json=cadastro_valido("sem.aceite@teste.local", CPFS_VALIDOS[4], aceite_privacidade=False),
    )
    assert r.status_code == 422 and "aceite_privacidade" in r.json()["campos"]
    r = anon.post(
        "/api/contas/cadastro", json=cadastro_valido("sem.crm@teste.local", CPFS_VALIDOS[4], medico={"tipo": "CRM"})
    )
    assert r.status_code == 422 and {"medico.crm", "medico.uf"} <= set(r.json()["campos"])
    r = anon.post(
        "/api/contas/cadastro",
        json=cadastro_valido(
            "acons@teste.local",
            CPFS_VALIDOS[4],
            medico={"tipo": "ACONSELHADOR", "formacao": "Biomedicina", "instituicao": "Hospital"},
        ),
    )
    assert r.status_code == 201
    r = anon.post(
        "/api/contas/cadastro",
        json=cadastro_valido(
            "pesq.sem@teste.local", CPF(101), papel="PESQUISADOR", pesquisador={"tipo": "INDEPENDENTE", "orcid": "abc"}
        ),
    )
    assert r.status_code == 422 and {"pesquisador.cargo", "pesquisador.linha_pesquisa", "pesquisador.orcid"} <= set(
        r.json()["campos"]
    )


# ---------------------------------------------------------------------------
# Segurança: CSRF, limite de tentativas, sessão, dados fora de URL e do navegador
# ---------------------------------------------------------------------------
def test_requisicao_sem_token_csrf_e_recusada(plataforma, medico):
    sem = TestClient(plataforma["app"])
    sem.cookies = medico.cookies  # mesma sessão, sem o cabeçalho
    r = sem.post("/api/pacientes", json=registro_pessoa("Sem Token"))
    assert r.status_code == 403 and r.json()["erro"] == "csrf"
    r = sem.post("/api/pacientes", json={}, headers={"X-CSRF-Token": "token-errado"})
    assert r.status_code == 403 and r.json()["erro"] == "csrf"
    assert sem.get("/api/pacientes").status_code == 200  # leitura não exige o token
    assert any(a["acao"] == "acesso_negado" and "CSRF" in (a["detalhe"] or "") for a in acoes_auditadas(plataforma))


def test_limite_de_tentativas_bloqueia_login_com_erro_generico(plataforma):
    anon = TestClient(plataforma["app"])
    assert anon.post("/api/contas/cadastro", json=cadastro_valido("bloqueio@teste.local", CPF(102))).status_code == 201
    for _ in range(3):
        r = anon.post("/api/contas/login", json={"email": "bloqueio@teste.local", "senha": "errada-errada"})
        assert r.status_code == 401 and r.json()["mensagem"] == "E-mail ou senha inválidos."
    r = anon.post("/api/contas/login", json={"email": "bloqueio@teste.local", "senha": "senha-segura-123"})
    assert r.status_code == 429 and "tentativas" in r.json()["mensagem"].lower()
    # e-mail inexistente recebe o mesmo erro genérico (não revela se a conta existe)
    r = anon.post("/api/contas/login", json={"email": "nao.existe@teste.local", "senha": "qualquer-coisa-1"})
    assert r.status_code == 401 and r.json()["mensagem"] == "E-mail ou senha inválidos."
    acoes = acoes_auditadas(plataforma)
    assert sum(1 for a in acoes if a["acao"] == "login_falha") >= 4
    assert all("errada" not in (a["detalhe"] or "") for a in acoes)  # senha nunca na auditoria


def test_sessao_expira_por_inatividade_e_cookie_e_protegido(plataforma):
    c = entrar(plataforma, "pesquisador@demo.local")
    r = TestClient(plataforma["app"]).post(
        "/api/contas/login",
        json={"email": "pesquisador@demo.local", "senha": plataforma["cred"]["pesquisador@demo.local"]["senha"]},
    )
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and COOKIE_SESSAO in cookie
    assert r.headers["cache-control"] == "no-store" and "default-src 'self'" in r.headers["content-security-policy"]
    assert c.get("/api/contas/quem-sou-eu").status_code == 200
    with plataforma["app"].state.sessoes() as bd:
        s = bd.get(Sessao, hash_token(c.cookies[COOKIE_SESSAO]))
        s.ultimo_acesso = s.ultimo_acesso - _dt.timedelta(minutes=31)
        bd.commit()
    r = c.get("/api/contas/quem-sou-eu")
    assert r.status_code == 401 and r.json()["mensagem"] == permissoes.MENSAGEM_401
    # logout encerra a sessão
    c2 = entrar(plataforma, "pesquisador@demo.local")
    assert c2.post("/api/contas/logout").status_code == 200 and c2.get("/api/contas/quem-sou-eu").status_code == 401


def test_nenhum_dado_pessoal_em_url_nem_no_armazenamento_do_navegador(plataforma):
    app_js = (DIR_STATIC / "app.js").read_text(encoding="utf-8")
    assert "localStorage" not in app_js and "sessionStorage" not in app_js and "document.cookie" not in app_js
    assert "indexedDB" not in app_js
    # rotas por hash só com ids ou identificador aleatório da análise
    for hash_ in re.findall(r"#/[a-z/-]*\$\{[^}]+\}", app_js):
        assert re.search(
            r"\$\{(p\.id|pac\.id|id|r\.id|ids\[0\]|pacienteId|a\.paciente_id|u\.id|primeiro|proximo)\}", hash_
        ), hash_  # só ids e identificadores
    # parâmetros de rota da API são só ids/identificadores; busca por nome vai no corpo (POST)
    for rota in rotas_api(plataforma["app"]):
        for nome in re.findall(r"\{([^}]+)\}", rota.path):
            assert nome in (
                "usuario_id",
                "paciente_id",
                "consentimento_id",
                "descendente_id",
                "parente_id",
                "papel",
                "ident",
                "nome",
                "codigo",
                "analise_id",
                "documento_id",
            ), rota.path
    assert any(r.path == "/api/pacientes/busca" and "POST" in r.methods for r in rotas_api(plataforma["app"]))
    # a interface declara a CSP sem inline e carrega só recursos locais
    html = (DIR_STATIC / "index.html").read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html and 'src="/static/app.js"' in html


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------
ACOES_EXIGIDAS = {
    "cadastro",
    "login",
    "login_falha",
    "logout",
    "senha_alterada",
    "usuario_aprovado",
    "usuario_reprovado",
    "informacoes_solicitadas",
    "paciente_criado",
    "paciente_visualizado",
    "paciente_editado",
    "paciente_exportado",
    "paciente_excluido",
    "consentimento_registrado",
    "consentimento_revogado",
    "analise_executada",
    "pacote_baixado",
    "acesso_negado",
    "vcf_anexado",
    "vcf_removido",
    "descendente_editado",
    "casos_consultados",
    "casos_exportados",
    "documento_anexado",
    "documento_aberto",
    "documento_removido",
    "resultado_aberto",
}


def test_auditoria_registra_cada_acao_sem_nome_e_a_verificacao_detecta_adulteracao(
    plataforma, medico, admin, pesquisador
):
    p = paciente_do(medico)
    ficha = medico.get(f"/api/pacientes/{p['id']}").json()
    corpo = {
        "nome": p["nome"],
        "prontuario": "DEMO-0001",
        "momento": "APOS_LAUDO",
        "mae": genitor(ficha["genitores"]["MAE"]["nome"], ficha["genitores"]["MAE"]["data_nascimento"]),
        "pai": genitor(ficha["genitores"]["PAI"]["nome"], ficha["genitores"]["PAI"]["data_nascimento"]),
    }
    assert medico.put(f"/api/pacientes/{p['id']}", json=corpo).status_code == 200
    assert medico.post(f"/api/pacientes/{p['id']}/exportar").status_code == 200
    r = medico.put(
        "/api/contas/minha",
        json={
            "nome": "Outro Nome",
            "medico": {"tipo": "ACONSELHADOR", "crm": "999", "uf": "RJ", "especialidade": "Genética"},
        },
    )
    assert r.status_code == 200 and r.json()["nome"] != "Outro Nome"
    assert (
        r.json()["perfil"]["crm"] == "123456"
        and r.json()["perfil"]["uf"] == "SP"
        and r.json()["perfil"]["tipo"] == "CRM"
    )
    assert r.json()["perfil"]["especialidade"] == "Genética"
    assert anexar_cenario(medico, p["id"], "PAI", 1).status_code == 201  # substitui o anexo da demonstração
    assert medico.request("DELETE", f"/api/pacientes/{p['id']}/genitores/PAI/vcf").status_code == 200
    assert anexar_cenario(medico, p["id"], "PAI", 1).status_code == 201
    assert (
        medico.put(
            f"/api/pacientes/{p['id']}/descendentes/{p['descendentes'][0]['id']}",
            json={"nome": p["nome"], "data_nascimento": "1996-03-12", "sexo": "F"},
        ).status_code
        == 200
    )
    assert pesquisador.get("/api/pesquisa/casos").status_code == 200
    assert pesquisador.post("/api/pesquisa/casos/exportar", json={}).status_code == 200
    doc = medico.get(f"/api/pacientes/{p['id']}").json()["prontuario_documento"]
    assert medico.get(f"/api/pacientes/{p['id']}/documentos/{doc['id']}").status_code == 200
    r = medico.post(
        f"/api/pacientes/{p['id']}/documentos",
        data={"tipo": "LAUDO_C9ORF72", "papel": "PAI"},
        files={"arquivo": ("laudo.pdf", demo.pdf_ficticio(["laudo"]), "application/pdf")},
    )
    assert r.status_code == 201
    did = r.json()["genitores"]["PAI"]["laudo_documento"]["id"]
    assert medico.request("DELETE", f"/api/pacientes/{p['id']}/documentos/{did}").status_code == 200
    assert (
        medico.post(
            "/api/contas/minha/senha",
            json={"senha_atual": plataforma["cred"]["medico@demo.local"]["senha"], "senha_nova": "nova-senha-forte-9"},
        ).status_code
        == 200
    )
    plataforma["cred"]["medico@demo.local"]["senha"] = "nova-senha-forte-9"
    medico2 = entrar(plataforma, "medico@demo.local")
    r = medico2.post(
        "/api/analises",
        data={
            "modo": "cenario",
            "cenario": "1",
            "n": "300",
            "motor": "numpy",
            "cox": "0",
            "paciente_id": str(p["id"]),
            "descendente_id": str(p["descendentes"][0]["id"]),
            "confirma_assintomatico": "1",
        },
    )
    assert r.status_code == 201, r.text
    assert medico2.get(f"/api/analises/{r.json()['id']}/pacote.zip").status_code == 200
    arm = r.json()["armazenada"]
    assert medico2.get(f"/api/pacientes/{arm['paciente_id']}/analises/{arm['analise_id']}").status_code == 200
    anon = TestClient(plataforma["app"])
    assert (
        anon.post("/api/contas/cadastro", json=cadastro_valido("para.reprovar@teste.local", CPF(103))).status_code
        == 201
    )
    uid = next(
        u["id"]
        for u in admin.get("/api/admin/cadastros/pendentes").json()["cadastros"]
        if u["email"] == "para.reprovar@teste.local"
    )
    assert (
        admin.post(
            f"/api/admin/usuarios/{uid}/solicitar-informacoes", json={"mensagem": "Envie o número do CRM."}
        ).status_code
        == 200
    )
    assert admin.post(f"/api/admin/usuarios/{uid}/reprovar", json={"mensagem": "CRM não confere."}).status_code == 200
    assert medico2.post("/api/contas/logout").status_code == 200
    acoes = acoes_auditadas(plataforma)
    assert ACOES_EXIGIDAS <= {a["acao"] for a in acoes}
    assert all(a["acao"] in auditoria.ACOES for a in acoes)
    texto_auditoria = json.dumps(acoes, ensure_ascii=False)
    for dado in DADOS_PACIENTES:
        assert dado not in texto_auditoria, dado
    assert "nova-senha-forte-9" not in texto_auditoria
    # cadeia íntegra; adulterar um registro quebra a verificação a partir dele
    assert admin.get("/api/admin/auditoria/verificacao").json()["ok"] is True
    with plataforma["app"].state.sessoes() as bd:
        alvo = bd.execute(select(auditoria.Auditoria).where(auditoria.Auditoria.sequencia == 5)).scalar_one()
        original, alvo_id = alvo.detalhe, alvo.id
        bd.execute(text("UPDATE auditoria SET detalhe = 'adulterado' WHERE id = :id"), {"id": alvo_id})
        bd.commit()
        bd.expire_all()  # a sessão mantém os objetos em memória; forçar releitura do banco
        v = auditoria.verificar(bd)
        assert v["ok"] is False and v["primeira_falha"] == 5
        bd.execute(text("UPDATE auditoria SET detalhe = :d WHERE id = :id"), {"d": original, "id": alvo_id})
        bd.commit()
        bd.expire_all()
        assert auditoria.verificar(bd)["ok"] is True
    # o admin lê a auditoria completa (sem nomes) e o médico só a própria
    completa = admin.get("/api/admin/auditoria?por_pagina=500").json()
    assert completa["total"] >= len(acoes) and {r_["usuario_id"] for r_ in completa["registros"]} >= {None, 1, 2}
    propria = entrar(plataforma, "medico@demo.local").get("/api/contas/minha/auditoria").json()["registros"]
    assert propria and all(r_["usuario_id"] == 2 for r_ in propria)


# ---------------------------------------------------------------------------
# Painel do administrador e situação do cadastro
# ---------------------------------------------------------------------------
def test_fluxo_de_aprovacao_informacoes_resposta_desativacao(plataforma, admin):
    anon = TestClient(plataforma["app"])
    assert (
        anon.post(
            "/api/contas/cadastro", json=cadastro_valido("fluxo@teste.local", CPF(104), papel="PESQUISADOR")
        ).status_code
        == 201
    )
    u = entrar(plataforma, "fluxo@teste.local", "senha-segura-123")
    uid = u.get("/api/contas/quem-sou-eu").json()["usuario"]["id"]
    assert (
        admin.post(
            f"/api/admin/usuarios/{uid}/solicitar-informacoes", json={"mensagem": "Informe o vínculo."}
        ).status_code
        == 200
    )
    s = u.get("/api/contas/situacao").json()
    assert (
        s["situacao"] == "INFORMACOES_SOLICITADAS"
        and s["mensagem_admin"] == "Informe o vínculo."
        and s["pode_responder"]
    )
    assert u.post("/api/contas/situacao/resposta", json={"resposta": "Sou vinculado ao grupo X."}).status_code == 200
    assert u.get("/api/contas/situacao").json()["situacao"] == "PENDENTE"
    pend = next(x for x in admin.get("/api/admin/cadastros/pendentes").json()["cadastros"] if x["id"] == uid)
    assert pend["resposta_usuario"] == "Sou vinculado ao grupo X."
    assert admin.post(f"/api/admin/usuarios/{uid}/aprovar").status_code == 200
    assert u.get("/api/pesquisa/casos").status_code == 200
    # admin não altera a própria conta por aqui; desativar encerra sessões; reativar devolve VERIFICADO
    meu = admin.get("/api/contas/quem-sou-eu").json()["usuario"]["id"]
    assert admin.post(f"/api/admin/usuarios/{meu}/desativar").status_code == 409
    assert admin.post(f"/api/admin/usuarios/{uid}/desativar").status_code == 200
    assert u.get("/api/contas/quem-sou-eu").status_code == 401
    r = anon.post("/api/contas/login", json={"email": "fluxo@teste.local", "senha": "senha-segura-123"})
    assert r.status_code == 403 and "desativada" in r.json()["mensagem"]
    assert admin.post(f"/api/admin/usuarios/{uid}/reativar").json()["situacao"] == "VERIFICADO"
    assert admin.get("/api/admin/usuarios?papel=PESQUISADOR").json()["total"] >= 2
    assert admin.post("/api/admin/usuarios/busca", json={"texto": "fluxo@teste"}).json()["total"] == 1


def test_minha_conta_exporta_dados_e_registra_encerramento(plataforma, pesquisador, admin):
    r = pesquisador.get("/api/contas/minha").json()
    assert r["perfil"]["tipo"] == "INSTITUCIONAL" and {a["documento"] for a in r["aceites"]} == {
        "AVISO_PRIVACIDADE",
        "TERMO_USO",
    }
    assert all(a["versao"] == textos.VERSAO_TERMO_USO for a in r["aceites"] if a["documento"] == "TERMO_USO")
    r = pesquisador.put(
        "/api/contas/minha",
        json={
            "nome": "Pesquisador Renomeado",
            "pesquisador": {
                "tipo": "INDEPENDENTE",
                "cargo": "Pós-doc",
                "linha_pesquisa": "ELA",
                "orcid": "0000-0001-2345-6789",
            },
        },
    )
    # nome, CPF, tipo e ORCID são imutáveis depois do cadastro; cargo e linha mudam
    assert r.status_code == 200 and r.json()["perfil"]["cargo"] == "Pós-doc"
    assert r.json()["nome"] == "Pesquisador de Demonstração" and r.json()["perfil"]["orcid"] == "0000-0002-1825-0097"
    assert r.json()["perfil"]["tipo"] == "INDEPENDENTE"  # o vínculo (institucional/independente) continua editável
    assert pesquisador.get("/api/contas/minha").json()["imutaveis"] == [
        "nome",
        "cpf",
        "medico.tipo",
        "medico.crm",
        "medico.uf",
        "pesquisador.orcid",
    ]
    e = pesquisador.post("/api/contas/minha/exportar").json()
    assert (
        e["usuario"]["cpf"].count(".") == 2
        and e["auditoria_propria"]
        and e["usuario"]["email"] == "pesquisador@demo.local"
    )
    r = pesquisador.post("/api/contas/minha/encerramento").json()
    assert r["encerramento_solicitado_em"]
    assert pesquisador.get("/api/contas/minha").json()["encerramento_solicitado_em"] == r["encerramento_solicitado_em"]
    # administrador não pede encerramento (gere os demais usuários)
    assert admin.post("/api/contas/minha/encerramento").status_code == 403
    assert admin.get("/api/contas/minha").json()["encerramento_solicitado_em"] is None


def test_privacidade_publica_com_encarregado_e_termos_versionados(plataforma):
    anon = TestClient(plataforma["app"])
    s = anon.get("/api/sistema").json()
    assert (
        s["demonstracao"] is True
        and s["selo_demonstracao"]
        and s["versoes_termos"]["aviso_privacidade"] == textos.VERSAO_AVISO_PRIVACIDADE
    )
    p = anon.get("/api/privacidade").json()
    texto_p = json.dumps(p, ensure_ascii=False)
    for trecho in (
        "art. 5º, II",
        "art. 11, II, f",
        "art. 8º, §5º",
        "art. 13, §4º",
        "art. 18",
        "art. 41",
        "pseudonimizado",
        "art. 16",
    ):
        assert trecho in texto_p, trecho
    assert "anonimizado" not in texto_p  # sempre "pseudonimizado" (art. 12 e 13, §4º)
    assert s["encarregado"]["nome"] in texto_p
    assert (
        anon.post("/api/contas/login", data={"email": "x", "senha": "y"}).status_code == 415
    )  # só JSON nas rotas públicas


# ---------------------------------------------------------------------------
# Análises: upload, cenários, dono, pacote e extensões
# ---------------------------------------------------------------------------
def test_analise_por_upload_e_por_cenario_so_para_quem_executou(plataforma, medico, admin):
    sint = DIR_DADOS / "sinteticos"
    with open(sint / "cenario_2_mae.vcf", "rb") as fm, open(sint / "cenario_2_pai.vcf", "rb") as fp:
        r = medico.post(
            "/api/analises",
            data={
                "modo": "vcf",
                "n": "600",
                "semente": "3",
                "motor": "numpy",
                "cox": "1",
                "c9orf72_mae": "12,45",
                "c9orf72_pai": "8",
                "sexo": "M",
                "idade_atual": "40",
                "c9_antecipacao": "2",
                "confirma_assintomatico": "1",
            },
            files={"vcf_mae": ("Ana Ficticia Lima.vcf", fm, "text/plain"), "vcf_pai": ("pai.vcf", fp, "text/plain")},
        )
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["entrada"]["laudo_c9orf72"] == {"mae": [12, 45], "pai": 8} and res["metadados"]["laudo_c9orf72"] == {
        "mae": [12, 45],
        "pai": 8,
    }
    assert [x["variante"] for x in res["resumo"]] == ["C9orf72 expansão GGGGCC"] and res["cox"]["tabela"][0][
        "cox"
    ] == "ajustado"
    assert res["transmissao_c9orf72"]["hipoteses"]["antecipacao"] == 2.0 and "tabela_01c_transmissao_c9orf72" in {
        t["nome"] for t in res["tabelas"]
    }
    assert (
        "Ana Ficticia Lima" not in r.text and "Ana Ficticia Lima" not in res["relatorio_md"]
    )  # nome do arquivo nunca entra
    assert (
        set(res["curvas"]) == {"C9orf72 expansão GGGGCC", "qualquer lócus"}
        and len(res["curvas"]["C9orf72 expansão GGGGCC"]["t"]) == 91
    )
    assert res["limitacoes"]["modelo"] == textos.LIMITACAO_MODELO and res["aviso_legal"]
    ident = res["id"]
    pasta = plataforma["app"].state.analises.obter(
        ident, medico.get("/api/contas/quem-sou-eu").json()["usuario"]["id"]
    )["pasta"]
    assert not list(pasta.glob("*.vcf")) and not list(pasta.glob("*.vcf.gz"))  # VCFs apagados após a execução
    assert medico.get(f"/api/analises/{ident}").status_code == 200
    assert (
        medico.get(f"/api/analises/{ident}/figuras/figura_09_cox_vs_cura_mista.png").headers["content-type"]
        == "image/png"
    )
    assert medico.get(f"/api/analises/{ident}/figuras/../../etc/passwd").status_code in (404, 422)
    z = medico.get(f"/api/analises/{ident}/pacote.zip")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    import io
    import zipfile

    nomes = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "relatorio.md" in nomes and "metadados.json" in nomes and not any(n.endswith(".vcf") for n in nomes)
    outro = novo_medico_verificado(plataforma, admin, "medico.c@teste.local", CPF(105))
    assert (
        outro.get(f"/api/analises/{ident}").status_code == 404
        and outro.get(f"/api/analises/{ident}/pacote.zip").status_code == 404
    )
    # cenário de exemplo com registro (só em demonstração): sexo e idade vêm do descendente, não do formulário
    p = paciente_do(medico)
    d = p["descendentes"][0]
    r = medico.post(
        "/api/analises",
        data={
            "modo": "cenario",
            "cenario": "3",
            "n": "400",
            "motor": "numpy",
            "cox": "0",
            "paciente_id": str(p["id"]),
            "descendente_id": str(d["id"]),
            "sexo": "M",
            "idade_atual": "99",
            "confirma_assintomatico": "1",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["entrada"]["sexo"] == d["sexo"] and r.json()["entrada"]["idade_atual"] == d["idade"]
    assert p["nome"] not in r.text and d["nome"] not in r.text
    r = medico.post(
        "/api/analises",
        data={"modo": "cenario", "cenario": "3", "n": "400", "motor": "numpy", "paciente_id": str(p["id"])},
    )
    assert r.status_code == 422 and "descendente_id" in r.json()["campos"]
    # entradas inválidas
    r = medico.post("/api/analises", data={"modo": "vcf", "n": "10", "c9orf72_mae": "abc"})
    assert r.status_code == 422 and {"vcf_mae", "vcf_pai", "n", "c9orf72_mae"} <= set(r.json()["campos"])
    r = medico.post("/api/analises", data={"modo": "cenario", "cenario": "9"})
    assert r.status_code == 422
    assert {c["numero"] for c in medico.get("/api/cenarios").json()["cenarios"]} == {1, 2, 3, 4, 5}
    par = medico.get("/api/parametros").json()
    assert {g["gene"] for g in par["genes"]} == {"SOD1", "C9orf72", "TARDBP", "FUS"} and par["tabela_calibracao"]


def test_popular_demo_recusa_banco_com_usuarios(plataforma):
    with plataforma["app"].state.sessoes() as bd:
        with pytest.raises(RuntimeError):
            demo.popular(bd, Cifra(plataforma["cfg"].chave), plataforma["cfg"], analisar=False)


# ---------------------------------------------------------------------------
# Três casos, genitores, VCFs cifrados, suposição, resumo guardado, filtros, pesquisador, ajuda
# ---------------------------------------------------------------------------
def test_cadastro_dos_tres_casos_com_regras_de_descendentes_e_prontuario(plataforma, medico):
    # caso 1: exatamente uma pessoa; prontuário e genitores obrigatórios; situação clínica não existe mais
    r = medico.post("/api/pacientes", json={"tipo": "PESSOA", "descendentes": [], "situacao_clinica": "SINTOMATICO"})
    assert r.status_code == 422
    assert {"prontuario", "mae.nome", "mae.data_nascimento", "pai.nome", "pai.data_nascimento", "descendentes"} <= set(
        r.json()["campos"]
    )
    r = medico.post(
        "/api/pacientes",
        json=registro_pessoa("Pessoa Caso Um", "1991-04-04", "M", "P-1", situacao_clinica="SINTOMATICO"),
    )
    assert r.status_code == 201, r.text
    p1 = r.json()
    assert p1["tipo"] == "PESSOA" and p1["tipo_rotulo"].startswith("Caso 1") and p1["nome"] == "Pessoa Caso Um"
    assert "situacao_clinica" not in p1 and p1["descendentes"][0]["sexo"] == "M" and p1["vcfs_presentes"] == 0
    assert p1["genitores"]["MAE"]["rotulo"] == "Mãe" and p1["pesquisa_situacao"] == "NAO_INICIADO"
    # caso 2: casal, sem descendente, nome sugerido a partir dos parceiros, laudo validado
    corpo = {
        "tipo": "CASAL",
        "prontuario": "C-1",
        "mae": genitor("Parceira Teste", "1990-05-05", "12,45"),
        "pai": genitor("Parceiro Teste", "1989-06-06", "abc"),
    }
    r = medico.post("/api/pacientes", json=corpo)
    assert r.status_code == 422 and "pai.laudo_c9orf72" in r.json()["campos"]
    corpo["pai"]["laudo_c9orf72"] = None
    r = medico.post(
        "/api/pacientes",
        json={**corpo, "descendentes": [{"nome": "Não Pode", "data_nascimento": "2020-01-01", "sexo": "F"}]},
    )
    assert r.status_code == 422 and "descendentes" in r.json()["campos"]
    r = medico.post("/api/pacientes", json=corpo)
    assert r.status_code == 201, r.text
    p2 = r.json()
    assert p2["nome"] == "Parceira Teste e Parceiro Teste" and p2["tipo_rotulo"].startswith("Caso 2")
    assert (
        p2["genitores"]["MAE"]["rotulo"] == "Parceira (futura mãe)"
        and p2["genitores"]["MAE"]["laudo_c9orf72"] == "12,45"
    )
    assert p2["descendentes"] == [] and [e["titular"] for e in p2["pesquisa"]["exigidos"]] == ["MAE", "PAI"]
    # caso 3: família com nome obrigatório e ao menos um filho; momento do aconselhamento validado
    corpo = {
        "tipo": "FAMILIA",
        "prontuario": "F-1",
        "momento": "ERRADO",
        "mae": genitor("Mãe Família", "1950-01-01"),
        "pai": genitor("Pai Família", "1948-01-01"),
        "descendentes": [],
    }
    r = medico.post("/api/pacientes", json=corpo)
    assert r.status_code == 422 and {"nome", "descendentes", "momento"} <= set(r.json()["campos"])
    corpo.update(
        {
            "nome": "Família de Teste",
            "momento": "ANTES_DO_TESTE",
            "descendentes": [
                {"nome": "Filha Um", "data_nascimento": "1975-01-01", "sexo": "F"},
                {"nome": "Filho Dois", "data_nascimento": "2012-01-01", "sexo": "M"},
            ],
        }
    )
    r = medico.post("/api/pacientes", json=corpo)
    assert r.status_code == 201, r.text
    p3 = r.json()
    assert p3["tipo_rotulo"].startswith("Caso 3") and p3["momento_rotulo"] == "Antes do teste ou da consulta"
    assert [d["ordem"] for d in p3["descendentes"]] == [1, 2] and p3["descendentes"][1]["menor_de_idade"]
    assert [e["titular"] for e in p3["pesquisa"]["exigidos"]] == ["MAE", "PAI", "DESCENDENTE", "RESPONSAVEL"]
    # tipo desconhecido e tipo imutável na edição; descendente só se inclui em família
    assert medico.post("/api/pacientes", json={**registro_pessoa(), "tipo": "OUTRO"}).status_code == 422
    r = medico.put(
        f"/api/pacientes/{p1['id']}", json={**registro_pessoa("Pessoa Caso Um", prontuario="P-1b"), "tipo": "CASAL"}
    )
    assert r.status_code == 200 and r.json()["tipo"] == "PESSOA" and r.json()["prontuario"] == "P-1b"
    r = medico.post(
        f"/api/pacientes/{p1['id']}/descendentes",
        json={"nome": "Outro Filho", "data_nascimento": "2000-01-01", "sexo": "M"},
    )
    assert r.status_code == 422
    assert (
        medico.request("DELETE", f"/api/pacientes/{p3['id']}/descendentes/{p3['descendentes'][0]['id']}").status_code
        == 200
    )
    assert (
        medico.request("DELETE", f"/api/pacientes/{p3['id']}/descendentes/{p3['descendentes'][1]['id']}").status_code
        == 409
    )
    # opções para o formulário e os filtros
    op = medico.get("/api/pacientes/opcoes").json()
    assert [t["valor"] for t in op["tipos"]] == ["PESSOA", "CASAL", "FAMILIA"] and set(op["genes"]) == {
        "SOD1",
        "C9orf72",
        "TARDBP",
        "FUS",
    }
    assert len(op["momentos"]) == 3 and op["suposicao_nao_portador"]


def test_vcf_do_genitor_e_validado_cifrado_substituivel_e_removivel(plataforma, medico):
    p = medico.post("/api/pacientes", json=registro_pessoa("Pessoa Com Vcf", prontuario="V-1")).json()
    pid = p["id"]
    # extensão errada, vazio, conteúdo inválido, montagem divergente
    r = medico.post(f"/api/pacientes/{pid}/genitores/MAE/vcf", files={"vcf": ("x.txt", b"abc", "text/plain")})
    assert r.status_code == 422 and ".vcf" in r.json()["campos"]["vcf"]
    r = medico.post(f"/api/pacientes/{pid}/genitores/MAE/vcf", files={"vcf": ("x.vcf", b"", "text/plain")})
    assert r.status_code == 422 and "vazio" in r.json()["campos"]["vcf"].lower()
    r = medico.post(
        f"/api/pacientes/{pid}/genitores/MAE/vcf", files={"vcf": ("x.vcf", b"isto nao e um vcf\n", "text/plain")}
    )
    assert r.status_code == 422 and "vcf" in r.json()["campos"]
    grch37 = (SINT / "cenario_1_mae.vcf").read_text(encoding="utf-8").replace("GRCh38", "GRCh37")
    r = medico.post(f"/api/pacientes/{pid}/genitores/MAE/vcf", files={"vcf": ("x.vcf", grch37.encode(), "text/plain")})
    assert r.status_code == 422 and "GRCh38" in r.json()["campos"]["vcf"]
    assert (
        medico.post(
            f"/api/pacientes/{pid}/genitores/AVO/vcf", files={"vcf": ("x.vcf", b"##fileformat=VCFv4.2\n", "text/plain")}
        ).status_code
        == 404
    )
    assert medico.post(f"/api/pacientes/{pid}/genitores/MAE/vcf").status_code == 422  # sem arquivo
    # anexo válido: cifrado, com hash, sem nome original; substituir apaga o anterior; remover apaga
    r = anexar_cenario(medico, pid, "MAE", 1)
    assert r.status_code == 201, r.text
    v = r.json()["genitores"]["MAE"]["vcf"]
    assert v["presente"] and v["tamanho"] > 100 and len(v["hash_curto"]) == 12 and v["enviado_em"]
    assert "Nome Pessoal" not in r.text
    with plataforma["app"].state.sessoes() as bd:
        g = bd.get(Paciente, pid).genitor("MAE")
        arquivo1 = plataforma["cfg"].dir_vcfs / g.vcf_arquivo
        assert (
            arquivo1.exists() and b"##fileformat" not in arquivo1.read_bytes() and g.vcf_hash and len(g.vcf_hash) == 64
        )
        assert Cifra(plataforma["cfg"].chave).decifrar_bytes(arquivo1.read_bytes()).startswith(b"##fileformat")
    r = anexar_cenario(medico, pid, "MAE", 2)
    assert (
        r.status_code == 201
        and not arquivo1.exists()
        and r.json()["genitores"]["MAE"]["vcf"]["hash_curto"] != v["hash_curto"]
    )
    assert medico.request("DELETE", f"/api/pacientes/{pid}/genitores/MAE/vcf").status_code == 200
    assert (
        not list(plataforma["cfg"].dir_vcfs.glob("*.vcf"))
        and medico.get(f"/api/pacientes/{pid}").json()["vcfs_presentes"] == 0
    )
    assert medico.request("DELETE", f"/api/pacientes/{pid}/genitores/MAE/vcf").status_code == 404
    # exportação traz só metadados do VCF, nunca o conteúdo
    assert anexar_cenario(medico, pid, "PAI", 1).status_code == 201
    e = medico.post(f"/api/pacientes/{pid}/exportar").text
    assert "##fileformat" not in e and "hash_curto" in e
    acoes = {a["acao"] for a in acoes_auditadas(plataforma)}
    assert {"vcf_anexado", "vcf_removido"} <= acoes


def test_analise_pela_ficha_usa_anexos_grava_resumo_e_declara_suposicao(plataforma, medico):
    pacientes = medico.get("/api/pacientes").json()["pacientes"]
    ana = next(p for p in pacientes if p["nome"].startswith("Ana"))
    did = ana["descendentes"][0]["id"]
    base = {"n": "300", "motor": "numpy", "cox": "0", "paciente_id": str(ana["id"]), "confirma_assintomatico": "1"}
    # VCFs dos anexos, laudo da ficha, sexo e idade do descendente; o formulário não pode sobrepor
    r = medico.post(
        "/api/analises", data={**base, "descendente_id": str(did), "sexo": "M", "idade_atual": "5", "c9orf72_mae": "45"}
    )
    assert r.status_code == 201, r.text
    res = r.json()
    assert (
        res["entrada"]["tipo"] == "PESSOA"
        and res["entrada"]["sexo"] == "F"
        and res["entrada"]["idade_atual"] == ana["descendentes"][0]["idade"]
    )
    # o laudo vem da ficha (outros testes do módulo podem tê-la editado); sem o laudo dos dois, o C9orf72 fica indeterminado
    genit = medico.get(f"/api/pacientes/{ana['id']}").json()["genitores"]
    laudos = {
        lado: int(genit[papel]["laudo_c9orf72"])
        for papel, lado in (("MAE", "mae"), ("PAI", "pai"))
        if genit[papel]["laudo_c9orf72"]
    }
    assert res["entrada"]["laudo_c9orf72"] == (laudos or None) and res["c9orf72_indeterminado"] is (len(laudos) < 2)
    assert res["entrada"]["suposicoes"] == {} and res["entrada"]["resumo_id"]
    # pessoa com idade: os três indicadores valem a partir dessa idade, sem sintomas (e não desde o nascimento)
    pr, idade_ana = res["principais"], ana["descendentes"][0]["idade"]
    assert pr["condicionado"] is True and pr["idade_referencia"] == idade_ana and pr["F"] == {}
    assert 0.45 < pr["transmissao"] < 0.5 and 0 < pr["vida"]["q025"] < pr["vida"]["valor"] < pr["vida"]["q975"] < 1
    assert set(pr["janelas"]) == {"10", "20"}
    assert 0 < pr["janelas"]["10"]["valor"] < pr["janelas"]["20"]["valor"] < pr["vida"]["valor"]
    assert idade_ana < pr["inicio"]["q25"] < pr["inicio"]["mediana"] < pr["inicio"]["q75"]
    assert res["entrada"]["assintomatico_confirmado"] is True and res["entrada"]["assintomatico_confirmado_em"]
    assert ana["nome"] not in r.text and "Maria" not in res["relatorio_md"]
    ficha = medico.get(f"/api/pacientes/{ana['id']}").json()
    ult = ficha["ultima_analise"]
    assert ficha["n_analises"] >= 1 and "SOD1" in ficha["genes_de_risco"]
    assert ult["condicionado"] is True and ult["idade_referencia"] == idade_ana
    assert ult["p_portador"] == pr["transmissao"] and ult["p_manifesta"] == pr["vida"]["valor"]
    assert ult["idade_mediana"] == pr["inicio"]["mediana"] and ult["assintomatico_confirmado"] is True
    # sem a confirmação de que a pessoa não tem sintomas, a análise não roda
    sem_conf = {k: v for k, v in base.items() if k != "confirma_assintomatico"}
    r_sem = medico.post("/api/analises", data={**sem_conf, "descendente_id": str(did)})
    assert r_sem.status_code == 422 and "confirma_assintomatico" in r_sem.json()["campos"]
    assert ficha["ultima_analise"]["id"] == res["entrada"]["resumo_id"]  # outros testes do módulo já analisaram Ana
    assert (
        ficha["analises"][-1]["resumo"]["loci"][0]["gene"] == "SOD1"
        and ficha["comparativo"][0]["descendente_nome"] == ana["nome"]
    )
    with plataforma["app"].state.sessoes() as bd:
        a = bd.execute(select(AnalisePaciente).where(AnalisePaciente.paciente_id == ana["id"])).scalars().first()
        assert a and b"SOD1" not in a.resumo_cifrado.encode() and a.vcf_hash_mae and a.descendente_id == did
        ultima = (
            bd.execute(select(AnalisePaciente).where(AnalisePaciente.id == res["entrada"]["resumo_id"])).scalars().one()
        )
        assert ultima.assintomatico_confirmado is True and ultima.assintomatico_confirmado_em is not None
    # genitor sem VCF: exige a suposição; os dois sem VCF: não roda; a suposição fica no resultado e no resumo
    casal = next(p for p in pacientes if p["nome"].startswith("Fernanda"))
    r = medico.post("/api/analises", data={**base, "paciente_id": str(casal["id"])})
    assert r.status_code == 422 and "vcf_pai" in r.json()["campos"]
    r = medico.post("/api/analises", data={**base, "paciente_id": str(casal["id"]), "assumir_nao_portador": "MAE,PAI"})
    assert r.status_code == 422 and "assumir_nao_portador" in r.json()["campos"]
    r = medico.post(
        "/api/analises",
        data={**base, "paciente_id": str(casal["id"]), "assumir_nao_portador": "PAI", "sexo_filho": "M"},
    )
    assert r.status_code == 201, r.text
    res = r.json()
    assert (
        res["entrada"]["suposicoes"] == {"nao_portador": ["PAI"], "laudo_normal_suposto": ["PAI"]}
        and res["entrada"]["sexo"] == "M"
        and res["entrada"]["idade_atual"] is None
    )
    assert res["entrada"]["laudo_c9orf72"] == {"mae": 45, "pai": cenarios.LAUDO_NORMAL}
    assert res["principais"]["transmissao"] == 0.5 and not res["c9orf72_indeterminado"]
    # futuro filho: indicadores desde o nascimento, sem pessoa a confirmar
    assert res["principais"]["condicionado"] is False and set(res["principais"]["F"]) == {"50", "60", "70"}
    assert res["entrada"]["assintomatico_confirmado"] is None
    assert [x["variante"] for x in res["resumo"]] == ["C9orf72 expansão GGGGCC"] and res["suposicoes_texto"][
        "nao_portador"
    ]
    ficha = medico.get(f"/api/pacientes/{casal['id']}").json()
    assert (
        ficha["com_suposicao"]
        and ficha["ultima_analise"]["suposicoes"]["nao_portador"] == ["PAI"]
        and ficha["comparativo"][0]["descendente_nome"] == "Futuro filho"
    )
    r = medico.post(
        "/api/analises",
        data={**base, "paciente_id": str(casal["id"]), "descendente_id": "1", "assumir_nao_portador": "PAI"},
    )
    assert r.status_code == 422 and "descendente_id" in r.json()["campos"]
    # família: um filho por vez; o comparativo lista cada filho
    fam = next(p for p in pacientes if "Ramos" in p["nome"])
    for d in fam["descendentes"]:
        r = medico.post("/api/analises", data={**base, "paciente_id": str(fam["id"]), "descendente_id": str(d["id"])})
        assert r.status_code == 201, r.text
        assert r.json()["entrada"]["sexo"] == d["sexo"]
    ficha = medico.get(f"/api/pacientes/{fam['id']}").json()
    assert [c["descendente_nome"] for c in ficha["comparativo"]] == [d["nome"] for d in fam["descendentes"]]
    # SOD1 recessivo, pais heterozigotos: 0,25 ao nascer; menor para quem chegou à idade atual sem sintomas
    assert all(c["condicionado"] and 0.1 < c["p_portador"] < 0.25 for c in ficha["comparativo"])
    assert [c["idade_referencia"] for c in ficha["comparativo"]] == [d["idade"] for d in fam["descendentes"]]
    # cenário de exemplo com registro só em demonstração
    d2 = Path(str(plataforma["cfg"].bd.parent)) / "prod"
    cfg2 = Configuracao(chave=plataforma["cfg"].chave, bd=d2 / "bd.sqlite3", dir_vcfs=d2 / "vcfs", demonstracao=False)
    app2 = criar_app(cfg2)
    with app2.state.sessoes() as bd:
        cred = demo.popular(bd, Cifra(cfg2.chave), cfg2, analisar=False)["credenciais"]
    c2 = TestClient(app2)
    r = c2.post(
        "/api/contas/login",
        json={
            "email": "medico@demo.local",
            "senha": next(c["senha"] for c in cred if c["email"] == "medico@demo.local"),
        },
    )
    c2.headers["X-CSRF-Token"] = r.json()["csrf"]
    p = c2.get("/api/pacientes").json()["pacientes"][0]
    r = c2.post(
        "/api/analises",
        data={
            "modo": "cenario",
            "cenario": "1",
            "n": "200",
            "paciente_id": str(p["id"]),
            "descendente_id": str(p["descendentes"][0]["id"]),
        },
    )
    assert r.status_code == 422 and "modo" in r.json()["campos"]
    assert (
        c2.get("/api/sistema").json()["demonstracao"] is False
        and c2.get("/api/sistema").json()["selo_demonstracao"] is None
    )


def test_filtros_do_medico_funcao_pura_e_rota(plataforma, medico):
    def item(**k):
        base = {
            "nome": "Zé",
            "prontuario": "1",
            "tipo": "PESSOA",
            "momento": None,
            "genitores": {"MAE": {"nome": "m"}, "PAI": {"nome": "p"}},
            "descendentes": [{"nome": "Zé", "idade": 40, "sexo": "M", "menor_de_idade": False}],
            "pesquisa_situacao": "NAO_INICIADO",
            "vcfs_completos": True,
            "genes_de_risco": [],
            "n_analises": 0,
            "risco_maximo": None,
            "laudo_informado": False,
            "com_suposicao": False,
            "ultima_analise": None,
            "criado_em": "2026-11-15T10:00:00Z",
        }
        base.update(k)
        return base

    itens = [
        item(
            nome="Ana",
            genes_de_risco=["SOD1"],
            n_analises=1,
            risco_maximo=0.3,
            ultima_analise={"executado_em": "2026-11-15T12:00:00Z"},
            pesquisa_situacao="LIBERADO",
        ),
        item(
            nome="Bia",
            tipo="CASAL",
            descendentes=[],
            vcfs_completos=False,
            com_suposicao=True,
            genes_de_risco=["C9orf72"],
            n_analises=1,
            risco_maximo=0.1,
            ultima_analise={"executado_em": "2026-11-01T12:00:00Z"},
            laudo_informado=True,
        ),
        item(
            nome="Caio",
            descendentes=[{"nome": "Caio", "idade": 10, "sexo": "M", "menor_de_idade": True}],
            momento="APOS_LAUDO",
            criado_em="2026-10-01T10:00:00Z",
        ),
    ]
    f = mod_pacientes.filtrar_pacientes
    nomes = lambda r: [x["nome"] for x in r]  # noqa: E731
    assert nomes(f(itens, {})) == ["Ana", "Bia", "Caio"]
    assert nomes(f(itens, {"genes": ["sod1"]})) == ["Ana"] and nomes(f(itens, {"genes": ["SOD1", "C9orf72"]})) == [
        "Ana",
        "Bia",
    ]
    assert nomes(f(itens, {"tipo": "CASAL"})) == ["Bia"] and nomes(f(itens, {"sexo": "M"})) == ["Ana", "Caio"]
    assert nomes(f(itens, {"idade_min": 30})) == ["Ana"] and nomes(f(itens, {"idade_max": 12})) == ["Caio"]
    assert nomes(f(itens, {"menor_de_idade": True})) == ["Caio"] and nomes(f(itens, {"menor_de_idade": False})) == [
        "Ana",
        "Bia",
    ]
    assert nomes(f(itens, {"momento": "APOS_LAUDO"})) == ["Caio"] and nomes(f(itens, {"pesquisa": "LIBERADO"})) == [
        "Ana"
    ]
    assert nomes(f(itens, {"vcfs": "INCOMPLETOS"})) == ["Bia"] and nomes(f(itens, {"analise": "SEM"})) == ["Caio"]
    assert nomes(f(itens, {"risco_min": 0.2})) == ["Ana"] and nomes(f(itens, {"laudo_c9orf72": True})) == ["Bia"]
    assert nomes(f(itens, {"suposicao": True})) == ["Bia"] and nomes(f(itens, {"analise_de": "2026-11-10"})) == ["Ana"]
    assert nomes(f(itens, {"analise_ate": "2026-11-10"})) == ["Bia"] and nomes(
        f(itens, {"cadastro_ate": "2026-10-31"})
    ) == ["Caio"]
    assert nomes(f(itens, {"texto": "cai"})) == ["Caio"] and nomes(f(itens, {"texto": "m"})) == ["Ana", "Bia", "Caio"]
    assert nomes(f(itens, {"ordenar": "risco", "direcao": "desc"})) == ["Ana", "Bia", "Caio"]
    assert nomes(f(itens, {"ordenar": "idade"})) == ["Caio", "Ana", "Bia"] and nomes(
        f(itens, {"ordenar": "cadastro"})
    ) == ["Caio", "Ana", "Bia"]
    assert nomes(f(itens, {"ordenar": "ultima_analise", "direcao": "desc"})) == ["Ana", "Bia", "Caio"]
    # rota: filtros no corpo, validação dos valores, eco dos filtros ativos
    r = medico.post("/api/pacientes/busca", json={"tipo": "CASAL"})
    assert (
        r.status_code == 200
        and all(p["tipo"] == "CASAL" for p in r.json()["pacientes"])
        and r.json()["filtros"] == {"tipo": "CASAL"}
    )
    r = medico.post("/api/pacientes/busca", json={"texto": "ramos", "sexo": "f"})
    assert r.status_code == 200 and [p["nome"] for p in r.json()["pacientes"]] == ["Família Fictícia Ramos"]
    r = medico.post("/api/pacientes/busca", json={"ordenar": "x", "pesquisa": "y", "analise_de": "ontem", "vcfs": "z"})
    assert r.status_code == 422 and {"ordenar", "pesquisa", "analise_de", "vcfs"} <= set(r.json()["campos"])
    assert medico.post("/api/pacientes/busca", json={"idade_min": 200}).status_code == 422


def test_pesquisador_ve_so_casos_liberados_pseudonimizados_com_filtros_totais_e_csv(plataforma, medico, pesquisador):
    pacientes = medico.get("/api/pacientes").json()["pacientes"]
    liberados = {p["nome"] for p in pacientes if p["liberado_para_pesquisa"]}
    assert liberados >= {"Ana Fictícia Lima", "Carla Fictícia Alves"}
    carla = next(p for p in pacientes if p["nome"].startswith("Carla"))
    r = medico.post(
        "/api/analises",
        data={
            "n": "300",
            "motor": "numpy",
            "cox": "0",
            "paciente_id": str(carla["id"]),
            "descendente_id": str(carla["descendentes"][0]["id"]),
            "confirma_assintomatico": "1",
        },
    )
    assert r.status_code == 201, r.text
    c = pesquisador.get("/api/pesquisa/casos").json()
    assert len(c["casos"]) == len(liberados) and c["mensagem"] is None and c["opcoes"]["genes"]
    caso = next(x for x in c["casos"] if "C9orf72" in x["genes_de_risco"] and x["tipo"] == "PESSOA")
    assert (
        len(caso["codigo"]) == 32
        and caso["descendentes"][0]["faixa_etaria"] == "30–39"
        and caso["descendentes"][0]["sexo"] == "F"
    )
    a = caso["descendentes"][0]["analise"]
    assert (
        a["executado_em"].count("-") == 1
        and "id" not in a
        and "descendente_id" not in a
        and a["p_portador"]
        and a["inicio"]["mediana"]
    )
    assert (
        c["totais"]["casos"] == len(liberados)
        and c["totais"]["por_gene"]["C9orf72"] >= 1
        and c["totais"]["analises"] >= 1
    )
    texto_c = json.dumps(c, ensure_ascii=False)
    for dado in DADOS_PACIENTES:
        assert dado not in texto_c, dado
    assert "medico" not in texto_c and "prontuario" not in texto_c and "data_nascimento" not in texto_c
    assert "documento" not in texto_c and "ficticio.pdf" not in texto_c
    # filtros e totais
    r = pesquisador.post("/api/pesquisa/casos/busca", json={"genes": ["C9orf72"], "sexo": "F"})
    assert (
        r.status_code == 200 and all("C9orf72" in x["genes_de_risco"] for x in r.json()["casos"]) and r.json()["casos"]
    )
    r = pesquisador.post(
        "/api/pesquisa/casos/busca", json={"decada": "30–39", "heranca": "dominante", "risco_min": 0.05}
    )
    assert r.status_code == 200 and r.json()["totais"]["casos"] >= 1
    assert (
        pesquisador.post("/api/pesquisa/casos/busca", json={"com_analise": False}).json()["casos"][0]["n_analises"] == 0
        if pesquisador.post("/api/pesquisa/casos/busca", json={"com_analise": False}).json()["casos"]
        else True
    )
    r = pesquisador.post("/api/pesquisa/casos/busca", json={"decada": "x", "analise_de": "2026"})
    assert r.status_code == 422 and {"decada", "analise_de"} <= set(r.json()["campos"])
    # função pura
    casos = c["casos"]
    assert mod_pesquisa.filtrar_casos(casos, {"tipo": "FAMILIA"}) == [] or all(
        x["tipo"] == "FAMILIA" for x in mod_pesquisa.filtrar_casos(casos, {"tipo": "FAMILIA"})
    )
    assert mod_pesquisa.decada(7) == "0–9" and mod_pesquisa.decada(105) == "100+"
    # CSV pseudonimizado, uma linha por análise, decimal com vírgula
    r = pesquisador.post("/api/pesquisa/casos/exportar", json={"genes": ["C9orf72"]})
    assert (
        r.status_code == 200
        and r.headers["content-type"].startswith("text/csv")
        and "casos_pseudonimizados.csv" in r.headers["content-disposition"]
    )
    linhas = r.text.lstrip("﻿").splitlines()
    assert linhas[0].startswith("codigo;tipo;momento;pessoa;sexo;faixa_etaria;analise_em") and len(linhas) >= 2
    assert ";0," in linhas[1] and caso["codigo"] in r.text
    for dado in DADOS_PACIENTES:
        assert dado not in r.text, dado
    # detalhe de um registro: variantes dos VCFs, dosagens, curva e metadados, sem identificadores nem VCF
    d = pesquisador.get(f"/api/pesquisa/casos/{caso['codigo']}")
    assert d.status_code == 200, d.text
    an = d.json()["descendentes"][0]["analise"]
    assert an["variantes"] and {"amostra", "gene", "posicao", "ref", "alt", "classe", "dosagem"} <= set(
        an["variantes"][0]
    )
    assert an["vetor"] and an["loci"] and an["curva"]["t"] and len(an["curva"]["F"]) == len(an["curva"]["t"])
    for dado in DADOS_PACIENTES:
        assert dado not in d.text, dado
    assert "##fileformat" not in d.text and "vcf_arquivo" not in d.text and "medico" not in d.text
    assert pesquisador.get("/api/pesquisa/casos/" + "0" * 32).status_code == 404
    assert pesquisador.get("/api/pesquisa/casos/abc").status_code == 404
    r = pesquisador.post("/api/pesquisa/casos/exportar-variantes", json={"genes": ["C9orf72"]})
    assert r.status_code == 200 and r.text.lstrip("\ufeff").startswith("codigo;tipo;pessoa;analise_em;genitor;gene;")
    assert caso["codigo"] in r.text and len(r.text.splitlines()) >= 2
    r = pesquisador.post("/api/pesquisa/casos/exportar-detalhado", json={})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    det = json.loads(r.text)
    assert det["registros"] and any(
        x["analise"] and x["analise"]["variantes"] for c_ in det["registros"] for x in c_["descendentes"]
    )
    for dado in DADOS_PACIENTES:
        assert dado not in r.text, dado
    # revogar um consentimento retira o caso da lista do pesquisador
    cid = next(x["id"] for x in medico.get(f"/api/pacientes/{carla['id']}").json()["consentimentos"] if x["ativo"])
    assert medico.post(f"/api/pacientes/{carla['id']}/consentimentos/{cid}/revogar").status_code == 200
    assert len(pesquisador.get("/api/pesquisa/casos").json()["casos"]) == len(liberados) - 1
    acoes = {a["acao"] for a in acoes_auditadas(plataforma)}
    assert {"casos_consultados", "casos_exportados"} <= acoes


def test_ajuda_publica_descreve_os_tres_casos_e_nenhum_aviso_experimental_na_interface(plataforma):
    anon = TestClient(plataforma["app"])
    a = anon.get("/api/ajuda").json()
    assert [c["tipo"] for c in a["casos"]] == ["PESSOA", "CASAL", "FAMILIA"] and a["casos"][1]["rotulo"].startswith(
        "Caso 2"
    )
    assert len(a["fora_do_escopo"]) == 6 and len(a["usos"]) == 3 and a["encarregado"]["nome"] and a["fluxo"]
    # fora do escopo declarado: sintomáticos, números agregados da família, fenótipo de parente sem genótipo e
    # ancestralidade; o genótipo de parentes entra, e a independência entre genes continua assumida e declarada
    fora = " ".join(a["fora_do_escopo"]).lower()
    for termo in ("sintomátic", "pelo menos um filho", "sem genótipo", "ancestralidade"):
        assert termo in fora, termo
    assert "parentes" in a["limitacao"] and "independência entre os genes" in a["limitacao"]
    assert "parente testado" in " ".join(a["fluxo"]) and "não apresenta sintomas" in " ".join(a["fluxo"])
    priv = anon.get("/api/privacidade").text
    assert "parente" in priv and "sem sintomas" in priv and "sem nenhum dado clínico" in priv
    s = anon.get("/api/sistema").json()
    assert s["marca"] == "EloSense" and s["marca_subtitulo"]
    assert s["ambiente"] == "homologacao" and s["demonstracao"] is True and "homologação" in s["selo_demonstracao"]
    assert Configuracao(chave=plataforma["cfg"].chave).ambiente == "producao"
    assert Configuracao(chave=plataforma["cfg"].chave, ambiente="homologacao").demonstracao is True
    with pytest.raises(Exception):
        Configuracao(chave=plataforma["cfg"].chave, ambiente="teste")
    # os textos exibidos (privacidade, termo de uso, ajuda) não chamam o sistema de experimental
    for caminho in ("/api/privacidade", "/api/ajuda"):
        assert "experimental" not in anon.get(caminho).text.lower(), caminho
    assert "experimental" not in json.dumps(s["termo_uso"], ensure_ascii=False).lower()
    for arquivo in ("app.js", "index.html"):
        conteudo = (DIR_STATIC / arquivo).read_text(encoding="utf-8")
        assert "aviso_experimental" not in conteudo and "Sistema experimental" not in conteudo, arquivo


def test_painel_do_medico_resume_so_os_proprios_registros(plataforma, medico, admin):
    r = medico.get("/api/pacientes/painel")
    assert r.status_code == 200, r.text
    d = r.json()
    lista = medico.get("/api/pacientes").json()["pacientes"]
    assert d["totais"]["registros"] == len(lista) and sum(d["totais"]["por_tipo"].values()) == len(lista)
    assert d["totais"]["analises"] == sum(p["n_analises"] for p in lista)
    assert d["totais"]["liberados_pesquisa"] == sum(1 for p in lista if p["liberado_para_pesquisa"])
    assert len(d["recentes"]) <= 6 and all("nome" in p and "ultima_analise" in p for p in d["recentes"])
    assert all({"registro", "pessoa", "executado_em", "genes_de_risco"} <= set(a) for a in d["analises_recentes"])
    assert all(p["vcfs_presentes"] < 2 for p in d["pendencias"]["sem_vcf"])
    outro = novo_medico_verificado(plataforma, admin, "medico.painel@teste.local", CPF(106))
    v = outro.get("/api/pacientes/painel").json()
    assert v["totais"]["registros"] == 0 and v["recentes"] == [] and v["analises_recentes"] == []
    for dado in DADOS_PACIENTES:
        assert dado not in outro.get("/api/pacientes/painel").text


def test_documentos_cifrados_e_resultados_completos_guardados(plataforma, medico, admin):
    pacientes = medico.get("/api/pacientes").json()["pacientes"]
    ana = next(p for p in pacientes if p["nome"].startswith("Ana"))
    pid, did = ana["id"], ana["descendentes"][0]["id"]
    cfg = plataforma["cfg"]
    ficha = medico.get(f"/api/pacientes/{pid}").json()
    # documentos da demonstração: prontuário anexado; o arquivo em disco é cifrado e tem nome aleatório
    doc = ficha["prontuario_documento"]
    assert doc and doc["tipo"] == "PRONTUARIO" and doc["mime"] == "application/pdf" and doc["nome"].endswith(".pdf")
    assert all(b"%PDF" not in f.read_bytes() and "prontuario" not in f.name for f in cfg.dir_documentos.glob("*.bin"))
    ab = medico.get(f"/api/pacientes/{pid}/documentos/{doc['id']}")
    assert (
        ab.status_code == 200
        and ab.headers["content-type"].startswith("application/pdf")
        and ab.content.startswith(b"%PDF")
    )
    # validação: tipo, genitor, extensão, conteúdo, vazio
    pdf = demo.pdf_ficticio(["laudo de teste"])
    r = medico.post(
        f"/api/pacientes/{pid}/documentos", data={"tipo": "OUTRO"}, files={"arquivo": ("a.pdf", pdf, "application/pdf")}
    )
    assert r.status_code == 422 and "tipo" in r.json()["campos"]
    r = medico.post(
        f"/api/pacientes/{pid}/documentos",
        data={"tipo": "LAUDO_C9ORF72"},
        files={"arquivo": ("a.pdf", pdf, "application/pdf")},
    )
    assert r.status_code == 422 and "papel" in r.json()["campos"]
    r = medico.post(
        f"/api/pacientes/{pid}/documentos",
        data={"tipo": "PRONTUARIO"},
        files={"arquivo": ("a.txt", b"x", "text/plain")},
    )
    assert r.status_code == 422 and "arquivo" in r.json()["campos"]
    r = medico.post(
        f"/api/pacientes/{pid}/documentos",
        data={"tipo": "PRONTUARIO"},
        files={"arquivo": ("a.png", b"nao e png", "image/png")},
    )
    assert r.status_code == 422 and "conteúdo" in r.json()["campos"]["arquivo"]
    r = medico.post(
        f"/api/pacientes/{pid}/documentos",
        data={"tipo": "PRONTUARIO"},
        files={"arquivo": ("a.pdf", b"", "application/pdf")},
    )
    assert r.status_code == 422
    # substituir o prontuário apaga o arquivo anterior; anexar laudo do pai; remover
    with plataforma["app"].state.sessoes() as bd:
        from ela_preditivo.web.modelos import Documento

        antigo = bd.get(Documento, doc["id"]).arquivo
    assert (cfg.dir_documentos / antigo).exists()
    r = medico.post(
        f"/api/pacientes/{pid}/documentos",
        data={"tipo": "PRONTUARIO"},
        files={"arquivo": ("Prontuario Ana.pdf", pdf, "application/pdf")},
    )
    assert r.status_code == 201 and r.json()["prontuario_documento"]["nome"] == "Prontuario Ana.pdf"
    assert not (cfg.dir_documentos / antigo).exists() and r.json()["prontuario_documento"]["id"] != doc["id"]
    assert "Prontuario Ana" not in plataforma["cfg"].bd.read_bytes().decode("latin-1")  # nome original cifrado no banco
    r = medico.post(
        f"/api/pacientes/{pid}/documentos",
        data={"tipo": "LAUDO_C9ORF72", "papel": "PAI"},
        files={"arquivo": ("laudo.png", b"\x89PNG\r\n\x1a\n...", "image/png")},
    )
    assert r.status_code == 201 and r.json()["genitores"]["PAI"]["laudo_documento"]["mime"] == "image/png"
    laudo_id = r.json()["genitores"]["PAI"]["laudo_documento"]["id"]
    assert medico.request("DELETE", f"/api/pacientes/{pid}/documentos/{laudo_id}").status_code == 200
    assert medico.get(f"/api/pacientes/{pid}").json()["genitores"]["PAI"]["laudo_documento"] is None
    # outro médico: 404 em tudo
    outro = novo_medico_verificado(plataforma, admin, "medico.docs@teste.local", CPF(107))
    novo_doc = medico.get(f"/api/pacientes/{pid}").json()["prontuario_documento"]["id"]
    assert outro.get(f"/api/pacientes/{pid}/documentos/{novo_doc}").status_code == 404
    assert outro.request("DELETE", f"/api/pacientes/{pid}/documentos/{novo_doc}").status_code == 404
    assert (
        outro.post(
            f"/api/pacientes/{pid}/documentos",
            data={"tipo": "PRONTUARIO"},
            files={"arquivo": ("a.pdf", pdf, "application/pdf")},
        ).status_code
        == 404
    )
    # resultado completo guardado: reabrir, figura, pacote; lista de análises; 404 para outro médico
    r = medico.post(
        "/api/analises",
        data={
            "n": "300",
            "motor": "numpy",
            "cox": "0",
            "paciente_id": str(pid),
            "descendente_id": str(did),
            "confirma_assintomatico": "1",
        },
    )
    assert r.status_code == 201, r.text
    arm = r.json()["armazenada"]
    assert arm["paciente_id"] == pid
    g = medico.get(f"/api/pacientes/{pid}/analises/{arm['analise_id']}")
    assert g.status_code == 200 and g.json()["principais"] == r.json()["principais"] and g.json()["relatorio_md"]
    fig = g.json()["figuras"][0]["nome"]
    assert (
        medico.get(f"/api/pacientes/{pid}/analises/{arm['analise_id']}/figuras/{fig}").headers["content-type"]
        == "image/png"
    )
    assert medico.get(f"/api/pacientes/{pid}/analises/{arm['analise_id']}/figuras/../x").status_code in (404, 422)
    z = medico.get(f"/api/pacientes/{pid}/analises/{arm['analise_id']}/pacote.zip")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    assert outro.get(f"/api/pacientes/{pid}/analises/{arm['analise_id']}").status_code == 404
    assert all(b"relatorio" not in f.read_bytes()[:200] for f in cfg.dir_analises.glob("*.bin"))  # cifrado em disco
    lista = medico.get("/api/pacientes/analises").json()
    assert lista["total"] >= 1 and any(
        a["id"] == arm["analise_id"] and a["tem_resultado"] and a["registro"] == ana["nome"] for a in lista["analises"]
    )
    assert {x["id"] for x in lista["registros"]} >= {pid} and outro.get("/api/pacientes/analises").json()["total"] == 0
    # excluir um registro apaga documentos e resultados do disco
    r = medico.post("/api/pacientes", json=registro_pessoa("Pessoa Com Arquivos", "1985-01-01", "F", "ARQ-1"))
    pid2 = r.json()["id"]
    assert (
        anexar_cenario(medico, pid2, "MAE", 1).status_code == 201
        and anexar_cenario(medico, pid2, "PAI", 1).status_code == 201
    )
    assert (
        medico.post(
            f"/api/pacientes/{pid2}/documentos",
            data={"tipo": "PRONTUARIO"},
            files={"arquivo": ("p.pdf", pdf, "application/pdf")},
        ).status_code
        == 201
    )
    r = medico.post(
        "/api/analises",
        data={
            "n": "300",
            "motor": "numpy",
            "cox": "0",
            "paciente_id": str(pid2),
            "descendente_id": str(r.json()["descendentes"][0]["id"]),
            "confirma_assintomatico": "1",
        },
    )
    assert r.status_code == 201, r.text
    with plataforma["app"].state.sessoes() as bd:
        from ela_preditivo.web.modelos import Documento

        p2 = bd.get(Paciente, pid2)
        arquivos_disco = [
            cfg.dir_analises / p2.analises[0].resultado_arquivo,
            cfg.dir_analises / p2.analises[0].pacote_arquivo,
        ]
        arquivos_disco += [cfg.dir_documentos / x.arquivo for x in p2.documentos]
    assert all(a.exists() for a in arquivos_disco)
    assert (
        medico.request("DELETE", f"/api/pacientes/{pid2}", json={"confirmacao_nome": "Pessoa Com Arquivos"}).status_code
        == 200
    )
    assert not any(a.exists() for a in arquivos_disco)
    acoes = {a["acao"] for a in acoes_auditadas(plataforma)}
    assert {"documento_anexado", "documento_aberto", "documento_removido", "resultado_aberto"} <= acoes


def test_auditoria_sob_pedidos_simultaneos(plataforma, medico):
    """Dois pedidos auditados ao mesmo tempo não podem colidir na sequência nem bifurcar a cadeia."""
    from concurrent.futures import ThreadPoolExecutor

    pacientes = medico.get("/api/pacientes").json()["pacientes"]
    ana = next(p for p in pacientes if p["nome"].startswith("Ana"))
    ficha = medico.get(f"/api/pacientes/{ana['id']}").json()
    doc = ficha["prontuario_documento"]["id"]
    analise = next(a for a in ficha["analises"] if a["tem_resultado"])
    caminhos = [
        f"/api/pacientes/{ana['id']}/analises/{analise['id']}",
        f"/api/pacientes/{ana['id']}/documentos/{doc}",
    ] * 6
    with ThreadPoolExecutor(max_workers=6) as ex:
        codigos = list(ex.map(lambda c: medico.get(c).status_code, caminhos))
    assert codigos == [200] * len(caminhos), codigos
    with plataforma["app"].state.sessoes() as bd:
        assert auditoria.verificar(bd)["ok"]


def test_genitor_sem_laudo_deixa_o_c9orf72_indeterminado_na_analise(plataforma, medico):
    """Na plataforma, genitor com VCF e sem laudo do C9orf72 → lócus descartado, resultado parcial declarado;
    com o laudo normal dos dois registrado, o lócus volta ao cálculo."""
    base = {"n": "300", "motor": "numpy", "cox": "0", "confirma_assintomatico": "1"}
    sem = medico.post("/api/pacientes", json=registro_pessoa("Pessoa Sem Laudo", "1990-05-05", "F", "SL-1"))
    assert sem.status_code == 201, sem.text
    pid, did = sem.json()["id"], sem.json()["descendentes"][0]["id"]
    assert anexar_cenario(medico, pid, "MAE", 1).status_code == 201
    assert anexar_cenario(medico, pid, "PAI", 1).status_code == 201
    r = medico.post("/api/analises", data={**base, "paciente_id": str(pid), "descendente_id": str(did)})
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["c9orf72_indeterminado"] is True and res["entrada"]["laudo_c9orf72"] is None
    assert res["entrada"]["suposicoes"] == {} and res["texto_c9orf72_indeterminado"]
    assert "expansão GGGGCC" in res["metadados"]["loci_descartados"] and [x["gene"] for x in res["resumo"]] == ["SOD1"]
    assert "Resultado parcial para o C9orf72" in res["relatorio_md"]
    ficha = medico.get(f"/api/pacientes/{pid}").json()
    assert ficha["analises"][-1]["resumo"]["c9orf72_indeterminado"] is True and ficha["genes_de_risco"] == ["SOD1"]
    normal = str(cenarios.LAUDO_NORMAL)
    com = medico.post(
        "/api/pacientes",
        json=registro_pessoa(
            "Pessoa Com Laudo",
            "1990-05-05",
            "F",
            "SL-2",
            mae=genitor("Mãe Testada", "1960-02-02", normal),
            pai=genitor("Pai Testado", "1958-03-03", normal),
        ),
    )
    assert com.status_code == 201, com.text
    pid2, did2 = com.json()["id"], com.json()["descendentes"][0]["id"]
    assert anexar_cenario(medico, pid2, "MAE", 1).status_code == 201
    assert anexar_cenario(medico, pid2, "PAI", 1).status_code == 201
    r = medico.post("/api/analises", data={**base, "paciente_id": str(pid2), "descendente_id": str(did2)})
    assert r.status_code == 201, r.text
    assert r.json()["c9orf72_indeterminado"] is False and r.json()["metadados"]["loci_descartados"] == []
    assert r.json()["entrada"]["laudo_c9orf72"] == {"mae": cenarios.LAUDO_NORMAL, "pai": cenarios.LAUDO_NORMAL}


def test_indicadores_condicionados_confirmacao_e_horizonte_pela_api(plataforma, medico, pesquisador):
    """Análise de pessoa com idade exige a confirmação de assintomático e devolve os três indicadores condicionados;
    sem idade (futuro filho) valem desde o nascimento; "risco vitalício" é o mesmo número em toda parte."""
    base = {"modo": "cenario", "n": "400", "motor": "numpy", "cox": "0"}
    # cenário 1, mulher de 55 anos sem sintomas: 39,3 % de chance de portar e 11,3 % de risco daqui em diante
    r = medico.post("/api/analises", data={**base, "cenario": "1", "sexo": "F", "idade_atual": "55"})
    assert r.status_code == 422 and "confirma_assintomatico" in r.json()["campos"]
    r = medico.post(
        "/api/analises", data={**base, "cenario": "1", "sexo": "F", "idade_atual": "55", "confirma_assintomatico": "1"}
    )
    assert r.status_code == 201, r.text
    res = r.json()
    pr = res["principais"]
    assert pr["condicionado"] is True and pr["idade_referencia"] == 55 and pr["horizonte"] == 90
    assert pr["transmissao"] == pytest.approx(0.3930, abs=5e-5) and pr["vida"]["valor"] == pytest.approx(
        0.1130, abs=5e-5
    )
    assert set(pr["janelas"]) == {"10", "20"} and pr["F"] == {} and 55 < pr["inicio"]["mediana"] < 90
    assert res["metadados"]["indicadores_condicionados"]["idade_referencia"] == 55
    assert res["entrada"]["assintomatico_confirmado"] is True
    # o relatório traz os mesmos números (49,... não: 39,3 % e 11,3 %)
    assert "para 39.3%" in res["relatorio_md"] and "é 11.3%" in res["relatorio_md"]
    t4 = next(t for t in res["tabelas"] if t["nome"] == "tabela_04_risco_condicional")
    linha = next(l for l in t4["linhas"] if l["idade_atual"] == 55)
    assert linha["p_portador_condicional"] == pytest.approx(pr["transmissao"])
    assert linha["risco_vitalicio"] == pytest.approx(pr["vida"]["valor"])
    # sem idade: futuro filho, sem confirmação, indicadores desde o nascimento
    r = medico.post("/api/analises", data={**base, "cenario": "5", "sexo": "F"})
    assert r.status_code == 201, r.text
    res5 = r.json()
    pr5 = res5["principais"]
    assert pr5["condicionado"] is False and pr5["idade_referencia"] is None and set(pr5["F"]) == {"50", "60", "70"}
    assert res5["entrada"]["assintomatico_confirmado"] is None
    # FUS no cenário 5: 0,0918 na Tabela 3 e na Tabela 4 (idade 0); o indicador combinado bate com as duas tabelas
    t3 = next(t for t in res5["tabelas"] if t["nome"] == "tabela_03_risco_vitalicio")
    t4 = next(t for t in res5["tabelas"] if t["nome"] == "tabela_04_risco_condicional")
    col = "fração que manifesta em algum momento (sem limite de idade)"
    fus3 = next(l for l in t3["linhas"] if l["variante"].startswith("FUS"))
    fus4 = next(l for l in t4["linhas"] if l["unidade"].startswith("FUS") and l["idade_atual"] == 0)
    assert fus3["p_manifesta_exato"] == pytest.approx(0.0918, abs=5e-5) and fus3[col] == pytest.approx(0.0960, abs=5e-5)
    assert fus4["risco_vitalicio"] == pytest.approx(fus3["p_manifesta_exato"], abs=1e-9)
    comb3 = next(l for l in t3["linhas"] if l["variante"] == "qualquer lócus")
    comb4 = next(l for l in t4["linhas"] if l["unidade"] == "qualquer lócus" and l["idade_atual"] == 0)
    assert pr5["vida"]["valor"] == pytest.approx(comb3["p_manifesta_exato"]) == pytest.approx(comb4["risco_vitalicio"])
    assert col in t3["colunas"]
    # resumo guardado na ficha, lista de análises e painel usam os valores condicionados, com a idade de referência
    ana = next(p for p in medico.get("/api/pacientes").json()["pacientes"] if p["nome"].startswith("Ana"))
    did = ana["descendentes"][0]["id"]
    r = medico.post(
        "/api/analises",
        data={
            "n": "400",
            "motor": "numpy",
            "cox": "0",
            "paciente_id": str(ana["id"]),
            "descendente_id": str(did),
            "confirma_assintomatico": "1",
        },
    )
    assert r.status_code == 201, r.text
    pra, aid = r.json()["principais"], r.json()["entrada"]["resumo_id"]
    idade = ana["descendentes"][0]["idade"]
    ficha = medico.get(f"/api/pacientes/{ana['id']}").json()
    guardado = next(a for a in ficha["analises"] if a["id"] == aid)
    assert guardado["assintomatico_confirmado"] is True and guardado["assintomatico_confirmado_em"]
    resumo = guardado["resumo"]
    assert resumo["condicionado"] is True and resumo["idade_referencia"] == idade
    assert resumo["transmissao"] == pra["transmissao"] and resumo["vida"] == pra["vida"]
    assert resumo["janelas"] == pra["janelas"] and resumo["inicio"] == pra["inicio"]
    locus = resumo["loci"][0]
    assert locus["p_portador"] == 0.5 and locus["p_portador_condicional"] == pytest.approx(pra["transmissao"])
    assert locus["risco_residual"] == pytest.approx(pra["vida"]["valor"])
    lista = medico.get("/api/pacientes/analises").json()["analises"]
    item = next(a for a in lista if a["id"] == aid)
    assert item["condicionado"] is True and item["idade_referencia"] == idade
    assert item["p_portador"] == pra["transmissao"] and item["p_manifesta"] == pra["vida"]["valor"]
    painel = medico.get("/api/pacientes/painel").json()
    recente = next(a for a in painel["analises_recentes"] if a["id"] == aid)
    assert recente["idade_referencia"] == idade and recente["p_manifesta"] == pra["vida"]["valor"]
    # o pesquisador recebe a referência só por década, nunca a idade exata; o CSV traz os valores condicionados
    casos = pesquisador.get("/api/pesquisa/casos").json()["casos"]
    visto = [d["analise"] for c in casos for d in c["descendentes"] if d["analise"] and d["analise"]["condicionado"]]
    assert visto and all("idade_referencia" not in a and "idade_na_analise" not in a for a in visto)
    assert all(re.fullmatch(r"\d+–\d+|100\+", a["faixa_idade_referencia"]) for a in visto)
    csv = pesquisador.post("/api/pesquisa/casos/exportar", json={}).text.lstrip("\ufeff").splitlines()
    cab = csv[0].split(";")
    assert {"faixa_idade_referencia", "risco_10_anos", "risco_20_anos", "p_manifesta_vida"} <= set(cab)
    i_ref, i_10 = cab.index("faixa_idade_referencia"), cab.index("risco_10_anos")
    assert any(l.split(";")[i_ref] and l.split(";")[i_10] for l in csv[1:])


def test_demonstracao_nao_tem_menor_de_idade():
    hoje = _dt.date.today()
    for r in demo.REGISTROS_FICTICIOS:
        for d in r["descendentes"]:
            nasc = _dt.date.fromisoformat(d["nascimento"])
            idade = hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
            assert idade >= 18, d["nome"]
        assert "enor de idade" not in r["observacoes"]


# ---------------------------------------------------------------------------
# Genitor sem exame inferido por parentes: situação clínica, parentes testados, filho já testado, LGPD
# ---------------------------------------------------------------------------
def anexar_parente(
    cliente, pid: int, papel: str, parentesco: str, arquivo: str | None = None, laudo: str | None = None
):
    dados = {"parentesco": parentesco}
    if laudo is not None:
        dados["laudo_c9orf72"] = laudo
    if arquivo is None:
        return cliente.post(f"/api/pacientes/{pid}/genitores/{papel}/parentes", data=dados)
    with open(SINT / arquivo, "rb") as f:
        return cliente.post(
            f"/api/pacientes/{pid}/genitores/{papel}/parentes",
            data=dados,
            files={"vcf": ("Nome Do Parente.vcf", f, "text/plain")},
        )


def test_demonstracao_traz_genitor_inferido_por_parentes_e_filho_testado(plataforma, medico):
    pacientes = medico.get("/api/pacientes").json()["pacientes"]
    heitor = next(p for p in pacientes if p["nome"].startswith("Heitor"))
    assert heitor["genitores_inferidos"] == ["PAI"] and heitor["pode_analisar"] and heitor["n_parentes"] == 1
    ficha = medico.get(f"/api/pacientes/{heitor['id']}").json()
    pai = ficha["genitores"]["PAI"]
    assert pai["vcf"]["presente"] is False and pai["inferido_por_parentes"] is True
    assert pai["situacao_clinica"] == "FALECIDO_SEM_ELA" and pai["idade_situacao"] == 60 and pai["situacao_rotulo"]
    assert [(x["parentesco"], x["rotulo"], x["vcf"]["presente"]) for x in pai["parentes"]] == [
        ("MAE_DO_GENITOR", "Avó paterna", True)
    ]
    assert "PARENTE" in [e["titular"] for e in ficha["pesquisa"]["exigidos"]]  # o parente também é titular
    base = {"n": "500", "motor": "numpy", "cox": "0", "confirma_assintomatico": "1"}
    did = ficha["descendentes"][0]["id"]
    r = medico.post("/api/analises", data={**base, "paciente_id": str(heitor["id"]), "descendente_id": str(did)})
    assert r.status_code == 201, r.text
    res = r.json()
    # avó heterozigota, pai falecido sem ELA aos 60: 17,92 % de chance de o neto portar, ao nascer
    assert res["resumo"][0]["p_portador_exato"] == pytest.approx(0.1792, abs=5e-5)
    assert res["resumo"][0]["p_manifesta_exato"] == pytest.approx(0.0935, abs=1e-4)
    assert res["principais"]["condicionado"] and res["principais"]["transmissao"] < 0.1792  # 38 anos sem sintomas
    inf = res["parentes"]
    assert inf["genitores"]["pai"]["situacao"] == "falecido_sem_ela" and inf["penetrancia_compartilhada"] is True
    locus = inf["loci_inferidos"][0]
    assert locus["p_genitor_portador_genotipos"] == pytest.approx(0.5)
    assert locus["p_genitor_portador_condicionada"] == pytest.approx(0.3585, abs=5e-4)
    assert inf["suposicoes"] and res["texto_inferencia"] and res["limite_inferior"] is False
    assert res["aviso_parceiro_inferido"] is None and res["entrada"]["parentes"]["PAI"]["inferido"] is True
    assert "tabela_01d_genitor_inferido" in {t["nome"] for t in res["tabelas"]}
    assert "Genitor inferido por parentes" in {s["titulo"] for s in res["secoes"]}
    assert res["vetor"][0]["genitor_inferido"] == "pai" and res["vetor"][0]["dosagem_pai"] is None
    assert res["entrada"]["suposicoes"] == {}  # nada foi assumido: a dosagem do pai é inferida
    for nome in ("Heitor", "Otávio", "Tereza", "DEMO-0007"):
        assert nome not in r.text, nome
    pasta = plataforma["app"].state.analises.obter(
        res["id"], medico.get("/api/contas/quem-sou-eu").json()["usuario"]["id"]
    )["pasta"]
    assert not list(pasta.glob("*.vcf")) and not list(pasta.glob("*.vcf.gz"))  # VCFs dos parentes também são apagados
    guardado = medico.get(f"/api/pacientes/{heitor['id']}").json()["analises"][-1]["resumo"]
    assert guardado["parentes"]["loci_inferidos"] and guardado["parentes"]["pessoas"][0] == {
        "parente": "avó paterna",
        "com_vcf": True,
        "com_laudo": True,
    }
    # família com filho já testado: ele é evidência e sai da lista de pessoas em risco
    fam = next(p for p in pacientes if p["nome"] == "Família Fictícia Teles")
    testada, jonas = fam["descendentes"]
    assert testada["testado"] is True and jonas["testado"] is False and fam["genitores_inferidos"] == ["PAI"]
    r = medico.post("/api/analises", data={**base, "paciente_id": str(fam["id"]), "descendente_id": str(testada["id"])})
    assert r.status_code == 422 and "já fez o teste" in r.json()["campos"]["descendente_id"]
    r = medico.post("/api/analises", data={**base, "paciente_id": str(fam["id"]), "descendente_id": str(jonas["id"])})
    assert r.status_code == 201, r.text
    locus = r.json()["parentes"]["loci_inferidos"][0]
    assert locus["p_genitor_portador_genotipos"] == pytest.approx(1 / 3)  # avó portadora; mãe e filha negativas
    assert "filho(a) já testado(a): 0" in locus["parentes_e_dosagens"]
    assert r.json()["entrada"]["parentes"]["filhos_testados"] == 1
    assert any("suposta herdada" in s for s in r.json()["parentes"]["suposicoes"])


def test_parentes_situacao_clinica_e_filho_testado_pela_api(plataforma, medico, pesquisador, admin):
    normal = str(cenarios.LAUDO_NORMAL)
    corpo = registro_pessoa(
        "Pessoa Com Avó Testada",
        "1986-07-07",
        "F",
        "PAR-1",
        mae=genitor("Mãe Testada Par", "1960-02-02", normal),
        pai=genitor("Pai Sem Exame Par", "1958-03-03"),
    )
    r = medico.post("/api/pacientes", json=corpo)
    assert r.status_code == 201, r.text
    pid, did = r.json()["id"], r.json()["descendentes"][0]["id"]
    assert r.json()["pode_analisar"] is False and r.json()["genitores"]["PAI"]["parentes"] == []
    assert anexar_cenario(medico, pid, "MAE", 1).status_code == 201  # mãe testada, sem a variante
    base = {"n": "500", "motor": "numpy", "cox": "0", "confirma_assintomatico": "1", "paciente_id": str(pid)}
    analisar = lambda **extra: medico.post(
        "/api/analises", data={**base, "descendente_id": str(did), **extra}
    )  # noqa: E731
    r = analisar()
    assert r.status_code == 422 and "parente testado" in r.json()["campos"]["vcf_pai"]
    # validação do parente: parentesco, e VCF ou laudo
    r = anexar_parente(medico, pid, "PAI", "PRIMO", "cenario_1_pai.vcf")
    assert r.status_code == 422 and "parentesco" in r.json()["campos"]
    r = anexar_parente(medico, pid, "PAI", "MAE_DO_GENITOR")
    assert r.status_code == 422 and "vcf" in r.json()["campos"]
    r = anexar_parente(medico, pid, "PAI", "MAE_DO_GENITOR", laudo="abc")
    assert r.status_code == 422 and "laudo_c9orf72" in r.json()["campos"]
    r = anexar_parente(medico, pid, "MAE", "MAE_DO_GENITOR", "cenario_1_pai.vcf")  # a mãe tem VCF: é observada
    assert r.status_code == 422 and "já tem VCF" in r.json()["campos"]["parentesco"]
    antes = len(list(plataforma["cfg"].dir_vcfs.glob("*.bin")))
    r = anexar_parente(medico, pid, "PAI", "MAE_DO_GENITOR", "cenario_1_pai.vcf", laudo=normal)  # avó heterozigota
    assert r.status_code == 201, r.text
    pai = r.json()["genitores"]["PAI"]
    assert pai["inferido_por_parentes"] is True and r.json()["pode_analisar"] is True
    xid = pai["parentes"][0]["id"]
    assert pai["parentes"][0]["laudo_c9orf72"] == normal and pai["parentes"][0]["vcf"]["hash_curto"]
    assert "Nome Do Parente" not in r.text and "vcf_arquivo" not in r.text
    arquivos_vcf = list(plataforma["cfg"].dir_vcfs.glob("*.bin"))
    assert len(arquivos_vcf) == antes + 1 and all(b"##fileformat" not in a.read_bytes() for a in arquivos_vcf)
    assert anexar_parente(medico, pid, "PAI", "MAE_DO_GENITOR", "cenario_1_pai.vcf").status_code == 422  # já existe
    # a situação clínica do genitor sem exame é obrigatória quando há parente
    r = analisar()
    assert r.status_code == 422 and "situacao_pai" in r.json()["campos"]
    sit = f"/api/pacientes/{pid}/genitores/PAI/situacao"
    assert medico.put(sit, json={"situacao": "DOENTE"}).status_code == 422
    assert "idade" in medico.put(sit, json={"situacao": "FALECIDO_SEM_ELA"}).json()["campos"]
    r = medico.put(sit, json={"situacao": "VIVO_ASSINTOMATICO"})  # vivo: idade pela data de nascimento
    assert (
        r.status_code == 200 and r.json()["genitores"]["PAI"]["idade_situacao"] == r.json()["genitores"]["PAI"]["idade"]
    )
    r = medico.put(sit, json={"situacao": "FALECIDO_SEM_ELA", "idade": 60})
    assert r.status_code == 200 and r.json()["genitores"]["PAI"]["situacao_clinica"] == "FALECIDO_SEM_ELA"
    with plataforma["app"].state.sessoes() as bd:
        g = bd.get(Paciente, pid).genitor("PAI")
        assert "FALECIDO" not in g.situacao_clinica_cifrada  # dado de saúde cifrado em repouso
    r = analisar()
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["resumo"][0]["p_portador_exato"] == pytest.approx(0.1792, abs=5e-5) and not res["c9orf72_indeterminado"]
    assert (
        res["metadados"]["parentes"]["genitores"]["pai"]["idade"] == 60 and res["metadados"]["sorteios_rejeitados"] > 0
    )
    # Hardy-Weinberg pedido, mas a tabela curada não tem frequência: volta à suposição de não portador, registrada
    r = analisar(prior_avos="hardy_weinberg")
    assert r.status_code == 201 and r.json()["entrada"]["prior_avos"] == "hardy_weinberg"
    assert r.json()["parentes"]["loci_inferidos"][0]["prior_dos_avos_sem_exame"] == "suposto não portador"
    assert analisar(prior_avos="uniforme").status_code == 422
    # genitor afetado: sem condicionamento, resultado rotulado como limite inferior
    assert (
        medico.put(sit, json={"situacao": "AFETADO", "idade": 55}).json()["genitores"]["PAI"]["idade_situacao"] is None
    )
    r = analisar()
    assert r.status_code == 201 and r.json()["limite_inferior"] is True and r.json()["texto_limite_inferior"]
    assert r.json()["resumo"][0]["p_portador_exato"] == pytest.approx(0.25)
    assert medico.put(sit, json={"situacao": "FALECIDO_SEM_ELA", "idade": 60}).status_code == 200
    assert analisar().status_code == 201  # a última análise guardada volta a ser a do pai falecido sem ELA aos 60
    # RBAC e isolamento: só o médico dono mexe nos parentes
    assert anexar_parente(pesquisador, pid, "PAI", "IRMAO_DO_GENITOR", "cenario_1_mae.vcf").status_code == 403
    assert admin.put(sit, json={"situacao": "AFETADO"}).status_code == 403
    outro = novo_medico_verificado(plataforma, admin, "medico.parentes@teste.local", CPF(108))
    assert anexar_parente(outro, pid, "PAI", "IRMAO_DO_GENITOR", "cenario_1_mae.vcf").status_code == 404
    assert outro.request("DELETE", f"/api/pacientes/{pid}/parentes/{xid}").status_code == 404
    assert outro.put(sit, json={"situacao": "AFETADO"}).status_code == 404
    # pesquisa: o parente é titular; sem o consentimento dele o caso não é liberado
    cons = f"/api/pacientes/{pid}/consentimentos"
    for titular, extra in (("MAE", {}), ("PAI", {}), ("DESCENDENTE", {"descendente_id": did})):
        r = medico.post(cons, json={"titular": titular, "confirmado": True, "versao_termo": VERSAO_TERMO, **extra})
        assert r.status_code == 201, r.text
    assert r.json()["liberado_para_pesquisa"] is False
    assert [e["titular"] for e in r.json()["pesquisa"]["exigidos"] if not e["consentido"]] == ["PARENTE"]
    r = medico.post(
        cons, json={"titular": "PARENTE", "parente_id": xid, "confirmado": True, "versao_termo": VERSAO_TERMO}
    )
    assert r.status_code == 422 and "nome_titular" in r.json()["campos"]
    r = medico.post(
        cons,
        json={
            "titular": "PARENTE",
            "nome_titular": "Avó Que Consentiu",
            "confirmado": True,
            "versao_termo": VERSAO_TERMO,
        },
    )
    assert r.status_code == 422 and "parente_id" in r.json()["campos"]
    r = medico.post(
        cons,
        json={
            "titular": "PARENTE",
            "parente_id": xid,
            "nome_titular": "Avó Que Consentiu",
            "confirmado": True,
            "versao_termo": VERSAO_TERMO,
        },
    )
    assert r.status_code == 201 and r.json()["liberado_para_pesquisa"] is True
    casos = pesquisador.get("/api/pesquisa/casos").json()["casos"]
    caso = next(c for c in casos if c["genitores"]["PAI"]["parentes"] == ["MAE_DO_GENITOR"] and c["n_analises"])
    assert caso["descendentes"][0]["analise"]["inferido_por_parentes"] is True
    det = pesquisador.get(f"/api/pesquisa/casos/{caso['codigo']}").json()["descendentes"][0]["analise"]
    assert det["parentes"]["genitores"]["pai"] == {
        "situacao": "falecido_sem_ela",
        "faixa_idade": "60–69",
        "limite_inferior": False,
    }
    assert det["parentes"]["loci_inferidos"] and "Avó Que Consentiu" not in json.dumps(det, ensure_ascii=False)
    # um irmão a mais, com laudo apenas; depois remoção: o arquivo cifrado e o consentimento saem juntos
    r = anexar_parente(medico, pid, "PAI", "IRMAO_DO_GENITOR", laudo=normal)
    assert r.status_code == 201 and len(r.json()["genitores"]["PAI"]["parentes"]) == 2
    assert r.json()["liberado_para_pesquisa"] is False  # parente novo: falta o consentimento dele
    yid = r.json()["genitores"]["PAI"]["parentes"][1]["id"]
    assert medico.request("DELETE", f"/api/pacientes/{pid}/parentes/{yid}").json()["liberado_para_pesquisa"] is True
    r = medico.request("DELETE", f"/api/pacientes/{pid}/parentes/{xid}")
    assert (
        r.status_code == 200
        and r.json()["genitores"]["PAI"]["parentes"] == []
        and r.json()["genitores_inferidos"] == []
    )
    assert len(list(plataforma["cfg"].dir_vcfs.glob("*.bin"))) == antes
    with plataforma["app"].state.sessoes() as bd:
        assert bd.execute(select(Parente).where(Parente.paciente_id == pid)).scalars().all() == []
        assert not [c for c in bd.get(Paciente, pid).consentimentos if c.titular == "PARENTE"]
    assert medico.request("DELETE", f"/api/pacientes/{pid}/parentes/{xid}").status_code == 404
    assert analisar().status_code == 422
    acoes = acoes_auditadas(plataforma)
    assert {"parente_adicionado", "parente_removido"} <= {a["acao"] for a in acoes}
    for a in acoes:
        if a["acao"] in ("parente_adicionado", "parente_removido", "paciente_editado"):
            assert "Avó" not in (a["detalhe"] or "") and "FALECIDO" not in (a["detalhe"] or "")
    # VCF de filho já testado: só no caso de família
    r = medico.post(f"/api/pacientes/{pid}/descendentes/{did}/vcf", files={"vcf": ("f.vcf", b"x", "text/plain")})
    assert r.status_code == 422 and "caso 3" in r.json()["campos"]["vcf"]
    fam = next(p for p in medico.get("/api/pacientes").json()["pacientes"] if "Ramos" in p["nome"])
    fid = fam["descendentes"][0]["id"]
    with open(SINT / "cenario_4_mae.vcf", "rb") as f:
        r = medico.post(
            f"/api/pacientes/{fam['id']}/descendentes/{fid}/vcf", files={"vcf": ("Filho.vcf", f, "text/plain")}
        )
    assert r.status_code == 201 and r.json()["descendentes"][0]["testado"] is True
    r = medico.request("DELETE", f"/api/pacientes/{fam['id']}/descendentes/{fid}/vcf")
    assert r.status_code == 200 and r.json()["descendentes"][0]["testado"] is False
    assert medico.request("DELETE", f"/api/pacientes/{fam['id']}/descendentes/{fid}/vcf").status_code == 404
    # opções da interface
    op = medico.get("/api/pacientes/opcoes").json()
    assert [s["valor"] for s in op["situacoes_genitor"]] == [
        "VIVO_ASSINTOMATICO",
        "FALECIDO_SEM_ELA",
        "AFETADO",
        "DESCONHECIDA",
    ]
    assert len(op["parentescos"]) == 3 and op["inferencia_por_parentes"] and op["aviso_parceiro_inferido"]


def test_casal_com_parceiro_inferido_avisa_o_profissional(plataforma, medico):
    corpo = {
        "tipo": "CASAL",
        "prontuario": "PAR-2",
        "mae": genitor("Parceira Testada", "1992-01-01", str(cenarios.LAUDO_NORMAL)),
        "pai": genitor("Parceiro Sem Teste", "1990-01-01"),
        "descendentes": [],
    }
    r = medico.post("/api/pacientes", json=corpo)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert anexar_cenario(medico, pid, "MAE", 1).status_code == 201
    r = anexar_parente(medico, pid, "PAI", "PAI_DO_GENITOR", "cenario_1_pai.vcf", laudo=str(cenarios.LAUDO_NORMAL))
    assert r.status_code == 201 and r.json()["genitores"]["PAI"]["parentes"][0]["rotulo"] == "Pai do parceiro"
    assert (
        medico.put(f"/api/pacientes/{pid}/genitores/PAI/situacao", json={"situacao": "DESCONHECIDA"}).status_code == 200
    )
    r = medico.post(
        "/api/analises", data={"n": "400", "motor": "numpy", "cox": "0", "paciente_id": str(pid), "sexo_filho": "F"}
    )
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["aviso_parceiro_inferido"] == textos.AVISO_PARCEIRO_INFERIDO  # revela a chance de o parceiro portar
    assert res["principais"]["condicionado"] is False and res["principais"]["transmissao"] == pytest.approx(0.25)
    assert res["parentes"]["loci_inferidos"][0]["genitor_inferido"] == "pai"
    # excluir o registro apaga também o VCF do parente
    antes = len(list(plataforma["cfg"].dir_vcfs.glob("*.bin")))
    nome = medico.get(f"/api/pacientes/{pid}").json()["nome"]
    assert medico.request("DELETE", f"/api/pacientes/{pid}", json={"confirmacao_nome": nome}).status_code == 200
    assert len(list(plataforma["cfg"].dir_vcfs.glob("*.bin"))) == antes - 2


def test_tornado_e_opcao_da_analise_desligada_por_padrao(plataforma, medico):
    dados = {"modo": "cenario", "cenario": "5", "n": "400", "motor": "numpy", "cox": "0", "sexo": "F"}
    dados |= {"idade_atual": "40", "confirma_assintomatico": "1"}
    r = medico.post("/api/analises", data=dados)
    assert r.status_code == 201, r.text
    sem = r.json()
    assert sem["tornado"] is None and sem["entrada"]["tornado"] is False and sem["metadados"]["tornado"] is False
    assert "tabela_20_tornado" not in {t["nome"] for t in sem["tabelas"]}
    r = medico.post("/api/analises", data=dados | {"tornado": "1"})
    assert r.status_code == 201, r.text
    com = r.json()
    assert com["entrada"]["tornado"] is True and com["metadados"]["tornado"] is True
    assert "tabela_20_tornado" in {t["nome"] for t in com["tabelas"]}
    assert "figura_12_tornado.png" in {f["nome"] for f in com["figuras"]}
    assert any(s["titulo"] == "Sensibilidade tipo tornado" for s in com["secoes"])
    linhas = com["tornado"]["linhas"]
    assert linhas[0]["parametro"] == "penetrância do TARDBP" and all(l["fonte"] for l in linhas)
    # FUS não tem incerteza publicada para a idade de início: fica fora e isso é dito
    assert len(com["tornado"]["fora"]) == 1 and "FUS" in com["tornado"]["fora"][0]
    assert not any("idade de início do FUS" in l["parametro"] for l in linhas)
    # a opção não altera os indicadores
    assert com["principais"]["vida"] == sem["principais"]["vida"] and com["principais"]["condicionado"] is True
    assert com["principais"]["transmissao"] == sem["principais"]["transmissao"]
    # no formulário a opção existe e só vem marcada se o profissional marcar
    js = (DIR_STATIC / "app.js").read_text(encoding="utf-8")
    assert "nome: 'tornado'" in js and "marcado: valores.tornado === true" in js
