"""Painel do administrador: cadastros pendentes, gestão de usuários e auditoria completa.

O administrador não acessa pacientes, dados clínicos, VCFs nem resultados: nenhuma rota daqui toca essas tabelas.
"""

from __future__ import annotations

import datetime as _dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from . import auditoria, primeiro_acesso
from .bd import agora
from .contas import usuario_dict
from .comum import exigir_campos, iso, obter_bd, obter_cifra, obter_config
from .modelos import PAPEIS, SITUACOES, Auditoria, Sessao, Usuario
from .permissoes import AUDITORIA_VER_TUDO, USUARIOS_GERIR, exigir
from .seguranca import normalizar_texto, verificar_senha

router = APIRouter(prefix="/api/admin", tags=["admin"])


class Mensagem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    mensagem: str = Field(min_length=3, max_length=4000)


class Busca(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    texto: str = Field(min_length=1, max_length=200)


def _alvo(bd, admin: Usuario, usuario_id: int) -> Usuario:
    if usuario_id == admin.id:
        raise HTTPException(409, "Você não pode alterar a própria conta por aqui.")
    u = bd.get(Usuario, usuario_id)
    if u is None:
        raise HTTPException(404, "Usuário não encontrado.")
    return u


def _dict_admin(u: Usuario, cifra) -> dict:
    d = usuario_dict(u, cifra, completo=True)
    d["mensagem_admin"] = u.mensagem_admin
    d["resposta_usuario"] = u.resposta_usuario
    d["respondido_em"] = iso(u.respondido_em)
    d["bloqueado_ate"] = iso(u.bloqueado_ate)
    return d


@router.get("/cadastros/pendentes")
def pendentes(request: Request, admin: Usuario = Depends(exigir(USUARIOS_GERIR))):
    bd, cifra = obter_bd(request), obter_cifra(request)
    usuarios = bd.execute(
        select(Usuario)
        .where(Usuario.situacao.in_(["PENDENTE", "INFORMACOES_SOLICITADAS"]))
        .order_by(Usuario.criado_em.asc())
    ).scalars()
    return {"cadastros": [_dict_admin(u, cifra) for u in usuarios]}


@router.get("/usuarios")
def listar_usuarios(
    request: Request,
    admin: Usuario = Depends(exigir(USUARIOS_GERIR)),
    papel: str | None = Query(default=None),
    situacao: str | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=50, ge=1, le=200),
):
    bd, cifra = obter_bd(request), obter_cifra(request)
    filtros = []
    if papel:
        if papel not in PAPEIS:
            raise HTTPException(422, "Papel desconhecido.")
        filtros.append(Usuario.papel == papel)
    if situacao:
        if situacao not in SITUACOES:
            raise HTTPException(422, "Situação desconhecida.")
        filtros.append(Usuario.situacao == situacao)
    total = bd.execute(select(func.count(Usuario.id)).where(*filtros)).scalar_one()
    usuarios = bd.execute(
        select(Usuario)
        .where(*filtros)
        .order_by(Usuario.criado_em.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars()
    return {"total": int(total), "pagina": pagina, "usuarios": [_dict_admin(u, cifra) for u in usuarios]}


@router.post("/usuarios/busca")
def buscar_usuarios(entrada: Busca, request: Request, admin: Usuario = Depends(exigir(USUARIOS_GERIR))):
    """Busca por nome ou e-mail no corpo da requisição (nunca na URL)."""
    bd, cifra = obter_bd(request), obter_cifra(request)
    termo = normalizar_texto(entrada.texto)
    usuarios = bd.execute(select(Usuario).order_by(Usuario.criado_em.desc())).scalars()
    achados = [u for u in usuarios if termo in normalizar_texto(u.nome) or termo in u.email.lower()]
    return {"total": len(achados), "usuarios": [_dict_admin(u, cifra) for u in achados[:200]]}


@router.get("/usuarios/{usuario_id}")
def ver_usuario(usuario_id: int, request: Request, admin: Usuario = Depends(exigir(USUARIOS_GERIR))):
    bd, cifra = obter_bd(request), obter_cifra(request)
    u = bd.get(Usuario, usuario_id)
    if u is None:
        raise HTTPException(404, "Usuário não encontrado.")
    return _dict_admin(u, cifra)


def _mudar(bd, admin: Usuario, u: Usuario, situacao: str, acao: str, mensagem: str | None = None) -> dict:
    u.situacao = situacao
    u.mensagem_admin = mensagem
    u.atualizado_em = agora()
    if situacao == "VERIFICADO":
        u.verificado_em = agora()
        u.verificado_por_id = admin.id
    auditoria.registrar(bd, acao=acao, usuario=admin, alvo_tipo="usuario", alvo_id=u.id)
    bd.commit()
    return {"mensagem": "Situação atualizada.", "situacao": u.situacao}


@router.post("/usuarios/{usuario_id}/aprovar")
def aprovar(usuario_id: int, request: Request, admin: Usuario = Depends(exigir(USUARIOS_GERIR))):
    bd = obter_bd(request)
    u = _alvo(bd, admin, usuario_id)
    if u.situacao == "VERIFICADO":
        raise HTTPException(409, "Conta já verificada.")
    return _mudar(bd, admin, u, "VERIFICADO", auditoria.USUARIO_APROVADO)


@router.post("/usuarios/{usuario_id}/reprovar")
def reprovar(usuario_id: int, entrada: Mensagem, request: Request, admin: Usuario = Depends(exigir(USUARIOS_GERIR))):
    bd = obter_bd(request)
    u = _alvo(bd, admin, usuario_id)
    return _mudar(bd, admin, u, "REPROVADO", auditoria.USUARIO_REPROVADO, entrada.mensagem)


@router.post("/usuarios/{usuario_id}/solicitar-informacoes")
def solicitar_informacoes(
    usuario_id: int, entrada: Mensagem, request: Request, admin: Usuario = Depends(exigir(USUARIOS_GERIR))
):
    bd = obter_bd(request)
    u = _alvo(bd, admin, usuario_id)
    if u.situacao == "VERIFICADO":
        raise HTTPException(409, "Conta já verificada; desative-a se for o caso.")
    return _mudar(bd, admin, u, "INFORMACOES_SOLICITADAS", auditoria.INFORMACOES_SOLICITADAS, entrada.mensagem)


@router.post("/usuarios/{usuario_id}/desativar")
def desativar(usuario_id: int, request: Request, admin: Usuario = Depends(exigir(USUARIOS_GERIR))):
    bd = obter_bd(request)
    u = _alvo(bd, admin, usuario_id)
    for s in bd.execute(select(Sessao).where(Sessao.usuario_id == u.id, Sessao.encerrada_em.is_(None))).scalars():
        s.encerrada_em = agora()
    return _mudar(bd, admin, u, "DESATIVADO", auditoria.USUARIO_DESATIVADO, u.mensagem_admin)


@router.post("/usuarios/{usuario_id}/reativar")
def reativar(usuario_id: int, request: Request, admin: Usuario = Depends(exigir(USUARIOS_GERIR))):
    bd = obter_bd(request)
    u = _alvo(bd, admin, usuario_id)
    if u.situacao != "DESATIVADO":
        raise HTTPException(409, "A conta não está desativada.")
    nova = "VERIFICADO" if u.verificado_em is not None else "PENDENTE"
    u.encerramento_solicitado_em = None
    return _mudar(bd, admin, u, nova, auditoria.USUARIO_REATIVADO)


class ContaDeAdministrador(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    nome: str = Field(max_length=200)
    cpf: str = Field(max_length=20)
    email: str = Field(max_length=254)
    senha_atual: str = Field(max_length=200)


@router.post("/administradores", status_code=201)
def criar_administrador(
    entrada: ContaDeAdministrador, request: Request, admin: Usuario = Depends(exigir(USUARIOS_GERIR))
):
    """Um administrador cria outro, conferindo a própria senha. Quem cria não escolhe nem fica com a senha do
    colega: o sistema gera uma temporária, devolvida aqui uma única vez, e o novo administrador a troca no primeiro
    login. Ninguém se cadastra nem é promovido a administrador."""
    bd, cifra = obter_bd(request), obter_cifra(request)
    if not verificar_senha(admin.senha_hash, entrada.senha_atual):
        exigir_campos({"senha_atual": "Senha atual incorreta."})
    temporaria = primeiro_acesso.senha_temporaria()
    u = primeiro_acesso.criar_administrador(
        bd,
        cifra,
        entrada,
        "pela interface, por outro administrador; senha temporária",
        autor=admin,
        senha=temporaria,
        trocar_senha=True,
    )
    return {
        "mensagem": "Administrador criado.",
        "usuario": _dict_admin(u, cifra),
        "senha_temporaria": temporaria,
        "aviso": "Entregue a senha temporária ao novo administrador por um canal seguro. Ela não será mostrada de "
        "novo e precisa ser trocada no primeiro login.",
    }


@router.get("/demonstracao")
def situacao_da_demonstracao(request: Request, admin: Usuario = Depends(exigir(USUARIOS_GERIR))):
    return {"pode_popular": primeiro_acesso.pode_popular_demonstracao(obter_bd(request), obter_config(request))}


@router.post("/demonstracao", status_code=201)
def criar_demonstracao(request: Request, admin: Usuario = Depends(exigir(USUARIOS_GERIR))):
    """Em homologação, antes de haver médico ou pesquisador: os usuários e registros fictícios de `popular-demo`."""
    if not primeiro_acesso.pode_popular_demonstracao(obter_bd(request), obter_config(request)):
        raise HTTPException(
            409, "A demonstração só pode ser criada em homologação, uma vez, antes de haver médicos ou pesquisadores."
        )
    return primeiro_acesso.popular_demonstracao(request)


@router.get("/auditoria")
def consultar_auditoria(
    request: Request,
    admin: Usuario = Depends(exigir(AUDITORIA_VER_TUDO)),
    usuario_id: int | None = Query(default=None),
    acao: str | None = Query(default=None),
    resultado: str | None = Query(default=None),
    de: str | None = Query(default=None, description="AAAA-MM-DD"),
    ate: str | None = Query(default=None, description="AAAA-MM-DD"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=100, ge=1, le=500),
):
    bd = obter_bd(request)
    filtros = []
    if usuario_id is not None:
        filtros.append(Auditoria.usuario_id == usuario_id)
    if acao:
        if acao not in auditoria.ACOES:
            raise HTTPException(422, "Ação desconhecida.")
        filtros.append(Auditoria.acao == acao)
    if resultado:
        if resultado not in ("OK", "NEGADO", "FALHA"):
            raise HTTPException(422, "Resultado desconhecido.")
        filtros.append(Auditoria.resultado == resultado)
    for nome, valor, op in (("de", de, ">="), ("ate", ate, "<")):
        if valor:
            try:
                data = _dt.datetime.strptime(valor, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(422, f"Data '{nome}' inválida (use AAAA-MM-DD).")
            if op == ">=":
                filtros.append(Auditoria.ocorrido_em >= data)
            else:
                filtros.append(Auditoria.ocorrido_em < data + _dt.timedelta(days=1))
    total = bd.execute(select(func.count(Auditoria.id)).where(*filtros)).scalar_one()
    regs = bd.execute(
        select(Auditoria)
        .where(*filtros)
        .order_by(Auditoria.sequencia.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars()
    registros = [auditoria.serializar(r) for r in regs]
    auditoria.registrar(bd, acao=auditoria.AUDITORIA_CONSULTADA, usuario=admin, detalhe=f"filtros: {len(filtros)}")
    bd.commit()
    return {
        "total": int(total),
        "pagina": pagina,
        "por_pagina": por_pagina,
        "acoes": list(auditoria.ACOES),
        "registros": registros,
    }


@router.get("/auditoria/verificacao")
def verificar_auditoria(request: Request, admin: Usuario = Depends(exigir(AUDITORIA_VER_TUDO))):
    return auditoria.verificar(obter_bd(request))
