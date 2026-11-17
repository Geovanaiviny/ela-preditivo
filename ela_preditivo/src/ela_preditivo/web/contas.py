"""Contas: autocadastro com aprovação, login/logout, "quem sou eu", situação do cadastro e "Minha conta"."""

from __future__ import annotations

import datetime as _dt
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from . import auditoria, textos
from .bd import agora
from .comum import RE_EMAIL, UFS, exigir_campos, iso, obter_bd, obter_cifra, obter_config, origem, texto_curto
from .modelos import (
    PAPEIS_AUTOCADASTRO,
    ROTULO_PAPEL,
    ROTULO_SITUACAO,
    AceiteTermo,
    PerfilMedico,
    PerfilPesquisador,
    Sessao,
    Usuario,
)
from .permissoes import CONTA_GERIR, AUDITORIA_VER_PROPRIA, exigir, permissoes_do_papel
from .seguranca import (
    formatar_cpf,
    gerar_token,
    hash_senha,
    hash_token,
    mascarar_cpf,
    normalizar_cpf,
    normalizar_email,
    validar_cpf,
    validar_senha,
    verificar_senha,
)

router = APIRouter(prefix="/api/contas", tags=["contas"])
COOKIE_SESSAO = "ela_sessao"
RE_ORCID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
RE_CRM = re.compile(r"^\d{4,10}$")
_HASH_FALSO = hash_senha("tempo-constante-para-login-sem-usuario")  # igual custo quando o e-mail não existe


# ---------------------------------------------------------------------------
# Modelos de entrada (campos extras são ignorados: ninguém envia papel, situação ou id por aqui)
# ---------------------------------------------------------------------------
class PerfilMedicoEntrada(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    tipo: Literal["CRM", "ACONSELHADOR"] = "CRM"
    crm: str | None = Field(default=None, max_length=20)
    uf: str | None = Field(default=None, max_length=2)
    especialidade: str | None = Field(default=None, max_length=120)
    formacao: str | None = Field(default=None, max_length=200)
    instituicao: str | None = Field(default=None, max_length=200)


class PerfilPesquisadorEntrada(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    tipo: Literal["INSTITUCIONAL", "INDEPENDENTE"] = "INSTITUCIONAL"
    orcid: str | None = Field(default=None, max_length=19)
    lattes_url: str | None = Field(default=None, max_length=300)
    instituicao: str | None = Field(default=None, max_length=200)
    grupo: str | None = Field(default=None, max_length=200)
    cargo: str | None = Field(default=None, max_length=200)
    linha_pesquisa: str | None = Field(default=None, max_length=300)
    projetos: str | None = Field(default=None, max_length=2000)
    evidencias: str | None = Field(default=None, max_length=4000)


class CadastroEntrada(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    nome: str = Field(max_length=200)
    cpf: str = Field(max_length=20)
    email: str = Field(max_length=254)
    senha: str = Field(max_length=200)
    papel_pretendido: Literal["MEDICO", "PESQUISADOR"]
    aceite_privacidade: bool = False
    aceite_termo_uso: bool = False
    versao_privacidade: str | None = None
    versao_termo_uso: str | None = None
    medico: PerfilMedicoEntrada | None = None
    pesquisador: PerfilPesquisadorEntrada | None = None


class LoginEntrada(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    email: str = Field(max_length=254)
    senha: str = Field(max_length=200)


class RespostaSituacao(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    resposta: str = Field(min_length=1, max_length=4000)


IMUTAVEIS = ["nome", "cpf", "medico.tipo", "medico.crm", "medico.uf", "pesquisador.orcid"]


class MinhaContaEntrada(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    nome: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    medico: PerfilMedicoEntrada | None = None
    pesquisador: PerfilPesquisadorEntrada | None = None


class TrocaSenha(BaseModel):
    model_config = ConfigDict(extra="ignore")
    senha_atual: str = Field(max_length=200)
    senha_nova: str = Field(max_length=200)


# ---------------------------------------------------------------------------
# Validação dos perfis profissionais
# ---------------------------------------------------------------------------
def validar_perfil_medico(p: PerfilMedicoEntrada | None, campos: dict) -> None:
    if p is None:
        campos["medico"] = "Informe os dados profissionais."
        return
    if p.tipo == "CRM":
        if not p.crm or not RE_CRM.match(p.crm):
            campos["medico.crm"] = "Informe o número do CRM (só dígitos)."
        if not p.uf or p.uf.upper() not in UFS:
            campos["medico.uf"] = "Informe a UF do CRM."
    else:  # aconselhador genético sem CRM: formação e instituição no lugar do CRM
        if not p.formacao:
            campos["medico.formacao"] = "Informe a formação."
        if not p.instituicao:
            campos["medico.instituicao"] = "Informe a instituição."


def validar_perfil_pesquisador(p: PerfilPesquisadorEntrada | None, campos: dict) -> None:
    if p is None:
        campos["pesquisador"] = "Informe os dados de pesquisa."
        return
    if not p.cargo:
        campos["pesquisador.cargo"] = "Informe o cargo ou a condição acadêmica."
    if not p.linha_pesquisa:
        campos["pesquisador.linha_pesquisa"] = "Informe a linha de pesquisa."
    if p.orcid and not RE_ORCID.match(p.orcid):
        campos["pesquisador.orcid"] = "ORCID no formato 0000-0000-0000-0000."
    if p.lattes_url and not re.match(r"^https?://", p.lattes_url):
        campos["pesquisador.lattes_url"] = "Informe o link completo do Lattes (começando por http)."


def _aplicar_perfil_medico(usuario: Usuario, p: PerfilMedicoEntrada) -> None:
    perfil = usuario.perfil_medico or PerfilMedico(usuario=usuario, tipo=p.tipo)
    perfil.tipo = p.tipo
    perfil.crm = texto_curto(p.crm, 20) if p.tipo == "CRM" else None
    perfil.uf = p.uf.upper() if (p.tipo == "CRM" and p.uf) else None
    perfil.especialidade = texto_curto(p.especialidade, 120)
    perfil.formacao = texto_curto(p.formacao, 200) if p.tipo == "ACONSELHADOR" else None
    perfil.instituicao = texto_curto(p.instituicao, 200) if p.tipo == "ACONSELHADOR" else None
    usuario.perfil_medico = perfil


def _aplicar_perfil_pesquisador(usuario: Usuario, p: PerfilPesquisadorEntrada) -> None:
    perfil = usuario.perfil_pesquisador or PerfilPesquisador(usuario=usuario, tipo=p.tipo)
    perfil.tipo = p.tipo
    for campo, maximo in (
        ("orcid", 19),
        ("lattes_url", 300),
        ("instituicao", 200),
        ("grupo", 200),
        ("cargo", 200),
        ("linha_pesquisa", 300),
        ("projetos", 2000),
        ("evidencias", 4000),
    ):
        setattr(perfil, campo, texto_curto(getattr(p, campo), maximo))
    usuario.perfil_pesquisador = perfil


# ---------------------------------------------------------------------------
# Serialização
# ---------------------------------------------------------------------------
def perfil_dict(usuario: Usuario) -> dict | None:
    if usuario.perfil_medico is not None:
        m = usuario.perfil_medico
        return {
            "tipo": m.tipo,
            "crm": m.crm,
            "uf": m.uf,
            "especialidade": m.especialidade,
            "formacao": m.formacao,
            "instituicao": m.instituicao,
        }
    if usuario.perfil_pesquisador is not None:
        p = usuario.perfil_pesquisador
        return {
            "tipo": p.tipo,
            "orcid": p.orcid,
            "lattes_url": p.lattes_url,
            "instituicao": p.instituicao,
            "grupo": p.grupo,
            "cargo": p.cargo,
            "linha_pesquisa": p.linha_pesquisa,
            "projetos": p.projetos,
            "evidencias": p.evidencias,
        }
    return None


def usuario_dict(usuario: Usuario, cifra, completo: bool = False) -> dict:
    cpf = cifra.decifrar(usuario.cpf_cifrado)
    d = {
        "id": usuario.id,
        "nome": usuario.nome,
        "email": usuario.email,
        "cpf_mascarado": mascarar_cpf(cpf),
        "papel": usuario.papel,
        "papel_rotulo": ROTULO_PAPEL.get(usuario.papel, usuario.papel),
        "situacao": usuario.situacao,
        "situacao_rotulo": ROTULO_SITUACAO.get(usuario.situacao, usuario.situacao),
        "criado_em": iso(usuario.criado_em),
    }
    if completo:
        d.update(
            {
                "perfil": perfil_dict(usuario),
                "aceites": [
                    {"documento": a.documento, "versao": a.versao, "aceito_em": iso(a.aceito_em)}
                    for a in usuario.aceites
                ],
                "verificado_em": iso(usuario.verificado_em),
                "encerramento_solicitado_em": iso(usuario.encerramento_solicitado_em),
                "atualizado_em": iso(usuario.atualizado_em),
            }
        )
    return d


def quem_sou_eu_dict(usuario: Usuario, sessao: Sessao, request: Request) -> dict:
    config = obter_config(request)
    return {
        "usuario": usuario_dict(usuario, obter_cifra(request)),
        "permissoes": sorted(permissoes_do_papel(usuario.papel)),
        "verificado": usuario.verificado,
        "trocar_senha": bool(usuario.trocar_senha),  # senha temporária: a interface leva à troca
        "csrf": sessao.csrf_token,
        "demonstracao": config.demonstracao,
        "sessao_minutos": config.sessao_minutos,
    }


# ---------------------------------------------------------------------------
# Rotas públicas: cadastro e login
# ---------------------------------------------------------------------------
@router.post("/cadastro", status_code=201)
def cadastro(entrada: CadastroEntrada, request: Request):
    bd, cifra = obter_bd(request), obter_cifra(request)
    campos: dict[str, str] = {}
    nome = " ".join(entrada.nome.split())
    if len(nome) < 3:
        campos["nome"] = "Informe o nome completo."
    cpf = normalizar_cpf(entrada.cpf)
    if not validar_cpf(cpf):
        campos["cpf"] = "CPF inválido: confira os dígitos."
    email = normalizar_email(entrada.email)
    if not RE_EMAIL.match(email):
        campos["email"] = "Informe um e-mail válido."
    erro_senha = validar_senha(entrada.senha, email, cpf)
    if erro_senha:
        campos["senha"] = erro_senha
    if entrada.papel_pretendido not in PAPEIS_AUTOCADASTRO:
        campos["papel_pretendido"] = "Papel não permitido."
    if entrada.papel_pretendido == "MEDICO":
        validar_perfil_medico(entrada.medico, campos)
    else:
        validar_perfil_pesquisador(entrada.pesquisador, campos)
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
    hoje = agora()
    usuario = Usuario(
        nome=nome,
        email=email,
        cpf_cifrado=cifra.cifrar(cpf),
        cpf_hmac=cifra.hmac_cpf(cpf),
        senha_hash=hash_senha(entrada.senha),
        papel=entrada.papel_pretendido,
        situacao="PENDENTE",
        criado_em=hoje,
        atualizado_em=hoje,
    )
    if entrada.papel_pretendido == "MEDICO":
        _aplicar_perfil_medico(usuario, entrada.medico)
    else:
        _aplicar_perfil_pesquisador(usuario, entrada.pesquisador)
    usuario.aceites = [
        AceiteTermo(documento="AVISO_PRIVACIDADE", versao=textos.VERSAO_AVISO_PRIVACIDADE, aceito_em=hoje),
        AceiteTermo(documento="TERMO_USO", versao=textos.VERSAO_TERMO_USO, aceito_em=hoje),
    ]
    bd.add(usuario)
    bd.flush()
    auditoria.registrar(bd, acao=auditoria.CADASTRO, usuario=usuario, alvo_tipo="usuario", alvo_id=usuario.id)
    bd.commit()
    return {
        "mensagem": "Cadastro recebido. Sua conta ficará pendente até a verificação manual pelo administrador. "
        "Entre com seu e-mail e senha para acompanhar a situação.",
        "situacao": "PENDENTE",
    }


@router.post("/login")
def login(entrada: LoginEntrada, request: Request, response: Response):
    bd, config = obter_bd(request), obter_config(request)
    limite = request.app.state.limite
    email = normalizar_email(entrada.email)
    ip = origem(request)
    restante = limite.bloqueado(ip, email)
    if restante:
        auditoria.registrar(
            bd, acao=auditoria.LOGIN_FALHA, resultado="NEGADO", detalhe="bloqueio por tentativas (origem)"
        )
        bd.commit()
        raise HTTPException(429, f"Muitas tentativas. Tente novamente em {max(1, restante // 60)} minuto(s).")
    usuario = bd.execute(select(Usuario).where(Usuario.email == email)).scalar_one_or_none()
    hoje = agora()
    if usuario is not None and usuario.bloqueado_ate is not None and usuario.bloqueado_ate > hoje:
        auditoria.registrar(
            bd, acao=auditoria.LOGIN_FALHA, usuario=usuario, resultado="NEGADO", detalhe="conta bloqueada"
        )
        bd.commit()
        raise HTTPException(429, f"Muitas tentativas. Tente novamente em {config.bloqueio_minutos} minutos.")
    ok = verificar_senha(usuario.senha_hash if usuario else _HASH_FALSO, entrada.senha) and usuario is not None
    if not ok:
        limite.registrar_falha(ip, email)
        if usuario is not None:
            usuario.tentativas_falhas += 1
            if usuario.tentativas_falhas >= config.tentativas_login:
                usuario.bloqueado_ate = hoje + _dt.timedelta(minutes=config.bloqueio_minutos)
                usuario.tentativas_falhas = 0
        auditoria.registrar(
            bd, acao=auditoria.LOGIN_FALHA, usuario=usuario, resultado="FALHA", detalhe="credenciais inválidas"
        )
        bd.commit()
        raise HTTPException(401, "E-mail ou senha inválidos.")
    if usuario.situacao == "DESATIVADO":
        auditoria.registrar(
            bd, acao=auditoria.LOGIN_FALHA, usuario=usuario, resultado="NEGADO", detalhe="conta desativada"
        )
        bd.commit()
        raise HTTPException(403, "Conta desativada. Procure o administrador.")
    limite.limpar(ip, email)
    usuario.tentativas_falhas = 0
    usuario.bloqueado_ate = None
    token = gerar_token()
    sessao = Sessao(
        id=hash_token(token),
        usuario_id=usuario.id,
        csrf_token=gerar_token(),
        criado_em=hoje,
        ultimo_acesso=hoje,
        expira_em=hoje + _dt.timedelta(hours=config.sessao_maximo_horas),
    )
    bd.add(sessao)
    auditoria.registrar(bd, acao=auditoria.LOGIN, usuario=usuario)
    bd.commit()
    response.set_cookie(COOKIE_SESSAO, token, httponly=True, samesite="strict", secure=config.cookie_seguro, path="/")
    return quem_sou_eu_dict(usuario, sessao, request)


# ---------------------------------------------------------------------------
# Sessão (qualquer situação de conta)
# ---------------------------------------------------------------------------
@router.get("/quem-sou-eu")
def quem_sou_eu(
    request: Request,
    usuario: Usuario = Depends(exigir(permitir_nao_verificado=True, permitir_troca_pendente=True)),
):
    return quem_sou_eu_dict(usuario, request.state.sessao, request)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    usuario: Usuario = Depends(exigir(permitir_nao_verificado=True, permitir_troca_pendente=True)),
):
    bd = obter_bd(request)
    sessao: Sessao = request.state.sessao
    sessao.encerrada_em = agora()
    auditoria.registrar(bd, acao=auditoria.LOGOUT, usuario=usuario)
    bd.commit()
    response.delete_cookie(COOKIE_SESSAO, path="/")
    return {"mensagem": "Sessão encerrada."}


@router.get("/situacao")
def situacao(request: Request, usuario: Usuario = Depends(exigir(permitir_nao_verificado=True))):
    return {
        "situacao": usuario.situacao,
        "situacao_rotulo": ROTULO_SITUACAO.get(usuario.situacao, usuario.situacao),
        "papel": usuario.papel,
        "papel_rotulo": ROTULO_PAPEL.get(usuario.papel, usuario.papel),
        "mensagem_admin": usuario.mensagem_admin,
        "resposta_usuario": usuario.resposta_usuario,
        "respondido_em": iso(usuario.respondido_em),
        "verificado_em": iso(usuario.verificado_em),
        "criado_em": iso(usuario.criado_em),
        "pode_responder": usuario.situacao in ("INFORMACOES_SOLICITADAS", "REPROVADO"),
    }


@router.post("/situacao/resposta")
def responder_situacao(
    entrada: RespostaSituacao, request: Request, usuario: Usuario = Depends(exigir(permitir_nao_verificado=True))
):
    if usuario.situacao not in ("INFORMACOES_SOLICITADAS", "REPROVADO"):
        raise HTTPException(409, "Não há pedido do administrador a responder.")
    bd = obter_bd(request)
    usuario.resposta_usuario = entrada.resposta
    usuario.respondido_em = agora()
    usuario.situacao = "PENDENTE"
    usuario.atualizado_em = agora()
    auditoria.registrar(
        bd, acao=auditoria.SITUACAO_RESPONDIDA, usuario=usuario, alvo_tipo="usuario", alvo_id=usuario.id
    )
    bd.commit()
    return {"mensagem": "Resposta registrada. O cadastro voltou para a fila de verificação.", "situacao": "PENDENTE"}


# ---------------------------------------------------------------------------
# Minha conta (LGPD, art. 18: acesso, correção, portabilidade, encerramento)
# ---------------------------------------------------------------------------
@router.get("/minha")
def minha_conta(request: Request, usuario: Usuario = Depends(exigir(CONTA_GERIR, permitir_nao_verificado=True))):
    d = usuario_dict(usuario, obter_cifra(request), completo=True)
    d["imutaveis"] = IMUTAVEIS
    return d


@router.put("/minha")
def editar_minha_conta(
    entrada: MinhaContaEntrada,
    request: Request,
    usuario: Usuario = Depends(exigir(CONTA_GERIR, permitir_nao_verificado=True)),
):
    bd = obter_bd(request)
    campos: dict[str, str] = {}
    # Nome, CPF, tipo e número/UF do CRM e ORCID são definidos no cadastro e conferidos pelo administrador: não mudam
    # por aqui. O que vier no corpo para esses campos é ignorado e o valor atual é mantido.
    if entrada.medico is not None and usuario.perfil_medico is not None:
        entrada.medico.tipo = usuario.perfil_medico.tipo
        entrada.medico.crm = usuario.perfil_medico.crm
        entrada.medico.uf = usuario.perfil_medico.uf
    if entrada.pesquisador is not None and usuario.perfil_pesquisador is not None:
        entrada.pesquisador.orcid = usuario.perfil_pesquisador.orcid
    if entrada.email is not None:
        email = normalizar_email(entrada.email)
        if not RE_EMAIL.match(email):
            campos["email"] = "Informe um e-mail válido."
        elif email != usuario.email and bd.execute(select(Usuario.id).where(Usuario.email == email)).first():
            raise ErroConflito({"email": "Já existe um cadastro com este e-mail."})
        else:
            usuario.email = email
    if usuario.papel == "MEDICO" and entrada.medico is not None:
        validar_perfil_medico(entrada.medico, campos)
        if not campos:
            _aplicar_perfil_medico(usuario, entrada.medico)
    if usuario.papel == "PESQUISADOR" and entrada.pesquisador is not None:
        validar_perfil_pesquisador(entrada.pesquisador, campos)
        if not campos:
            _aplicar_perfil_pesquisador(usuario, entrada.pesquisador)
    exigir_campos(campos)
    usuario.atualizado_em = agora()
    auditoria.registrar(bd, acao=auditoria.CONTA_EDITADA, usuario=usuario, alvo_tipo="usuario", alvo_id=usuario.id)
    bd.commit()
    return usuario_dict(usuario, obter_cifra(request), completo=True)


class ErroConflito(HTTPException):
    def __init__(self, campos: dict[str, str]):
        super().__init__(409, {"mensagem": "Já existe um cadastro com estes dados.", "campos": campos})


@router.post("/minha/senha")
def trocar_senha(
    entrada: TrocaSenha,
    request: Request,
    usuario: Usuario = Depends(exigir(CONTA_GERIR, permitir_nao_verificado=True, permitir_troca_pendente=True)),
):
    bd, cifra = obter_bd(request), obter_cifra(request)
    if not verificar_senha(usuario.senha_hash, entrada.senha_atual):
        exigir_campos({"senha_atual": "Senha atual incorreta."})
    if verificar_senha(usuario.senha_hash, entrada.senha_nova):
        exigir_campos({"senha_nova": "A nova senha precisa ser diferente da atual."})
    erro = validar_senha(entrada.senha_nova, usuario.email, cifra.decifrar(usuario.cpf_cifrado))
    if erro:
        exigir_campos({"senha_nova": erro})
    usuario.senha_hash = hash_senha(entrada.senha_nova)
    usuario.trocar_senha = False  # a senha temporária não vira a senha de uso
    usuario.atualizado_em = agora()
    atual: Sessao = request.state.sessao
    for s in bd.execute(select(Sessao).where(Sessao.usuario_id == usuario.id, Sessao.encerrada_em.is_(None))).scalars():
        if s.id != atual.id:  # encerra as outras sessões
            s.encerrada_em = agora()
    auditoria.registrar(bd, acao=auditoria.SENHA_ALTERADA, usuario=usuario)
    bd.commit()
    return {"mensagem": "Senha alterada. As outras sessões foram encerradas."}


@router.post("/minha/exportar")
def exportar_minha_conta(
    request: Request, usuario: Usuario = Depends(exigir(CONTA_GERIR, permitir_nao_verificado=True))
):
    """Portabilidade (art. 18, V): os dados do próprio usuário, em JSON, inclusive o CPF completo e a auditoria própria."""
    bd, cifra = obter_bd(request), obter_cifra(request)
    dados = usuario_dict(usuario, cifra, completo=True)
    dados["cpf"] = formatar_cpf(cifra.decifrar(usuario.cpf_cifrado))
    propria = bd.execute(
        select(auditoria.Auditoria)
        .where(auditoria.Auditoria.usuario_id == usuario.id)
        .order_by(auditoria.Auditoria.sequencia.desc())
        .limit(500)
    ).scalars()
    auditoria.registrar(bd, acao=auditoria.CONTA_EXPORTADA, usuario=usuario, alvo_tipo="usuario", alvo_id=usuario.id)
    bd.commit()
    return {
        "exportado_em": iso(agora()),
        "usuario": dados,
        "auditoria_propria": [auditoria.serializar(r) for r in propria],
    }


@router.post("/minha/encerramento")
def pedir_encerramento(request: Request, usuario: Usuario = Depends(exigir(CONTA_GERIR, permitir_nao_verificado=True))):
    bd = obter_bd(request)
    if usuario.papel == "ADMIN":
        raise HTTPException(
            403,
            "Administradores não pedem encerramento pela plataforma: a conta é desativada por outro administrador.",
        )
    if usuario.encerramento_solicitado_em is None:
        usuario.encerramento_solicitado_em = agora()
        usuario.atualizado_em = agora()
        auditoria.registrar(
            bd, acao=auditoria.ENCERRAMENTO_SOLICITADO, usuario=usuario, alvo_tipo="usuario", alvo_id=usuario.id
        )
        bd.commit()
    return {
        "mensagem": "Pedido de encerramento registrado. O administrador desativará a conta; a auditoria permanece sem dado identificável.",
        "encerramento_solicitado_em": iso(usuario.encerramento_solicitado_em),
    }


@router.get("/minha/auditoria")
def minha_auditoria(request: Request, usuario: Usuario = Depends(exigir(AUDITORIA_VER_PROPRIA))):
    """Auditoria das próprias ações (todos os papéis)."""
    bd = obter_bd(request)
    regs = bd.execute(
        select(auditoria.Auditoria)
        .where(auditoria.Auditoria.usuario_id == usuario.id)
        .order_by(auditoria.Auditoria.sequencia.desc())
        .limit(200)
    ).scalars()
    return {"registros": [auditoria.serializar(r) for r in regs]}
