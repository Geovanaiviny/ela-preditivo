"""Análises (só o médico): cenários de exemplo, parâmetros do modelo, execução a partir dos VCFs dos genitores (anexados
à ficha e decifrados só para a pasta temporária, apagada ao fim), figuras e pacote .zip.

O resultado completo fica disponível ao médico que o executou por tempo limitado; quando a análise parte de um registro,
um resumo cifrado (genes de risco, probabilidades, idade provável de início, suposições) é guardado na ficha. Um genitor
sem VCF pode ser assumido não portador (VCF sem variantes), com a suposição declarada no resultado e nos metadados.
Sem registro (uso "planejamento familiar" avulso), os VCFs enviados não são guardados.
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import re
import secrets
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response

from .. import AVISO_LEGAL, DIR_DADOS, __version__, cenarios, pipeline, repeticoes
from ..calibracao import carregar_parametros
from ..ingestao import MontagemDivergente
from . import arquivos, auditoria, textos, vcfs
from .bd import agora
from .comum import exigir_campos, interpretar_laudo, iso, obter_bd, obter_cifra
from .config import Configuracao
from .modelos import AnalisePaciente, Descendente, Paciente, Usuario
from .pacientes import descendente_de, do_medico, idades, situacao_do_genitor
from .permissoes import ANALISES_BAIXAR, ANALISES_EXECUTAR, MODELO_VER, exigir

router = APIRouter(prefix="/api", tags=["analises"])
DIR_SINTETICOS = DIR_DADOS / "sinteticos"
MOTORES = ("numpy", "pymc")
RE_NOME_FIGURA = re.compile(r"^figura_\d{2}_[a-z0-9_]+\.png$")
EXTENSOES_VCF = vcfs.EXTENSOES_VCF
UNIDADE_COMBINADA = "qualquer lócus"
COLUNAS_VARIANTES = (
    "amostra",
    "gene",
    "cromossomo",
    "posicao",
    "ref",
    "alt",
    "id",
    "tipo",
    "dosagem",
    "repeticoes",
    "classe",
    "clnsig",
    "estrelas",
    "nome_curto",
    "heranca",
    "regra_qualificada",
)
COLUNAS_VETOR = (
    "gene",
    "variante",
    "rs",
    "tipo",
    "heranca",
    "dosagem_mae",
    "dosagem_pai",
    "repeticoes_mae",
    "repeticoes_pai",
    "clnsig",
    "estrelas",
    "p_portador_exato",
    "descartado",
    "observacao",
    "genitor_inferido",
    "p_dosagem_mae",
    "p_dosagem_pai",
)
PRIORS_AVOS = ("nao_portador", "hardy_weinberg")
SITUACAO_PARA_O_NUCLEO = {
    "VIVO_ASSINTOMATICO": "vivo_assintomatico",
    "FALECIDO_SEM_ELA": "falecido_sem_ela",
    "AFETADO": "afetado",
    "DESCONHECIDA": "desconhecido",
}


class RegistroAnalises:
    """Resultados em memória e em pasta temporária do processo, por análise, com dono e expiração."""

    def __init__(self, config: Configuracao):
        self.raiz = Path(tempfile.mkdtemp(prefix="ela_web_"))
        self.expiram = _dt.timedelta(minutes=config.analises_expiram_minutos)
        self._itens: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.execucao = threading.Lock()  # uma análise por vez (matplotlib e PyTensor não são reentrantes)

    def criar(self, dono_id: int) -> tuple[str, Path]:
        self.expurgar()
        ident = secrets.token_urlsafe(16)
        pasta = self.raiz / ident
        pasta.mkdir(parents=True)
        with self._lock:
            self._itens[ident] = {"dono_id": dono_id, "pasta": pasta, "criado_em": agora(), "resultado": None}
        return ident, pasta

    def guardar(self, ident: str, resultado: dict) -> None:
        with self._lock:
            self._itens[ident]["resultado"] = resultado

    def obter(self, ident: str, dono_id: int) -> dict | None:
        with self._lock:
            item = self._itens.get(ident)
        if item is None or item["dono_id"] != dono_id or item["resultado"] is None:
            return None
        return item

    def descartar(self, ident: str) -> None:
        with self._lock:
            item = self._itens.pop(ident, None)
        if item is not None:
            shutil.rmtree(item["pasta"], ignore_errors=True)

    def expurgar(self) -> None:
        limite = agora() - self.expiram
        with self._lock:
            vencidos = [k for k, v in self._itens.items() if v["criado_em"] < limite]
        for k in vencidos:
            self.descartar(k)

    def encerrar(self) -> None:
        with self._lock:
            self._itens.clear()
        shutil.rmtree(self.raiz, ignore_errors=True)


# ---------------------------------------------------------------------------
# Serialização do resultado (sem NaN, sem caminho de arquivo, sem nome de paciente)
# ---------------------------------------------------------------------------
def _registros(df: pd.DataFrame | None) -> list[dict]:
    if df is None or len(df) == 0:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def _limpar(valor):
    if isinstance(valor, dict):
        return {k: _limpar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_limpar(v) for v in valor]
    if isinstance(valor, (np.floating, float)):
        return None if not np.isfinite(valor) else float(valor)
    if isinstance(valor, (np.integer,)):
        return int(valor)
    if isinstance(valor, (np.bool_,)):
        return bool(valor)
    if isinstance(valor, Path):
        return valor.name
    return valor


def _secoes_relatorio(caminho: Path) -> list[dict]:
    texto = caminho.read_text(encoding="utf-8")
    secoes, titulo, corpo = [], None, []
    for linha in texto.splitlines():
        if linha.startswith("## "):
            if titulo and titulo not in ("Tabelas", "Figuras"):
                secoes.append({"titulo": titulo, "texto": "\n".join(corpo).strip()})
            titulo, corpo = linha[3:].strip(), []
        elif titulo:
            corpo.append(linha)
    if titulo and titulo not in ("Tabelas", "Figuras"):
        secoes.append({"titulo": titulo, "texto": "\n".join(corpo).strip()})
    return secoes


def _quantil_inicio(t: list, F: list, q: float) -> float | None:
    """Idade em que G(t) = F(t)/F(horizonte) cruza `q` (interpolação linear); None se F(horizonte) = 0."""
    pares = [(tt, ff) for tt, ff in zip(t, F) if tt is not None and ff is not None]
    if not pares or pares[-1][1] <= 0:
        return None
    fh = pares[-1][1]
    anterior = None
    for tt, ff in pares:
        g = ff / fh
        if g >= q:
            if anterior is None:
                return round(float(tt), 1)
            t0, g0 = anterior
            return round(float(t0 + (tt - t0) * ((q - g0) / (g - g0) if g > g0 else 0)), 1)
        anterior = (tt, g)
    return None


def principais(
    sem_locus: bool, combinado: dict, curvas: dict, condicionado: dict | None = None, idade_atual=None
) -> dict:
    """As três respostas do artefato, para a linha de indicadores.

    Sem idade atual (ou idade 0: futuro filho), valem desde o nascimento: 1. probabilidade de ter herdado /
    transmissão; 2. probabilidade de manifestação até o horizonte, com banda, e aos 50/60/70 anos; 3. idade provável
    de início (mediana e faixa 25–75 % de G(t) = F(t)/F(horizonte)) da unidade combinada.

    Com idade atual > 0 (`condicionado`, calculado pelo pipeline com a conta exata da Tabela 4 na idade do atendido),
    valem para quem chegou a essa idade sem sintomas: 1. P(portador de ≥ 1 lócus | assintomático); 2. risco residual
    até o horizonte, com banda, e nos próximos 10 e 20 anos; 3. mediana e faixa de 25 % a 75 % da idade de início entre
    quem vai manifestar. `idade_referencia` acompanha os valores em toda tela, lista e exportação."""
    ref = float(idade_atual) if idade_atual is not None and float(idade_atual) > 0 else None
    if sem_locus or not combinado:
        return {
            "sem_locus": True,
            "condicionado": ref is not None,
            "idade_referencia": ref,
            "transmissao": 0.0,
            "vida": {"valor": 0.0, "q025": 0.0, "q975": 0.0},
            "F": {},
            "janelas": {},
            "inicio": None,
        }
    if condicionado:
        ini = condicionado.get("inicio") or {}
        return {
            "sem_locus": False,
            "condicionado": True,
            "idade_referencia": condicionado.get("idade_referencia"),
            "horizonte": condicionado.get("horizonte"),
            "transmissao": condicionado.get("p_portador"),
            "vida": dict(condicionado.get("risco_residual") or {}),
            "F": {},
            "janelas": condicionado.get("janelas") or {},
            "inicio": {k: (None if ini.get(k) is None else round(float(ini[k]), 1)) for k in ("mediana", "q25", "q75")},
        }
    c = curvas.get(UNIDADE_COMBINADA) or (next(iter(curvas.values())) if curvas else None)
    F, inicio = {}, None
    if c:
        for alvo in (50, 60, 70):
            idx = next((i for i, x in enumerate(c["t"]) if x is not None and abs(x - alvo) < 1e-6), None)
            if idx is not None:
                F[str(alvo)] = {"valor": c["F"][idx], "q025": c["F_q025"][idx], "q975": c["F_q975"][idx]}
        inicio = {
            "mediana": combinado.get("idade_mediana_primeiro_inicio"),
            "q25": _quantil_inicio(c["t"], c["F"], 0.25),
            "q50_curva": _quantil_inicio(c["t"], c["F"], 0.5),
            "q75": _quantil_inicio(c["t"], c["F"], 0.75),
        }
    return {
        "sem_locus": False,
        "condicionado": False,
        "idade_referencia": None,
        "horizonte": combinado.get("horizonte"),
        "transmissao": combinado.get("p_portador_qualquer_exato"),
        "vida": {
            "valor": combinado.get("p_manifesta_qualquer_exato"),
            "q025": combinado.get("p_manifesta_qualquer_q025"),
            "q975": combinado.get("p_manifesta_qualquer_q975"),
        },
        "F": F,
        "janelas": {},
        "inicio": inicio,
    }


def resumo_para_guardar(resultado: dict) -> dict:
    """O que fica cifrado na ficha: genes de risco, probabilidades por lócus e combinadas, as três respostas (as
    condicionadas à idade atual, com a idade de referência, quando ela foi informada) e as suposições. Nunca o
    relatório, as figuras, os VCFs nem qualquer nome."""
    comb = resultado.get("combinado") or {}
    pr = resultado.get("principais") or {}
    ref = pr.get("idade_referencia") if pr.get("condicionado") else None
    tab4 = next((t for t in resultado.get("tabelas") or [] if t["nome"] == "tabela_04_risco_condicional"), None)
    na_idade = {}  # linha da Tabela 4 de cada unidade na idade de referência
    if ref is not None and tab4:
        for l in tab4["linhas"]:
            if l.get("idade_atual") is not None and abs(float(l["idade_atual"]) - float(ref)) < 1e-9:
                na_idade[l.get("unidade")] = l
    loci = [
        {
            "gene": l.get("gene"),
            "variante": l.get("variante"),
            "heranca": l.get("heranca"),
            "dosagem_mae": l.get("dosagem_mae"),
            "dosagem_pai": l.get("dosagem_pai"),
            "p_portador": l.get("p_portador_exato"),
            "p_manifesta": l.get("p_manifesta_exato"),
            "q025": l.get("p_manifesta_q025"),
            "q975": l.get("p_manifesta_q975"),
            "idade_mediana": l.get("idade_mediana_exata"),
            "p_portador_condicional": (na_idade.get(l.get("variante")) or {}).get("p_portador_condicional"),
            "risco_residual": (na_idade.get(l.get("variante")) or {}).get("risco_vitalicio"),
            "risco_residual_q025": (na_idade.get(l.get("variante")) or {}).get("risco_vitalicio_q025"),
            "risco_residual_q975": (na_idade.get(l.get("variante")) or {}).get("risco_vitalicio_q975"),
        }
        for l in resultado.get("resumo") or []
    ]
    tab1 = next((t for t in resultado.get("tabelas") or [] if t["nome"] == "tabela_01_variantes_anotadas"), None)
    variantes = [{k: l.get(k) for k in COLUNAS_VARIANTES} for l in (tab1["linhas"] if tab1 else [])]
    vetor = [{k: l.get(k) for k in COLUNAS_VETOR} for l in resultado.get("vetor") or []]
    curvas = resultado.get("curvas") or {}
    c = curvas.get(UNIDADE_COMBINADA) or (next(iter(curvas.values())) if curvas else None)
    curva = {k: c[k] for k in ("t", "F", "F_q025", "F_q975", "S")} if c else None
    return {
        "sem_locus": bool(resultado.get("sem_locus")),
        "variantes": variantes,  # Tabela 1: variantes aprovadas no filtro, por genitor (sem nomes nem arquivos)
        "vetor": vetor,  # Tabela 1b: dosagem por lócus de risco
        "curva": curva,  # F(t) da unidade combinada, com banda e S(t), um ponto por ano
        "genes_de_risco": sorted({l["gene"] for l in loci if l.get("gene")}),
        "loci": loci,
        "combinado": {
            k: comb.get(k)
            for k in (
                "p_portador_qualquer_exato",
                "p_manifesta_qualquer_exato",
                "p_manifesta_qualquer_q025",
                "p_manifesta_qualquer_q975",
                "idade_mediana_primeiro_inicio",
            )
        },
        "condicionado": bool(pr.get("condicionado")),
        "idade_referencia": pr.get("idade_referencia"),
        "transmissao": pr.get("transmissao"),
        "vida": pr.get("vida") or {},
        "janelas": pr.get("janelas") or {},
        "F": pr.get("F") or {},
        "inicio": pr.get("inicio"),
        "laudo_informado": bool((resultado.get("entrada") or {}).get("laudo_c9orf72")),
        # genitor sem exame inferido por parentes: situação, suposições e distribuição da dosagem (sem nomes)
        "parentes": _parentes_para_guardar(resultado.get("parentes")),
        "limite_inferior": bool(resultado.get("limite_inferior")),
        "loci_descartados": (resultado.get("metadados") or {}).get("loci_descartados") or [],
        "c9orf72_indeterminado": _c9orf72_indeterminado(resultado.get("vetor")),
        "horizonte": (resultado.get("metadados") or {}).get("horizonte"),
        "versao": (resultado.get("metadados") or {}).get("versao"),
    }


def _parentes_para_guardar(info: dict | None) -> dict | None:
    """Do resumo da inferência por parentes fica o que explica o resultado: situação de cada genitor inferido,
    parentes considerados (só o parentesco), suposições e a dosagem inferida por lócus. Nenhum nome de arquivo."""
    if not info:
        return None
    return {
        "genitores": info.get("genitores") or {},
        "pessoas": [
            {
                "parente": x.get("parente"),
                "com_vcf": bool(x.get("vcf")),
                "com_laudo": x.get("laudo_c9orf72") is not None,
            }
            for x in info.get("pessoas") or []
        ],
        "suposicoes": info.get("suposicoes") or [],
        "loci_inferidos": info.get("loci_inferidos") or [],
    }


def _c9orf72_indeterminado(vetor) -> bool:
    """Lócus do C9orf72 descartado por falta do laudo de um genitor: o resultado é parcial para esse gene."""
    return any(v.get("gene") == "C9orf72" and bool(v.get("descartado")) for v in (vetor or []))


def serializar_resultado(ident: str, r: dict, saida: Path, entrada: dict) -> dict:
    meta = json.loads((saida / "metadados.json").read_text(encoding="utf-8"))
    curvas = {}
    if r.get("curvas") is not None:
        for unidade, c in r["curvas"].groupby("unidade", sort=False):
            c = c[np.isclose(c.t % 1, 0)]  # um ponto por ano basta para o gráfico
            curvas[unidade] = {
                k: [None if not np.isfinite(v) else round(float(v), 6) for v in c[k].values]
                for k in ("t", "F", "F_q025", "F_q975", "S", "h")
            }
    tabelas = []
    for t in r["tabelas"]:
        df = pd.read_csv(t["csv"])
        tabelas.append(
            {
                "nome": t["nome"],
                "legenda": t["legenda"],
                "nota": t.get("nota") or "",
                "colunas": list(df.columns),
                "linhas": _registros(df),
            }
        )
    figuras = [{"nome": Path(f["png"]).name, "legenda": f["legenda"]} for f in r["figuras"]]
    transm = r.get("transmissao_c9orf72")
    cox = r.get("cox")
    tornado = r.get("tornado")
    provisorios = []
    try:
        par = carregar_parametros()
        provisorios = [g.nome for g in par.genes.values() if g.pen_confirmar or g.inicio_confirmar]
    except Exception:  # noqa: BLE001
        pass
    combinado = _limpar(r.get("combinado") or {})
    sem_locus = r["res"] is None
    return _limpar(
        {
            "id": ident,
            "criado_em": iso(agora()),
            "entrada": entrada,
            "sem_locus": sem_locus,
            "resumo": _registros(r.get("resumo")),
            "combinado": combinado,
            "principais": principais(
                sem_locus, combinado, curvas, _limpar(r.get("condicionado")), entrada.get("idade_atual")
            ),
            "suposicoes_texto": {
                "nao_portador": textos.SUPOSICAO_NAO_PORTADOR,
                "laudo_sem_vcf": textos.SUPOSICAO_LAUDO_SEM_VCF,
                "laudo_normal_suposto": textos.SUPOSICAO_LAUDO_NORMAL,
            },
            "c9orf72_indeterminado": _c9orf72_indeterminado(_registros(r.get("vetor"))),
            "texto_c9orf72_indeterminado": textos.C9ORF72_INDETERMINADO,
            # genitor sem exame inferido por parentes: o que entrou, as suposições e os avisos
            "parentes": _limpar(r.get("parentes")),
            "texto_inferencia": textos.INFERENCIA_POR_PARENTES,
            "limite_inferior": bool(r.get("limite_inferior")),
            "texto_limite_inferior": textos.LIMITE_INFERIOR_GENITOR_AFETADO,
            "aviso_parceiro_inferido": (
                textos.AVISO_PARCEIRO_INFERIDO
                if entrada.get("tipo") == "CASAL" and (r.get("parentes") or {}).get("loci_inferidos")
                else None
            ),
            "texto_variante_herdada": textos.SUPOSICAO_VARIANTE_HERDADA,
            "vetor": _registros(r.get("vetor")),
            "aderencia": _registros(r.get("aderencia")),
            "curvas": curvas,
            "tabelas": tabelas,
            "figuras": figuras,
            "secoes": _secoes_relatorio(Path(r["relatorio"])),
            "indicadores": r.get("indicadores") or {},
            "transmissao_c9orf72": transm.resumo() if transm is not None else None,
            "cox": (
                {"tabela": _registros(cox["tabela"]), "texto": cox["texto"], "mensagens": cox["mensagens"]}
                if cox is not None
                else None
            ),
            "tornado": (
                {"linhas": _registros(tornado), "fora": list(tornado.attrs.get("fora_do_tornado") or [])}
                if tornado is not None and not tornado.empty
                else None
            ),
            "metadados": {
                k: meta.get(k)
                for k in (
                    "versao",
                    "seed",
                    "n",
                    "motor",
                    "sexo",
                    "idade_atual",
                    "laudo_c9orf72",
                    "hipoteses_c9orf72",
                    "comparar_cox",
                    "tornado",
                    "horizonte",
                    "data",
                    "versao_parametros",
                    "data_parametros",
                    "base_anotacao",
                    "montagem",
                    "loci",
                    "loci_descartados",
                    "indicadores_condicionados",
                    "parentes",
                    "limite_inferior",
                    "sorteios_rejeitados",
                    "tempo_total_s",
                )
            },
            "limitacoes": {
                "modelo": textos.LIMITACAO_MODELO,
                "parametros_provisorios": provisorios,
                "texto": (
                    "Independência entre lóci; sem fatores modificadores; penetrância populacional de coortes "
                    "europeias/norte-americanas; dados sintéticos; sem ancestralidade nem fenótipo de parentes sem "
                    "teste genético; vale para pessoa sem sintomas."
                ),
            },
            "aviso_legal": AVISO_LEGAL,
            "aviso_experimental": textos.AVISO_EXPERIMENTAL,
            "relatorio_md": Path(r["relatorio"]).read_text(encoding="utf-8"),
        }
    )


# ---------------------------------------------------------------------------
# Entrada do formulário
# ---------------------------------------------------------------------------
def _inteiro(texto, campo, campos, minimo, maximo, padrao=None):
    if texto is None or str(texto).strip() == "":
        return padrao
    try:
        v = int(str(texto).strip())
    except ValueError:
        campos[campo] = "Informe um número inteiro."
        return padrao
    if not minimo <= v <= maximo:
        campos[campo] = f"Informe um valor entre {minimo} e {maximo}."
    return v


def _decimal(texto, campo, campos, minimo, maximo, padrao=None):
    if texto is None or str(texto).strip() == "":
        return padrao
    try:
        v = float(str(texto).strip().replace(",", "."))
    except ValueError:
        campos[campo] = "Informe um número."
        return padrao
    if not minimo <= v <= maximo:
        campos[campo] = f"Informe um valor entre {minimo:g} e {maximo:g}."
    return v


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------
@router.get("/cenarios")
def listar_cenarios(usuario: Usuario = Depends(exigir(ANALISES_EXECUTAR))):
    """Cenários sintéticos de exemplo (VCFs versionados em data/sinteticos), só para o médico autenticado."""
    itens = []
    for c in cenarios.CENARIOS:
        itens.append(
            {
                "numero": c.numero,
                "nome": c.nome,
                "descricao": c.descricao,
                "laudo_c9orf72": c.laudo_c9orf72 or {},
                "herancas": c.herancas,
                "disponivel": (DIR_SINTETICOS / f"cenario_{c.numero}_mae.vcf").exists(),
            }
        )
    return {"cenarios": itens, "aviso": "VCFs sintéticos gerados pelo artefato (seed 2026); nenhum dado genômico real."}


@router.get("/parametros")
def parametros(usuario: Usuario = Depends(exigir(MODELO_VER))):
    """Modelo e parâmetros (somente leitura): priors calibradas, distribuições de início, limiares, versões."""
    par = carregar_parametros()
    genes = []
    for g in par.genes.values():
        genes.append(
            {
                "gene": g.nome,
                "cromossomo": g.cromossomo,
                "heranca": g.heranca,
                "tipo_variante": g.tipo_variante,
                "penetrancia": {
                    "valor": g.pen_valor,
                    "ic95": list(g.pen_ic95),
                    "alpha": round(g.alpha, 3),
                    "beta": round(g.beta, 3),
                    "citacao": g.pen_citacao,
                    "confirmar": g.pen_confirmar,
                },
                "inicio": {
                    "distribuicao": g.inicio.tipo,
                    "parametros": g.inicio.params,
                    "mediana": round(g.inicio.mediana, 1),
                    "media": round(g.inicio.media, 1),
                    "metodo": g.inicio_ajuste.get("metodo") or g.inicio_ajuste.get("escolhido"),
                    "estatisticas": g.inicio_estatisticas or None,
                    "pontos": g.inicio_pontos or None,
                    "citacao": g.inicio_citacao,
                    "confirmar": g.inicio_confirmar,
                },
                "delta_sexo": {k: v for k, v in g.delta_sexo.items() if k in ("M", "F")},
                "delta_citacao": g.delta_citacao,
                "delta_confirmar": g.delta_confirmar,
            }
        )
    return _limpar(
        {
            "versao_pacote": __version__,
            "versao_parametros": par.versao,
            "data_parametros": par.data,
            "horizonte_anos": par.horizonte_anos,
            "filtro_qualidade": par.filtro_qualidade,
            "limiar_repeticoes_c9orf72": par.limiar_repeticoes,
            "genes": genes,
            "tabela_calibracao": _registros(par.tabela_calibracao()),
            "sensibilidade": par.sensibilidade,
            "dag": [
                "dose materna, dose paterna (0/1/2, do VCF ou do laudo) → alelo transmitido por cada genitor (Bernoulli d/2)",
                "dose do descendente = soma dos alelos → portador (dominante: ≥ 1; recessiva: = 2)",
                "penetrância π ~ Beta calibrada ao IC 95 % publicado → manifesta ~ Bernoulli(portador · π)",
                "idade de início | manifesta ~ Weibull por gene, deslocada pelo sexo (C9orf72: ±1 ano)",
                "vários lóci: independência, P(qualquer) = 1 − ∏(1 − P_g)",
            ],
            "extensoes": {
                "repeticoes": "transmissão do C9orf72 por repetições, limiar e antecipação (hipótese experimental)",
                "cox": "CoxPHFitter na coorte sintética de portadores, comparado com a cura mista",
                "tornado": "sensibilidade tipo tornado, um parâmetro por vez dentro da faixa publicada (opção da análise)",
            },
            "limitacao_modelo": textos.LIMITACAO_MODELO,
            "aviso_legal": AVISO_LEGAL,
        }
    )


class Execucao:
    """Opções de uma execução (comuns ao formulário e à demonstração)."""

    def __init__(
        self,
        n: int = 10_000,
        seed: int = 42,
        motor: str = "numpy",
        cox: bool = True,
        hipoteses=None,
        assumir: frozenset[str] = frozenset(),
        sexo_filho: str | None = None,
        modo: str = "vcf",
        cenario: int | None = None,
        assintomatico: bool = False,
        prior_avos: str = "nao_portador",
        tornado: bool = False,
    ):
        self.tornado = bool(tornado)  # sensibilidade tipo tornado do caso (desligada por padrão)
        self.prior_avos = prior_avos  # avô ou avó sem exame: suposto não portador (padrão) ou Hardy-Weinberg
        self.n, self.seed, self.motor, self.cox, self.hipoteses = n, seed, motor, cox, hipoteses
        self.assumir, self.sexo_filho, self.modo, self.cenario = assumir, sexo_filho, modo, cenario
        # confirmação do profissional de que a pessoa analisada não apresenta sintomas de ELA (obrigatória quando
        # há pessoa analisada; não se aplica ao futuro filho de um casal)
        self.assintomatico = bool(assintomatico)


def _preparar_vcfs_do_registro(
    config,
    cifra,
    p: Paciente,
    pasta: Path,
    assumir: frozenset[str],
    campos: dict,
    descendente: Descendente | None = None,
    prior_avos: str = "nao_portador",
):
    """Decifra os anexos para a pasta temporária e monta a evidência de parentes.

    Genitor com VCF: observado. Genitor sem VCF: inferido por parentes quando algum parente dele (ou um filho já
    testado, no caso de família) tem VCF, e então a situação clínica dele é obrigatória; senão, VCF sem variantes se
    assumido não portador; senão, erro de campo. Devolve (VCF da mãe, VCF do pai, suposições, argumento `parentes` do
    pipeline, resumo sem caminhos para a entrada)."""
    caminhos: dict[str, Path] = {}
    suposicoes: dict[str, list[str]] = {"nao_portador": [], "laudo_sem_vcf": []}
    parentes_arg: dict = {}
    resumo: dict = {}
    filhos = (
        [d for d in p.descendentes if d.tem_vcf and (descendente is None or d.id != descendente.id)]
        if p.tipo == "FAMILIA"
        else []
    )
    for papel, lado in (("MAE", "mae"), ("PAI", "pai")):
        g = p.genitor(papel)
        rotulo = textos.ROTULO_GENITOR[p.tipo][papel]
        if g is not None and g.tem_vcf:
            caminhos[lado] = vcfs.decifrar_para(config, cifra, g, pasta, lado)
            continue
        meus = p.parentes_de(papel) if g is not None else []
        inferido = any(x.tem_vcf for x in meus) or bool(filhos)
        if not inferido:
            if papel in assumir:
                caminhos[lado] = vcfs.sem_variantes(pasta / f"{lado}.vcf", f"{lado}_sem_exame")
                suposicoes["nao_portador"].append(papel)
                if g is not None and cifra.decifrar(g.laudo_c9orf72_cifrado):
                    suposicoes["laudo_sem_vcf"].append(papel)
            else:
                campos[f"vcf_{lado}"] = (
                    f"{rotulo} sem VCF anexado: anexe o arquivo na ficha, adicione um parente testado ou marque a "
                    "suposição de não portador."
                )
        if not (meus or inferido) or g is None:
            continue
        # parentes do genitor sem exame: VCFs inferem as variantes dele; laudos, o C9orf72
        sit = situacao_do_genitor(g, cifra)
        if sit["situacao"] is None:
            campos[f"situacao_{lado}"] = (
                f"Informe na ficha a situação clínica de {rotulo} (genitor sem exame com parente testado)."
            )
        item: dict = {
            "situacao": SITUACAO_PARA_O_NUCLEO.get(sit["situacao"], "desconhecido"),
            "idade": sit["idade"],
            "prior_avos": prior_avos,
            "irmaos": [],
        }
        for x in meus:
            dado = {
                "vcf": vcfs.decifrar_para(config, cifra, x, pasta, f"parente_{x.id}") if x.tem_vcf else None,
                "laudo_c9orf72": interpretar_laudo(
                    cifra.decifrar(x.laudo_c9orf72_cifrado), f"laudo_parente_{x.id}", campos
                ),
            }
            if x.parentesco == "IRMAO_DO_GENITOR":
                item["irmaos"].append(dado)
            else:
                item["pai" if x.parentesco == "PAI_DO_GENITOR" else "mae"] = dado
        parentes_arg[lado] = item
        resumo[papel] = {
            "situacao": sit["situacao"],
            "idade": sit["idade"],
            "inferido": inferido,
            "parentes": [x.parentesco for x in meus],
            "com_laudo": any(cifra.decifrar(x.laudo_c9orf72_cifrado) for x in meus),
        }
    if filhos and len(caminhos) < 2:  # filho já testado só é evidência quando algum genitor não tem VCF
        parentes_arg["filhos_testados"] = [
            {"vcf": vcfs.decifrar_para(config, cifra, d, pasta, f"filho_{d.id}")} for d in filhos
        ]
        resumo["filhos_testados"] = len(filhos)
    if assumir >= {"MAE", "PAI"}:
        campos["assumir_nao_portador"] = "É preciso o VCF de ao menos um genitor."
    suposicoes_usadas = {k: v for k, v in suposicoes.items() if v}
    return caminhos.get("mae"), caminhos.get("pai"), suposicoes_usadas, parentes_arg, resumo


def _laudo_do_registro(cifra, p: Paciente, campos: dict) -> dict:
    laudo = {}
    for papel, lado in (("MAE", "mae"), ("PAI", "pai")):
        g = p.genitor(papel)
        v = interpretar_laudo(cifra.decifrar(g.laudo_c9orf72_cifrado) if g else None, f"laudo_{lado}", campos)
        if v is not None:
            laudo[lado] = v
    return laudo


def _zip_em_memoria(saida: Path) -> bytes:
    """Zip da pasta de saída (relatório, tabelas, figuras, curvas, metadados), sem os VCFs."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for q in sorted(saida.rglob("*")):
            if q.is_file() and not q.name.endswith((".vcf", ".vcf.gz")):
                z.write(q, q.relative_to(saida).as_posix())
    return buf.getvalue()


def _executar(
    registro: RegistroAnalises,
    ident: str,
    pasta: Path,
    bd,
    usuario: Usuario,
    *,
    caminho_mae,
    caminho_pai,
    entrada: dict,
    rotulo: str,
    laudo: dict,
    exec_: Execucao,
    sexo: str | None,
    idade: float | None,
    paciente: Paciente | None = None,
    descendente: Descendente | None = None,
    cifra=None,
    config: Configuracao | None = None,
    parentes: dict | None = None,
) -> dict:
    """Roda o pipeline numa pasta temporária, serializa, guarda em memória e, se houver registro, persiste o resumo."""
    saida = pasta / "saida"
    try:
        with registro.execucao:
            r = pipeline.executar(
                caminho_mae,
                caminho_pai,
                saida,
                sexo=sexo,
                idade_atual=idade,
                n=exec_.n,
                seed=exec_.seed,
                motor=exec_.motor,
                rotulo=rotulo,
                laudo_c9orf72=laudo or None,
                hipoteses_c9orf72=exec_.hipoteses,
                comparar_cox=exec_.cox,
                parentes=parentes or None,
                tornado=exec_.tornado,
            )
        resultado = serializar_resultado(ident, r, saida, entrada)
        if paciente is not None:
            a = AnalisePaciente(
                paciente_id=paciente.id,
                descendente_id=descendente.id if descendente is not None else None,
                medico_id=usuario.id,
                executado_em=agora(),
                modo=exec_.modo,
                n=exec_.n,
                semente=exec_.seed,
                motor=exec_.motor,
                hipoteses=bool(exec_.hipoteses),
                cox=exec_.cox,
                sexo=sexo,
                idade_na_analise=int(idade) if idade is not None else None,
                assintomatico_confirmado=entrada.get("assintomatico_confirmado"),
                assintomatico_confirmado_em=agora() if entrada.get("assintomatico_confirmado") else None,
                suposicoes=json.dumps(entrada.get("suposicoes") or {}, ensure_ascii=False) or None,
                vcf_hash_mae=(paciente.genitor("MAE").vcf_hash if paciente.genitor("MAE") else None),
                vcf_hash_pai=(paciente.genitor("PAI").vcf_hash if paciente.genitor("PAI") else None),
                resumo_cifrado=cifra.cifrar(json.dumps(resumo_para_guardar(resultado), ensure_ascii=False)),
            )
            bd.add(a)
            bd.flush()
            resultado["entrada"]["resumo_id"] = a.id
            resultado["armazenada"] = {"paciente_id": paciente.id, "analise_id": a.id}
            if config is not None:  # resultado completo e pacote ficam cifrados em disco enquanto o registro existir
                a.resultado_arquivo = arquivos.guardar(
                    config.dir_analises, cifra, json.dumps(resultado, ensure_ascii=False).encode("utf-8"), ".json.bin"
                )
                a.pacote_arquivo = arquivos.guardar(config.dir_analises, cifra, _zip_em_memoria(saida), ".zip.bin")
            paciente.atualizado_em = agora()
        registro.guardar(ident, resultado)
        auditoria.registrar(
            bd,
            acao=auditoria.ANALISE_EXECUTADA,
            usuario=usuario,
            alvo_tipo="analise",
            alvo_id=ident,
            detalhe=(
                f"modo={exec_.modo}; cenario={entrada.get('cenario')}; motor={exec_.motor}; n={exec_.n}; cox={exec_.cox}; "
                f"tornado={exec_.tornado}; "
                f"hipoteses={'sim' if exec_.hipoteses else 'não'}; paciente={entrada.get('paciente_id')}; "
                f"descendente={entrada.get('descendente_id')}; suposicoes={','.join(sorted((entrada.get('suposicoes') or {}).get('nao_portador', []))) or 'nenhuma'}; "
                f"assintomatico={'confirmado' if entrada.get('assintomatico_confirmado') else 'não se aplica'}"
            ),
        )
        bd.commit()
        return resultado
    except HTTPException:
        registro.descartar(ident)
        raise
    except (MontagemDivergente, ValueError) as e:
        registro.descartar(ident)
        auditoria.registrar(
            bd, acao=auditoria.ANALISE_FALHA, usuario=usuario, resultado="FALHA", detalhe=type(e).__name__
        )
        bd.commit()
        raise HTTPException(422, f"Não foi possível analisar os arquivos: {str(e)[:300]}")
    except Exception as e:  # noqa: BLE001
        registro.descartar(ident)
        auditoria.registrar(
            bd, acao=auditoria.ANALISE_FALHA, usuario=usuario, resultado="FALHA", detalhe=type(e).__name__
        )
        bd.commit()
        raise
    finally:
        # VCFs (genitores, parentes e filho testado) nunca ficam na pasta da análise
        for arquivo in list(pasta.glob("*.vcf")) + list(pasta.glob("*.vcf.gz")):
            arquivo.unlink(missing_ok=True)


def executar_para_registro(
    bd,
    config: Configuracao,
    cifra,
    registro: RegistroAnalises,
    usuario: Usuario,
    p: Paciente,
    descendente: Descendente | None,
    exec_: Execucao,
) -> dict:
    """Análise de um registro: VCFs dos anexos (ou suposição), laudo da ficha, sexo e idade do descendente (ou do
    futuro filho, no caso CASAL). Usada pela rota e pela demonstração."""
    campos: dict[str, str] = {}
    if p.tipo == "CASAL":
        if descendente is not None:
            campos["descendente_id"] = "No caso 2 não há descendente: a análise é do futuro filho."
        sexo, idade = exec_.sexo_filho, None
        rotulo = f"registro {p.id}, futuro filho"
    else:
        if descendente is None:
            campos["descendente_id"] = "Indique o descendente a analisar."
            sexo, idade, rotulo = None, None, f"registro {p.id}"
        else:
            sexo, idade = descendente.sexo, float(idades(p, cifra)[descendente.id])
            rotulo = f"registro {p.id}, descendente {descendente.id}"  # nunca o nome
    if exec_.modo == "cenario" and not config.demonstracao:
        campos["modo"] = "Cenário de exemplo só é permitido em ambiente de demonstração."
    if descendente is not None and not exec_.assintomatico:
        campos["confirma_assintomatico"] = textos.ERRO_CONFIRMACAO_ASSINTOMATICO
    if descendente is not None and descendente.tem_vcf:
        campos["descendente_id"] = (
            "Este filho já fez o teste (VCF próprio anexado): o genótipo dele é conhecido e entra como evidência sobre "
            "o genitor sem exame; ele não é analisado como pessoa em risco."
        )
    if exec_.prior_avos not in PRIORS_AVOS:
        campos["prior_avos"] = "Opção desconhecida para avô ou avó sem exame."
    laudo = _laudo_do_registro(cifra, p, campos)
    exigir_campos(campos)
    ident, pasta = registro.criar(usuario.id)
    suposicoes: dict = {}
    parentes_arg: dict = {}
    resumo_parentes: dict = {}
    try:
        if exec_.modo == "cenario":
            num = exec_.cenario
            if num is None or not 1 <= num <= len(cenarios.CENARIOS):
                campos["cenario"] = "Cenário inexistente."
            exigir_campos(campos)
            c = cenarios.cenario_por_numero(num)
            caminho_mae, caminho_pai = (
                DIR_SINTETICOS / f"cenario_{num}_mae.vcf",
                DIR_SINTETICOS / f"cenario_{num}_pai.vcf",
            )
            if not caminho_mae.exists() or not caminho_pai.exists():
                raise HTTPException(409, "VCFs sintéticos ausentes; gere-os com `ela-preditivo gerar-cenarios`.")
            if not laudo:
                laudo = dict(c.laudo_c9orf72)
        else:
            caminho_mae, caminho_pai, suposicoes, parentes_arg, resumo_parentes = _preparar_vcfs_do_registro(
                config, cifra, p, pasta, exec_.assumir, campos, descendente, exec_.prior_avos
            )
            exigir_campos(campos)
            # genitor assumido não portador e sem laudo: a suposição cobre também o C9orf72 (laudo normal suposto),
            # senão o lócus ficaria indeterminado e o caso com um só parceiro testado nunca avaliaria o gene. Se algum
            # parente dele tem laudo, o C9orf72 do genitor é inferido por esse laudo, sem supor nada.
            for papel, lado in (("MAE", "mae"), ("PAI", "pai")):
                parente_com_laudo = (resumo_parentes.get(papel) or {}).get("com_laudo")
                if papel in suposicoes.get("nao_portador", []) and lado not in laudo and not parente_com_laudo:
                    laudo[lado] = cenarios.LAUDO_NORMAL
                    suposicoes.setdefault("laudo_normal_suposto", []).append(papel)
    except HTTPException:
        registro.descartar(ident)
        raise
    entrada = {
        "modo": exec_.modo,
        "cenario": exec_.cenario if exec_.modo == "cenario" else None,
        "laudo_c9orf72": laudo or None,
        "hipoteses_c9orf72": exec_.hipoteses,
        "sexo": sexo,
        "idade_atual": idade,
        "n": exec_.n,
        "semente": exec_.seed,
        "motor": exec_.motor,
        "comparar_cox": exec_.cox,
        "tornado": exec_.tornado,
        "paciente_id": p.id,
        "tipo": p.tipo,
        "descendente_id": descendente.id if descendente is not None else None,
        "assintomatico_confirmado": True if descendente is not None else None,
        "assintomatico_confirmado_em": iso(agora()) if descendente is not None else None,
        "suposicoes": suposicoes,
        "parentes": resumo_parentes or None,
        "prior_avos": exec_.prior_avos if resumo_parentes else None,
        "vcf_hash": {
            "mae": (p.genitor("MAE").vcf_hash or "")[:12] or None if p.genitor("MAE") else None,
            "pai": (p.genitor("PAI").vcf_hash or "")[:12] or None if p.genitor("PAI") else None,
        },
    }
    return _executar(
        registro,
        ident,
        pasta,
        bd,
        usuario,
        caminho_mae=caminho_mae,
        caminho_pai=caminho_pai,
        entrada=entrada,
        rotulo=rotulo,
        laudo=laudo,
        exec_=exec_,
        sexo=sexo,
        idade=idade,
        paciente=p,
        descendente=descendente,
        cifra=cifra,
        config=config,
        parentes=parentes_arg,
    )


@router.post("/analises", status_code=201)
def executar_analise(
    request: Request,
    usuario: Usuario = Depends(exigir(ANALISES_EXECUTAR)),
    modo: str = Form("vcf"),
    cenario: str | None = Form(None),
    vcf_mae: UploadFile | None = File(None),
    vcf_pai: UploadFile | None = File(None),
    c9orf72_mae: str | None = Form(None),
    c9orf72_pai: str | None = Form(None),
    c9_delta_mae: str | None = Form(None),
    c9_delta_pai: str | None = Form(None),
    c9_antecipacao: str | None = Form(None),
    sexo: str | None = Form(None),
    idade_atual: str | None = Form(None),
    n: str | None = Form(None),
    semente: str | None = Form(None),
    motor: str = Form("numpy"),
    cox: str | None = Form("1"),
    tornado: str | None = Form(None),
    paciente_id: str | None = Form(None),
    descendente_id: str | None = Form(None),
    sexo_filho: str | None = Form(None),
    assumir_nao_portador: str | None = Form(None),
    confirma_assintomatico: str | None = Form(None),
    prior_avos: str | None = Form(None),
):
    bd, config, cifra = obter_bd(request), request.app.state.config, obter_cifra(request)
    registro: RegistroAnalises = request.app.state.analises
    campos: dict[str, str] = {}
    if modo not in ("vcf", "cenario"):
        campos["modo"] = "Modo desconhecido."
    if motor not in MOTORES:
        campos["motor"] = "Motor desconhecido."
    n_ = _inteiro(n, "n", campos, 100, config.n_maximo_web, 10_000)
    seed = _inteiro(semente, "semente", campos, 0, 2**31 - 1, 42)
    hip = {
        "delta_mae": _inteiro(c9_delta_mae, "c9_delta_mae", campos, -200, 200),
        "delta_pai": _inteiro(c9_delta_pai, "c9_delta_pai", campos, -200, 200),
        "antecipacao": _decimal(c9_antecipacao, "c9_antecipacao", campos, 0, 40),
    }
    hipoteses = {k: v for k, v in hip.items() if v is not None} or None
    comparar_cox = str(cox or "").strip().lower() in ("1", "true", "sim", "on")
    com_tornado = str(tornado or "").strip().lower() in ("1", "true", "sim", "on")
    confirmou = str(confirma_assintomatico or "").strip().lower() in ("1", "true", "sim", "on")
    num_cenario = _inteiro(cenario, "cenario", campos, 1, len(cenarios.CENARIOS)) if modo == "cenario" else None
    if modo == "cenario" and num_cenario is None and "cenario" not in campos:
        campos["cenario"] = "Escolha o cenário de exemplo."

    # --- a partir de um registro (pessoa, casal ou família): VCFs, laudos, sexo e idade vêm da ficha ---
    if paciente_id not in (None, ""):
        pid = _inteiro(paciente_id, "paciente_id", campos, 1, 2**31 - 1)
        p = do_medico(bd, usuario, pid) if pid is not None else None
        assumir = frozenset(
            x.strip().upper() for x in str(assumir_nao_portador or "").replace(";", ",").split(",") if x.strip()
        )
        if assumir - {"MAE", "PAI"}:
            campos["assumir_nao_portador"] = "Use MAE, PAI ou MAE,PAI."
        sf = (sexo_filho or "").strip().upper() or None
        if sf not in (None, "M", "F"):
            campos["sexo_filho"] = "Sexo deve ser M ou F."
        exigir_campos(campos)
        descendente = None
        if p.tipo != "CASAL":
            did = _inteiro(descendente_id, "descendente_id", campos, 1, 2**31 - 1)
            if did is None:
                campos["descendente_id"] = "Indique o descendente a analisar."
            exigir_campos(campos)
            descendente = descendente_de(p, did)
        elif descendente_id not in (None, ""):
            exigir_campos({"descendente_id": "No caso 2 não há descendente: a análise é do futuro filho."})
        exec_ = Execucao(
            n=n_,
            seed=seed,
            motor=motor,
            cox=comparar_cox,
            tornado=com_tornado,
            hipoteses=hipoteses,
            assumir=assumir,
            sexo_filho=sf,
            modo=modo,
            cenario=num_cenario,
            assintomatico=confirmou,
            prior_avos=(prior_avos or "nao_portador").strip().lower(),
        )
        return executar_para_registro(bd, config, cifra, registro, usuario, p, descendente, exec_)

    # --- avulsa (sem registro): upload não guardado ou cenário de exemplo ---
    sexo_ = (sexo or "").strip().upper() or None
    if sexo_ not in (None, "M", "F"):
        campos["sexo"] = "Sexo deve ser M ou F."
    idade = _decimal(idade_atual, "idade_atual", campos, 0, 120, None)
    tem_pessoa = idade is not None and idade > 0  # idade vazia ou zero = futuro filho, sem pessoa a confirmar
    if tem_pessoa and not confirmou:
        campos["confirma_assintomatico"] = textos.ERRO_CONFIRMACAO_ASSINTOMATICO
    laudo = {}
    for lado, texto in (("mae", c9orf72_mae), ("pai", c9orf72_pai)):
        v = interpretar_laudo(texto, f"c9orf72_{lado}", campos)
        if v is not None:
            laudo[lado] = v
    if modo == "vcf":  # presença dos arquivos conferida já aqui, para devolver todos os erros de uma vez
        for lado, arquivo in (("mae", vcf_mae), ("pai", vcf_pai)):
            if arquivo is None or not arquivo.filename:
                campos[f"vcf_{lado}"] = "Envie o arquivo VCF."
    exigir_campos(campos)
    ident, pasta = registro.criar(usuario.id)
    rotulo = "caso"
    entrada = {
        "modo": modo,
        "cenario": None,
        "laudo_c9orf72": laudo or None,
        "hipoteses_c9orf72": hipoteses,
        "sexo": sexo_,
        "idade_atual": idade,
        "n": n_,
        "semente": seed,
        "motor": motor,
        "comparar_cox": comparar_cox,
        "tornado": com_tornado,
        "paciente_id": None,
        "tipo": None,
        "descendente_id": None,
        "assintomatico_confirmado": True if tem_pessoa else None,
        "assintomatico_confirmado_em": iso(agora()) if tem_pessoa else None,
        "suposicoes": {},
    }
    try:
        if modo == "cenario":
            c = cenarios.cenario_por_numero(num_cenario)
            caminho_mae = DIR_SINTETICOS / f"cenario_{num_cenario}_mae.vcf"
            caminho_pai = DIR_SINTETICOS / f"cenario_{num_cenario}_pai.vcf"
            if not caminho_mae.exists() or not caminho_pai.exists():
                raise HTTPException(409, "VCFs sintéticos ausentes; gere-os com `ela-preditivo gerar-cenarios`.")
            if not laudo:
                laudo = dict(c.laudo_c9orf72)
            entrada.update({"cenario": num_cenario, "laudo_c9orf72": laudo or None, "descricao_cenario": c.descricao})
            rotulo = f"Cenário {num_cenario}: {c.descricao}"
        else:
            caminho_mae = vcfs.guardar_upload(vcf_mae, pasta / "mae.vcf", "vcf_mae", campos, config.tamanho_maximo_vcf)
            caminho_pai = vcfs.guardar_upload(vcf_pai, pasta / "pai.vcf", "vcf_pai", campos, config.tamanho_maximo_vcf)
            exigir_campos(campos)
    except HTTPException:
        registro.descartar(ident)
        raise
    exec_ = Execucao(
        n=n_,
        seed=seed,
        motor=motor,
        cox=comparar_cox,
        hipoteses=hipoteses,
        modo=modo,
        cenario=num_cenario,
        tornado=com_tornado,
    )
    return _executar(
        registro,
        ident,
        pasta,
        bd,
        usuario,
        caminho_mae=caminho_mae,
        caminho_pai=caminho_pai,
        entrada=entrada,
        rotulo=rotulo,
        laudo=laudo,
        exec_=exec_,
        sexo=sexo_,
        idade=idade,
    )


def _analise_guardada(request: Request, usuario: Usuario, paciente_id: int, analise_id: int):
    bd, cifra, config = obter_bd(request), obter_cifra(request), request.app.state.config
    p = do_medico(bd, usuario, paciente_id)
    a = next((x for x in p.analises if x.id == analise_id), None)
    if a is None or not a.resultado_arquivo:
        raise HTTPException(404, "Resultado não encontrado.")
    return bd, cifra, config, p, a


@router.get("/pacientes/{paciente_id}/analises/{analise_id}")
def resultado_guardado(
    paciente_id: int, analise_id: int, request: Request, usuario: Usuario = Depends(exigir(ANALISES_EXECUTAR))
):
    """Resultado completo de uma análise guardada na ficha (JSON cifrado em disco), só para o médico dono."""
    bd, cifra, config, p, a = _analise_guardada(request, usuario, paciente_id, analise_id)
    resultado = json.loads(arquivos.ler(config.dir_analises, cifra, a.resultado_arquivo).decode("utf-8"))
    auditoria.registrar(
        bd,
        acao=auditoria.RESULTADO_ABERTO,
        usuario=usuario,
        alvo_tipo="analise_paciente",
        alvo_id=a.id,
        detalhe=f"paciente {p.id}",
    )
    bd.commit()
    return resultado


@router.get("/pacientes/{paciente_id}/analises/{analise_id}/figuras/{nome}")
def figura_guardada(
    paciente_id: int,
    analise_id: int,
    nome: str,
    request: Request,
    usuario: Usuario = Depends(exigir(ANALISES_EXECUTAR)),
):
    bd, cifra, config, p, a = _analise_guardada(request, usuario, paciente_id, analise_id)
    if not RE_NOME_FIGURA.match(nome) or not a.pacote_arquivo:
        raise HTTPException(404, "Figura não encontrada.")
    with zipfile.ZipFile(io.BytesIO(arquivos.ler(config.dir_analises, cifra, a.pacote_arquivo))) as z:
        membro = f"figuras/{nome}"
        if membro not in z.namelist():
            raise HTTPException(404, "Figura não encontrada.")
        dados = z.read(membro)
    return Response(content=dados, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/pacientes/{paciente_id}/analises/{analise_id}/pacote.zip")
def pacote_guardado(
    paciente_id: int, analise_id: int, request: Request, usuario: Usuario = Depends(exigir(ANALISES_BAIXAR))
):
    bd, cifra, config, p, a = _analise_guardada(request, usuario, paciente_id, analise_id)
    if not a.pacote_arquivo:
        raise HTTPException(404, "Pacote não encontrado.")
    dados = arquivos.ler(config.dir_analises, cifra, a.pacote_arquivo)
    auditoria.registrar(
        bd,
        acao=auditoria.PACOTE_BAIXADO,
        usuario=usuario,
        alvo_tipo="analise_paciente",
        alvo_id=a.id,
        detalhe=f"paciente {p.id}",
    )
    bd.commit()
    return Response(
        content=dados,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="analise_{a.id}.zip"', "Cache-Control": "no-store"},
    )


def _item(request: Request, usuario: Usuario, ident: str) -> dict:
    item = request.app.state.analises.obter(ident, usuario.id)
    if item is None:
        raise HTTPException(404, "Análise não encontrada ou expirada.")
    return item


@router.get("/analises/{ident}")
def ver_analise(ident: str, request: Request, usuario: Usuario = Depends(exigir(ANALISES_EXECUTAR))):
    return _item(request, usuario, ident)["resultado"]


@router.get("/analises/{ident}/figuras/{nome}")
def figura(ident: str, nome: str, request: Request, usuario: Usuario = Depends(exigir(ANALISES_EXECUTAR))):
    item = _item(request, usuario, ident)
    if not RE_NOME_FIGURA.match(nome) or nome not in {f["nome"] for f in item["resultado"]["figuras"]}:
        raise HTTPException(404, "Figura não encontrada.")
    caminho = item["pasta"] / "saida" / "figuras" / nome
    if not caminho.exists():
        raise HTTPException(404, "Figura não encontrada.")
    return FileResponse(caminho, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/analises/{ident}/pacote.zip")
def pacote(ident: str, request: Request, usuario: Usuario = Depends(exigir(ANALISES_BAIXAR))):
    """Pacote com relatório, tabelas, figuras, curvas e metadados (sem os VCFs), só para quem executou."""
    bd = obter_bd(request)
    item = _item(request, usuario, ident)
    saida = item["pasta"] / "saida"
    destino = item["pasta"] / "pacote.zip"
    if not destino.exists():
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(saida.rglob("*")):
                if p.is_file() and not p.name.endswith((".vcf", ".vcf.gz")):
                    z.write(p, p.relative_to(saida).as_posix())
    auditoria.registrar(bd, acao=auditoria.PACOTE_BAIXADO, usuario=usuario, alvo_tipo="analise", alvo_id=ident)
    bd.commit()
    return FileResponse(
        destino,
        media_type="application/zip",
        filename=f"analise_{ident[:8]}.zip",
        headers={"Cache-Control": "no-store"},
    )
