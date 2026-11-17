"""Primeiro acesso pela interface: o administrador e os dados de demonstração são criados na tela, só enquanto o
sistema está por configurar. Administrador criado por outro administrador recebe senha temporária, gerada pelo sistema e
trocada obrigatoriamente no primeiro login."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from ela_preditivo.web import auditoria, demo, permissoes, textos
from ela_preditivo.web.api import criar_app
from ela_preditivo.web.bd import criar_engine, criar_tabelas, fabrica_sessoes
from ela_preditivo.web.config import Configuracao, gerar_chave
from ela_preditivo.web.modelos import Usuario

CPF = demo._cpf_valido
SENHA = "senha-do-admin-123"


def servico(tmp_path, ambiente: str = "producao"):
    cfg = Configuracao(
        chave=gerar_chave().encode(),
        bd=tmp_path / "ela_web.sqlite3",
        dir_vcfs=tmp_path / "vcfs",
        dir_bases=tmp_path / "bases",
        ambiente=ambiente,
    )
    return criar_app(cfg), cfg


def conta(email: str = "adm@exemplo.br", cpf: str | None = None, **extra) -> dict:
    d = {
        "nome": "Administradora de Teste",
        "cpf": cpf or CPF(8001),
        "email": email,
        "senha": SENHA,
        "aceite_privacidade": True,
        "aceite_termo_uso": True,
        "versao_privacidade": textos.VERSAO_AVISO_PRIVACIDADE,
        "versao_termo_uso": textos.VERSAO_TERMO_USO,
    }
    d.update(extra)
    return d


def entrar(app, email: str, senha: str = SENHA) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/contas/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c


def acoes(app) -> list[dict]:
    with app.state.sessoes() as bd:
        return [
            auditoria.serializar(r)
            for r in bd.execute(select(auditoria.Auditoria).order_by(auditoria.Auditoria.sequencia)).scalars()
        ]


def test_primeiro_acesso_cria_o_administrador_uma_unica_vez(tmp_path):
    app, _ = servico(tmp_path)
    anon = TestClient(app)
    # recém-instalada, em produção: falta o administrador e não há demonstração a oferecer
    assert anon.get("/api/sistema").json()["primeiro_acesso"] == {"administrador": True, "demonstracao": False}
    assert anon.post("/api/primeiro-acesso/demonstracao", json={}).status_code == 409
    # as mesmas exigências do cadastro: aceites na versão atual, CPF válido, senha forte, corpo em JSON
    r = anon.post("/api/primeiro-acesso/administrador", json=conta(aceite_privacidade=False, versao_termo_uso="0"))
    assert r.status_code == 422 and set(r.json()["campos"]) == {"aceite_privacidade", "aceite_termo_uso"}
    r = anon.post("/api/primeiro-acesso/administrador", json=conta(cpf="111.111.111-11", senha="curta", nome="x"))
    assert r.status_code == 422 and set(r.json()["campos"]) == {"cpf", "senha", "nome"}
    assert anon.post("/api/primeiro-acesso/administrador", data=conta()).status_code == 415
    assert anon.get("/api/sistema").json()["primeiro_acesso"]["administrador"] is True
    r = anon.post("/api/primeiro-acesso/administrador", json=conta(papel="MEDICO", situacao="PENDENTE"))
    assert r.status_code == 201 and "Entre" in r.json()["mensagem"]
    # a porta fecha: a segunda tentativa é recusada, mesmo com outros dados
    assert anon.get("/api/sistema").json()["primeiro_acesso"] == {"administrador": False, "demonstracao": False}
    r = anon.post("/api/primeiro-acesso/administrador", json=conta("outro@exemplo.br", CPF(8002)))
    assert r.status_code == 409 and "já existe administrador" in r.json()["mensagem"]
    adm = entrar(app, "adm@exemplo.br")
    eu = adm.get("/api/contas/quem-sou-eu").json()
    assert eu["usuario"]["papel"] == "ADMIN" and eu["verificado"] is True and eu["trocar_senha"] is False
    assert set(eu["permissoes"]) == permissoes.MATRIZ["ADMIN"]
    assert [u["email"] for u in adm.get("/api/admin/usuarios").json()["usuarios"]] == ["adm@exemplo.br"]
    criado = [a for a in acoes(app) if a["acao"] == "admin_criado"]
    assert len(criado) == 1 and criado[0]["detalhe"] == "primeiro acesso pela interface"
    # ninguém se cadastra como administrador: o cadastro comum continua só para médico e pesquisador
    r = anon.post("/api/contas/cadastro", json={**conta("quer@exemplo.br", CPF(8003)), "papel_pretendido": "ADMIN"})
    assert r.status_code == 422 and "papel_pretendido" in r.json()["campos"]
    assert SENHA.encode() not in (tmp_path / "ela_web.sqlite3").read_bytes()


def test_administrador_cria_outro_com_senha_temporaria_e_troca_obrigatoria(tmp_path):
    app, _ = servico(tmp_path)
    anon = TestClient(app)
    assert anon.post("/api/primeiro-acesso/administrador", json=conta()).status_code == 201
    adm = entrar(app, "adm@exemplo.br")
    novo = {"nome": "Segundo Administrador", "cpf": CPF(8010), "email": "segundo@exemplo.br", "senha_atual": SENHA}
    # quem cria confirma a própria senha; dados inválidos e duplicados são recusados
    r = adm.post("/api/admin/administradores", json={**novo, "senha_atual": "senha-errada-000"})
    assert r.status_code == 422 and r.json()["campos"] == {"senha_atual": "Senha atual incorreta."}
    assert adm.post("/api/admin/administradores", json={**novo, "cpf": "123"}).json()["campos"]["cpf"]
    r = adm.post("/api/admin/administradores", json={**novo, "email": "adm@exemplo.br"})
    assert r.status_code == 409 and "email" in r.json()["campos"]
    # a senha é do sistema: a que quem cria tentar impor é ignorada
    r = adm.post("/api/admin/administradores", json={**novo, "senha": "escolhida-por-outro-1", "papel": "MEDICO"})
    assert r.status_code == 201, r.text
    d = r.json()
    temporaria = d["senha_temporaria"]
    assert len(temporaria) >= 16 and d["usuario"]["papel"] == "ADMIN" and d["usuario"]["situacao"] == "VERIFICADO"
    assert "primeiro login" in d["aviso"] and temporaria.encode() not in (tmp_path / "ela_web.sqlite3").read_bytes()
    r = anon.post("/api/contas/login", json={"email": "segundo@exemplo.br", "senha": "escolhida-por-outro-1"})
    assert r.status_code == 401
    # com a senha temporária, a conta só serve para trocar a senha
    seg = entrar(app, "segundo@exemplo.br", temporaria)
    assert seg.get("/api/contas/quem-sou-eu").json()["trocar_senha"] is True
    for metodo, rota in (
        ("GET", "/api/admin/usuarios"),
        ("GET", "/api/admin/auditoria"),
        ("GET", "/api/base"),
        ("GET", "/api/contas/minha"),
        ("POST", "/api/admin/administradores"),
    ):
        r = seg.request(metodo, rota, json={} if metodo == "POST" else None)
        assert r.status_code == 403 and r.json()["mensagem"] == permissoes.MENSAGEM_TROCAR_SENHA, rota
    troca = {"senha_atual": temporaria, "senha_nova": temporaria}
    assert seg.post("/api/contas/minha/senha", json=troca).json()["campos"]["senha_nova"].startswith("A nova senha")
    assert seg.post("/api/contas/minha/senha", json={**troca, "senha_nova": "curta"}).status_code == 422
    assert seg.get("/api/contas/quem-sou-eu").json()["trocar_senha"] is True
    assert seg.post("/api/contas/minha/senha", json={**troca, "senha_nova": "minha-senha-nova-9"}).status_code == 200
    assert seg.get("/api/contas/quem-sou-eu").json()["trocar_senha"] is False
    assert len(seg.get("/api/admin/usuarios").json()["usuarios"]) == 2
    # a temporária deixa de valer; a nova entra direto, sem troca pendente
    r = anon.post("/api/contas/login", json={"email": "segundo@exemplo.br", "senha": temporaria})
    assert r.status_code == 401
    assert entrar(app, "segundo@exemplo.br", "minha-senha-nova-9").get("/api/admin/usuarios").status_code == 200
    # a auditoria diz quem criou quem e registra as tentativas barradas pela senha temporária
    registros = acoes(app)
    criado = [a for a in registros if a["acao"] == "admin_criado"][-1]
    ids = {u["email"]: u["id"] for u in adm.get("/api/admin/usuarios").json()["usuarios"]}
    assert criado["usuario_id"] == ids["adm@exemplo.br"] and criado["alvo_id"] == str(ids["segundo@exemplo.br"])
    assert "senha temporária" in criado["detalhe"] and temporaria not in str(registros)
    assert any(a["acao"] == "acesso_negado" and "senha_temporaria" in (a["detalhe"] or "") for a in registros)
    # só administrador cria administrador: o médico verificado recebe 403
    assert (
        anon.post(
            "/api/contas/cadastro",
            json={
                **conta("medica@exemplo.br", CPF(8020)),
                "papel_pretendido": "MEDICO",
                "medico": {"tipo": "CRM", "crm": "54321", "uf": "RJ"},
            },
        ).status_code
        == 201
    )
    assert adm.post(f"/api/admin/usuarios/{max(ids.values()) + 1}/aprovar").status_code == 200
    medica = entrar(app, "medica@exemplo.br")
    r = medica.post("/api/admin/administradores", json={**novo, "cpf": CPF(8011), "email": "terceiro@exemplo.br"})
    assert r.status_code == 403 and r.json()["mensagem"] == permissoes.MENSAGEM_403


def test_demonstracao_pela_interface_mostra_as_senhas_uma_vez(tmp_path, monkeypatch):
    original = demo.popular
    monkeypatch.setattr(demo, "popular", lambda bd, cifra, config: original(bd, cifra, config, analisar=False))
    app, _ = servico(tmp_path, "homologacao")
    anon = TestClient(app)
    assert anon.get("/api/sistema").json()["primeiro_acesso"] == {"administrador": True, "demonstracao": True}
    r = anon.post("/api/primeiro-acesso/demonstracao", json={})
    assert r.status_code == 201, r.text
    d = r.json()
    assert (len(d["credenciais"]), d["registros"], d["vcfs"]) == (5, 8, 16) and "não serão mostradas de novo" in d[
        "aviso"
    ]
    assert {c["papel"] for c in d["credenciais"]} == {"ADMIN", "MEDICO", "PESQUISADOR"}
    # feito uma vez: a tela de primeiro acesso deixa de existir e nada mais devolve as senhas
    assert anon.get("/api/sistema").json()["primeiro_acesso"] == {"administrador": False, "demonstracao": False}
    assert anon.post("/api/primeiro-acesso/demonstracao", json={}).status_code == 409
    assert anon.post("/api/primeiro-acesso/administrador", json=conta()).status_code == 409
    banco = (tmp_path / "ela_web.sqlite3").read_bytes()
    senhas = {c["email"]: c["senha"] for c in d["credenciais"]}
    assert all(s.encode() not in banco for s in senhas.values())
    medico = entrar(app, "medico@demo.local", senhas["medico@demo.local"])
    assert medico.get("/api/contas/quem-sou-eu").json()["trocar_senha"] is False
    assert len(medico.get("/api/pacientes").json()["pacientes"]) == 8
    adm = entrar(app, "admin@demo.local", senhas["admin@demo.local"])
    assert adm.get("/api/admin/demonstracao").json() == {"pode_popular": False}
    assert adm.post("/api/admin/demonstracao").status_code == 409


def test_administrador_cria_a_demonstracao_depois_do_primeiro_acesso(tmp_path, monkeypatch):
    original = demo.popular
    monkeypatch.setattr(demo, "popular", lambda bd, cifra, config: original(bd, cifra, config, analisar=False))
    app, _ = servico(tmp_path, "homologacao")
    anon = TestClient(app)
    assert anon.post("/api/primeiro-acesso/administrador", json=conta()).status_code == 201
    # com administrador criado, a demonstração sem sessão fecha: senão qualquer um receberia a senha de um administrador
    assert anon.get("/api/sistema").json()["primeiro_acesso"] == {"administrador": False, "demonstracao": False}
    assert anon.post("/api/primeiro-acesso/demonstracao", json={}).status_code == 409
    assert anon.post("/api/admin/demonstracao").status_code == 401
    adm = entrar(app, "adm@exemplo.br")
    assert adm.get("/api/admin/demonstracao").json() == {"pode_popular": True}
    r = adm.post("/api/admin/demonstracao")
    assert r.status_code == 201 and len(r.json()["credenciais"]) == 5
    assert adm.get("/api/admin/demonstracao").json() == {"pode_popular": False}
    assert adm.post("/api/admin/demonstracao").status_code == 409
    assert (
        adm.get("/api/admin/usuarios").json()["total"] == 6
    )  # o administrador do primeiro acesso e os cinco da demonstração
    # em produção não há demonstração, nem para o administrador
    app2, _ = servico(tmp_path / "producao")
    assert TestClient(app2).post("/api/primeiro-acesso/administrador", json=conta()).status_code == 201
    adm2 = entrar(app2, "adm@exemplo.br")
    assert adm2.get("/api/admin/demonstracao").json() == {"pode_popular": False}
    assert adm2.post("/api/admin/demonstracao").status_code == 409


def test_banco_criado_antes_ganha_a_coluna_da_senha_temporaria(tmp_path):
    if sqlite3.sqlite_version_info < (3, 35):
        pytest.skip("este SQLite não remove coluna, e o teste precisa disso para imitar o banco antigo")
    engine = criar_engine(tmp_path / "antigo.sqlite3")
    criar_tabelas(engine)
    with engine.begin() as con:
        con.exec_driver_sql("ALTER TABLE usuarios DROP COLUMN trocar_senha")
        assert "trocar_senha" not in {linha[1] for linha in con.exec_driver_sql("PRAGMA table_info(usuarios)")}
    criar_tabelas(engine)  # é o que a subida do serviço faz
    with engine.begin() as con:
        assert "trocar_senha" in {linha[1] for linha in con.exec_driver_sql("PRAGMA table_info(usuarios)")}
    with fabrica_sessoes(engine)() as bd:
        assert list(bd.execute(select(Usuario)).scalars()) == []
