"""Arranque do serviço (ponto de entrada da imagem Docker): cria a chave de cifra e, se o ambiente trouxer, o
administrador; o resto (primeiro acesso e demonstração) acontece no navegador."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from ela_preditivo.web import arranque
from ela_preditivo.web.api import criar_app
from ela_preditivo.web.bd import criar_engine, fabrica_sessoes
from ela_preditivo.web.config import Configuracao
from ela_preditivo.web.demo import _cpf_valido
from ela_preditivo.web.modelos import Usuario

RAIZ = Path(__file__).resolve().parents[2]


def test_chave_do_ambiente_do_arquivo_ou_nova(tmp_path):
    avisos: list[str] = []
    amb: dict = {}
    chave = arranque.garantir_chave(tmp_path, amb, avisos.append)
    arquivo = tmp_path / "chave.env"
    Fernet(chave.encode())  # é uma chave Fernet válida
    assert amb["ELA_WEB_CHAVE"] == chave and arquivo.read_text(encoding="utf-8") == f"ELA_WEB_CHAVE={chave}\n"
    assert len(avisos) == 1 and "faça cópia" in avisos[0] and chave not in avisos[0]
    if os.name == "posix":
        assert stat.S_IMODE(arquivo.stat().st_mode) == 0o600
    # nas subidas seguintes a chave guardada volta, sem criar outra (o banco continua legível)
    amb2: dict = {}
    assert arranque.garantir_chave(tmp_path, amb2, avisos.append) == chave and len(avisos) == 1
    # a chave do ambiente manda, e nada é gravado
    outra = Fernet.generate_key().decode()
    assert arranque.garantir_chave(tmp_path / "nova", {"ELA_WEB_CHAVE": outra}, avisos.append) == outra
    assert not (tmp_path / "nova").exists()
    (tmp_path / "exportada.env").write_text(f"# comentário\nexport ELA_WEB_CHAVE='{outra}'\n", encoding="utf-8")
    assert arranque.ler_chave(tmp_path / "exportada.env") == outra and arranque.ler_chave(tmp_path / "x") is None


def test_subida_avisa_do_primeiro_acesso_e_cria_o_administrador_do_ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("ELA_WEB_CHAVE", Fernet.generate_key().decode())
    monkeypatch.setenv("ELA_WEB_BD", str(tmp_path / "ela_web.sqlite3"))
    monkeypatch.setenv("ELA_WEB_VCFS", str(tmp_path / "vcfs"))
    monkeypatch.setenv("ELA_WEB_AMBIENTE", "producao")
    for nome in ("ELA_ADMIN_NOME", "ELA_ADMIN_CPF", "ELA_ADMIN_EMAIL", "ELA_ADMIN_SENHA"):
        monkeypatch.delenv(nome, raising=False)
    avisos: list[str] = []
    # sem administrador no ambiente, a subida não cria nada: o primeiro acesso é feito no navegador
    assert arranque.preparar_banco(dict(os.environ), avisos.append) == []
    assert any("faça o primeiro acesso" in a for a in avisos) and not any("demonstração" in a for a in avisos)
    # com o administrador no ambiente: criado uma vez, verificado, e não de novo na subida seguinte
    amb = {
        **os.environ,
        "ELA_ADMIN_EMAIL": "admin@exemplo.br",
        "ELA_ADMIN_CPF": _cpf_valido(7001),
        "ELA_ADMIN_SENHA": "senha-de-teste-123",
    }
    assert arranque.preparar_banco(amb, avisos.append) == ["criar-admin"]
    assert arranque.preparar_banco(amb, avisos.append) == []
    with fabrica_sessoes(criar_engine(tmp_path / "ela_web.sqlite3"))() as bd:
        usuarios = list(bd.execute(select(Usuario)).scalars())
    assert [(u.email, u.papel, u.situacao, u.nome) for u in usuarios] == [
        ("admin@exemplo.br", "ADMIN", "VERIFICADO", "Administrador")
    ]
    # a senha do ambiente fica num arquivo de configuração: é temporária, e o primeiro acesso pela tela fecha
    app = criar_app(Configuracao.do_ambiente())
    c = TestClient(app)
    assert c.get("/api/sistema").json()["primeiro_acesso"] == {"administrador": False, "demonstracao": False}
    r = c.post("/api/contas/login", json={"email": "admin@exemplo.br", "senha": "senha-de-teste-123"})
    assert r.status_code == 200 and r.json()["trocar_senha"] is True
    # faltando CPF ou senha, ou com CPF inválido, não cria e diz por quê
    assert arranque.preparar_banco({**os.environ, "ELA_ADMIN_EMAIL": "outro@exemplo.br"}, avisos.append) == []
    assert any("sem ELA_ADMIN_CPF ou ELA_ADMIN_SENHA" in a for a in avisos)
    ruim = {**amb, "ELA_ADMIN_EMAIL": "ruim@exemplo.br", "ELA_ADMIN_CPF": "111.111.111-11"}
    assert arranque.preparar_banco(ruim, avisos.append) == [] and any("não criado: CPF inválido" in a for a in avisos)
    # homologação com banco sem usuários: a demonstração não é criada na subida, e sim na tela de primeiro acesso
    monkeypatch.setenv("ELA_WEB_BD", str(tmp_path / "homologacao.sqlite3"))
    monkeypatch.setenv("ELA_WEB_AMBIENTE", "homologacao")
    avisos.clear()
    assert arranque.preparar_banco(dict(os.environ), avisos.append) == []
    assert any("a mesma tela cria os dados de demonstração" in a for a in avisos)
    with fabrica_sessoes(criar_engine(tmp_path / "homologacao.sqlite3"))() as bd:
        assert list(bd.execute(select(Usuario)).scalars()) == []


def test_arranque_roda_outro_comando_ou_sobe_o_servidor(tmp_path, monkeypatch):
    from ela_preditivo import cli

    monkeypatch.delenv("ELA_WEB_CHAVE", raising=False)
    monkeypatch.setenv("ELA_WEB_BD", str(tmp_path / "dados" / "ela_web.sqlite3"))
    monkeypatch.setenv("ELA_WEB_VCFS", str(tmp_path / "dados" / "vcfs"))
    monkeypatch.setenv("ELA_WEB_AMBIENTE", "producao")
    monkeypatch.setenv("ELA_WEB_HOST", "0.0.0.0")
    monkeypatch.setenv("ELA_WEB_PORTA", "8123")
    for nome in ("ELA_ADMIN_NOME", "ELA_ADMIN_CPF", "ELA_ADMIN_EMAIL", "ELA_ADMIN_SENHA"):
        monkeypatch.delenv(nome, raising=False)
    chamados: list[list[str]] = []
    monkeypatch.setattr(cli, "main", lambda a=None: chamados.append(list(a)) or 0)
    assert arranque.main(["verificar-auditoria"]) == 0 and chamados == [["verificar-auditoria"]]
    assert (tmp_path / "dados" / "chave.env").is_file() and os.environ["ELA_WEB_CHAVE"]
    chamados.clear()
    assert arranque.main([]) == 0
    assert chamados == [["servir", "--host", "0.0.0.0", "--porta", "8123"]]


def test_arquivos_do_docker_apontam_para_o_arranque_e_para_as_pastas_de_dados():
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["python", "-m", "ela_preditivo.web.arranque"]' in dockerfile
    for linha in (
        "ELA_DADOS_BRUTOS=/app/dados_reais",
        "ELA_WEB_BD=/app/dados_web/ela_web.sqlite3",
        "PYTENSOR_FLAGS=cxx=",
    ):
        assert linha in dockerfile, linha
    assert "elosense_dados:/app/dados_web" in compose and "./dados_reais:/app/dados_reais" in compose
    assert "${ELA_ENDERECO:-127.0.0.1}:${ELA_PORTA:-8000}:8000" in compose  # só a própria máquina, por padrão
    # nenhuma chave, senha ou e-mail fixo nos arquivos versionados
    exemplo = (RAIZ / ".env.exemplo").read_text(encoding="utf-8")
    for linha in exemplo.splitlines():
        if linha.startswith(("ELA_WEB_CHAVE", "ELA_ADMIN_")):
            assert linha.endswith("="), linha
    ignorados = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    # banco e opções locais nunca são versionados; em dados_reais/ só a base consolidada do ClinVar (pública) é
    # versionada: o que a tela Base de anotação e o `atualizar-base` gravam ali (envios, downloads, versoes/) fica fora
    assert ".env" in ignorados and "dados_web/" in ignorados
    assert "dados_reais/*" in ignorados and "!dados_reais/base_consolidada_ela.csv" in ignorados
    assert "dados_reais/" not in ignorados and "dados_reais" not in ignorados  # a pasta inteira não é ignorada
