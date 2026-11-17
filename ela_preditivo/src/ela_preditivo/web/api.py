"""Aplicação FastAPI da plataforma: fábrica `criar_app`, guarda de sessão/CSRF com negação por padrão e rotas públicas.

Servir: `ela-preditivo servir` (uvicorn). Testes: `criar_app(Configuracao(chave=..., bd=<arquivo temporário>))`.
"""

from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .. import AVISO_LEGAL, __version__
from . import admin, analises, artefato, auditoria, contas, pacientes, pesquisa, primeiro_acesso, textos
from .bd import agora, criar_engine, criar_tabelas, fabrica_sessoes
from .comum import MUTAVEIS, origem
from .config import Configuracao
from .modelos import Sessao, Usuario
from .permissoes import MENSAGEM_401, ROTAS_PUBLICAS
from .seguranca import Cifra, LimiteTentativas, comparar_tokens, hash_token

DIR_STATIC = Path(__file__).resolve().parent / "static"
COOKIE_SESSAO = "ela_sessao"
log = logging.getLogger("ela_preditivo.web")

CABECALHOS_SEGURANCA = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
        "frame-ancestors 'none'; form-action 'self'; base-uri 'self'; object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def carregar_sessao(request: Request, bd, config: Configuracao) -> tuple[Usuario | None, Sessao | None]:
    """Sessão do cookie: válida se não encerrada, dentro da expiração absoluta e da inatividade de 30 min."""
    token = request.cookies.get(COOKIE_SESSAO)
    if not token:
        return None, None
    sessao = bd.get(Sessao, hash_token(token))
    if sessao is None or sessao.encerrada_em is not None:
        return None, None
    hoje = agora()
    if hoje >= sessao.expira_em or hoje - sessao.ultimo_acesso > _dt.timedelta(minutes=config.sessao_minutos):
        sessao.encerrada_em = hoje
        bd.commit()
        return None, None
    usuario = bd.get(Usuario, sessao.usuario_id)
    if usuario is None or usuario.situacao == "DESATIVADO":
        sessao.encerrada_em = hoje
        bd.commit()
        return None, None
    sessao.ultimo_acesso = hoje
    bd.commit()
    return usuario, sessao


def criar_app(config: Configuracao | None = None) -> FastAPI:
    config = config or Configuracao.do_ambiente()
    engine = criar_engine(config.bd)
    criar_tabelas(engine)
    app = FastAPI(
        title="EloSense (ela_preditivo)", version=__version__, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.config = config
    app.state.engine = engine
    app.state.sessoes = fabrica_sessoes(engine)
    app.state.cifra = Cifra(config.chave)
    app.state.limite = LimiteTentativas(config.tentativas_login, config.bloqueio_minutos * 60)
    app.state.analises = analises.RegistroAnalises(config)
    app.state.tarefas = artefato.RegistroTarefas(config)
    config.dir_vcfs.mkdir(parents=True, exist_ok=True)

    @app.middleware("http")
    async def guarda(request: Request, call_next):
        caminho = request.url.path
        if not caminho.startswith("/api"):
            resposta = await call_next(request)
            _cabecalhos(resposta, publico=True)
            return resposta
        bd = app.state.sessoes()
        request.state.bd = bd
        request.state.usuario = None
        request.state.sessao = None
        try:
            usuario, sessao = carregar_sessao(request, bd, config)
            request.state.usuario, request.state.sessao = usuario, sessao
            if (request.method, caminho) in ROTAS_PUBLICAS:
                if request.method in MUTAVEIS and not request.headers.get("content-type", "").startswith(
                    "application/json"
                ):
                    return _json(415, "formato", "Envie os dados em JSON.")
            else:
                if usuario is None:
                    # "quem sou eu" sem sessão é a sondagem de arranque da própria interface (o cookie é HttpOnly e o
                    # navegador não sabe se há sessão); não é tentativa de acesso a recurso protegido, logo não vai à auditoria
                    if not (request.method == "GET" and caminho == "/api/contas/quem-sou-eu"):
                        auditoria.registrar(
                            bd,
                            acao=auditoria.ACESSO_NEGADO,
                            resultado="NEGADO",
                            detalhe=f"{request.method} {caminho} (sem sessão; origem {origem(request)})",
                        )
                        bd.commit()
                    return _json(401, "nao_autenticado", MENSAGEM_401)
                if request.method in MUTAVEIS and not comparar_tokens(
                    request.headers.get("X-CSRF-Token"), sessao.csrf_token
                ):
                    auditoria.registrar(
                        bd,
                        usuario=usuario,
                        acao=auditoria.ACESSO_NEGADO,
                        resultado="NEGADO",
                        detalhe=f"{request.method} {caminho} (token CSRF ausente ou inválido)",
                    )
                    bd.commit()
                    return _json(403, "csrf", "Requisição recusada: proteção contra falsificação. Recarregue a página.")
            resposta = await call_next(request)
        finally:
            bd.close()
        _cabecalhos(resposta, publico=False)
        return resposta

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError):
        campos = {}
        for e in exc.errors():
            loc = [str(x) for x in e.get("loc", []) if x not in ("body", "query", "path", "form")]
            campos[".".join(loc) or "corpo"] = _mensagem_validacao(e)
        return _json(422, "validacao", "Corrija os campos indicados.", campos=campos)

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict):
            return _json(exc.status_code, "validacao", exc.detail.get("mensagem", ""), campos=exc.detail.get("campos"))
        codigo = {401: "nao_autenticado", 403: "sem_permissao", 404: "nao_encontrado", 409: "conflito", 429: "limite"}
        return _json(exc.status_code, codigo.get(exc.status_code, "erro"), str(exc.detail), headers=exc.headers)

    @app.exception_handler(Exception)
    async def _interno(request: Request, exc: Exception):
        log.exception("erro interno em %s %s", request.method, request.url.path)
        return _json(500, "interno", "Erro interno. Tente novamente; se persistir, avise o administrador.")

    app.include_router(contas.router)
    app.include_router(admin.router)
    app.include_router(pacientes.router)
    app.include_router(pesquisa.router)
    app.include_router(analises.router)
    app.include_router(artefato.router)
    app.include_router(primeiro_acesso.router)

    @app.get("/api/sistema")
    def sistema(request: Request):
        """Informação pública: versão, avisos, selo de demonstração, encarregado e versões dos termos."""
        return {
            "nome": "ela_preditivo",
            "marca": textos.MARCA,
            "marca_subtitulo": textos.MARCA_SUBTITULO,
            "descricao": textos.DESCRICAO_SISTEMA,
            "versao": __version__,
            "aviso_legal": AVISO_LEGAL,
            "aviso_experimental": textos.AVISO_EXPERIMENTAL,
            "ambiente": config.ambiente,
            "demonstracao": config.demonstracao,
            "selo_demonstracao": textos.SELO_DEMONSTRACAO if config.demonstracao else None,
            "encarregado": {"nome": config.encarregado_nome, "contato": config.encarregado_contato},
            "versoes_termos": {
                "aviso_privacidade": textos.VERSAO_AVISO_PRIVACIDADE,
                "termo_uso": textos.VERSAO_TERMO_USO,
                "consentimento_pesquisa": textos.VERSAO_TERMO_CONSENTIMENTO_PESQUISA,
            },
            "termo_uso": textos.TERMO_USO,
            "sessao_minutos": config.sessao_minutos,
            # o que ainda está por configurar: sem administrador, a interface abre no primeiro acesso
            "primeiro_acesso": primeiro_acesso.situacao(request.state.bd, config),
        }

    @app.get("/api/privacidade")
    def privacidade():
        return textos.aviso_privacidade(config.encarregado_nome, config.encarregado_contato)

    @app.get("/api/ajuda")
    def ajuda():
        """Página pública de ajuda: os três casos atendidos, o que fica fora do escopo e o fluxo de uso."""
        return {
            **textos.ajuda(),
            "encarregado": {"nome": config.encarregado_nome, "contato": config.encarregado_contato},
        }

    app.mount("/static", StaticFiles(directory=DIR_STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def raiz():
        return FileResponse(DIR_STATIC / "index.html", headers={"Cache-Control": "no-store"})

    @app.on_event("shutdown")
    def _encerrar():
        app.state.analises.encerrar()
        app.state.tarefas.encerrar()

    return app


def _cabecalhos(resposta, publico: bool) -> None:
    for k, v in CABECALHOS_SEGURANCA.items():
        resposta.headers.setdefault(k, v)
    if not publico:
        resposta.headers["Cache-Control"] = "no-store"


def _json(status: int, erro: str, mensagem: str, campos: dict | None = None, headers=None) -> JSONResponse:
    corpo = {"erro": erro, "mensagem": mensagem}
    if campos:
        corpo["campos"] = campos
    return JSONResponse(corpo, status_code=status, headers=headers)


def _mensagem_validacao(e: dict) -> str:
    tipo = e.get("type", "")
    if tipo == "missing":
        return "Campo obrigatório."
    if tipo.startswith("literal") or tipo.startswith("enum"):
        return "Valor fora das opções permitidas."
    if tipo.startswith("string_too_short"):
        return "Texto curto demais."
    if tipo.startswith("string_too_long"):
        return "Texto longo demais."
    if tipo.startswith("int") or tipo.startswith("float"):
        return "Informe um número válido."
    if tipo.startswith("bool"):
        return "Informe sim ou não."
    return "Valor inválido."


def rotas_api(app: FastAPI) -> list:
    """Todas as rotas `/api` registradas, inclusive as de routers incluídos (o teste de negação por padrão percorre esta lista)."""
    from fastapi.routing import APIRoute

    achadas: list = []

    def _andar(rotas):
        for r in rotas:
            if isinstance(r, APIRoute):
                achadas.append(r)
                continue
            sub = getattr(r, "routes", None)  # Router/Mount
            if sub is None:  # FastAPI ≥ 0.120: routers incluídos viram _IncludedRouter(original_router=...)
                sub = getattr(getattr(r, "original_router", None), "routes", None)
            if sub is None:
                sub = getattr(getattr(r, "router", None), "routes", None)
            if sub:
                _andar(sub)

    _andar(app.routes)
    return [r for r in achadas if r.path.startswith("/api")]


def exigencia_da_rota(rota) -> dict | None:
    """Marcador `_exigencia` da dependência `permissoes.exigir`, se a rota passa por ela."""

    def _procurar(dep):
        chamada = getattr(dep, "call", None)
        marca = getattr(chamada, "_exigencia", None)
        if marca is not None:
            return marca
        for sub in getattr(dep, "dependencies", []) or []:
            achada = _procurar(sub)
            if achada is not None:
                return achada
        return None

    return _procurar(rota.dependant)


def sessoes_ativas_do_usuario(bd, usuario_id: int) -> list[Sessao]:
    return list(
        bd.execute(select(Sessao).where(Sessao.usuario_id == usuario_id, Sessao.encerrada_em.is_(None))).scalars()
    )
