"""Visão do pesquisador: casos liberados para pesquisa, pseudonimizados (LGPD, art. 13, §4º), com filtros, totais e
exportação em CSV.

Um caso é um registro com `liberado_pesquisa_em` não nulo (consentimento ativo de cada genitor e de cada descendente ou
responsável). Sai apenas o código aleatório, o tipo de atendimento, o momento, o sexo e a década de idade de cada
descendente e o resumo das análises. Nunca nome, prontuário, data de nascimento, nome dos genitores, médico, ids nem o
VCF (`test_web.py` confere que nenhuma resposta do pesquisador contém esses dados).
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import re
import statistics
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from . import auditoria, textos
from .bd import agora
from .comum import exigir_campos, obter_bd, obter_cifra
from .modelos import MOMENTOS, TIPOS_ATENDIMENTO, Paciente, Usuario
from .pacientes import MAIORIDADE, analise_compacta, analise_dict, genes_do_modelo, idade_em
from .permissoes import PESQUISA_CASOS, exigir

router = APIRouter(prefix="/api/pesquisa", tags=["pesquisa"])
DECADAS = [f"{d}–{d + 9}" for d in range(0, 100, 10)] + ["100+"]
HERANCAS = ("dominante", "recessiva")


class BuscaCasos(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    tipo: str | None = Field(default=None, max_length=10)
    sexo: str | None = Field(default=None, max_length=1)
    decada: str | None = Field(default=None, max_length=8)
    momento: str | None = Field(default=None, max_length=20)
    genes: list[str] = Field(default_factory=list, max_length=10)
    heranca: str | None = Field(default=None, max_length=20)
    risco_min: float | None = Field(default=None, ge=0, le=1)
    risco_max: float | None = Field(default=None, ge=0, le=1)
    analise_de: str | None = Field(default=None, max_length=7, description="AAAA-MM")
    analise_ate: str | None = Field(default=None, max_length=7)
    hipoteses: bool | None = None
    suposicao: bool | None = None
    com_analise: bool | None = None


def decada(idade: int) -> str:
    return "100+" if idade >= 100 else f"{(idade // 10) * 10}–{(idade // 10) * 10 + 9}"


def _mes(iso_: str | None) -> str | None:
    return iso_[:7] if iso_ else None


def _analise_pseudonimizada(a: dict | None, detalhado: bool = False) -> dict | None:
    """Resumo compacto sem ids internos; `detalhado` acrescenta lóci, variantes, dosagens, curva e metadados."""
    if a is None:
        return None
    c = analise_compacta(a)
    c.pop("id", None)
    c.pop("descendente_id", None)
    # o pesquisador recebe a idade só por década (como a faixa etária do descendente), nunca a idade exata
    c.pop("idade_na_analise", None)
    ref = c.pop("idade_referencia", None)
    c["faixa_idade_referencia"] = decada(int(ref)) if ref is not None else None
    c["executado_em"] = _mes(c["executado_em"])
    r = a["resumo"]
    c["herancas"] = sorted({l.get("heranca") for l in r.get("loci", []) if l.get("heranca")})
    if detalhado:
        c.update(
            {
                "loci": r.get("loci", []),
                "variantes": r.get("variantes", []),
                "vetor": r.get("vetor", []),
                "curva": r.get("curva"),
                "semente": a.get("semente"),
                "cox": a.get("cox"),
                "loci_descartados": r.get("loci_descartados", []),
                "horizonte": r.get("horizonte"),
                "versao": r.get("versao"),
                "parentes": _parentes_pseudonimizados(r.get("parentes")),
                "limite_inferior": bool(r.get("limite_inferior")),
            }
        )
    c["inferido_por_parentes"] = bool((r.get("parentes") or {}).get("loci_inferidos"))
    return c


def _parentes_pseudonimizados(info: dict | None) -> dict | None:
    """Inferência por parentes para o pesquisador: situação do genitor com a idade só por década, parentesco dos
    parentes considerados, suposições e dosagem inferida por lócus."""
    if not info:
        return None
    genitores = {}
    for lado, g in (info.get("genitores") or {}).items():
        idade = g.get("idade")
        genitores[lado] = {
            "situacao": g.get("situacao"),
            "faixa_idade": decada(int(idade)) if idade is not None else None,
            "limite_inferior": bool(g.get("limite_inferior")),
        }
    loci = []
    for l in info.get("loci_inferidos") or []:
        loci.append({k: v for k, v in l.items() if k != "situacao_clinica"})
    return {
        "genitores": genitores,
        "pessoas": info.get("pessoas") or [],
        "suposicoes": info.get("suposicoes") or [],
        "loci_inferidos": loci,
    }


def caso_dict(p: Paciente, cifra, hoje: _dt.date, detalhado: bool = False) -> dict:
    analises = [analise_dict(a, cifra) for a in p.analises]
    ultimas: dict[int | None, dict] = {}
    for a in analises:
        ultimas[a["descendente_id"]] = a
    descendentes = []
    for d in p.descendentes:
        idade = idade_em(_dt.date.fromisoformat(cifra.decifrar(d.data_nascimento_cifrada)), hoje)
        descendentes.append(
            {
                "indice": d.ordem,
                "sexo": d.sexo,
                "faixa_etaria": decada(idade),
                "menor_de_idade": idade < MAIORIDADE,
                "analise": _analise_pseudonimizada(ultimas.get(d.id), detalhado),
            }
        )
    futuro = _analise_pseudonimizada(ultimas.get(None), detalhado) if p.tipo == "CASAL" else None
    analisadas = [x["analise"] for x in descendentes if x["analise"]] + ([futuro] if futuro else [])
    genes = sorted({g for a in analisadas for g in a["genes_de_risco"]})
    riscos = [a["p_manifesta"] for a in analisadas if a["p_manifesta"] is not None]
    tipo = textos.TIPOS_ATENDIMENTO[p.tipo]
    return {
        "codigo": p.codigo_pesquisa,
        "tipo": p.tipo,
        "tipo_rotulo": tipo["rotulo"],
        "tipo_curto": tipo["curto"],
        "momento": p.momento,
        "momento_rotulo": textos.MOMENTOS.get(p.momento) if p.momento else None,
        "liberado_em": _mes(p.liberado_pesquisa_em.isoformat() if p.liberado_pesquisa_em else None),
        "genitores": {
            g.papel: {
                "laudo_informado": bool(cifra.decifrar(g.laudo_c9orf72_cifrado)),
                "vcf_presente": g.tem_vcf,
                # genitor sem exame: quantos parentes testados entram na inferência (só o número e o parentesco)
                "parentes": [x.parentesco for x in p.parentes_de(g.papel)],
            }
            for g in p.genitores
        },
        "descendentes": descendentes,
        "futuro_filho": futuro,
        "n_analises": len(analisadas),
        "genes_de_risco": genes,
        "herancas": sorted({h for a in analisadas for h in a["herancas"]}),
        "risco_maximo": max(riscos) if riscos else None,
        "com_hipoteses": any(a["hipoteses"] for a in analisadas),
        "com_suposicao": any(a["com_suposicao"] for a in analisadas),
        "ultima_analise_em": max((a["executado_em"] for a in analisadas if a["executado_em"]), default=None),
    }


def filtrar_casos(casos: list[dict], f: dict) -> list[dict]:
    genes = {g.upper() for g in (f.get("genes") or []) if g}
    res = []
    for c in casos:
        pessoas = c["descendentes"] + (
            [{"sexo": c["futuro_filho"]["sexo"], "faixa_etaria": None}] if c["futuro_filho"] else []
        )
        if f.get("tipo") and c["tipo"] != f["tipo"]:
            continue
        if f.get("momento") and c["momento"] != f["momento"]:
            continue
        if f.get("sexo") and not any((x.get("sexo") or "") == f["sexo"] for x in pessoas):
            continue
        if f.get("decada") and not any(x.get("faixa_etaria") == f["decada"] for x in pessoas):
            continue
        if genes and not genes & {g.upper() for g in c["genes_de_risco"]}:
            continue
        if f.get("heranca") and f["heranca"] not in c["herancas"]:
            continue
        if f.get("risco_min") is not None and (c["risco_maximo"] is None or c["risco_maximo"] < f["risco_min"]):
            continue
        if f.get("risco_max") is not None and (c["risco_maximo"] is None or c["risco_maximo"] > f["risco_max"]):
            continue
        if f.get("analise_de") and (c["ultima_analise_em"] is None or c["ultima_analise_em"] < f["analise_de"]):
            continue
        if f.get("analise_ate") and (c["ultima_analise_em"] is None or c["ultima_analise_em"] > f["analise_ate"]):
            continue
        if f.get("hipoteses") is not None and c["com_hipoteses"] != f["hipoteses"]:
            continue
        if f.get("suposicao") is not None and c["com_suposicao"] != f["suposicao"]:
            continue
        if f.get("com_analise") is not None and (c["n_analises"] > 0) != f["com_analise"]:
            continue
        res.append(c)
    res.sort(key=lambda c: (c["liberado_em"] or "", c["codigo"]), reverse=True)
    return res


def totais(casos: list[dict]) -> dict:
    analisadas = []
    for c in casos:
        analisadas += [x["analise"] for x in c["descendentes"] if x["analise"]]
        if c["futuro_filho"]:
            analisadas.append(c["futuro_filho"])
    riscos = [c["risco_maximo"] for c in casos if c["risco_maximo"] is not None]
    return {
        "casos": len(casos),
        "analises": len(analisadas),
        "por_tipo": dict(Counter(c["tipo"] for c in casos)),
        "por_sexo": dict(Counter((a["sexo"] or "NI") for a in analisadas)),
        "por_gene": dict(Counter(g for c in casos for g in c["genes_de_risco"])),
        "por_momento": dict(Counter(c["momento"] or "NI" for c in casos)),
        "com_suposicao": sum(1 for c in casos if c["com_suposicao"]),
        "risco_vitalicio_mediano": round(statistics.median(riscos), 4) if riscos else None,
    }


def _casos_liberados(bd, cifra, detalhado: bool = False) -> list[dict]:
    hoje = agora().date()
    regs = bd.execute(
        select(Paciente).where(Paciente.liberado_pesquisa_em.is_not(None)).order_by(Paciente.id)
    ).scalars()
    return [caso_dict(p, cifra, hoje, detalhado) for p in regs]


def _opcoes() -> dict:
    return {
        "tipos": [
            {"valor": k, "rotulo": v["rotulo"], "curto": v["curto"]} for k, v in textos.TIPOS_ATENDIMENTO.items()
        ],
        "momentos": [{"valor": k, "rotulo": v} for k, v in textos.MOMENTOS.items()],
        "genes": genes_do_modelo(),
        "decadas": DECADAS,
        "herancas": list(HERANCAS),
    }


def _validar(f: dict) -> None:
    campos = {}
    if f["tipo"] and f["tipo"].upper() not in TIPOS_ATENDIMENTO:
        campos["tipo"] = "Tipo desconhecido."
    if f["momento"] and f["momento"].upper() not in MOMENTOS:
        campos["momento"] = "Momento desconhecido."
    if f["sexo"] and f["sexo"].upper() not in ("M", "F"):
        campos["sexo"] = "Use M ou F."
    if f["decada"] and f["decada"] not in DECADAS:
        campos["decada"] = "Década desconhecida."
    for k in ("analise_de", "analise_ate"):
        if f[k] and not (len(f[k]) == 7 and f[k][4] == "-" and f[k][:4].isdigit() and f[k][5:].isdigit()):
            campos[k] = "Use AAAA-MM."
    exigir_campos(campos)
    for k in ("tipo", "momento", "sexo"):
        if f[k]:
            f[k] = f[k].upper()


@router.get("/casos")
def casos(request: Request, usuario: Usuario = Depends(exigir(PESQUISA_CASOS))):
    bd, cifra = obter_bd(request), obter_cifra(request)
    lista = filtrar_casos(_casos_liberados(bd, cifra), {})
    auditoria.registrar(bd, acao=auditoria.CASOS_CONSULTADOS, usuario=usuario, detalhe=f"{len(lista)} caso(s)")
    bd.commit()
    return {
        "casos": lista,
        "totais": totais(lista),
        "opcoes": _opcoes(),
        "descricao": textos.DESCRICAO_PESQUISA,
        "mensagem": (
            "Nenhum registro disponível para pesquisa até agora. Os registros aparecem aqui quando o médico registra o "
            "consentimento de cada genitor e de cada descendente (ou responsável): um código aleatório no lugar do nome, "
            "sem prontuário nem data de nascimento."
            if not lista
            else None
        ),
    }


@router.post("/casos/busca")
def buscar_casos(entrada: BuscaCasos, request: Request, usuario: Usuario = Depends(exigir(PESQUISA_CASOS))):
    bd, cifra = obter_bd(request), obter_cifra(request)
    f = entrada.model_dump()
    _validar(f)
    lista = filtrar_casos(_casos_liberados(bd, cifra), f)
    auditoria.registrar(
        bd, acao=auditoria.CASOS_CONSULTADOS, usuario=usuario, detalhe=f"{len(lista)} caso(s); com filtros"
    )
    bd.commit()
    return {"casos": lista, "totais": totais(lista), "filtros": {k: v for k, v in f.items() if v not in (None, "", [])}}


@router.get("/casos/{codigo}")
def ver_caso(codigo: str, request: Request, usuario: Usuario = Depends(exigir(PESQUISA_CASOS))):
    """Um registro de pesquisa completo (lóci, variantes aprovadas por genitor, dosagens, curva, metadados). O VCF em si
    nunca sai; o código é o pseudônimo aleatório, não um id interno."""
    bd, cifra = obter_bd(request), obter_cifra(request)
    if not re.fullmatch(r"[0-9a-f]{32}", codigo or ""):
        raise HTTPException(404, "Registro de pesquisa não encontrado.")
    p = bd.execute(
        select(Paciente).where(Paciente.codigo_pesquisa == codigo, Paciente.liberado_pesquisa_em.is_not(None))
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Registro de pesquisa não encontrado.")
    caso = caso_dict(p, cifra, agora().date(), detalhado=True)
    auditoria.registrar(bd, acao=auditoria.CASOS_CONSULTADOS, usuario=usuario, detalhe="detalhe de 1 registro")
    bd.commit()
    return caso


@router.post("/casos/exportar-detalhado")
def exportar_detalhado(entrada: BuscaCasos, request: Request, usuario: Usuario = Depends(exigir(PESQUISA_CASOS))):
    """JSON com os registros filtrados e todos os dados de pesquisa (sem identificadores nem VCFs)."""
    bd, cifra = obter_bd(request), obter_cifra(request)
    f = entrada.model_dump()
    _validar(f)
    lista = filtrar_casos(_casos_liberados(bd, cifra, detalhado=True), f)
    auditoria.registrar(
        bd, acao=auditoria.CASOS_EXPORTADOS, usuario=usuario, detalhe=f"{len(lista)} registro(s) em JSON detalhado"
    )
    bd.commit()
    corpo = {
        "exportado_em": agora().replace(microsecond=0).isoformat() + "Z",
        "filtros": {k: v for k, v in f.items() if v not in (None, "", [])},
        "registros": lista,
    }
    return Response(
        content=json.dumps(corpo, ensure_ascii=False, indent=1).encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="registros_pesquisa.json"', "Cache-Control": "no-store"},
    )


COLUNAS_CSV_VARIANTES = [
    "codigo",
    "tipo",
    "pessoa",
    "analise_em",
    "genitor",
    "gene",
    "cromossomo",
    "posicao",
    "ref",
    "alt",
    "id",
    "tipo_variante",
    "classe",
    "clnsig",
    "estrelas",
    "nome_curto",
    "heranca",
    "dosagem",
    "repeticoes",
]


def csv_variantes(casos: list[dict]) -> str:
    """Uma linha por variante aprovada, por genitor e por análise (registros detalhados)."""
    linhas = [";".join(COLUNAS_CSV_VARIANTES)]
    for c in casos:
        pessoas = [(f"descendente {x['indice']}", x["analise"]) for x in c["descendentes"]]
        if c["futuro_filho"]:
            pessoas.append(("futuro filho", c["futuro_filho"]))
        for pessoa, a in pessoas:
            for v in (a or {}).get("variantes") or []:
                valores = [
                    c["codigo"],
                    c["tipo"],
                    pessoa,
                    (a or {}).get("executado_em") or "",
                    v.get("amostra") or "",
                    v.get("gene") or "",
                    v.get("cromossomo"),
                    v.get("posicao"),
                    v.get("ref") or "",
                    v.get("alt") or "",
                    v.get("id") or "",
                    v.get("tipo") or "",
                    v.get("classe") or "",
                    v.get("clnsig") or "",
                    v.get("estrelas"),
                    v.get("nome_curto") or "",
                    v.get("heranca") or "",
                    v.get("dosagem"),
                    v.get("repeticoes"),
                ]
                linhas.append(";".join("" if x is None else str(x).replace(";", ",") for x in valores))
    return "\n".join(linhas) + "\n"


@router.post("/casos/exportar-variantes")
def exportar_variantes(entrada: BuscaCasos, request: Request, usuario: Usuario = Depends(exigir(PESQUISA_CASOS))):
    bd, cifra = obter_bd(request), obter_cifra(request)
    f = entrada.model_dump()
    _validar(f)
    lista = filtrar_casos(_casos_liberados(bd, cifra, detalhado=True), f)
    conteudo = csv_variantes(lista)
    auditoria.registrar(
        bd, acao=auditoria.CASOS_EXPORTADOS, usuario=usuario, detalhe=f"{len(lista)} registro(s): variantes em CSV"
    )
    bd.commit()
    return Response(
        content=("\ufeff" + conteudo).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="variantes_pesquisa.csv"', "Cache-Control": "no-store"},
    )


def _num(v) -> str:
    if v is None:
        return ""
    return f"{float(v):.4f}".replace(".", ",")


COLUNAS_CSV = [
    "codigo",
    "tipo",
    "momento",
    "pessoa",
    "sexo",
    "faixa_etaria",
    "analise_em",
    "modo",
    "motor",
    "n",
    "hipoteses",
    "suposicao_nao_portador",
    "genes_de_risco",
    "herancas",
    "faixa_idade_referencia",
    "p_transmissao",
    "p_manifesta_vida",
    "p_manifesta_q025",
    "p_manifesta_q975",
    "risco_10_anos",
    "risco_20_anos",
    "F_50",
    "F_60",
    "F_70",
    "inicio_mediana",
    "inicio_q25",
    "inicio_q75",
]


def csv_casos(casos: list[dict]) -> str:
    """Uma linha por análise (descendente ou futuro filho); separador ';' e decimal com vírgula (pt-BR).

    Com `faixa_idade_referencia` preenchida, `p_transmissao`, `p_manifesta_vida` (risco residual até o horizonte), a
    banda, `risco_10_anos`, `risco_20_anos` e a idade de início são os valores condicionados à pessoa sem sintomas nessa
    faixa de idade; vazia, valem desde o nascimento e `F_50`, `F_60`, `F_70` são o risco acumulado até essas idades."""
    linhas = [";".join(COLUNAS_CSV)]
    for c in casos:
        pessoas = [
            (f"descendente {x['indice']}", x["sexo"], x["faixa_etaria"], x["analise"]) for x in c["descendentes"]
        ]
        if c["futuro_filho"]:
            pessoas.append(("futuro filho", c["futuro_filho"]["sexo"], "", c["futuro_filho"]))
        for pessoa, sexo, faixa, a in pessoas:
            a = a or {}
            F = a.get("F") or {}
            jan = a.get("janelas") or {}
            ini = a.get("inicio") or {}
            valores = [
                c["codigo"],
                c["tipo"],
                c["momento"] or "",
                pessoa,
                sexo or "",
                faixa or "",
                a.get("executado_em") or "",
                a.get("modo") or "",
                a.get("motor") or "",
                str(a.get("n") or ""),
                "sim" if a.get("hipoteses") else "não",
                ",".join((a.get("suposicoes") or {}).get("nao_portador", [])),
                ",".join(a.get("genes_de_risco") or []),
                ",".join(a.get("herancas") or []),
                a.get("faixa_idade_referencia") or "",
                _num(a.get("p_portador")),
                _num(a.get("p_manifesta")),
                _num(a.get("q025")),
                _num(a.get("q975")),
                _num((jan.get("10") or {}).get("valor")),
                _num((jan.get("20") or {}).get("valor")),
                _num((F.get("50") or {}).get("valor")),
                _num((F.get("60") or {}).get("valor")),
                _num((F.get("70") or {}).get("valor")),
                _num(ini.get("mediana")),
                _num(ini.get("q25")),
                _num(ini.get("q75")),
            ]
            linhas.append(";".join(str(v).replace(";", ",") for v in valores))
    return "\n".join(linhas) + "\n"


@router.post("/casos/exportar")
def exportar_casos(entrada: BuscaCasos, request: Request, usuario: Usuario = Depends(exigir(PESQUISA_CASOS))):
    bd, cifra = obter_bd(request), obter_cifra(request)
    f = entrada.model_dump()
    _validar(f)
    lista = filtrar_casos(_casos_liberados(bd, cifra), f)
    conteudo = csv_casos(lista)
    auditoria.registrar(bd, acao=auditoria.CASOS_EXPORTADOS, usuario=usuario, detalhe=f"{len(lista)} caso(s) em CSV")
    bd.commit()
    buf = io.BytesIO(("﻿" + conteudo).encode("utf-8"))
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="casos_pseudonimizados.csv"',
            "Cache-Control": "no-store",
        },
    )
