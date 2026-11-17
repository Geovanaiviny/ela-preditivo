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
ARTEFATO_EXECUTAR = "artefato.executar"  # reprodução, avaliação e cenários sintéticos pela interface
BASE_VER = "base.ver"  # base de anotação em uso e versões registradas
BASE_GERIR = "base.gerir"  # enviar, registrar e baixar bases de anotação
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
    ARTEFATO_EXECUTAR,
    BASE_VER,
    BASE_GERIR,
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
            ARTEFATO_EXECUTAR,
            BASE_VER,
            AUDITORIA_VER_PROPRIA,
            CONTA_GERIR,
        }
    ),
    "PESQUISADOR": frozenset(
        {MODELO_VER, ARTEFATO_EXECUTAR, BASE_VER, PESQUISA_CASOS, AUDITORIA_VER_PROPRIA, CONTA_GERIR}
    ),
    # a base de anotação é dado público do ClinVar e a sua troca é operação do sistema, por isso fica com o
    # administrador; ele continua sem ver registros, resultados e parâmetros
    "ADMIN": frozenset({USUARIOS_GERIR, BASE_VER, BASE_GERIR, AUDITORIA_VER_TUDO, AUDITORIA_VER_PROPRIA, CONTA_GERIR}),
}

# Rotas sem sessão: cadastro, login, informação pública e primeiro acesso. Qualquer outra rota /api exige sessão.
ROTAS_PUBLICAS: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/sistema"),
        ("GET", "/api/privacidade"),
        ("GET", "/api/ajuda"),
        ("POST", "/api/contas/cadastro"),
        ("POST", "/api/contas/login"),
        # primeiro acesso: só respondem enquanto não há administrador (ou, a demonstração, usuário algum)
        ("POST", "/api/primeiro-acesso/administrador"),
        ("POST", "/api/primeiro-acesso/demonstracao"),
    }
)

MENSAGEM_401 = "Sessão ausente ou expirada. Entre novamente."
MENSAGEM_403 = "Seu perfil não tem acesso a esta função."
MENSAGEM_NAO_VERIFICADO = "Sua conta ainda não foi verificada. Acompanhe a situação do cadastro."
MENSAGEM_TROCAR_SENHA = "Troque a senha temporária para continuar."


def permissoes_do_papel(papel: str) -> frozenset[str]:
    return MATRIZ.get(papel, frozenset())


def tem_permissao(papel: str, permissao: str) -> bool:
    return permissao in permissoes_do_papel(papel)


def exigir(*permissoes: str, permitir_nao_verificado: bool = False, permitir_troca_pendente: bool = False):
    """Dependência FastAPI: sessão válida + conta verificada (salvo rotas de situação/conta) + todas as permissões.
    Quem entrou com senha temporária só alcança as rotas marcadas com `permitir_troca_pendente` (sessão e troca
    de senha) até definir a própria senha.

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
        if usuario.trocar_senha and not permitir_troca_pendente:
            _negar(request, usuario, "senha_temporaria")
            raise HTTPException(403, MENSAGEM_TROCAR_SENHA)
        if not permitir_nao_verificado and not usuario.verificado:
            _negar(request, usuario, "conta_nao_verificada")
            raise HTTPException(403, MENSAGEM_NAO_VERIFICADO)
        faltam = [p for p in permissoes if not tem_permissao(usuario.papel, p)]
        if faltam:
            _negar(request, usuario, "permissao:" + ",".join(faltam))
            raise HTTPException(403, MENSAGEM_403)
        return usuario

    dependencia._exigencia = {
        "permissoes": permissoes,
        "permitir_nao_verificado": permitir_nao_verificado,
        "permitir_troca_pendente": permitir_troca_pendente,
    }
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
