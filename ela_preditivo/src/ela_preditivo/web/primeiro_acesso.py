"""Primeiro acesso pela interface: criar o administrador e, em homologação, os dados de demonstração.

Além do cadastro e do login, são as únicas ações de quem ainda não tem sessão, e só enquanto o sistema está por
configurar: o administrador é criado aqui só enquanto não existe nenhum, e a demonstração só enquanto o banco não tem
usuário algum. Depois disso as duas rotas respondem 409. Daí em diante, administrador novo só nasce pelas mãos de outro
administrador, autenticado e com a senha conferida (`POST /api/admin/administradores`), e a demonstração só por um
administrador (`POST /api/admin/demonstracao`). Ninguém se cadastra nem é promovido a administrador.

Senhas: no primeiro acesso a pessoa define a própria senha, porque uma senha gerada apareceria na mesma tela, para
quem chegou primeiro, sem proteger nada. Quando é outro administrador (ou o ambiente, na subida) quem cria a conta,
a senha é temporária: gerada pelo sistema, mostrada uma única vez e trocada obrigatoriamente no primeiro login.

Quem chega primeiro ao endereço cria o administrador. Por isso o serviço atende só a própria máquina por padrão; num
servidor exposto, faça o primeiro acesso logo após a subida ou crie o administrador pelas variáveis `ELA_ADMIN_*`.
"""

from __future__ import annotations

import secrets
import threading

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from . import auditoria, demo, textos
from .comum import RE_EMAIL, exigir_campos, obter_bd, obter_cifra, obter_config
from .modelos import Usuario
from .seguranca import normalizar_cpf, normalizar_email, validar_cpf, validar_senha

router = APIRouter(prefix="/api/primeiro-acesso", tags=["primeiro-acesso"])
EMAIL_ADMIN_DEMO = "admin@demo.local"
AVISO_SENHAS = "Guarde as senhas agora: elas não ficam em claro no banco e não serão mostradas de novo."
_trava = threading.Lock()  # dois primeiros acessos ao mesmo tempo não criam dois administradores


class NovoAdministrador(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    nome: str = Field(max_length=200)
    cpf: str = Field(max_length=20)
    email: str = Field(max_length=254)
    senha: str = Field(max_length=200)
    aceite_privacidade: bool = False
    aceite_termo_uso: bool = False
    versao_privacidade: str | None = None
    versao_termo_uso: str | None = None


def _contar(bd, *filtros) -> int:
    return int(bd.scalar(select(func.count()).select_from(Usuario).where(*filtros)) or 0)


def situacao(bd, config) -> dict:
    """O que ainda pode ser feito sem sessão: criar o administrador e, em homologação, a demonstração."""
    return {
        "administrador": _contar(bd, Usuario.papel == "ADMIN") == 0,
        "demonstracao": bool(config.demonstracao) and _contar(bd) == 0,
    }


def pode_popular_demonstracao(bd, config) -> bool:
    """Para o administrador: homologação, sem médico nem pesquisador e sem demonstração já criada."""
    return (
        bool(config.demonstracao)
        and _contar(bd, Usuario.papel != "ADMIN") == 0
        and _contar(bd, Usuario.email == EMAIL_ADMIN_DEMO) == 0
    )


def senha_temporaria() -> str:
    """Senha inicial de uma conta criada por terceiro: aleatória, mostrada uma vez e trocada no primeiro login."""
    return secrets.token_urlsafe(12)


def criar_administrador(
    bd,
    cifra,
    entrada,
    detalhe: str,
    autor: Usuario | None = None,
    senha: str | None = None,
    trocar_senha: bool = False,
) -> Usuario:
    """Valida os dados como no cadastro e cria um administrador já verificado; a auditoria registra quem o criou.
    Sem `senha`, vale a da entrada, escolhida pelo próprio titular, que também declara os aceites. Com `senha`
    (temporária), os aceites são registrados como na criação pela linha de comando."""
    campos: dict[str, str] = {}
    do_titular = senha is None
    senha = entrada.senha if do_titular else senha
    nome = " ".join(entrada.nome.split())
    if len(nome) < 3:
        campos["nome"] = "Informe o nome completo."
    cpf = normalizar_cpf(entrada.cpf)
    if not validar_cpf(cpf):
        campos["cpf"] = "CPF inválido: confira os dígitos."
    email = normalizar_email(entrada.email)
    if not RE_EMAIL.match(email):
        campos["email"] = "Informe um e-mail válido."
    erro_senha = validar_senha(senha, email, cpf)
    if erro_senha:
        campos["senha"] = erro_senha
    if do_titular:
        if not entrada.aceite_privacidade or entrada.versao_privacidade != textos.VERSAO_AVISO_PRIVACIDADE:
            campos["aceite_privacidade"] = "É preciso ler e aceitar o aviso de privacidade (versão atual)."
        if not entrada.aceite_termo_uso or entrada.versao_termo_uso != textos.VERSAO_TERMO_USO:
            campos["aceite_termo_uso"] = "É preciso ler e aceitar o termo de uso (versão atual)."
    exigir_campos(campos)
    duplicados: dict[str, str] = {}
    if bd.execute(select(Usuario.id).where(Usuario.cpf_hmac == cifra.hmac_cpf(cpf))).first():
        duplicados["cpf"] = "Já existe um cadastro com este CPF."
    if bd.execute(select(Usuario.id).where(Usuario.email == email)).first():
        duplicados["email"] = "Já existe um cadastro com este e-mail."
    exigir_campos(duplicados, status=409, mensagem="Já existe um cadastro com estes dados.")
    u = demo.criar_usuario(
        bd,
        cifra,
        nome=nome,
        cpf=cpf,
        email=email,
        senha=senha,
        papel="ADMIN",
        situacao="VERIFICADO",
        trocar_senha=trocar_senha,
    )
    auditoria.registrar(
        bd, acao=auditoria.ADMIN_CRIADO, usuario=autor or u, alvo_tipo="usuario", alvo_id=u.id, detalhe=detalhe
    )
    bd.commit()
    return u


def popular_demonstracao(request: Request) -> dict:
    """Roda `demo.popular` (o `popular-demo` da linha de comando) e devolve as credenciais para mostrar uma única vez."""
    bd, cifra, config = obter_bd(request), obter_cifra(request), obter_config(request)
    try:
        with request.app.state.analises.execucao:  # as análises de exemplo não rodam junto com uma análise clínica
            r = demo.popular(bd, cifra, config)
    except (RuntimeError, ValueError) as e:
        bd.rollback()
        raise HTTPException(409, f"Não foi possível criar a demonstração: {e}.") from e
    return {
        "credenciais": r["credenciais"],
        "registros": r["pacientes"],
        "vcfs": r["vcfs"],
        "analises": r["analises"],
        "aviso": AVISO_SENHAS,
    }


@router.post("/administrador", status_code=201)
def primeiro_administrador(entrada: NovoAdministrador, request: Request):
    bd, cifra, config = obter_bd(request), obter_cifra(request), obter_config(request)
    with _trava:
        if not situacao(bd, config)["administrador"]:
            raise HTTPException(409, "O primeiro acesso já foi feito: já existe administrador. Entre com a sua conta.")
        criar_administrador(bd, cifra, entrada, "primeiro acesso pela interface")
    return {"mensagem": "Administrador criado. Entre com o e-mail e a senha informados."}


@router.post("/demonstracao", status_code=201)
def primeira_demonstracao(request: Request):
    bd, config = obter_bd(request), obter_config(request)
    with _trava:
        if not situacao(bd, config)["demonstracao"]:
            raise HTTPException(
                409, "A demonstração sem sessão só existe em homologação e enquanto o banco não tem nenhum usuário."
            )
        return popular_demonstracao(request)
