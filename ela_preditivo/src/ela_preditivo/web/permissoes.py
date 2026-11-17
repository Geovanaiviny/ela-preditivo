"""RBAC: permissões nomeadas atribuídas aos papéis, num único lugar; nunca a um usuário.

Negação por padrão: toda rota `/api` exige sessão e permissão explícita, exceto a lista curta `ROTAS_PUBLICAS`.
A verificação é feita no servidor (middleware em `api.py` + dependência `exigir`); a interface só reflete o resultado.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

# Permissões
PACIENTES_GERIR = "pacientes.gerir"
CONSENTIMENTOS_GERIR = "consentimentos.gerir"
ANALISES_EXECUTAR = "analises.executar"
ANALISES_BAIXAR = "analises.baixar"
MODELO_VER = "modelo.ver"
PESQUISA_CASOS = "pesquisa.casos"
USUARIOS_GERIR = "usuarios.gerir"
AUDITORIA_VER_TUDO = "auditoria.ver_tudo"
AUDITORIA_VER_PROPRIA = "auditoria.ver_propria"
CONTA_GERIR = "conta.gerir"

PERMISSOES = (
    PACIENTES_GERIR,
    CONSENTIMENTOS_GERIR,
    ANALISES_EXECUTAR,
    ANALISES_BAIXAR,
    MODELO_VER,
    PESQUISA_CASOS,
    USUARIOS_GERIR,
    AUDITORIA_VER_TUDO,
    AUDITORIA_VER_PROPRIA,
    CONTA_GERIR,
)

MATRIZ: dict[str, frozenset[str]] = {
    "MEDICO": frozenset(
        {
            PACIENTES_GERIR,
            CONSENTIMENTOS_GERIR,
            ANALISES_EXECUTAR,
            ANALISES_BAIXAR,
            MODELO_VER,
            AUDITORIA_VER_PROPRIA,
            CONTA_GERIR,
        }
    ),
    "PESQUISADOR": frozenset({MODELO_VER, PESQUISA_CASOS, AUDITORIA_VER_PROPRIA, CONTA_GERIR}),
    "ADMIN": frozenset({USUARIOS_GERIR, AUDITORIA_VER_TUDO, AUDITORIA_VER_PROPRIA, CONTA_GERIR}),
}

# Rotas sem sessão: cadastro, login e informação pública. Qualquer outra rota /api exige sessão.
ROTAS_PUBLICAS: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/sistema"),
        ("GET", "/api/privacidade"),
        ("GET", "/api/ajuda"),
        ("POST", "/api/contas/cadastro"),
        ("POST", "/api/contas/login"),
    }
)

MENSAGEM_401 = "Sessão ausente ou expirada. Entre novamente."
MENSAGEM_403 = "Seu perfil não tem acesso a esta função."
MENSAGEM_NAO_VERIFICADO = "Sua conta ainda não foi verificada. Acompanhe a situação do cadastro."


def permissoes_do_papel(papel: str) -> frozenset[str]:
    return MATRIZ.get(papel, frozenset())


def tem_permissao(papel: str, permissao: str) -> bool:
    return permissao in permissoes_do_papel(papel)


def exigir(*permissoes: str, permitir_nao_verificado: bool = False):
    """Dependência FastAPI: sessão válida + conta verificada (salvo rotas de situação/conta) + todas as permissões.

    A função devolvida carrega `_exigencia`, que o teste de cobertura das rotas usa para garantir que toda rota
    `/api` fora da lista pública passa por aqui.
    """
    for p in permissoes:
        if p not in PERMISSOES:
            raise ValueError(f"permissão desconhecida: {p}")

    def dependencia(request: Request):
        usuario = getattr(request.state, "usuario", None)
        if usuario is None:
            raise HTTPException(401, MENSAGEM_401)
        if not permitir_nao_verificado and not usuario.verificado:
            _negar(request, usuario, "conta_nao_verificada")
            raise HTTPException(403, MENSAGEM_NAO_VERIFICADO)
        faltam = [p for p in permissoes if not tem_permissao(usuario.papel, p)]
        if faltam:
            _negar(request, usuario, "permissao:" + ",".join(faltam))
            raise HTTPException(403, MENSAGEM_403)
        return usuario

    dependencia._exigencia = {"permissoes": permissoes, "permitir_nao_verificado": permitir_nao_verificado}
    return dependencia


def _negar(request: Request, usuario, motivo: str) -> None:
    """Toda negação de acesso vai para a auditoria (art. 37)."""
    from . import auditoria  # import tardio para evitar ciclo

    bd = getattr(request.state, "bd", None)
    if bd is None:
        return
    auditoria.registrar(
        bd,
        usuario=usuario,
        acao=auditoria.ACESSO_NEGADO,
        resultado="NEGADO",
        detalhe=f"{request.method} {request.url.path} ({motivo})"[:300],
    )
    bd.commit()
