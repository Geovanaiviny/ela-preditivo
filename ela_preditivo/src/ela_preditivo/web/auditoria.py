"""Auditoria (LGPD, art. 37): registro só de inclusão, encadeado por hash SHA-256.

Nunca grava nome de paciente, CPF completo nem senha: só ids, ação, resultado e um detalhe curto sem dado pessoal.
"""

from __future__ import annotations

import hashlib
import threading

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from .bd import agora
from .modelos import Auditoria

# Ações registradas
CADASTRO = "cadastro"
LOGIN = "login"
LOGIN_FALHA = "login_falha"
LOGOUT = "logout"
SENHA_ALTERADA = "senha_alterada"
CONTA_EDITADA = "conta_editada"
CONTA_EXPORTADA = "conta_exportada"
ENCERRAMENTO_SOLICITADO = "encerramento_solicitado"
SITUACAO_RESPONDIDA = "situacao_respondida"
USUARIO_APROVADO = "usuario_aprovado"
USUARIO_REPROVADO = "usuario_reprovado"
INFORMACOES_SOLICITADAS = "informacoes_solicitadas"
USUARIO_DESATIVADO = "usuario_desativado"
USUARIO_REATIVADO = "usuario_reativado"
PACIENTE_CRIADO = "paciente_criado"
PACIENTE_VISUALIZADO = "paciente_visualizado"
PACIENTE_EDITADO = "paciente_editado"
PACIENTE_EXPORTADO = "paciente_exportado"
PACIENTE_EXCLUIDO = "paciente_excluido"
CONSENTIMENTO_REGISTRADO = "consentimento_registrado"
CONSENTIMENTO_REVOGADO = "consentimento_revogado"
CASO_LIBERADO_PESQUISA = "caso_liberado_pesquisa"
CASO_RETIRADO_PESQUISA = "caso_retirado_pesquisa"
ANALISE_EXECUTADA = "analise_executada"
ANALISE_FALHA = "analise_falha"
PACOTE_BAIXADO = "pacote_baixado"
ACESSO_NEGADO = "acesso_negado"
AUDITORIA_CONSULTADA = "auditoria_consultada"
ADMIN_CRIADO = "admin_criado"
DEMO_POPULADA = "demo_populada"
VCF_ANEXADO = "vcf_anexado"
VCF_REMOVIDO = "vcf_removido"
DESCENDENTE_EDITADO = "descendente_editado"
CASOS_CONSULTADOS = "casos_consultados"
CASOS_EXPORTADOS = "casos_exportados"
DOCUMENTO_ANEXADO = "documento_anexado"
DOCUMENTO_ABERTO = "documento_aberto"
DOCUMENTO_REMOVIDO = "documento_removido"
RESULTADO_ABERTO = "resultado_aberto"
PARENTE_ADICIONADO = "parente_adicionado"
PARENTE_REMOVIDO = "parente_removido"
TAREFA_INICIADA = "tarefa_iniciada"
TAREFA_CANCELADA = "tarefa_cancelada"
TAREFA_REMOVIDA = "tarefa_removida"
BASE_ENVIADA = "base_enviada"
BASE_REGISTRADA = "base_registrada"

ACOES = (
    CADASTRO,
    LOGIN,
    LOGIN_FALHA,
    LOGOUT,
    SENHA_ALTERADA,
    CONTA_EDITADA,
    CONTA_EXPORTADA,
    ENCERRAMENTO_SOLICITADO,
    SITUACAO_RESPONDIDA,
    USUARIO_APROVADO,
    USUARIO_REPROVADO,
    INFORMACOES_SOLICITADAS,
    USUARIO_DESATIVADO,
    USUARIO_REATIVADO,
    PACIENTE_CRIADO,
    PACIENTE_VISUALIZADO,
    PACIENTE_EDITADO,
    PACIENTE_EXPORTADO,
    PACIENTE_EXCLUIDO,
    CONSENTIMENTO_REGISTRADO,
    CONSENTIMENTO_REVOGADO,
    CASO_LIBERADO_PESQUISA,
    CASO_RETIRADO_PESQUISA,
    ANALISE_EXECUTADA,
    ANALISE_FALHA,
    PACOTE_BAIXADO,
    ACESSO_NEGADO,
    AUDITORIA_CONSULTADA,
    ADMIN_CRIADO,
    DEMO_POPULADA,
    VCF_ANEXADO,
    VCF_REMOVIDO,
    DESCENDENTE_EDITADO,
    CASOS_CONSULTADOS,
    CASOS_EXPORTADOS,
    DOCUMENTO_ANEXADO,
    DOCUMENTO_ABERTO,
    DOCUMENTO_REMOVIDO,
    RESULTADO_ABERTO,
    PARENTE_ADICIONADO,
    PARENTE_REMOVIDO,
    TAREFA_INICIADA,
    TAREFA_CANCELADA,
    TAREFA_REMOVIDA,
    BASE_ENVIADA,
    BASE_REGISTRADA,
)
HASH_GENESE = "0" * 64


def _hash(seq: int, ocorrido_em, usuario_id, papel, acao, alvo_tipo, alvo_id, resultado, detalhe, anterior) -> str:
    base = "|".join(
        str(x if x is not None else "")
        for x in (
            seq,
            ocorrido_em.isoformat(),
            usuario_id,
            papel,
            acao,
            alvo_tipo,
            alvo_id,
            resultado,
            detalhe,
            anterior,
        )
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def registrar(
    bd: Session,
    *,
    acao: str,
    usuario=None,
    usuario_id: int | None = None,
    papel: str | None = None,
    alvo_tipo: str | None = None,
    alvo_id=None,
    resultado: str = "OK",
    detalhe: str | None = None,
) -> Auditoria:
    """Acrescenta um registro à cadeia (o chamador faz o commit). `detalhe` não pode conter dado pessoal."""
    if acao not in ACOES:
        raise ValueError(f"ação de auditoria desconhecida: {acao}")
    if usuario is not None:
        usuario_id, papel = usuario.id, usuario.papel
    _trancar(bd)
    ultimo = bd.execute(select(Auditoria).order_by(Auditoria.sequencia.desc()).limit(1)).scalar_one_or_none()
    seq = (ultimo.sequencia + 1) if ultimo else 1
    anterior = ultimo.hash if ultimo else HASH_GENESE
    quando = agora()
    alvo_id = None if alvo_id is None else str(alvo_id)
    detalhe = (detalhe or "")[:300] or None
    reg = Auditoria(
        sequencia=seq,
        ocorrido_em=quando,
        usuario_id=usuario_id,
        papel=papel,
        acao=acao,
        alvo_tipo=alvo_tipo,
        alvo_id=alvo_id,
        resultado=resultado,
        detalhe=detalhe,
        hash_anterior=anterior,
        hash=_hash(seq, quando, usuario_id, papel, acao, alvo_tipo, alvo_id, resultado, detalhe, anterior),
    )
    bd.add(reg)
    bd.flush()
    return reg


# A cadeia exige que os registros sejam gravados um por vez: dois pedidos simultâneos leriam o mesmo "último"
# e tentariam a mesma sequência (UNIQUE) ou bifurcariam o encadeamento. A tranca é tomada ao registrar e
# devolvida quando a transação da sessão termina (commit, rollback ou fechamento), que nas rotas é logo em seguida.
_TRANCA = threading.Lock()
_CHAVE_TRANCA = "auditoria_trancada"
_ESPERA_TRANCA_S = 30.0


def _trancar(bd: Session) -> None:
    if bd.info.get(_CHAVE_TRANCA):
        return
    # se a espera estourar, segue assim mesmo: a restrição UNIQUE ainda impede a sequência duplicada
    bd.info[_CHAVE_TRANCA] = _TRANCA.acquire(timeout=_ESPERA_TRANCA_S)


@event.listens_for(Session, "after_transaction_end")
def _destrancar(bd: Session, transacao) -> None:
    if transacao.parent is None and bd.info.pop(_CHAVE_TRANCA, None):
        _TRANCA.release()


def verificar(bd: Session) -> dict:
    """Percorre a cadeia inteira e confere sequência, encadeamento e hash de cada registro."""
    registros = bd.execute(select(Auditoria).order_by(Auditoria.sequencia)).scalars().all()
    anterior, esperado = HASH_GENESE, 1
    for r in registros:
        calculado = _hash(
            r.sequencia,
            r.ocorrido_em,
            r.usuario_id,
            r.papel,
            r.acao,
            r.alvo_tipo,
            r.alvo_id,
            r.resultado,
            r.detalhe,
            r.hash_anterior,
        )
        if r.sequencia != esperado or r.hash_anterior != anterior or r.hash != calculado:
            return {"ok": False, "total": len(registros), "primeira_falha": r.sequencia}
        anterior, esperado = r.hash, r.sequencia + 1
    return {"ok": True, "total": len(registros), "primeira_falha": None}


def total(bd: Session) -> int:
    return int(bd.execute(select(func.count(Auditoria.id))).scalar_one())


def serializar(r: Auditoria) -> dict:
    return {
        "sequencia": r.sequencia,
        "ocorrido_em": r.ocorrido_em.isoformat() + "Z",
        "usuario_id": r.usuario_id,
        "papel": r.papel,
        "acao": r.acao,
        "alvo_tipo": r.alvo_tipo,
        "alvo_id": r.alvo_id,
        "resultado": r.resultado,
        "detalhe": r.detalhe,
        "hash": r.hash,
    }
