"""Atendimentos (registro "paciente": pessoa, casal ou família), genitores com VCF cifrado, descendentes, consentimentos
para pesquisa e busca com filtros (LGPD, arts. 8º, 11, 13 §4º, 14, 16, 18).

Só o médico, só os próprios registros (outro médico recebe 404). Identificadores cifrados em repouso e filtrados em
memória; busca e filtros por POST (nada pessoal na URL); exclusão com confirmação do nome do registro, que apaga
VCFs, resumos de análise e consentimentos; exportação em JSON; consentimento por titular (genitores e cada descendente),
nunca pré-marcado, revogável na mesma tela.
"""

from __future__ import annotations

import datetime as _dt
import json
import secrets

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .. import anotacao, ingestao
from .. import parentes as parentes_mod
from ..calibracao import carregar_parametros
from . import arquivos, auditoria, textos, vcfs
from .bd import agora
from .comum import (
    exigir_campos,
    interpretar_laudo,
    iso,
    laudo_texto,
    obter_bd,
    obter_cifra,
    obter_config,
    quantil_inicio,
    texto_curto,
)
from .modelos import (
    BASE_LEGAL_ATENDIMENTO,
    MAXIMO_IRMAOS_POR_GENITOR,
    MOMENTOS,
    PAPEIS_GENITOR,
    PARENTESCOS,
    SITUACOES_GENITOR,
    TIPOS_ATENDIMENTO,
    TIPOS_DOCUMENTO,
    TITULARES,
    AnalisePaciente,
    Consentimento,
    Descendente,
    Documento,
    Genitor,
    Paciente,
    Parente,
    Usuario,
)
from .permissoes import CONSENTIMENTOS_GERIR, PACIENTES_GERIR, exigir
from .seguranca import normalizar_texto

router = APIRouter(prefix="/api/pacientes", tags=["pacientes"])
MAIORIDADE = 18
ROTULO_TITULAR = textos.ROTULO_TITULAR
GENES_PADRAO = ("SOD1", "C9orf72", "TARDBP", "FUS")
SITUACOES_PESQUISA = {
    "LIBERADO": "Liberado para pesquisa (pseudonimizado)",
    "PENDENTE": "Consentimentos pendentes",
    "NAO_INICIADO": "Sem consentimento registrado",
}
ORDENACOES = {
    "nome": "Nome do registro",
    "idade": "Idade (menor descendente)",
    "ultima_analise": "Última análise",
    "risco": "Maior risco vitalício",
    "cadastro": "Data de cadastro",
}


# ---------------------------------------------------------------------------
# Entradas
# ---------------------------------------------------------------------------
class GenitorEntrada(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    nome: str = Field(default="", max_length=200)
    data_nascimento: str = Field(default="", max_length=10, description="AAAA-MM-DD")
    laudo_c9orf72: str | None = Field(default=None, max_length=20)


class DescendenteEntrada(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    nome: str = Field(default="", max_length=200)
    data_nascimento: str = Field(default="", max_length=10)
    sexo: str = Field(default="", max_length=1)


class PacienteEntrada(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    tipo: str = Field(default="PESSOA", max_length=10)
    nome: str | None = Field(default=None, max_length=200)
    prontuario: str | None = Field(default=None, max_length=60)
    momento: str | None = Field(default=None, max_length=20)
    observacoes: str | None = Field(default=None, max_length=4000)
    mae: GenitorEntrada = Field(default_factory=GenitorEntrada)
    pai: GenitorEntrada = Field(default_factory=GenitorEntrada)
    descendentes: list[DescendenteEntrada] = Field(default_factory=list, max_length=20)


class Busca(BaseModel):
    """Filtros da lista do médico; tudo opcional e sempre no corpo da requisição."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    texto: str | None = Field(default=None, max_length=200)
    tipo: str | None = Field(default=None, max_length=10)
    sexo: str | None = Field(default=None, max_length=1)
    idade_min: int | None = Field(default=None, ge=0, le=120)
    idade_max: int | None = Field(default=None, ge=0, le=120)
    menor_de_idade: bool | None = None
    momento: str | None = Field(default=None, max_length=20)
    pesquisa: str | None = Field(default=None, max_length=20)
    vcfs: str | None = Field(default=None, max_length=12)
    genes: list[str] = Field(default_factory=list, max_length=10)
    analise: str | None = Field(default=None, max_length=5)
    risco_min: float | None = Field(default=None, ge=0, le=1)
    laudo_c9orf72: bool | None = None
    suposicao: bool | None = None
    analise_de: str | None = Field(default=None, max_length=10)
    analise_ate: str | None = Field(default=None, max_length=10)
    cadastro_de: str | None = Field(default=None, max_length=10)
    cadastro_ate: str | None = Field(default=None, max_length=10)
    ordenar: str = Field(default="nome", max_length=20)
    direcao: str = Field(default="asc", max_length=4)


class ConfirmacaoExclusao(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    confirmacao_nome: str = Field(max_length=200)


class SituacaoGenitorEntrada(BaseModel):
    """Situação clínica do genitor sem exame e a idade correspondente (atual, ou ao falecer)."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    situacao: str | None = Field(default=None, max_length=20)
    idade: int | None = Field(default=None, ge=0, le=120)


class ConsentimentoEntrada(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    titular: str = Field(max_length=20)
    descendente_id: int | None = None
    parente_id: int | None = None
    nome_titular: str | None = Field(default=None, max_length=200)
    confirmado: bool = False  # a interface nunca pré-marca; o servidor exige a marcação explícita
    versao_termo: str | None = None


# ---------------------------------------------------------------------------
# Utilitários de data, validação e leitura
# ---------------------------------------------------------------------------
def idade_em(data_nascimento: _dt.date, hoje: _dt.date) -> int:
    anos = hoje.year - data_nascimento.year
    if (hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day):
        anos -= 1
    return anos


def _data(valor: str | None, campo: str, campos: dict, hoje: _dt.date) -> _dt.date | None:
    if not valor:
        campos[campo] = "Informe a data de nascimento."
        return None
    try:
        d = _dt.date.fromisoformat(valor)
    except ValueError:
        campos[campo] = "Data inválida (use AAAA-MM-DD)."
        return None
    if d > hoje:
        campos[campo] = "A data de nascimento não pode estar no futuro."
    elif idade_em(d, hoje) > 120:
        campos[campo] = "Confira a data: idade acima de 120 anos."
    return d


def _nome(valor: str | None, campo: str, campos: dict, mensagem: str) -> str:
    nome = " ".join((valor or "").split())
    if len(nome) < 3:
        campos[campo] = mensagem
    return nome


def _validar_genitor(g: GenitorEntrada, prefixo: str, campos: dict, hoje: _dt.date) -> dict:
    nome = _nome(g.nome, f"{prefixo}.nome", campos, "Informe o nome completo.")
    nasc = _data(g.data_nascimento, f"{prefixo}.data_nascimento", campos, hoje)
    laudo = interpretar_laudo(g.laudo_c9orf72, f"{prefixo}.laudo_c9orf72", campos)
    return {"nome": nome, "nasc": nasc, "laudo": laudo_texto(laudo)}


def _validar_descendente(d: DescendenteEntrada, prefixo: str, campos: dict, hoje: _dt.date) -> dict:
    nome = _nome(d.nome, f"{prefixo}.nome", campos, "Informe o nome completo.")
    nasc = _data(d.data_nascimento, f"{prefixo}.data_nascimento", campos, hoje)
    sexo = (d.sexo or "").upper()
    if sexo not in ("M", "F"):
        campos[f"{prefixo}.sexo"] = "Informe o sexo (F ou M)."
    return {"nome": nome, "nasc": nasc, "sexo": sexo}


def _validar(entrada: PacienteEntrada, tipo: str, hoje: _dt.date, com_descendentes: bool = True) -> tuple[dict, dict]:
    campos: dict[str, str] = {}
    if tipo not in TIPOS_ATENDIMENTO:
        campos["tipo"] = "Escolha o caso: pessoa, casal ou família."
    prontuario = texto_curto(entrada.prontuario, 60)
    if not prontuario:
        campos["prontuario"] = "Informe o número do prontuário."
    momento = (entrada.momento or "").strip().upper() or None
    if momento is not None and momento not in MOMENTOS:
        campos["momento"] = "Momento do aconselhamento desconhecido."
    mae = _validar_genitor(entrada.mae, "mae", campos, hoje)
    pai = _validar_genitor(entrada.pai, "pai", campos, hoje)
    descs: list[dict] = []
    if com_descendentes:
        n = len(entrada.descendentes)
        if tipo == "PESSOA" and n != 1:
            campos["descendentes"] = "Informe os dados da pessoa atendida (exatamente uma)."
        elif tipo == "CASAL" and n != 0:
            campos["descendentes"] = "No caso 2 não há descendente cadastrado: o filho é hipotético."
        elif tipo == "FAMILIA" and n < 1:
            campos["descendentes"] = "Informe ao menos um filho."
        for i, d in enumerate(entrada.descendentes):
            descs.append(_validar_descendente(d, f"descendentes.{i}", campos, hoje))
    nome = texto_curto(entrada.nome, 200)
    if not nome:
        if tipo == "PESSOA" and descs:
            nome = descs[0]["nome"]
        elif tipo == "CASAL" and mae["nome"] and pai["nome"]:
            nome = f"{mae['nome']} e {pai['nome']}"
    if not nome or len(nome) < 3:
        campos["nome"] = (
            "Informe o nome da família (ex.: Família Silva)." if tipo == "FAMILIA" else "Informe o nome do registro."
        )
    dados = {
        "nome": nome,
        "prontuario": prontuario,
        "momento": momento,
        "observacoes": texto_curto(entrada.observacoes, 4000),
        "mae": mae,
        "pai": pai,
        "descendentes": descs,
    }
    return campos, dados


def _aplicar_genitor(g: Genitor, dados: dict, cifra) -> None:
    g.nome_cifrado = cifra.cifrar(dados["nome"])
    g.data_nascimento_cifrada = cifra.cifrar(dados["nasc"].isoformat())
    g.laudo_c9orf72_cifrado = cifra.cifrar(dados["laudo"])
    g.atualizado_em = agora()


def _aplicar_descendente(d: Descendente, dados: dict, cifra) -> None:
    d.nome_cifrado = cifra.cifrar(dados["nome"])
    d.data_nascimento_cifrada = cifra.cifrar(dados["nasc"].isoformat())
    d.sexo = dados["sexo"]
    d.atualizado_em = agora()


def _aplicar(p: Paciente, dados: dict, cifra) -> None:
    p.nome_cifrado = cifra.cifrar(dados["nome"])
    p.prontuario_cifrado = cifra.cifrar(dados["prontuario"])
    p.momento = dados["momento"]
    p.observacoes_cifradas = cifra.cifrar(dados["observacoes"])
    for papel in PAPEIS_GENITOR:
        g = p.genitor(papel)
        if g is None:
            g = Genitor(papel=papel, atualizado_em=agora())
            p.genitores.append(g)
        _aplicar_genitor(g, dados["mae" if papel == "MAE" else "pai"], cifra)
    p.atualizado_em = agora()


def _apagar_arquivos_de_analises(config, analises: list[AnalisePaciente]) -> None:
    for a in analises:
        arquivos.apagar(config.dir_analises, a.resultado_arquivo)
        arquivos.apagar(config.dir_analises, a.pacote_arquivo)


def do_medico(bd, usuario: Usuario, paciente_id: int) -> Paciente:
    """Registro do próprio médico; qualquer outro (inclusive de outro médico) devolve 404, sem revelar que existe."""
    p = bd.execute(
        select(Paciente).where(Paciente.id == paciente_id, Paciente.medico_id == usuario.id)
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Registro não encontrado.")
    return p


def descendente_de(p: Paciente, descendente_id: int | None) -> Descendente:
    d = next((d for d in p.descendentes if d.id == descendente_id), None)
    if d is None:
        raise HTTPException(404, "Descendente não encontrado.")
    return d


def idades(p: Paciente, cifra, hoje: _dt.date | None = None) -> dict[int, int]:
    hoje = hoje or agora().date()
    return {
        d.id: idade_em(_dt.date.fromisoformat(cifra.decifrar(d.data_nascimento_cifrada)), hoje) for d in p.descendentes
    }


# ---------------------------------------------------------------------------
# Pesquisa: titulares exigidos e liberação
# ---------------------------------------------------------------------------
def requisitos_pesquisa(p: Paciente, idades_desc: dict[int, int], nomes: dict[int, str] | None = None) -> dict:
    """Situação de cada titular cujo consentimento é exigido para liberar o caso à pesquisa: os dois genitores, cada
    parente testado de um genitor sem exame (o dado genético dele seria exposto) e, fora do caso CASAL, cada descendente
    (ou o responsável legal, se menor de 18)."""
    ativos = {(c.titular, c.descendente_id, c.parente_id) for c in p.consentimentos if c.ativo}
    exigidos = []
    for papel in PAPEIS_GENITOR:
        exigidos.append(
            {
                "titular": papel,
                "descendente_id": None,
                "parente_id": None,
                "rotulo": textos.ROTULO_GENITOR[p.tipo][papel],
            }
        )
    for x in p.parentes:
        exigidos.append(
            {
                "titular": "PARENTE",
                "descendente_id": None,
                "parente_id": x.id,
                "rotulo": f"Parente testado: {textos.rotulo_parente(p.tipo, x.papel_genitor, x.parentesco)}",
            }
        )
    if p.tipo != "CASAL":
        for d in p.descendentes:
            t = "RESPONSAVEL" if idades_desc.get(d.id, 99) < MAIORIDADE else "DESCENDENTE"
            rotulo = ROTULO_TITULAR[t] if p.tipo == "PESSOA" else f"{ROTULO_TITULAR[t]}: filho(a) {d.ordem}"
            if nomes and d.id in nomes:
                rotulo = f"{rotulo} ({nomes[d.id]})" if p.tipo != "PESSOA" else rotulo
            exigidos.append({"titular": t, "descendente_id": d.id, "parente_id": None, "rotulo": rotulo})
    for e in exigidos:
        chave = (e["titular"], e["descendente_id"], e["parente_id"])
        e["consentido"] = chave in ativos or (
            e["titular"] == "DESCENDENTE" and ("RESPONSAVEL", e["descendente_id"], None) in ativos
        )
    return {"exigidos": exigidos, "liberado": bool(exigidos) and all(e["consentido"] for e in exigidos)}


def situacao_pesquisa(p: Paciente, liberado: bool) -> str:
    if liberado:
        return "LIBERADO"
    return "PENDENTE" if any(c.ativo for c in p.consentimentos) else "NAO_INICIADO"


def atualizar_liberacao(bd, p: Paciente, cifra, usuario: Usuario) -> bool:
    """Gera o código pseudonimizado na primeira liberação; registra liberação e retirada na auditoria."""
    liberado = requisitos_pesquisa(p, idades(p, cifra))["liberado"]
    if liberado and p.liberado_pesquisa_em is None:
        if p.codigo_pesquisa is None:
            p.codigo_pesquisa = secrets.token_hex(16)  # aleatório; não deriva de nome, prontuário ou data
        p.liberado_pesquisa_em = agora()
        auditoria.registrar(
            bd, acao=auditoria.CASO_LIBERADO_PESQUISA, usuario=usuario, alvo_tipo="paciente", alvo_id=p.id
        )
    elif not liberado and p.liberado_pesquisa_em is not None:
        p.liberado_pesquisa_em = None
        auditoria.registrar(
            bd, acao=auditoria.CASO_RETIRADO_PESQUISA, usuario=usuario, alvo_tipo="paciente", alvo_id=p.id
        )
    return liberado


# ---------------------------------------------------------------------------
# Serialização
# ---------------------------------------------------------------------------
def consentimento_dict(c: Consentimento, cifra) -> dict:
    return {
        "id": c.id,
        "titular": c.titular,
        "titular_rotulo": ROTULO_TITULAR.get(c.titular, c.titular),
        "descendente_id": c.descendente_id,
        "parente_id": c.parente_id,
        "nome_titular": cifra.decifrar(c.nome_titular_cifrado),
        "finalidade": c.finalidade,
        "versao_termo": c.versao_termo,
        "concedido_em": iso(c.concedido_em),
        "revogado_em": iso(c.revogado_em),
        "ativo": c.ativo,
    }


def documento_dict(d: Documento, cifra) -> dict:
    return {
        "id": d.id,
        "tipo": d.tipo,
        "genitor_id": d.genitor_id,
        "nome": cifra.decifrar(d.nome_original_cifrado),
        "mime": d.mime,
        "tamanho": d.tamanho,
        "enviado_em": iso(d.enviado_em),
    }


def _vcf_dict(x) -> dict:
    """Metadados do VCF anexado a um genitor, parente ou descendente (nunca o conteúdo nem o nome do arquivo)."""
    return {
        "presente": x.vcf_arquivo is not None,
        "tamanho": x.vcf_tamanho,
        "enviado_em": iso(x.vcf_enviado_em),
        "hash_curto": (x.vcf_hash or "")[:12] or None,
    }


def situacao_do_genitor(g: Genitor, cifra) -> dict:
    """Situação clínica do genitor sem exame e a idade correspondente ({"situacao": None, "idade": None} se ausente)."""
    bruto = cifra.decifrar(g.situacao_clinica_cifrada) if g.situacao_clinica_cifrada else None
    try:
        d = json.loads(bruto) if bruto else {}
    except ValueError:
        d = {}
    situacao = d.get("situacao") if d.get("situacao") in SITUACOES_GENITOR else None
    return {"situacao": situacao, "idade": d.get("idade") if situacao else None}


def parente_dict(x: Parente, tipo: str, cifra) -> dict:
    laudo = cifra.decifrar(x.laudo_c9orf72_cifrado)
    return {
        "id": x.id,
        "papel_genitor": x.papel_genitor,
        "parentesco": x.parentesco,
        "rotulo": textos.rotulo_parente(tipo, x.papel_genitor, x.parentesco),
        "laudo_c9orf72": laudo,
        "laudo_informado": bool(laudo),
        "vcf": _vcf_dict(x),
        "criado_em": iso(x.criado_em),
    }


def genitor_dict(
    g: Genitor,
    tipo: str,
    cifra,
    hoje: _dt.date,
    completo: bool,
    documentos: list | None = None,
    parentes: list | None = None,
) -> dict:
    nasc = cifra.decifrar(g.data_nascimento_cifrada)
    laudo = cifra.decifrar(g.laudo_c9orf72_cifrado)
    sit = situacao_do_genitor(g, cifra)
    meus = [parente_dict(x, tipo, cifra) for x in (parentes or [])]
    d = {
        "papel": g.papel,
        "rotulo": textos.ROTULO_GENITOR.get(tipo, textos.ROTULO_GENITOR["PESSOA"])[g.papel],
        "nome": cifra.decifrar(g.nome_cifrado),
        "idade": idade_em(_dt.date.fromisoformat(nasc), hoje),
        "laudo_c9orf72": laudo,
        "laudo_informado": bool(laudo),
        "vcf": _vcf_dict(g),
        # genitor sem exame: situação clínica (condiciona a inferência) e parentes testados dele
        "situacao_clinica": sit["situacao"],
        "situacao_rotulo": textos.SITUACOES_GENITOR.get(sit["situacao"]) if sit["situacao"] else None,
        "idade_situacao": sit["idade"],
        "parentes": meus,
        "inferido_por_parentes": (not g.tem_vcf) and any(x["vcf"]["presente"] for x in meus),
        # C9orf72: sem laudo próprio, o genitor é inferido se algum parente dele tem laudo; senão fica indeterminado
        "c9orf72_por_parentes": [x["rotulo"] for x in meus if x["laudo_informado"]] if not laudo else [],
        "laudo_documento": next(
            (
                documento_dict(x, cifra)
                for x in (documentos or [])
                if x.tipo == "LAUDO_C9ORF72" and x.genitor_id == g.id
            ),
            None,
        ),
    }
    if completo:
        d["data_nascimento"] = nasc
    return d


def analise_dict(a: AnalisePaciente, cifra) -> dict:
    """Resumo completo de uma análise guardada (só o médico dono vê; o pesquisador recebe uma versão sem ids)."""
    return {
        "id": a.id,
        "descendente_id": a.descendente_id,
        "executado_em": iso(a.executado_em),
        "modo": a.modo,
        "n": a.n,
        "semente": a.semente,
        "motor": a.motor,
        "hipoteses": a.hipoteses,
        "cox": a.cox,
        "sexo": a.sexo,
        "idade_na_analise": a.idade_na_analise,
        "assintomatico_confirmado": a.assintomatico_confirmado,
        "assintomatico_confirmado_em": iso(a.assintomatico_confirmado_em),
        "suposicoes": json.loads(a.suposicoes) if a.suposicoes else {},
        "tem_resultado": bool(a.resultado_arquivo),
        "resumo": json.loads(cifra.decifrar(a.resumo_cifrado)),
    }


def _desde_o_nascimento_pela_curva(r: dict) -> dict:
    """F(50), F(60), F(70) e os quartis da idade de início desde o nascimento, lidos da curva guardada no resumo. Nas
    análises condicionadas o resumo só traz os valores a partir da idade de referência; a curva F(t) cobre os dois."""
    c = r.get("curva") or {}
    t, F = c.get("t") or [], c.get("F") or []
    acumulado = {}
    for alvo in (50, 60, 70):
        idx = next((i for i, x in enumerate(t) if x is not None and abs(x - alvo) < 1e-6), None)
        acumulado[str(alvo)] = F[idx] if idx is not None else None
    return {
        "F": acumulado,
        "q25": quantil_inicio(t, F, 0.25) if t else None,
        "q75": quantil_inicio(t, F, 0.75) if t else None,
    }


def analise_compacta(a: dict) -> dict:
    """O essencial de uma análise para listas, comparativos e filtros: as três respostas do artefato. Quando a
    análise tem idade de referência, os três valores são os condicionados (pessoa sem sintomas a partir dessa idade).

    O risco aparece em campos próprios, para nenhum rótulo misturar as duas coisas: `risco_vitalicio` é sempre o
    risco desde o nascimento até o horizonte, e `risco_residual` é o risco da idade de referência até o horizonte,
    só nas análises condicionadas. `p_manifesta` é a resposta 2 da pessoa: o residual quando há, senão o vitalício."""
    r = a["resumo"]
    comb = r.get("combinado") or {}
    vida = r.get("vida") or {}  # ausente em resumos antigos: cai no valor desde o nascimento
    condicionado = bool(r.get("condicionado"))
    inicio = r.get("inicio") or {}
    sem_locus = r.get("sem_locus", True)
    nascimento = _desde_o_nascimento_pela_curva(r)

    def desde_o_nascimento(chave):  # resumo sem lócus de risco: risco zero, não ausente
        v = comb.get(chave)
        return 0.0 if v is None and sem_locus else v

    return {
        "id": a["id"],
        "descendente_id": a["descendente_id"],
        "executado_em": a["executado_em"],
        "modo": a["modo"],
        "n": a["n"],
        "motor": a["motor"],
        "hipoteses": a["hipoteses"],
        "sexo": a["sexo"],
        "idade_na_analise": a["idade_na_analise"],
        "assintomatico_confirmado": a.get("assintomatico_confirmado"),
        "suposicoes": a["suposicoes"],
        "com_suposicao": bool(a["suposicoes"]),
        "tem_resultado": a.get("tem_resultado", False),
        "sem_locus": r.get("sem_locus", True),
        "genes_de_risco": r.get("genes_de_risco", []),
        # C9orf72 fora do cálculo por falta do nº de repetições de um genitor: o resultado é parcial para o gene
        "c9orf72_indeterminado": bool(r.get("c9orf72_indeterminado")),
        "condicionado": condicionado,
        "idade_referencia": r.get("idade_referencia") if condicionado else None,
        "p_portador": r["transmissao"] if r.get("transmissao") is not None else comb.get("p_portador_qualquer_exato"),
        "p_manifesta": vida.get("valor", comb.get("p_manifesta_qualquer_exato")),
        "q025": vida.get("q025", comb.get("p_manifesta_qualquer_q025")),
        "q975": vida.get("q975", comb.get("p_manifesta_qualquer_q975")),
        "risco_vitalicio": desde_o_nascimento("p_manifesta_qualquer_exato"),
        "risco_vitalicio_q025": desde_o_nascimento("p_manifesta_qualquer_q025"),
        "risco_vitalicio_q975": desde_o_nascimento("p_manifesta_qualquer_q975"),
        "risco_residual": vida.get("valor") if condicionado else None,
        "risco_residual_q025": vida.get("q025") if condicionado else None,
        "risco_residual_q975": vida.get("q975") if condicionado else None,
        "p_portador_desde_nascimento": desde_o_nascimento("p_portador_qualquer_exato"),
        "inicio_mediana_desde_nascimento": comb.get("idade_mediana_primeiro_inicio"),
        "inicio_q25_desde_nascimento": nascimento["q25"],
        "inicio_q75_desde_nascimento": nascimento["q75"],
        "F_desde_nascimento": nascimento["F"],
        "idade_mediana": inicio.get("mediana") if condicionado else comb.get("idade_mediana_primeiro_inicio"),
        "inicio": inicio,
        "janelas": r.get("janelas") or {},
        "F": r.get("F") or {},
    }


def tem_locus_de_risco(lido, tabela, parametros) -> bool:
    """O VCF já lido traz ao menos um lócus de risco (classe risco, dosagem ≥ 1)? Mesma conta da análise: anotação
    pela tabela dada e `parentes.dosagens_do_vcf` (a expansão do C9orf72 não é lida do VCF)."""
    anotadas = anotacao.anotar(lido, tabela, parametros.limiar_repeticoes)
    return any((d.get("dosagem") or 0) >= 1 for d in parentes_mod.dosagens_do_vcf(anotadas, parametros).values())


def filho_testado_com_locus_de_risco(config, cifra, p: Paciente) -> bool:
    """Algum filho já testado do registro tem lócus de risco? É o que permite inferir o genitor sem exame só pelo
    filho; o filho sem variante de risco é evidência, mas não basta sozinho.

    Calculado na hora, com a base de anotação em uso (a mesma que a análise usa por padrão), para a ficha nunca
    mostrar uma classificação antiga depois de uma troca de base. O VCF é decifrado e lido só em memória: nada é
    gravado, nenhum arquivo é entregue e a leitura não gera registro de auditoria. VCF que não abre não infere
    nada; a análise relata o erro."""
    filhos = [d for d in p.descendentes if d.tem_vcf]
    if not filhos or config is None:
        return False
    parametros = carregar_parametros()
    base = anotacao.localizar_base_real(config.dir_bases)
    tabela = anotacao.tabela_anotacao(base_real=base if base is not None else False)
    regioes = ingestao.carregar_regioes()
    for d in filhos:
        try:
            texto = vcfs.texto_em_memoria(config, cifra, d)
            lido = ingestao.ler_vcf(f"filho_{d.id}.vcf", regioes, parametros.filtro_qualidade, conteudo=texto)
        except Exception:  # noqa: BLE001
            continue
        if tem_locus_de_risco(lido, tabela, parametros):
            return True
    return False


def paciente_dict(p: Paciente, cifra, resumo: bool = False, config=None) -> dict:
    hoje = agora().date()
    idades_desc = idades(p, cifra, hoje)
    analises = [analise_dict(a, cifra) for a in p.analises]
    ultimas: dict[int | None, dict] = {}
    for a in analises:  # ordenadas por id: a última de cada descendente (None = futuro filho do casal) prevalece
        ultimas[a["descendente_id"]] = analise_compacta(a)
    ultima = analise_compacta(analises[-1]) if analises else None
    descendentes = []
    nomes = {}
    for d in p.descendentes:
        nome = cifra.decifrar(d.nome_cifrado)
        nomes[d.id] = nome
        item = {
            "id": d.id,
            "ordem": d.ordem,
            "nome": nome,
            "idade": idades_desc[d.id],
            "menor_de_idade": idades_desc[d.id] < MAIORIDADE,
            "sexo": d.sexo,
            "ultima_analise": ultimas.get(d.id),
            "n_analises": sum(1 for a in analises if a["descendente_id"] == d.id),
            # filho que já fez o teste (caso de família): evidência sobre o genitor sem exame, não pessoa em risco
            "vcf": _vcf_dict(d),
            "testado": d.tem_vcf,
        }
        if not resumo:
            item["data_nascimento"] = cifra.decifrar(d.data_nascimento_cifrada)
        descendentes.append(item)
    genitores = {
        g.papel: genitor_dict(
            g, p.tipo, cifra, hoje, completo=not resumo, documentos=p.documentos, parentes=p.parentes_de(g.papel)
        )
        for g in p.genitores
    }
    # um filho já testado também permite inferir o genitor sem exame, mas só quando traz ao menos um lócus de risco;
    # a leitura do VCF do filho acontece apenas se algum genitor depender dela
    sem_dado = [g for g in genitores.values() if not g["vcf"]["presente"] and not g["inferido_por_parentes"]]
    if sem_dado and filho_testado_com_locus_de_risco(config, cifra, p):
        for g in sem_dado:
            g["inferido_por_parentes"] = True
    for papel, g in genitores.items():  # sem exame: a ficha já diz o que a análise vai exigir, com o mesmo texto
        g["sem_exame"] = not g["vcf"]["presente"] and not g["inferido_por_parentes"]
        g["falta_exame"] = (
            textos.GENITOR_SEM_VCF.format(rotulo=textos.ROTULO_GENITOR[p.tipo][papel]) if g["sem_exame"] else None
        )
    prontuario_doc = next((documento_dict(x, cifra) for x in p.documentos if x.tipo == "PRONTUARIO"), None)
    requisitos = requisitos_pesquisa(p, idades_desc, nomes)
    genes = sorted({g for a in ultimas.values() for g in a["genes_de_risco"]})
    # o maior risco vitalício entre as pessoas do registro: uma só grandeza (desde o nascimento), comparável entre
    # pessoas de idades diferentes; o valor a partir da idade de cada uma fica na análise dela
    riscos = [a["risco_vitalicio"] for a in ultimas.values() if a["risco_vitalicio"] is not None]
    tipo = textos.TIPOS_ATENDIMENTO[p.tipo]
    d = {
        "id": p.id,
        "tipo": p.tipo,
        "tipo_rotulo": tipo["rotulo"],
        "tipo_curto": tipo["curto"],
        "tipo_numero": tipo["numero"],
        "nome": cifra.decifrar(p.nome_cifrado),
        "prontuario": cifra.decifrar(p.prontuario_cifrado),
        "prontuario_documento": prontuario_doc,
        "momento": p.momento,
        "momento_rotulo": textos.MOMENTOS.get(p.momento) if p.momento else None,
        "genitores": genitores,
        "descendentes": descendentes,
        "vcfs_presentes": sum(1 for g in p.genitores if g.tem_vcf),
        "vcfs_completos": all(g.tem_vcf for g in p.genitores) and len(p.genitores) == 2,
        "genitores_inferidos": [k for k, g in genitores.items() if g["inferido_por_parentes"]],
        "n_parentes": len(p.parentes),
        # a análise precisa de ao menos um genitor com VCF ou inferível por parentes (o outro pode ser assumido)
        "pode_analisar": any(g["vcf"]["presente"] or g["inferido_por_parentes"] for g in genitores.values()),
        "laudo_informado": any(g["laudo_informado"] for g in genitores.values()),
        "liberado_para_pesquisa": p.liberado_pesquisa_em is not None,
        "pesquisa_situacao": situacao_pesquisa(p, p.liberado_pesquisa_em is not None),
        "n_consentimentos_ativos": sum(1 for c in p.consentimentos if c.ativo),
        "ultima_analise": ultima,
        "ultimas_por_descendente": ultimas if not resumo else None,
        "n_analises": len(analises),
        "genes_de_risco": genes,
        "risco_vitalicio_maximo": max(riscos) if riscos else None,
        "com_suposicao": any(a["com_suposicao"] for a in ultimas.values()),
        "criado_em": iso(p.criado_em),
        "atualizado_em": iso(p.atualizado_em),
    }
    if resumo:
        d.pop("ultimas_por_descendente")
        return d
    d.update(
        {
            "observacoes": cifra.decifrar(p.observacoes_cifradas),
            "base_legal": p.base_legal,
            "linha_risco": textos.LINHA_RISCO[p.tipo],
            "liberado_pesquisa_em": iso(p.liberado_pesquisa_em),
            "pesquisa": requisitos,
            "consentimentos": [consentimento_dict(c, cifra) for c in p.consentimentos],
            "termo_consentimento": textos.TERMO_CONSENTIMENTO_PESQUISA,
            "analises": analises,
            "documentos": [documento_dict(x, cifra) for x in p.documentos],
            "comparativo": [
                {**ultimas[k], "descendente_nome": nomes.get(k, "Futuro filho")}
                for k in sorted(ultimas, key=lambda x: (x is None, x))
            ],
        }
    )
    return d


# ---------------------------------------------------------------------------
# Filtros (função pura, testável sem servidor)
# ---------------------------------------------------------------------------
def _dia(valor: str | None) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _data_iso(valor: str | None) -> _dt.date | None:
    return _dt.date.fromisoformat(valor[:10]) if valor else None


def filtrar_pacientes(itens: list[dict], f: dict) -> list[dict]:
    """Aplica os filtros de `Busca` a uma lista de `paciente_dict(resumo=True)` já decifrada."""
    termo = normalizar_texto(f.get("texto") or "")
    genes = {g.upper() for g in (f.get("genes") or []) if g}
    an_de, an_ate = _dia(f.get("analise_de")), _dia(f.get("analise_ate"))
    cad_de, cad_ate = _dia(f.get("cadastro_de")), _dia(f.get("cadastro_ate"))
    res = []
    for d in itens:
        if termo:
            alvo = [d["nome"], d["prontuario"]] + [x["nome"] for x in d["descendentes"]]
            alvo += [g["nome"] for g in d["genitores"].values()]
            if not any(termo in normalizar_texto(x) for x in alvo if x):
                continue
        if f.get("tipo") and d["tipo"] != f["tipo"]:
            continue
        if f.get("momento") and d["momento"] != f["momento"]:
            continue
        descs = d["descendentes"]
        if f.get("sexo") and not any(x["sexo"] == f["sexo"].upper() for x in descs):
            continue
        if f.get("idade_min") is not None and not any(x["idade"] >= f["idade_min"] for x in descs):
            continue
        if f.get("idade_max") is not None and not any(x["idade"] <= f["idade_max"] for x in descs):
            continue
        if f.get("menor_de_idade") is not None:
            tem_menor = any(x["menor_de_idade"] for x in descs)
            if tem_menor != f["menor_de_idade"]:
                continue
        if f.get("pesquisa") and d["pesquisa_situacao"] != f["pesquisa"]:
            continue
        if f.get("vcfs") == "COMPLETOS" and not d["vcfs_completos"]:
            continue
        if f.get("vcfs") == "INCOMPLETOS" and d["vcfs_completos"]:
            continue
        if genes and not genes & {g.upper() for g in d["genes_de_risco"]}:
            continue
        if f.get("analise") == "COM" and d["n_analises"] == 0:
            continue
        if f.get("analise") == "SEM" and d["n_analises"] > 0:
            continue
        if f.get("risco_min") is not None and (
            d["risco_vitalicio_maximo"] is None or d["risco_vitalicio_maximo"] < f["risco_min"]
        ):
            continue
        if f.get("laudo_c9orf72") is not None and d["laudo_informado"] != f["laudo_c9orf72"]:
            continue
        if f.get("suposicao") is not None and d["com_suposicao"] != f["suposicao"]:
            continue
        ultima = _data_iso(d["ultima_analise"]["executado_em"]) if d["ultima_analise"] else None
        if an_de and (ultima is None or ultima < an_de):
            continue
        if an_ate and (ultima is None or ultima > an_ate):
            continue
        cadastro = _data_iso(d["criado_em"])
        if cad_de and cadastro < cad_de:
            continue
        if cad_ate and cadastro > cad_ate:
            continue
        res.append(d)
    chave = f.get("ordenar") or "nome"
    inverso = (f.get("direcao") or "asc") == "desc"

    def k(d):
        if chave == "idade":
            v = min((x["idade"] for x in d["descendentes"]), default=None)
        elif chave == "ultima_analise":
            v = d["ultima_analise"]["executado_em"] if d["ultima_analise"] else None
        elif chave == "risco":
            v = d["risco_vitalicio_maximo"]
        elif chave == "cadastro":
            v = d["criado_em"]
        else:
            v = normalizar_texto(d["nome"])
        return (v is None, v if v is not None else 0)

    res.sort(key=k, reverse=inverso)
    if inverso:  # valores ausentes ficam sempre no fim
        res.sort(key=lambda d: k(d)[0])
    return res


def genes_do_modelo() -> list[str]:
    try:
        from ..calibracao import carregar_parametros

        return [g.nome for g in carregar_parametros().genes.values()]
    except Exception:  # noqa: BLE001
        return list(GENES_PADRAO)


# ---------------------------------------------------------------------------
# Rotas: lista, opções, criação, busca
# ---------------------------------------------------------------------------
def _lista_do_medico(bd, cifra, usuario: Usuario, config=None) -> list[dict]:
    pacientes = bd.execute(select(Paciente).where(Paciente.medico_id == usuario.id).order_by(Paciente.id)).scalars()
    return [paciente_dict(p, cifra, resumo=True, config=config) for p in pacientes]


@router.get("")
def listar(request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))):
    bd, cifra = obter_bd(request), obter_cifra(request)
    itens = filtrar_pacientes(_lista_do_medico(bd, cifra, usuario, obter_config(request)), {})
    return {"total": len(itens), "pacientes": itens, "base_legal": BASE_LEGAL_ATENDIMENTO}


def _analises_do_medico(pacientes: list[Paciente], itens: list[dict], cifra) -> list[dict]:
    """Todas as análises do médico, uma linha por execução, com o nome do registro e da pessoa (só o médico dono vê)."""
    nomes = {d["id"]: d["nome"] for d in itens}
    por_id = {d["id"]: d for d in itens}
    analises = []
    for p in pacientes:
        desc = {d.id: cifra.decifrar(d.nome_cifrado) for d in p.descendentes}
        for a in p.analises:
            c = analise_compacta(analise_dict(a, cifra))
            analises.append(
                {
                    "id": c["id"],
                    "paciente_id": p.id,
                    "descendente_id": a.descendente_id,
                    "registro": nomes[p.id],
                    "prontuario": por_id[p.id]["prontuario"],
                    "tipo": p.tipo,
                    "tipo_curto": por_id[p.id]["tipo_curto"],
                    "pessoa": (
                        desc.get(a.descendente_id, "Futuro filho") if a.descendente_id is not None else "Futuro filho"
                    ),
                    "sexo": c["sexo"],
                    "idade_na_analise": c["idade_na_analise"],
                    "condicionado": c["condicionado"],
                    "idade_referencia": c["idade_referencia"],
                    "executado_em": c["executado_em"],
                    "modo": c["modo"],
                    "motor": c["motor"],
                    "n": c["n"],
                    "hipoteses": c["hipoteses"],
                    "genes_de_risco": c["genes_de_risco"],
                    "sem_locus": c["sem_locus"],
                    "c9orf72_indeterminado": c["c9orf72_indeterminado"],
                    "p_portador": c["p_portador"],
                    "p_manifesta": c["p_manifesta"],
                    "q025": c["q025"],
                    "q975": c["q975"],
                    "risco_vitalicio": c["risco_vitalicio"],
                    "risco_residual": c["risco_residual"],
                    "idade_mediana": c["idade_mediana"],
                    "com_suposicao": c["com_suposicao"],
                    "tem_resultado": c["tem_resultado"],
                }
            )
    analises.sort(key=lambda a: (a["executado_em"] or "", a["id"]), reverse=True)
    return analises


@router.get("/analises")
def listar_analises(request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))):
    """Seção "Análises" do médico: todas as execuções já feitas, com acesso ao resultado guardado."""
    bd, cifra = obter_bd(request), obter_cifra(request)
    pacientes = list(bd.execute(select(Paciente).where(Paciente.medico_id == usuario.id)).scalars())
    itens = [paciente_dict(p, cifra, resumo=True, config=obter_config(request)) for p in pacientes]
    analises = _analises_do_medico(pacientes, itens, cifra)
    registros = sorted(
        (
            {
                "id": d["id"],
                "nome": d["nome"],
                "tipo": d["tipo"],
                "tipo_curto": d["tipo_curto"],
                "prontuario": d["prontuario"],
                "vcfs_presentes": d["vcfs_presentes"],
                "descendentes": [{"id": x["id"], "nome": x["nome"]} for x in d["descendentes"]],
            }
            for d in itens
        ),
        key=lambda d: normalizar_texto(d["nome"]),
    )
    return {"total": len(analises), "analises": analises, "registros": registros}


@router.get("/painel")
def painel(request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))):
    """Visão geral do médico para a tela inicial: totais, pendências, registros e análises recentes (só os próprios)."""
    bd, cifra = obter_bd(request), obter_cifra(request)
    pacientes = list(bd.execute(select(Paciente).where(Paciente.medico_id == usuario.id)).scalars())
    itens = [paciente_dict(p, cifra, resumo=True, config=obter_config(request)) for p in pacientes]
    por_tipo = {t: sum(1 for d in itens if d["tipo"] == t) for t in TIPOS_ATENDIMENTO}
    analises = _analises_do_medico(pacientes, itens, cifra)
    recentes = sorted(itens, key=lambda d: d["atualizado_em"] or "", reverse=True)
    return {
        "totais": {
            "registros": len(itens),
            "por_tipo": por_tipo,
            "analises": len(analises),
            "com_analise": sum(1 for d in itens if d["n_analises"] > 0),
            "sem_analise": sum(1 for d in itens if d["n_analises"] == 0),
            "vcfs_incompletos": sum(1 for d in itens if not d["vcfs_completos"]),
            "liberados_pesquisa": sum(1 for d in itens if d["liberado_para_pesquisa"]),
            "consentimentos_pendentes": sum(1 for d in itens if d["pesquisa_situacao"] == "PENDENTE"),
            "com_suposicao": sum(1 for d in itens if d["com_suposicao"]),
        },
        "recentes": recentes[:6],
        "analises_recentes": analises[:6],
        "pendencias": {
            "sem_vcf": [
                {"id": d["id"], "nome": d["nome"], "vcfs_presentes": d["vcfs_presentes"]}
                for d in itens
                if not d["vcfs_completos"]
            ][:6],
            "sem_analise": [
                {"id": d["id"], "nome": d["nome"], "tipo_curto": d["tipo_curto"]}
                for d in itens
                if d["n_analises"] == 0 and d["vcfs_presentes"] > 0
            ][:6],
        },
    }


@router.get("/opcoes")
def opcoes(usuario: Usuario = Depends(exigir(PACIENTES_GERIR))):
    """Valores e rótulos para o formulário e o painel de filtros (nada pessoal)."""
    return {
        "tipos": [{"valor": k, **v} for k, v in textos.TIPOS_ATENDIMENTO.items()],
        "momentos": [{"valor": k, "rotulo": v} for k, v in textos.MOMENTOS.items()],
        "genes": genes_do_modelo(),
        "pesquisa": [{"valor": k, "rotulo": v} for k, v in SITUACOES_PESQUISA.items()],
        "ordenacoes": [{"valor": k, "rotulo": v} for k, v in ORDENACOES.items()],
        "rotulos_genitor": textos.ROTULO_GENITOR,
        "suposicao_nao_portador": textos.SUPOSICAO_NAO_PORTADOR,
        "suposicao_laudo_sem_vcf": textos.SUPOSICAO_LAUDO_SEM_VCF,
        "situacoes_genitor": [{"valor": k, "rotulo": v} for k, v in textos.SITUACOES_GENITOR.items()],
        "parentescos": [{"valor": k, "rotulo": v} for k, v in textos.PARENTESCOS.items()],
        "inferencia_por_parentes": textos.INFERENCIA_POR_PARENTES,
        "aviso_parceiro_inferido": textos.AVISO_PARCEIRO_INFERIDO,
        "confirmacao_assintomatico": textos.CONFIRMACAO_ASSINTOMATICO,
    }


@router.post("", status_code=201)
def criar(entrada: PacienteEntrada, request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))):
    bd, cifra = obter_bd(request), obter_cifra(request)
    tipo = (entrada.tipo or "").upper()
    campos, dados = _validar(entrada, tipo, agora().date())
    exigir_campos(campos)
    p = Paciente(
        medico_id=usuario.id, tipo=tipo, criado_em=agora(), atualizado_em=agora(), base_legal=BASE_LEGAL_ATENDIMENTO
    )
    _aplicar(p, dados, cifra)
    for i, dd in enumerate(dados["descendentes"], start=1):
        d = Descendente(ordem=i, atualizado_em=agora())
        _aplicar_descendente(d, dd, cifra)
        p.descendentes.append(d)
    bd.add(p)
    bd.flush()
    auditoria.registrar(
        bd,
        acao=auditoria.PACIENTE_CRIADO,
        usuario=usuario,
        alvo_tipo="paciente",
        alvo_id=p.id,
        detalhe=f"tipo={tipo}; descendentes={len(p.descendentes)}",
    )
    bd.commit()
    bd.refresh(p)
    return paciente_dict(p, cifra, config=obter_config(request))


@router.post("/busca")
def buscar(entrada: Busca, request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))):
    """Busca e filtros: a lista do próprio médico é decifrada em memória e filtrada (campos cifrados não são
    pesquisáveis no banco; os filtros vão no corpo, nunca na URL)."""
    bd, cifra = obter_bd(request), obter_cifra(request)
    f = entrada.model_dump()
    campos = {}
    if f["ordenar"] not in ORDENACOES:
        campos["ordenar"] = "Ordenação desconhecida."
    if f["direcao"] not in ("asc", "desc"):
        campos["direcao"] = "Use asc ou desc."
    if f["tipo"] and f["tipo"].upper() not in TIPOS_ATENDIMENTO:
        campos["tipo"] = "Tipo desconhecido."
    if f["pesquisa"] and f["pesquisa"].upper() not in SITUACOES_PESQUISA:
        campos["pesquisa"] = "Situação de pesquisa desconhecida."
    if f["vcfs"] and f["vcfs"].upper() not in ("COMPLETOS", "INCOMPLETOS"):
        campos["vcfs"] = "Use COMPLETOS ou INCOMPLETOS."
    if f["analise"] and f["analise"].upper() not in ("COM", "SEM"):
        campos["analise"] = "Use COM ou SEM."
    for k in ("analise_de", "analise_ate", "cadastro_de", "cadastro_ate"):
        if f[k] and _dia(f[k]) is None:
            campos[k] = "Data inválida (use AAAA-MM-DD)."
    exigir_campos(campos)
    for k in ("tipo", "pesquisa", "vcfs", "analise", "momento", "sexo"):
        if f[k]:
            f[k] = f[k].upper()
    achados = filtrar_pacientes(_lista_do_medico(bd, cifra, usuario, obter_config(request)), f)
    ativos = {k: v for k, v in f.items() if v not in (None, "", [], "nome", "asc")}
    return {"total": len(achados), "pacientes": achados, "filtros": ativos}


# ---------------------------------------------------------------------------
# Rotas: um registro
# ---------------------------------------------------------------------------
@router.get("/{paciente_id}")
def ver(paciente_id: int, request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))):
    bd, cifra = obter_bd(request), obter_cifra(request)
    p = do_medico(bd, usuario, paciente_id)
    auditoria.registrar(bd, acao=auditoria.PACIENTE_VISUALIZADO, usuario=usuario, alvo_tipo="paciente", alvo_id=p.id)
    bd.commit()
    return paciente_dict(p, cifra, config=obter_config(request))


@router.put("/{paciente_id}")
def editar(
    paciente_id: int, entrada: PacienteEntrada, request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))
):
    """Edita registro e genitores; o tipo não muda e os descendentes têm rotas próprias."""
    bd, cifra = obter_bd(request), obter_cifra(request)
    p = do_medico(bd, usuario, paciente_id)
    if not texto_curto(entrada.nome, 200) and p.tipo == "PESSOA" and p.descendentes:
        entrada.nome = cifra.decifrar(p.descendentes[0].nome_cifrado)
    campos, dados = _validar(entrada, p.tipo, agora().date(), com_descendentes=False)
    exigir_campos(campos)
    _aplicar(p, dados, cifra)
    atualizar_liberacao(bd, p, cifra, usuario)
    auditoria.registrar(bd, acao=auditoria.PACIENTE_EDITADO, usuario=usuario, alvo_tipo="paciente", alvo_id=p.id)
    bd.commit()
    return paciente_dict(p, cifra, config=obter_config(request))


@router.delete("/{paciente_id}")
def excluir(
    paciente_id: int,
    request: Request,
    entrada: ConfirmacaoExclusao = Body(...),
    usuario: Usuario = Depends(exigir(PACIENTES_GERIR)),
):
    """Eliminação (art. 16 e 18, VI): remove identificadores, genitores, VCFs, resumos de análise e consentimentos; a
    auditoria guarda só o id."""
    bd, cifra, config = obter_bd(request), obter_cifra(request), obter_config(request)
    p = do_medico(bd, usuario, paciente_id)
    nome = cifra.decifrar(p.nome_cifrado)
    if normalizar_texto(entrada.confirmacao_nome) != normalizar_texto(nome):
        exigir_campos({"confirmacao_nome": "Digite o nome do registro exatamente como está na ficha."})
    n_cons, n_an, n_desc = len(p.consentimentos), len(p.analises), len(p.descendentes)
    n_vcf = vcfs.remover_todos(config, list(p.genitores) + list(p.parentes) + list(p.descendentes))
    _apagar_arquivos_de_analises(config, p.analises)
    for d in p.documentos:
        arquivos.apagar(config.dir_documentos, d.arquivo)
    bd.delete(p)  # cascade apaga genitores, descendentes, documentos, consentimentos e resumos
    auditoria.registrar(
        bd,
        acao=auditoria.PACIENTE_EXCLUIDO,
        usuario=usuario,
        alvo_tipo="paciente",
        alvo_id=paciente_id,
        detalhe=f"{n_desc} descendente(s), {n_vcf} VCF(s), {n_an} resumo(s) e {n_cons} consentimento(s) removidos",
    )
    bd.commit()
    return {
        "mensagem": (
            "Registro excluído: identificadores, VCFs, resumos de análise e consentimentos removidos. "
            "A auditoria permanece, sem dado identificável."
        )
    }


@router.post("/{paciente_id}/exportar")
def exportar(paciente_id: int, request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))):
    """Acesso e portabilidade (art. 18, II e V): dados cadastrais, consentimentos e resumos, em JSON (sem os VCFs)."""
    bd, cifra = obter_bd(request), obter_cifra(request)
    p = do_medico(bd, usuario, paciente_id)
    dados = paciente_dict(p, cifra, config=obter_config(request))
    dados.pop("termo_consentimento", None)
    auditoria.registrar(bd, acao=auditoria.PACIENTE_EXPORTADO, usuario=usuario, alvo_tipo="paciente", alvo_id=p.id)
    bd.commit()
    return {
        "exportado_em": iso(agora()),
        "exportado_por": {"id": usuario.id, "nome": usuario.nome},
        "finalidade": "Direito de acesso e portabilidade dos titulares (LGPD, art. 18, II e V), por intermédio do médico.",
        "paciente": dados,
    }


# ---------------------------------------------------------------------------
# Rotas: genitores (dados e VCF)
# ---------------------------------------------------------------------------
def _genitor(p: Paciente, papel: str) -> Genitor:
    papel = papel.upper()
    g = p.genitor(papel) if papel in PAPEIS_GENITOR else None
    if g is None:
        raise HTTPException(404, "Genitor não encontrado.")
    return g


@router.put("/{paciente_id}/genitores/{papel}")
def editar_genitor(
    paciente_id: int,
    papel: str,
    entrada: GenitorEntrada,
    request: Request,
    usuario: Usuario = Depends(exigir(PACIENTES_GERIR)),
):
    bd, cifra = obter_bd(request), obter_cifra(request)
    p = do_medico(bd, usuario, paciente_id)
    g = _genitor(p, papel)
    campos: dict[str, str] = {}
    dados = _validar_genitor(entrada, papel.lower(), campos, agora().date())
    exigir_campos(campos)
    _aplicar_genitor(g, dados, cifra)
    p.atualizado_em = agora()
    auditoria.registrar(
        bd,
        acao=auditoria.PACIENTE_EDITADO,
        usuario=usuario,
        alvo_tipo="paciente",
        alvo_id=p.id,
        detalhe=f"genitor {g.papel}",
    )
    bd.commit()
    return paciente_dict(p, cifra, config=obter_config(request))


@router.post("/{paciente_id}/genitores/{papel}/vcf", status_code=201)
def anexar_vcf(
    paciente_id: int,
    papel: str,
    request: Request,
    vcf: UploadFile | None = File(None),
    usuario: Usuario = Depends(exigir(PACIENTES_GERIR)),
):
    """Anexa (ou substitui) o VCF do genitor: validado pela ingestão do artefato e guardado cifrado, sem o nome original."""
    bd, cifra, config = obter_bd(request), obter_cifra(request), obter_config(request)
    p = do_medico(bd, usuario, paciente_id)
    g = _genitor(p, papel)
    campos: dict[str, str] = {}
    tmp = vcfs.pasta_temporaria(config)
    try:
        caminho = vcfs.guardar_upload(vcf, tmp / "envio.vcf", "vcf", campos, config.tamanho_maximo_vcf)
        exigir_campos(campos)
        erro = vcfs.validar(caminho)
        if erro:
            exigir_campos({"vcf": erro})
        substituiu = g.tem_vcf
        vcfs.anexar(config, cifra, g, caminho)
    finally:
        vcfs.apagar_pasta(tmp)
    p.atualizado_em = agora()
    auditoria.registrar(
        bd,
        acao=auditoria.VCF_ANEXADO,
        usuario=usuario,
        alvo_tipo="paciente",
        alvo_id=p.id,
        detalhe=f"genitor {g.papel}; {g.vcf_tamanho} bytes; substituiu={'sim' if substituiu else 'não'}",
    )
    bd.commit()
    return paciente_dict(p, cifra, config=obter_config(request))


@router.delete("/{paciente_id}/genitores/{papel}/vcf")
def remover_vcf(paciente_id: int, papel: str, request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))):
    bd, cifra, config = obter_bd(request), obter_cifra(request), obter_config(request)
    p = do_medico(bd, usuario, paciente_id)
    g = _genitor(p, papel)
    if not g.tem_vcf:
        raise HTTPException(404, "Este genitor não tem VCF anexado.")
    vcfs.remover(config, g)
    g.atualizado_em = agora()
    p.atualizado_em = agora()
    auditoria.registrar(
        bd,
        acao=auditoria.VCF_REMOVIDO,
        usuario=usuario,
        alvo_tipo="paciente",
        alvo_id=p.id,
        detalhe=f"genitor {g.papel}",
    )
    bd.commit()
    return paciente_dict(p, cifra, config=obter_config(request))


# ---------------------------------------------------------------------------
# Rotas: genitor sem exame (situação clínica), parentes testados e VCF de filho já testado
# ---------------------------------------------------------------------------
@router.put("/{paciente_id}/genitores/{papel}/situacao")
def definir_situacao_genitor(
    paciente_id: int,
    papel: str,
    entrada: SituacaoGenitorEntrada,
    request: Request,
    usuario: Usuario = Depends(exigir(PACIENTES_GERIR)),
):
    """Situação clínica do genitor que não pôde ser testado e a idade correspondente: condicionam a inferência da
    dosagem dele pelos parentes. Dado de saúde, guardado cifrado; a auditoria registra só que mudou."""
    bd, cifra = obter_bd(request), obter_cifra(request)
    p = do_medico(bd, usuario, paciente_id)
    g = _genitor(p, papel)
    campos: dict[str, str] = {}
    situacao = (entrada.situacao or "").strip().upper() or None
    if situacao == "DESCONHECIDO":
        situacao = "DESCONHECIDA"
    if situacao is not None and situacao not in SITUACOES_GENITOR:
        campos["situacao"] = "Situação clínica desconhecida."
    idade = entrada.idade
    if situacao == "VIVO_ASSINTOMATICO" and idade is None:  # vivo: a idade atual vem da data de nascimento
        idade = idade_em(_dt.date.fromisoformat(cifra.decifrar(g.data_nascimento_cifrada)), agora().date())
    if situacao == "FALECIDO_SEM_ELA" and idade is None:
        campos["idade"] = "Informe a idade ao falecer."
    exigir_campos(campos)
    if situacao is None:
        g.situacao_clinica_cifrada = None
    else:
        sem_idade = situacao in ("AFETADO", "DESCONHECIDA")
        g.situacao_clinica_cifrada = cifra.cifrar(
            json.dumps({"situacao": situacao, "idade": None if sem_idade else int(idade)})
        )
    g.atualizado_em = agora()
    p.atualizado_em = agora()
    auditoria.registrar(
        bd,
        acao=auditoria.PACIENTE_EDITADO,
        usuario=usuario,
        alvo_tipo="paciente",
        alvo_id=p.id,
        detalhe=f"situação clínica do genitor {g.papel} {'definida' if situacao else 'removida'}",
    )
    bd.commit()
    return paciente_dict(p, cifra, config=obter_config(request))


@router.post("/{paciente_id}/genitores/{papel}/parentes", status_code=201)
def adicionar_parente(
    paciente_id: int,
    papel: str,
    request: Request,
    parentesco: str = Form(""),
    laudo_c9orf72: str | None = Form(None),
    vcf: UploadFile | None = File(None),
    usuario: Usuario = Depends(exigir(PACIENTES_GERIR)),
):
    """Parente testado de um genitor sem exame (pai, mãe ou irmão dele): VCF e, para o C9orf72, o laudo. O VCF segue
    as regras dos genitores: validado pela ingestão, cifrado em disco com nome aleatório, sem download, auditado."""
    bd, cifra, config = obter_bd(request), obter_cifra(request), obter_config(request)
    p = do_medico(bd, usuario, paciente_id)
    g = _genitor(p, papel)
    campos: dict[str, str] = {}
    parentesco = (parentesco or "").strip().upper()
    existentes = p.parentes_de(g.papel)
    if g.tem_vcf:
        campos["parentesco"] = (
            "Este genitor já tem VCF próprio: o genótipo dele é observado. Parentes só entram para genitor sem exame."
        )
    elif parentesco not in PARENTESCOS:
        campos["parentesco"] = "Escolha o parentesco: pai, mãe ou irmão do genitor."
    elif parentesco != "IRMAO_DO_GENITOR" and any(x.parentesco == parentesco for x in existentes):
        campos["parentesco"] = "Este parente já está cadastrado; remova-o para substituir."
    elif sum(1 for x in existentes if x.parentesco == "IRMAO_DO_GENITOR") >= MAXIMO_IRMAOS_POR_GENITOR:
        campos["parentesco"] = f"Limite de {MAXIMO_IRMAOS_POR_GENITOR} irmãos por genitor."
    laudo = interpretar_laudo(laudo_c9orf72, "laudo_c9orf72", campos)
    tem_arquivo = vcf is not None and bool(vcf.filename)
    if not tem_arquivo and laudo is None and "laudo_c9orf72" not in campos:
        campos["vcf"] = "Envie o VCF do parente ou informe o laudo do C9orf72 dele (ao menos um dos dois)."
    exigir_campos(campos)
    x = Parente(
        papel_genitor=g.papel,
        parentesco=parentesco,
        laudo_c9orf72_cifrado=cifra.cifrar(laudo_texto(laudo)),
        criado_em=agora(),
        atualizado_em=agora(),
    )
    if tem_arquivo:
        tmp = vcfs.pasta_temporaria(config)
        try:
            caminho = vcfs.guardar_upload(vcf, tmp / "envio.vcf", "vcf", campos, config.tamanho_maximo_vcf)
            exigir_campos(campos)
            erro = vcfs.validar(caminho)
            if erro:
                exigir_campos({"vcf": erro})
            vcfs.anexar(config, cifra, x, caminho)
        finally:
            vcfs.apagar_pasta(tmp)
    p.parentes.append(x)
    p.atualizado_em = agora()
    bd.flush()
    atualizar_liberacao(bd, p, cifra, usuario)  # o parente é titular: a liberação passa a exigir o consentimento dele
    auditoria.registrar(
        bd,
        acao=auditoria.PARENTE_ADICIONADO,
        usuario=usuario,
        alvo_tipo="paciente",
        alvo_id=p.id,
        detalhe=(
            f"genitor {g.papel}; {parentesco}; VCF={'sim' if x.tem_vcf else 'não'}; "
            f"laudo={'sim' if laudo is not None else 'não'}"
        ),
    )
    bd.commit()
    bd.refresh(p)
    return paciente_dict(p, cifra, config=obter_config(request))


@router.delete("/{paciente_id}/parentes/{parente_id}")
def remover_parente(
    paciente_id: int, parente_id: int, request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))
):
    bd, cifra, config = obter_bd(request), obter_cifra(request), obter_config(request)
    p = do_medico(bd, usuario, paciente_id)
    x = next((x for x in p.parentes if x.id == parente_id), None)
    if x is None:
        raise HTTPException(404, "Parente não encontrado.")
    detalhe = f"genitor {x.papel_genitor}; {x.parentesco}"
    vcfs.remover(config, x)
    p.parentes.remove(x)  # o consentimento desse parente sai junto (cascata)
    bd.flush()
    bd.expire(p)
    p = do_medico(bd, usuario, paciente_id)
    p.atualizado_em = agora()
    atualizar_liberacao(bd, p, cifra, usuario)
    auditoria.registrar(
        bd, acao=auditoria.PARENTE_REMOVIDO, usuario=usuario, alvo_tipo="paciente", alvo_id=p.id, detalhe=detalhe
    )
    bd.commit()
    bd.expire(p)
    return paciente_dict(do_medico(bd, usuario, paciente_id), cifra, config=obter_config(request))


@router.post("/{paciente_id}/descendentes/{descendente_id}/vcf", status_code=201)
def anexar_vcf_descendente(
    paciente_id: int,
    descendente_id: int,
    request: Request,
    vcf: UploadFile | None = File(None),
    usuario: Usuario = Depends(exigir(PACIENTES_GERIR)),
):
    """VCF próprio de um filho que já fez o teste (só no caso de família): entra como evidência sobre o genitor sem
    exame, e esse filho deixa de ser analisado como pessoa em risco."""
    bd, cifra, config = obter_bd(request), obter_cifra(request), obter_config(request)
    p = do_medico(bd, usuario, paciente_id)
    d = descendente_de(p, descendente_id)
    if p.tipo != "FAMILIA":
        exigir_campos({"vcf": "O VCF do próprio filho só se aplica ao caso 3 (família): filho que já fez o teste."})
    campos: dict[str, str] = {}
    tmp = vcfs.pasta_temporaria(config)
    try:
        caminho = vcfs.guardar_upload(vcf, tmp / "envio.vcf", "vcf", campos, config.tamanho_maximo_vcf)
        exigir_campos(campos)
        erro = vcfs.validar(caminho)
        if erro:
            exigir_campos({"vcf": erro})
        substituiu = d.tem_vcf
        vcfs.anexar(config, cifra, d, caminho)
    finally:
        vcfs.apagar_pasta(tmp)
    p.atualizado_em = agora()
    auditoria.registrar(
        bd,
        acao=auditoria.VCF_ANEXADO,
        usuario=usuario,
        alvo_tipo="paciente",
        alvo_id=p.id,
        detalhe=f"descendente {d.id} (filho já testado); {d.vcf_tamanho} bytes; substituiu={'sim' if substituiu else 'não'}",
    )
    bd.commit()
    return paciente_dict(p, cifra, config=obter_config(request))


@router.delete("/{paciente_id}/descendentes/{descendente_id}/vcf")
def remover_vcf_descendente(
    paciente_id: int, descendente_id: int, request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))
):
    bd, cifra, config = obter_bd(request), obter_cifra(request), obter_config(request)
    p = do_medico(bd, usuario, paciente_id)
    d = descendente_de(p, descendente_id)
    if not d.tem_vcf:
        raise HTTPException(404, "Este descendente não tem VCF anexado.")
    vcfs.remover(config, d)
    d.atualizado_em = agora()
    p.atualizado_em = agora()
    auditoria.registrar(
        bd,
        acao=auditoria.VCF_REMOVIDO,
        usuario=usuario,
        alvo_tipo="paciente",
        alvo_id=p.id,
        detalhe=f"descendente {d.id} (filho já testado)",
    )
    bd.commit()
    return paciente_dict(p, cifra, config=obter_config(request))


# ---------------------------------------------------------------------------
# Rotas: documentos (prontuário e laudo do C9orf72), cifrados; só o médico dono abre
# ---------------------------------------------------------------------------
def _documento(p: Paciente, documento_id: int) -> Documento:
    d = next((x for x in p.documentos if x.id == documento_id), None)
    if d is None:
        raise HTTPException(404, "Documento não encontrado.")
    return d


@router.post("/{paciente_id}/documentos", status_code=201)
def anexar_documento(
    paciente_id: int,
    request: Request,
    tipo: str = Form(...),
    papel: str | None = Form(None),
    arquivo: UploadFile | None = File(None),
    usuario: Usuario = Depends(exigir(PACIENTES_GERIR)),
):
    """Anexa (ou substitui) o documento do prontuário ou o laudo do C9orf72 de um genitor (PDF, JPG ou PNG)."""
    bd, cifra, config = obter_bd(request), obter_cifra(request), obter_config(request)
    p = do_medico(bd, usuario, paciente_id)
    campos: dict[str, str] = {}
    tipo = (tipo or "").upper()
    genitor = None
    if tipo not in TIPOS_DOCUMENTO:
        campos["tipo"] = "Tipo de documento desconhecido."
    elif tipo == "LAUDO_C9ORF72":
        genitor = p.genitor((papel or "").upper()) if (papel or "").upper() in PAPEIS_GENITOR else None
        if genitor is None:
            campos["papel"] = "Indique o genitor do laudo (MAE ou PAI)."
    lido = arquivos.ler_upload_documento(arquivo, "arquivo", campos, config.tamanho_maximo_documento)
    exigir_campos(campos)
    dados, mime, nome_original = lido
    anterior = next(
        (x for x in p.documentos if x.tipo == tipo and x.genitor_id == (genitor.id if genitor else None)), None
    )
    if anterior is not None:
        arquivos.apagar(config.dir_documentos, anterior.arquivo)
        bd.delete(anterior)
        bd.flush()
    d = Documento(
        paciente=p,
        genitor_id=genitor.id if genitor else None,
        tipo=tipo,
        nome_original_cifrado=cifra.cifrar(nome_original),
        mime=mime,
        arquivo=arquivos.guardar(config.dir_documentos, cifra, dados),
        tamanho=len(dados),
        hash=arquivos.sha256(dados),
        enviado_em=agora(),
    )
    bd.add(d)
    bd.flush()
    p.atualizado_em = agora()
    auditoria.registrar(
        bd,
        acao=auditoria.DOCUMENTO_ANEXADO,
        usuario=usuario,
        alvo_tipo="documento",
        alvo_id=d.id,
        detalhe=(
            f"paciente {p.id}; {tipo}{'; genitor ' + genitor.papel if genitor else ''}; {len(dados)} bytes; "
            f"substituiu={'sim' if anterior else 'não'}"
        ),
    )
    bd.commit()
    bd.refresh(p)
    return paciente_dict(p, cifra, config=obter_config(request))


@router.get("/{paciente_id}/documentos/{documento_id}")
def abrir_documento(
    paciente_id: int, documento_id: int, request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))
):
    """Devolve o documento decifrado ao médico dono (abre no navegador); cada abertura vai à auditoria."""
    bd, cifra, config = obter_bd(request), obter_cifra(request), obter_config(request)
    p = do_medico(bd, usuario, paciente_id)
    d = _documento(p, documento_id)
    dados = arquivos.ler(config.dir_documentos, cifra, d.arquivo)
    auditoria.registrar(
        bd,
        acao=auditoria.DOCUMENTO_ABERTO,
        usuario=usuario,
        alvo_tipo="documento",
        alvo_id=d.id,
        detalhe=f"paciente {p.id}; {d.tipo}",
    )
    bd.commit()
    ext = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}[d.mime]
    return Response(
        content=dados,
        media_type=d.mime,
        headers={"Content-Disposition": f'inline; filename="documento_{d.id}.{ext}"', "Cache-Control": "no-store"},
    )


@router.delete("/{paciente_id}/documentos/{documento_id}")
def remover_documento(
    paciente_id: int, documento_id: int, request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))
):
    bd, cifra, config = obter_bd(request), obter_cifra(request), obter_config(request)
    p = do_medico(bd, usuario, paciente_id)
    d = _documento(p, documento_id)
    arquivos.apagar(config.dir_documentos, d.arquivo)
    tipo = d.tipo
    bd.delete(d)
    bd.flush()
    p.atualizado_em = agora()
    auditoria.registrar(
        bd,
        acao=auditoria.DOCUMENTO_REMOVIDO,
        usuario=usuario,
        alvo_tipo="documento",
        alvo_id=documento_id,
        detalhe=f"paciente {p.id}; {tipo}",
    )
    bd.commit()
    bd.refresh(p)
    return paciente_dict(p, cifra, config=obter_config(request))


# ---------------------------------------------------------------------------
# Rotas: descendentes
# ---------------------------------------------------------------------------
@router.post("/{paciente_id}/descendentes", status_code=201)
def incluir_descendente(
    paciente_id: int,
    entrada: DescendenteEntrada,
    request: Request,
    usuario: Usuario = Depends(exigir(PACIENTES_GERIR)),
):
    bd, cifra = obter_bd(request), obter_cifra(request)
    p = do_medico(bd, usuario, paciente_id)
    if p.tipo != "FAMILIA":
        exigir_campos(
            {"descendentes": "Só o caso 3 (família) admite mais de um descendente; o caso 2 não tem descendente."}
        )
    campos: dict[str, str] = {}
    dados = _validar_descendente(entrada, "descendente", campos, agora().date())
    exigir_campos(campos)
    d = Descendente(ordem=max((x.ordem for x in p.descendentes), default=0) + 1, atualizado_em=agora())
    _aplicar_descendente(d, dados, cifra)
    p.descendentes.append(d)
    p.atualizado_em = agora()
    bd.flush()
    atualizar_liberacao(bd, p, cifra, usuario)  # um novo descendente exige novo consentimento
    auditoria.registrar(
        bd,
        acao=auditoria.DESCENDENTE_EDITADO,
        usuario=usuario,
        alvo_tipo="descendente",
        alvo_id=d.id,
        detalhe=f"paciente {p.id}; incluído",
    )
    bd.commit()
    return paciente_dict(p, cifra, config=obter_config(request))


@router.put("/{paciente_id}/descendentes/{descendente_id}")
def editar_descendente(
    paciente_id: int,
    descendente_id: int,
    entrada: DescendenteEntrada,
    request: Request,
    usuario: Usuario = Depends(exigir(PACIENTES_GERIR)),
):
    bd, cifra = obter_bd(request), obter_cifra(request)
    p = do_medico(bd, usuario, paciente_id)
    d = descendente_de(p, descendente_id)
    campos: dict[str, str] = {}
    dados = _validar_descendente(entrada, "descendente", campos, agora().date())
    exigir_campos(campos)
    _aplicar_descendente(d, dados, cifra)
    if p.tipo == "PESSOA":
        p.nome_cifrado = cifra.cifrar(dados["nome"])  # o registro da pessoa leva o nome dela
    p.atualizado_em = agora()
    atualizar_liberacao(bd, p, cifra, usuario)  # a idade pode mudar o titular exigido
    auditoria.registrar(
        bd,
        acao=auditoria.DESCENDENTE_EDITADO,
        usuario=usuario,
        alvo_tipo="descendente",
        alvo_id=d.id,
        detalhe=f"paciente {p.id}; editado",
    )
    bd.commit()
    return paciente_dict(p, cifra, config=obter_config(request))


@router.delete("/{paciente_id}/descendentes/{descendente_id}")
def remover_descendente(
    paciente_id: int, descendente_id: int, request: Request, usuario: Usuario = Depends(exigir(PACIENTES_GERIR))
):
    bd, cifra = obter_bd(request), obter_cifra(request)
    p = do_medico(bd, usuario, paciente_id)
    d = descendente_de(p, descendente_id)
    if p.tipo != "FAMILIA" or len(p.descendentes) <= 1:
        raise HTTPException(
            409, "O registro precisa manter ao menos um descendente; exclua o registro inteiro se for o caso."
        )
    n_an = sum(1 for a in p.analises if a.descendente_id == d.id)
    _apagar_arquivos_de_analises(obter_config(request), [a for a in p.analises if a.descendente_id == d.id])
    vcfs.remover(obter_config(request), d)  # VCF próprio do filho já testado, se houver
    bd.delete(d)  # cascata apaga resumos e consentimentos desse descendente
    bd.flush()
    bd.expire(p)
    p = do_medico(bd, usuario, paciente_id)
    p.atualizado_em = agora()
    atualizar_liberacao(bd, p, cifra, usuario)
    auditoria.registrar(
        bd,
        acao=auditoria.DESCENDENTE_EDITADO,
        usuario=usuario,
        alvo_tipo="descendente",
        alvo_id=descendente_id,
        detalhe=f"paciente {p.id}; removido; {n_an} resumo(s)",
    )
    bd.commit()
    bd.expire(p)
    return paciente_dict(do_medico(bd, usuario, paciente_id), cifra, config=obter_config(request))


# ---------------------------------------------------------------------------
# Rotas: consentimentos
# ---------------------------------------------------------------------------
@router.get("/{paciente_id}/consentimentos")
def listar_consentimentos(paciente_id: int, request: Request, usuario: Usuario = Depends(exigir(CONSENTIMENTOS_GERIR))):
    bd, cifra = obter_bd(request), obter_cifra(request)
    p = do_medico(bd, usuario, paciente_id)
    d = paciente_dict(p, cifra, config=obter_config(request))
    return {
        "paciente_id": p.id,
        "tipo": p.tipo,
        "descendentes": [
            {"id": x["id"], "nome": x["nome"], "idade": x["idade"], "menor_de_idade": x["menor_de_idade"]}
            for x in d["descendentes"]
        ],
        "pesquisa": d["pesquisa"],
        "consentimentos": d["consentimentos"],
        "termo": textos.TERMO_CONSENTIMENTO_PESQUISA,
    }


@router.post("/{paciente_id}/consentimentos", status_code=201)
def registrar_consentimento(
    paciente_id: int,
    entrada: ConsentimentoEntrada,
    request: Request,
    usuario: Usuario = Depends(exigir(CONSENTIMENTOS_GERIR)),
):
    bd, cifra = obter_bd(request), obter_cifra(request)
    p = do_medico(bd, usuario, paciente_id)
    campos: dict[str, str] = {}
    titular = (entrada.titular or "").upper()
    if titular not in TITULARES:
        campos["titular"] = "Titular desconhecido."
    if not entrada.confirmado:
        campos["confirmado"] = "Marque a declaração de consentimento (ela nunca vem marcada)."
    if entrada.versao_termo != textos.VERSAO_TERMO_CONSENTIMENTO_PESQUISA:
        campos["versao_termo"] = "Versão do termo desatualizada; recarregue a ficha."
    nome_titular = " ".join((entrada.nome_titular or "").split())
    descendente_id = None
    parente_id = None
    if titular == "PARENTE":
        x = next((x for x in p.parentes if x.id == entrada.parente_id), None)
        if x is None:
            campos["parente_id"] = "Indique a qual parente testado o consentimento se refere."
        else:
            parente_id = x.id
        if len(nome_titular) < 3:
            campos["nome_titular"] = "Informe o nome do parente que consentiu (ele também é titular de dado genético)."
    elif titular in PAPEIS_GENITOR:
        g = p.genitor(titular)
        nome_titular = nome_titular or (cifra.decifrar(g.nome_cifrado) if g else "")
        if len(nome_titular) < 3:
            campos["nome_titular"] = "Informe o nome de quem consentiu."
    elif titular in ("DESCENDENTE", "RESPONSAVEL"):
        if p.tipo == "CASAL":
            campos["titular"] = "No caso 2 só os dois parceiros consentem: não há descendente cadastrado."
        else:
            d = next((x for x in p.descendentes if x.id == entrada.descendente_id), None)
            if d is None:
                campos["descendente_id"] = "Indique a qual descendente o consentimento se refere."
            else:
                descendente_id = d.id
                idade = idades(p, cifra)[d.id]
                if titular == "DESCENDENTE":
                    if idade < MAIORIDADE:
                        campos["titular"] = (
                            f"Descendente com menos de {MAIORIDADE} anos: o consentimento deve ser registrado em nome de "
                            "um dos pais ou do responsável legal (art. 14, §1º)."
                        )
                    nome_titular = nome_titular or cifra.decifrar(d.nome_cifrado)
                elif len(nome_titular) < 3:
                    campos["nome_titular"] = "Identifique o responsável legal (nome completo)."
    exigir_campos(campos)
    for c in p.consentimentos:
        if (
            c.ativo
            and c.descendente_id == descendente_id
            and c.parente_id == parente_id
            and (c.titular == titular or {c.titular, titular} == {"DESCENDENTE", "RESPONSAVEL"})
        ):
            raise HTTPException(409, f"Já existe consentimento ativo de: {ROTULO_TITULAR[c.titular]}.")
    c = Consentimento(
        paciente=p,
        descendente_id=descendente_id,
        parente_id=parente_id,
        finalidade="PESQUISA",
        titular=titular,
        nome_titular_cifrado=cifra.cifrar(nome_titular),
        versao_termo=textos.VERSAO_TERMO_CONSENTIMENTO_PESQUISA,
        concedido_em=agora(),
        registrado_por_id=usuario.id,
    )
    bd.add(c)
    bd.flush()
    auditoria.registrar(
        bd,
        acao=auditoria.CONSENTIMENTO_REGISTRADO,
        usuario=usuario,
        alvo_tipo="consentimento",
        alvo_id=c.id,
        detalhe=(
            f"paciente {p.id}; titular {titular}; descendente {descendente_id}; parente {parente_id}; "
            f"termo {c.versao_termo}"
        ),
    )
    p.atualizado_em = agora()
    atualizar_liberacao(bd, p, cifra, usuario)
    bd.commit()
    bd.refresh(p)
    return paciente_dict(p, cifra, config=obter_config(request))


@router.post("/{paciente_id}/consentimentos/{consentimento_id}/revogar")
def revogar_consentimento(
    paciente_id: int,
    consentimento_id: int,
    request: Request,
    usuario: Usuario = Depends(exigir(CONSENTIMENTOS_GERIR)),
):
    """Revogar é tão simples quanto conceder (art. 8º, §5º): um clique na mesma tela, efeito imediato."""
    bd, cifra = obter_bd(request), obter_cifra(request)
    p = do_medico(bd, usuario, paciente_id)
    c = next((c for c in p.consentimentos if c.id == consentimento_id), None)
    if c is None:
        raise HTTPException(404, "Consentimento não encontrado.")
    if not c.ativo:
        raise HTTPException(409, "Consentimento já revogado.")
    c.revogado_em = agora()
    c.revogado_por_id = usuario.id
    auditoria.registrar(
        bd,
        acao=auditoria.CONSENTIMENTO_REVOGADO,
        usuario=usuario,
        alvo_tipo="consentimento",
        alvo_id=c.id,
        detalhe=f"paciente {p.id}; titular {c.titular}",
    )
    p.atualizado_em = agora()
    atualizar_liberacao(bd, p, cifra, usuario)
    bd.commit()
    bd.refresh(p)
    return paciente_dict(p, cifra, config=obter_config(request))
