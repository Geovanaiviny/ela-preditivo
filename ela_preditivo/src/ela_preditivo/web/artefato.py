"""Artefato pela interface: os comandos da linha de comando que reproduzem e mantêm o artefato (`gerar-cenarios`,
`avaliar`, `tudo` e `atualizar-base`) executados a partir da plataforma, com as mesmas opções e as mesmas saídas.

Cada execução é uma tarefa: um processo separado que roda o próprio comando `ela-preditivo`, de modo que o que a
interface produz é, por construção, o que a linha de comando produz. O processo separado não bloqueia as análises
clínicas (que rodam uma por vez dentro do servidor) e não recebe a chave de cifra. A saída fica na pasta da tarefa, de
onde a interface lê relatórios, tabelas e figuras e monta o pacote .zip. Por aqui só passam dados sintéticos e a base
pública do ClinVar; nenhum dado de paciente.

`cobertura_cli()` declara, opção por opção, onde cada comando da linha de comando está na interface. Um teste percorre o
`argparse` e falha quando uma opção nova fica sem correspondente.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import DIR_DADOS, RAIZ_PROJETO, anotacao, atualizacao
from ..calibracao import CAMINHO_PADRAO
from ..relatorio import FONTE
from . import auditoria
from .analises import (
    BASE_PADRAO,
    BASE_SO_CURADA,
    _limpar,
    _registros,
    _secoes_relatorio,
    guardar_envio,
    guardar_parametros,
    nome_de_base_aceito,
    nomes_bases,
)
from .bd import agora
from .comum import ErroCampos, exigir_campos, iso, obter_bd, obter_config
from .config import Configuracao
from .modelos import Usuario
from .permissoes import ARTEFATO_EXECUTAR, BASE_GERIR, BASE_VER, MODELO_VER, exigir, tem_permissao

router = APIRouter(prefix="/api", tags=["artefato"])

SEMENTE_MAXIMA = 2**31 - 1
N_MAXIMO = 1_000_000
ORIGEM_PACOTE = "pacote"
G_VERIFICACAO = "Verificação com famílias sintéticas (calibração, discriminação, cobertura, tornado)"
G_BASE = "Base de anotação"
RE_ID = re.compile(r"^[0-9]{14}-[0-9a-f]{6}$")
RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_RELATORIO_BASE = re.compile(r"^atualizacao_[0-9-]{10}_[0-9-]{10}\.md$")
ESTADOS_FINAIS = ("concluida", "falhou", "cancelada", "interrompida")
LINHAS_MAXIMAS = 2000  # linhas de uma tabela devolvidas à interface (o CSV completo vai no pacote)
TIPOS_DE_ARQUIVO = {
    ".png": "image/png",
    ".csv": "text/csv; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json",
    ".vcf": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


# ---------------------------------------------------------------------------
# Especificação dos comandos: uma só tabela para validar, montar o processo e desenhar o formulário
# ---------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class Opcao:
    nome: str  # campo do formulário
    flag: str  # opção da linha de comando
    tipo: str  # inteiro | decimal | inteiros | escolha | marcacao | data | arquivo | base | origem
    rotulo: str
    padrao: object = None
    minimo: float | None = None
    maximo: float | None = None
    opcoes: tuple = ()
    dica: str = ""
    grupo: str = ""
    flags_extras: tuple = ()  # outras opções da linha de comando cobertas pelo mesmo campo


@dataclasses.dataclass(frozen=True)
class Comando:
    nome: str
    titulo: str
    descricao: str
    permissao: str
    opcoes: tuple
    fixos: tuple = ()  # argumentos sempre passados
    com_saida: bool = True  # o comando recebe --saida (a pasta da tarefa)
    duracao: str = ""


_VERIFICACAO = (
    Opcao("sem_metricas", "--sem-metricas", "marcacao", "Não calcular as métricas de verificação", grupo=G_VERIFICACAO),
    Opcao(
        "mundos",
        "--mundos",
        "inteiro",
        "Mundos",
        200,
        5,
        5000,
        dica="Em cada mundo a penetrância é sorteada uma vez.",
        grupo=G_VERIFICACAO,
    ),
    Opcao(
        "por_estrato",
        "--por-estrato",
        "inteiro",
        "Pessoas por estrato e mundo",
        10,
        2,
        500,
        dica="Estrato = cenário × sexo × idade atual.",
        grupo=G_VERIFICACAO,
    ),
    Opcao(
        "semente_coorte",
        "--seed-coorte",
        "inteiro",
        "Semente da coorte",
        None,
        0,
        SEMENTE_MAXIMA,
        dica="Vazio = derivada da semente.",
        grupo=G_VERIFICACAO,
    ),
)
_BASE = (
    Opcao(
        "base",
        "--base-clinvar",
        "base",
        "Base de anotação",
        BASE_PADRAO,
        dica="A base em uso, só a tabela curada ou um arquivo da pasta de bases.",
        grupo=G_BASE,
        flags_extras=("--so-tabela-curada",),
    ),
)
_CONFIG = Opcao(
    "config",
    "--config",
    "arquivo",
    "Parâmetros alternativos (YAML)",
    dica="Vazio = parâmetros do artefato. O arquivo em uso pode ser baixado em Modelo e parâmetros.",
)

COMANDOS: dict[str, Comando] = {
    c.nome: c
    for c in (
        Comando(
            "tudo",
            "Reprodução completa",
            "Gera os cenários, executa os cinco para os dois sexos, faz a avaliação transversal com as métricas de "
            "verificação e monta o índice. É o que produz a pasta de resultados do trabalho.",
            ARTEFATO_EXECUTAR,
            (
                Opcao("semente", "--seed", "inteiro", "Semente", 42, 0, SEMENTE_MAXIMA),
                Opcao("n", "--n", "inteiro", "N por execução", 10_000, 100, N_MAXIMO),
                Opcao(
                    "ns",
                    "--ns",
                    "inteiros",
                    "N da estabilidade",
                    (1_000, 10_000, 100_000),
                    100,
                    N_MAXIMO,
                    dica="Valores separados por vírgula.",
                ),
                Opcao("repeticoes", "--repeticoes", "inteiro", "Repetições por N", 30, 2, 500),
                Opcao("motor", "--motor", "escolha", "Motor", "pymc", opcoes=("pymc", "numpy")),
                Opcao("idade_atual", "--idade-atual", "decimal", "Idade atual do descendente (anos)", 30.0, 0, 120),
                Opcao("sem_cox", "--sem-cox", "marcacao", "Não ajustar o modelo de Cox de comparação"),
                _CONFIG,
                *_VERIFICACAO,
                *_BASE,
            ),
            duracao="vários minutos com as opções padrão, porque inclui a avaliação",
        ),
        Comando(
            "avaliar",
            "Avaliação transversal e métricas de verificação",
            "Estabilidade, tempo, coerência, calibração e sensibilidade nos cenários sintéticos (Tabelas 5 a 9) e a "
            "verificação com famílias sintéticas de desfecho conhecido (Tabelas 12 a 20, Figuras 10 a 12).",
            ARTEFATO_EXECUTAR,
            (
                Opcao(
                    "origem_cenarios",
                    "--dir-cenarios",
                    "origem",
                    "Cenários",
                    ORIGEM_PACOTE,
                    dica="Os VCFs sintéticos do artefato ou os de uma execução de Gerar cenários.",
                ),
                Opcao(
                    "cenarios",
                    "--cenarios",
                    "inteiros",
                    "Só estes cenários",
                    None,
                    1,
                    5,
                    dica="Números de 1 a 5 separados por vírgula. Vazio = todos.",
                ),
                Opcao(
                    "n",
                    "--n",
                    "inteiros",
                    "N da estabilidade",
                    (1_000, 10_000, 100_000),
                    100,
                    N_MAXIMO,
                    dica="Valores separados por vírgula.",
                ),
                Opcao("repeticoes", "--repeticoes", "inteiro", "Repetições por N", 30, 2, 500),
                Opcao("semente", "--seed", "inteiro", "Semente", 1000, 0, SEMENTE_MAXIMA),
                Opcao("sexo", "--sexo", "escolha", "Sexo do descendente", "F", opcoes=("F", "M")),
                Opcao(
                    "n_coerencia",
                    "--n-coerencia",
                    "inteiro",
                    "N da coerência e da sensibilidade",
                    10_000,
                    100,
                    N_MAXIMO,
                ),
                _CONFIG,
                *_VERIFICACAO,
                *_BASE,
            ),
            duracao="alguns minutos com as opções padrão",
        ),
        Comando(
            "gerar-cenarios",
            "Gerar cenários sintéticos",
            "Gera os VCFs sintéticos dos cinco cenários familiares e dos cenários com genitor sem exame. O pacote traz "
            "os arquivos; a execução pode servir de origem para a avaliação.",
            ARTEFATO_EXECUTAR,
            (
                Opcao("semente", "--seed", "inteiro", "Semente", 2026, 0, SEMENTE_MAXIMA),
                Opcao("sem_ruido", "--sem-ruido", "marcacao", "Sem variantes de ruído (só os lóci de risco)"),
            ),
            duracao="alguns segundos",
        ),
        Comando(
            "atualizar-base",
            "Baixar a release do ClinVar",
            "Baixa a release mensal do ClinVar (VCF GRCh38 do NCBI), guarda só os registros dos quatro genes, registra a "
            "versão e mostra o que mudou desde a anterior.",
            BASE_GERIR,
            (
                Opcao(
                    "release",
                    "--release",
                    "data",
                    "Release",
                    None,
                    dica="AAAA-MM-DD de uma release do arquivo mensal. Vazio = a mais recente.",
                ),
            ),
            fixos=("--baixar",),
            com_saida=False,
            duracao="alguns minutos, conforme a conexão",
        ),
    )
}
COMANDOS_DO_ARTEFATO = tuple(c for c in COMANDOS.values() if c.permissao == ARTEFATO_EXECUTAR)


def _texto(v) -> str:
    return "" if v is None else str(v).strip()


def _ligado(v) -> bool:
    return v is True or _texto(v).lower() in ("1", "true", "sim", "on")


def _numero(valor, o: Opcao, campos: dict, tipo: str | None = None):
    tipo = tipo or o.tipo
    if isinstance(valor, bool):
        campos[o.nome] = "Informe um número."
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    t = _texto(valor).replace(",", ".") if tipo == "decimal" else _texto(valor)
    if t == "":
        return None
    try:
        n = float(t) if tipo == "decimal" else int(t)
    except ValueError:
        campos[o.nome] = "Informe um número." if tipo == "decimal" else "Informe um número inteiro."
        return None
    if (o.minimo is not None and n < o.minimo) or (o.maximo is not None and n > o.maximo):
        campos[o.nome] = f"Informe um valor entre {o.minimo:g} e {o.maximo:g}."
        return None
    return n


def montar(
    comando: Comando,
    bruto: dict,
    pasta: Path,
    config: Configuracao,
    registro: "RegistroTarefas",
    arquivos: dict[str, Path] | None = None,
) -> tuple[dict, list[str], list[str]]:
    """Valida os valores do formulário contra a especificação do comando. Devolve os parâmetros normalizados, os
    argumentos do processo e os mesmos argumentos sem caminho da máquina (o comando equivalente mostrado na tela)."""
    campos: dict[str, str] = {}
    par: dict = {}
    args: list[str] = []
    mostra: list[str] = []
    arquivos = arquivos or {}

    def acrescentar(flag: str, valores=(), exibidos=None) -> None:
        args.extend([flag, *[str(v) for v in valores]])
        mostra.extend([flag, *[str(v) for v in (valores if exibidos is None else exibidos)]])

    for o in comando.opcoes:
        v = bruto.get(o.nome)
        if o.tipo == "marcacao":
            par[o.nome] = _ligado(v)
            if par[o.nome]:
                acrescentar(o.flag)
        elif o.tipo in ("inteiro", "decimal"):
            n = _numero(v, o, campos)
            n = o.padrao if n is None and o.nome not in campos else n
            par[o.nome] = n
            if n is not None:
                acrescentar(o.flag, [f"{n:g}" if o.tipo == "decimal" else n])
        elif o.tipo == "inteiros":
            partes = v if isinstance(v, (list, tuple)) else [x for x in re.split(r"[,;\s]+", _texto(v)) if x]
            numeros = [_numero(x, o, campos, "inteiro") for x in partes]
            if o.nome in campos:
                continue
            numeros = list(numeros) or (list(o.padrao) if o.padrao else [])
            if len(numeros) > 10:
                campos[o.nome] = "No máximo dez valores."
                continue
            par[o.nome] = numeros or None
            if numeros:
                acrescentar(o.flag, numeros)
        elif o.tipo == "escolha":
            t = _texto(v) or o.padrao
            if t not in o.opcoes:
                campos[o.nome] = "Valor fora das opções permitidas."
                continue
            par[o.nome] = t
            acrescentar(o.flag, [t])
        elif o.tipo == "data":
            t = _texto(v)
            par[o.nome] = t or None
            if t:
                try:
                    if not RE_DATA.match(t):
                        raise ValueError(t)
                    _dt.date.fromisoformat(t)
                except ValueError:
                    campos[o.nome] = "Use o formato AAAA-MM-DD."
                    continue
                acrescentar(o.flag, [t])
        elif o.tipo == "base":
            t = _texto(v) or BASE_PADRAO
            par[o.nome] = t
            if t == BASE_SO_CURADA:
                acrescentar("--so-tabela-curada")
            elif t != BASE_PADRAO:
                if t not in nomes_bases(config):
                    campos[o.nome] = "Base de anotação desconhecida."
                    continue
                acrescentar(o.flag, [Path(config.dir_bases) / t], [f"{Path(config.dir_bases).name}/{t}"])
        elif o.tipo == "origem":
            t = _texto(v) or ORIGEM_PACOTE
            par[o.nome] = t
            if t == ORIGEM_PACOTE:
                acrescentar(o.flag, [DIR_DADOS / "sinteticos"], ["data/sinteticos"])
            else:
                origem = registro.obter(t)
                if origem is None or origem["comando"] != "gerar-cenarios" or origem["estado"] != "concluida":
                    campos[o.nome] = "Escolha os cenários do artefato ou uma execução concluída de Gerar cenários."
                    continue
                acrescentar(o.flag, [registro.pasta(t) / "saida"], [f"<cenários da execução {t}>"])
        elif o.tipo == "arquivo":
            caminho = arquivos.get(o.nome)
            par[o.nome] = caminho is not None
            if caminho is not None:
                acrescentar(o.flag, [caminho], [caminho.name])
        else:  # pragma: no cover - especificação errada
            raise ValueError(f"tipo de opção desconhecido: {o.tipo}")
    exigir_campos(campos)
    if comando.com_saida:
        args = ["--saida", str(pasta / "saida"), *args]
        mostra = ["--saida", "saida", *mostra]
    return par, [comando.nome, *comando.fixos, *args], [comando.nome, *comando.fixos, *mostra]


def _opcao_publica(o: Opcao) -> dict:
    d = dataclasses.asdict(o)
    d["padrao"] = list(o.padrao) if isinstance(o.padrao, tuple) else o.padrao
    d["opcoes"], d["flags_extras"] = list(o.opcoes), list(o.flags_extras)
    return d


def _comando_publico(c: Comando) -> dict:
    return {
        "nome": c.nome,
        "titulo": c.titulo,
        "descricao": c.descricao,
        "duracao": c.duracao,
        "opcoes": [_opcao_publica(o) for o in c.opcoes],
    }


# ---------------------------------------------------------------------------
# Tarefas: uma execução por vez, cada uma no seu processo e na sua pasta
# ---------------------------------------------------------------------------
def _lancar_processo(argumentos: list[str], pasta: Path, ambiente: dict) -> subprocess.Popen:
    """Roda `ela-preditivo <argumentos>` com o mesmo Python do servidor; a saída do comando vai para `log.txt`."""
    with open(pasta / "log.txt", "w", encoding="utf-8") as log:
        return subprocess.Popen(
            [sys.executable, "-m", "ela_preditivo.cli", *argumentos],
            cwd=pasta,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=ambiente,
            start_new_session=(os.name == "posix"),
        )


def ambiente_do_processo(config: Configuracao) -> dict:
    """Ambiente do processo da tarefa: o do servidor, sem a chave de cifra e com a pasta de bases do servidor."""
    amb = {k: v for k, v in os.environ.items() if k != "ELA_WEB_CHAVE"}
    amb["ELA_DADOS_BRUTOS"] = str(config.dir_bases)
    amb.setdefault("PYTENSOR_FLAGS", "cxx=")
    amb["MPLBACKEND"] = "Agg"
    amb["PYTHONUNBUFFERED"] = "1"  # o registro aparece à medida que o comando escreve
    amb["PYTHONIOENCODING"] = "utf-8"
    return amb


class RegistroTarefas:
    """Execuções do artefato disparadas pela interface. O estado de cada uma fica em `tarefa.json`, na pasta dela."""

    def __init__(self, config: Configuracao, lancar=None):
        self.raiz = Path(config.dir_tarefas)
        self.guardadas = int(config.tarefas_guardadas)
        self._lancar = lancar or _lancar_processo
        self._processos: dict[str, subprocess.Popen] = {}
        self._lock = threading.RLock()

    def pasta(self, ident: str) -> Path:
        return self.raiz / ident

    def _ler(self, ident: str) -> dict | None:
        if not RE_ID.match(ident or ""):
            return None
        p = self.raiz / ident / "tarefa.json"
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _gravar(self, t: dict) -> None:
        p = self.raiz / t["id"] / "tarefa.json"
        parcial = p.with_name("tarefa.json.parcial")
        parcial.write_text(json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8")
        parcial.replace(p)

    def _fechar(self, t: dict, estado: str, mensagem: str | None = None, codigo: int | None = None) -> dict:
        t.update(
            estado=estado,
            concluida_em=iso(agora()),
            duracao_s=round(max(time.time() - float(t.get("inicio_epoch") or time.time()), 0.0), 1),
            codigo_saida=codigo,
            mensagem=mensagem,
        )
        self._gravar(t)
        return t

    def _atualizar(self, t: dict) -> dict:
        """Fecha a tarefa quando o processo dela terminou (ou sumiu com um reinício do servidor)."""
        if t["estado"] != "executando":
            return t
        proc = self._processos.get(t["id"])
        if proc is None:
            return self._fechar(t, "interrompida", "O servidor foi reiniciado durante a execução.")
        codigo = proc.poll()
        if codigo is None:
            return t
        self._processos.pop(t["id"], None)
        if codigo == 0:
            return self._fechar(t, "concluida", codigo=0)
        return self._fechar(t, "falhou", "O comando terminou com erro; veja o registro da execução.", codigo)

    def obter(self, ident: str) -> dict | None:
        with self._lock:
            t = self._ler(ident)
            return None if t is None else self._atualizar(t)

    def listar(self) -> list[dict]:
        with self._lock:
            if not self.raiz.is_dir():
                return []
            tarefas = [self._ler(d.name) for d in self.raiz.iterdir() if d.is_dir()]
            tarefas = [self._atualizar(t) for t in tarefas if t is not None]
        return sorted(tarefas, key=lambda t: float(t.get("inicio_epoch") or 0), reverse=True)

    def em_execucao(self) -> dict | None:
        return next((t for t in self.listar() if t["estado"] == "executando"), None)

    def iniciar(self, comando: Comando, preparar, usuario: Usuario, ambiente: dict) -> dict:
        """`preparar(pasta)` valida a entrada e devolve (parâmetros, argumentos, argumentos para exibição)."""
        with self._lock:
            if self.em_execucao() is not None:
                raise HTTPException(409, "Já há uma execução em andamento. Aguarde o término ou cancele-a.")
            ident = f"{agora():%Y%m%d%H%M%S}-{secrets.token_hex(3)}"
            pasta = self.raiz / ident
            (pasta / "saida").mkdir(parents=True, mode=0o700)
            (pasta / "entrada").mkdir(mode=0o700)
            try:
                parametros, argumentos, exibidos = preparar(pasta)
                self._processos[ident] = self._lancar(argumentos, pasta, ambiente)
            except Exception:
                shutil.rmtree(pasta, ignore_errors=True)
                raise
            t = {
                "id": ident,
                "comando": comando.nome,
                "titulo": comando.titulo,
                "estado": "executando",
                "iniciada_em": iso(agora()),
                "inicio_epoch": time.time(),
                "concluida_em": None,
                "duracao_s": None,
                "codigo_saida": None,
                "mensagem": None,
                "usuario_id": usuario.id,
                "papel": usuario.papel,
                "parametros": parametros,
                "linha_de_comando": "ela-preditivo " + " ".join(shlex.quote(a) for a in exibidos),
            }
            self._gravar(t)
            self._expurgar()
            return t

    def cancelar(self, ident: str) -> dict | None:
        with self._lock:
            t = self.obter(ident)
            if t is None or t["estado"] != "executando":
                return t
            proc = self._processos.pop(ident, None)
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(10)
            return self._fechar(t, "cancelada", "Execução cancelada.")

    def remover(self, ident: str) -> bool:
        with self._lock:
            t = self.obter(ident)
            if t is None or t["estado"] == "executando":
                return False
            shutil.rmtree(self.raiz / ident, ignore_errors=True)
            return True

    def _expurgar(self) -> None:
        """Mantém as execuções mais recentes; as antigas já encerradas saem do disco."""
        for t in self.listar()[self.guardadas :]:
            if t["estado"] in ESTADOS_FINAIS:
                shutil.rmtree(self.raiz / t["id"], ignore_errors=True)

    def encerrar(self) -> None:
        """Fim do servidor: as execuções em andamento são encerradas e ficam marcadas como interrompidas."""
        with self._lock:
            for ident, proc in list(self._processos.items()):
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                t = self._ler(ident)
                if t is not None and t["estado"] == "executando":
                    self._fechar(t, "interrompida", "O servidor foi encerrado durante a execução.")
            self._processos.clear()


# ---------------------------------------------------------------------------
# Leitura da saída de uma tarefa (relatórios, tabelas, figuras), sem caminho da máquina
# ---------------------------------------------------------------------------
def _sem_caminhos(texto: str, *pastas: Path) -> str:
    for p in (*pastas, RAIZ_PROJETO.parent, Path.home()):
        texto = texto.replace(str(p) + os.sep, "").replace(str(p), ".")
    return texto


def _registro_da_execucao(pasta: Path, linhas: int = 60) -> str:
    p = pasta / "log.txt"
    if not p.is_file():
        return ""
    with open(p, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(f.tell() - 30_000, 0))
        texto = f.read().decode("utf-8", errors="replace")
    return "\n".join(_sem_caminhos(texto, pasta / "saida", pasta).splitlines()[-linhas:])


def _titulo(markdown: Path) -> str:
    with open(markdown, encoding="utf-8") as f:
        for linha in f:
            if linha.startswith("# "):
                return linha[2:].strip()
    return markdown.parent.name


def _tabela(csv: Path) -> dict:
    """Tabela gravada por `relatorio.salvar_tabela`: o CSV com os números e o .md com a legenda e a nota."""
    legenda, nota = csv.stem, ""
    md = csv.with_suffix(".md")
    if md.is_file():
        texto = md.read_text(encoding="utf-8")
        primeira = texto.splitlines()[0].strip() if texto.strip() else ""
        if primeira.startswith("**") and primeira.endswith("**"):
            legenda = primeira[2:-2]
        nota = texto.split(f"*{FONTE}*", 1)[1].strip() if f"*{FONTE}*" in texto else ""
    df = pd.read_csv(csv)
    return {
        "nome": csv.stem,
        "legenda": legenda,
        "nota": nota,
        "colunas": list(df.columns),
        "linhas": _registros(df.head(LINHAS_MAXIMAS)),
        "total_de_linhas": int(len(df)),
    }


def _figuras(markdown: str, pasta: Path, saida: Path) -> list[dict]:
    """Figuras citadas no relatório, na ordem em que aparecem, com o caminho relativo à saída da tarefa."""
    figuras = []
    for legenda, rel in re.findall(r"^!\[(.*)\]\(([^()\s]+\.png)\)\s*$", markdown, flags=re.MULTILINE):
        p = (pasta / rel).resolve()
        if p.is_file() and p.is_relative_to(saida.resolve()):
            figuras.append({"nome": p.name, "legenda": legenda, "caminho": p.relative_to(saida.resolve()).as_posix()})
    return figuras


def relatorio_da_pasta(pasta: Path, saida: Path) -> dict | None:
    """Relatório de uma pasta da saída (`relatorio.md`, `tabelas/`, `figuras/`, `metadados.json`) no formato que a
    interface desenha. Na raiz de uma reprodução completa não há relatório, e sim o índice `README.md`: dele saem o
    resumo da execução, a tabela consolidada e as figuras por cenário."""
    rel = pasta / "relatorio.md"
    indice = pasta / "README.md"
    if rel.is_file():
        texto = rel.read_text(encoding="utf-8")
        secoes = _secoes_relatorio(rel)
    elif indice.is_file() and pasta.resolve() == saida.resolve():
        texto = indice.read_text(encoding="utf-8")
        resumo = [
            linha
            for linha in texto.split("\n## ", 1)[0].splitlines()[1:]
            if linha.strip() and not linha.startswith(">")
        ]
        secoes = [{"titulo": "Resumo da execução", "texto": "\n".join(resumo)}]
        rel = indice
    else:
        return None
    meta = {}
    if (pasta / "metadados.json").is_file():
        try:
            meta = json.loads((pasta / "metadados.json").read_text(encoding="utf-8"))
        except ValueError:
            meta = {}
    tabelas = [_tabela(c) for c in sorted((pasta / "tabelas").glob("*.csv"))] if (pasta / "tabelas").is_dir() else []
    return _limpar(
        {
            "pasta": (
                "" if pasta.resolve() == saida.resolve() else pasta.resolve().relative_to(saida.resolve()).as_posix()
            ),
            "titulo": _titulo(rel),
            "secoes": secoes,
            "tabelas": tabelas,
            "figuras": _figuras(texto, pasta, saida),
            "metadados": {k: v for k, v in meta.items() if k != "aviso_legal"},
            "relatorio_md": texto,
        }
    )


def indice_da_saida(saida: Path) -> dict:
    """O que há na saída: os relatórios (pastas com `relatorio.md`, mais o índice da raiz) e todos os arquivos."""
    relatorios = []
    if (saida / "README.md").is_file() and not (saida / "relatorio.md").is_file():
        relatorios.append({"pasta": "", "titulo": "Índice e tabela consolidada"})
    for rel in sorted(saida.rglob("relatorio.md")):
        pasta = rel.parent.relative_to(saida).as_posix()
        relatorios.append({"pasta": "" if pasta == "." else pasta, "titulo": _titulo(rel)})
    arquivos = [
        {"caminho": p.relative_to(saida).as_posix(), "tamanho": p.stat().st_size}
        for p in sorted(saida.rglob("*"))
        if p.is_file()
    ]
    return {"relatorios": relatorios, "arquivos": arquivos[:5000], "total_de_arquivos": len(arquivos)}


def _dentro(saida: Path, relativo: str | None) -> Path:
    """Caminho relativo à saída da tarefa, recusando qualquer coisa que saia dela."""
    relativo = relativo or ""
    if len(relativo) > 300 or "\x00" in relativo or relativo.startswith(("/", "\\")) or ":" in relativo:
        raise HTTPException(404, "Arquivo não encontrado.")
    raiz = saida.resolve()
    p = (raiz / relativo).resolve()
    if not p.is_relative_to(raiz):
        raise HTTPException(404, "Arquivo não encontrado.")
    return p


def _publica(t: dict, usuario: Usuario, registro: RegistroTarefas | None = None) -> dict:
    """Tarefa como a interface a vê; com `registro`, inclui o registro da execução e o índice da saída."""
    d = {
        k: t.get(k)
        for k in (
            "id",
            "comando",
            "titulo",
            "estado",
            "iniciada_em",
            "concluida_em",
            "duracao_s",
            "codigo_saida",
            "mensagem",
            "papel",
            "parametros",
            "linha_de_comando",
        )
    }
    d["minha"] = t.get("usuario_id") == usuario.id
    if t["estado"] == "executando":
        d["decorrido_s"] = round(max(time.time() - float(t.get("inicio_epoch") or time.time()), 0.0), 1)
    if registro is not None:
        pasta = registro.pasta(t["id"])
        d["registro"] = _registro_da_execucao(pasta)
        d["saida"] = indice_da_saida(pasta / "saida") if t["estado"] == "concluida" else None
    return d


def _tarefa(request: Request, ident: str, comandos: tuple[str, ...]) -> dict:
    t = request.app.state.tarefas.obter(ident)
    if t is None or t["comando"] not in comandos:
        raise HTTPException(404, "Execução não encontrada.")
    return t


def _iniciar(request: Request, usuario: Usuario, comando: Comando, bruto: dict, envios: dict) -> dict:
    config, registro, bd = obter_config(request), request.app.state.tarefas, obter_bd(request)

    def preparar(pasta: Path):
        campos: dict[str, str] = {}
        arquivos = {}
        for o in comando.opcoes:
            if o.tipo == "arquivo" and envios.get(o.nome) is not None and envios[o.nome].filename:
                arquivos[o.nome] = guardar_parametros(
                    envios[o.nome],
                    pasta / "entrada" / "parametros.yaml",
                    o.nome,
                    campos,
                    config.tamanho_maximo_parametros,
                )
        exigir_campos(campos)
        return montar(comando, bruto, pasta, config, registro, {k: v for k, v in arquivos.items() if v is not None})

    t = registro.iniciar(comando, preparar, usuario, ambiente_do_processo(config))
    auditoria.registrar(
        bd,
        acao=auditoria.TAREFA_INICIADA,
        usuario=usuario,
        alvo_tipo="tarefa",
        alvo_id=t["id"],
        detalhe=f"comando={comando.nome}",
    )
    bd.commit()
    return t


# ---------------------------------------------------------------------------
# Rotas: reprodução, avaliação e cenários
# ---------------------------------------------------------------------------
NOMES_DO_ARTEFATO = tuple(c.nome for c in COMANDOS_DO_ARTEFATO)


@router.get("/artefato/comandos")
def listar_comandos(request: Request, usuario: Usuario = Depends(exigir(ARTEFATO_EXECUTAR))):
    """Comandos que a interface executa, com as opções (as mesmas da linha de comando) para desenhar os formulários."""
    config, registro = obter_config(request), request.app.state.tarefas
    em_uso = anotacao.localizar_base_real(config.dir_bases)
    andamento = registro.em_execucao()
    return {
        "comandos": [_comando_publico(c) for c in COMANDOS_DO_ARTEFATO],
        "bases": nomes_bases(config),
        "base_em_uso": em_uso.name if em_uso is not None else None,
        "origens": [
            {"id": t["id"], "iniciada_em": t["iniciada_em"]}
            for t in registro.listar()
            if t["comando"] == "gerar-cenarios" and t["estado"] == "concluida"
        ],
        "em_andamento": andamento["id"] if andamento is not None else None,
        "equivalencia": [
            {"comando": comando, "opcao": flag, "onde": c.onde, "campo": c.campo}
            for comando, flags in cobertura_cli().items()
            for flag, c in flags.items()
        ],
    }


@router.get("/artefato/tarefas")
def listar_tarefas(request: Request, usuario: Usuario = Depends(exigir(ARTEFATO_EXECUTAR))):
    tarefas = [t for t in request.app.state.tarefas.listar() if t["comando"] in NOMES_DO_ARTEFATO]
    return {"tarefas": [_publica(t, usuario) for t in tarefas]}


@router.post("/artefato/tarefas", status_code=201)
def iniciar_tarefa(
    request: Request,
    usuario: Usuario = Depends(exigir(ARTEFATO_EXECUTAR)),
    comando: str = Form(""),
    parametros: str = Form("{}"),
    arquivo_config: UploadFile | None = File(None, alias="config"),
):
    """Dispara um comando do artefato. `parametros` é um objeto JSON com os campos do formulário do comando."""
    cmd = COMANDOS.get(comando)
    if cmd is None or cmd.permissao != ARTEFATO_EXECUTAR:
        exigir_campos({"comando": "Comando desconhecido."})
    try:
        bruto = json.loads(parametros or "{}")
    except ValueError:
        bruto = None
    if not isinstance(bruto, dict):
        exigir_campos({"parametros": "Parâmetros inválidos."})
    return _publica(_iniciar(request, usuario, cmd, bruto, {"config": arquivo_config}), usuario)


@router.get("/artefato/tarefas/{ident}")
def ver_tarefa(ident: str, request: Request, usuario: Usuario = Depends(exigir(ARTEFATO_EXECUTAR))):
    return _publica(_tarefa(request, ident, NOMES_DO_ARTEFATO), usuario, request.app.state.tarefas)


@router.delete("/artefato/tarefas/{ident}")
def cancelar_ou_remover_tarefa(ident: str, request: Request, usuario: Usuario = Depends(exigir(ARTEFATO_EXECUTAR))):
    """Em andamento: cancela. Encerrada: remove a pasta. Só quem disparou a execução."""
    registro, bd = request.app.state.tarefas, obter_bd(request)
    t = _tarefa(request, ident, NOMES_DO_ARTEFATO)
    if t.get("usuario_id") != usuario.id:
        raise HTTPException(403, "Só quem disparou a execução pode cancelá-la ou removê-la.")
    if t["estado"] == "executando":
        t = registro.cancelar(ident)
        acao, resposta = auditoria.TAREFA_CANCELADA, _publica(t, usuario)
    else:
        registro.remover(ident)
        acao, resposta = auditoria.TAREFA_REMOVIDA, {"removida": True}
    auditoria.registrar(bd, acao=acao, usuario=usuario, alvo_tipo="tarefa", alvo_id=ident)
    bd.commit()
    return resposta


def _saida_concluida(request: Request, ident: str) -> Path:
    t = _tarefa(request, ident, NOMES_DO_ARTEFATO)
    if t["estado"] != "concluida":
        raise HTTPException(409, "A execução ainda não tem saída: aguarde o término.")
    return request.app.state.tarefas.pasta(ident) / "saida"


@router.get("/artefato/tarefas/{ident}/relatorio")
def relatorio_da_tarefa(
    ident: str, request: Request, pasta: str = "", usuario: Usuario = Depends(exigir(ARTEFATO_EXECUTAR))
):
    """Um relatório da saída: `pasta` vazia é a raiz (a avaliação, ou o índice de uma reprodução completa)."""
    saida = _saida_concluida(request, ident)
    alvo = _dentro(saida, pasta)
    r = relatorio_da_pasta(alvo, saida) if alvo.is_dir() else None
    if r is None:
        raise HTTPException(404, "Relatório não encontrado.")
    return r


@router.get("/artefato/tarefas/{ident}/arquivo")
def arquivo_da_tarefa(
    ident: str, request: Request, caminho: str = "", usuario: Usuario = Depends(exigir(ARTEFATO_EXECUTAR))
):
    """Um arquivo da saída (figura, tabela, relatório, VCF sintético)."""
    alvo = _dentro(_saida_concluida(request, ident), caminho)
    if not caminho or not alvo.is_file():
        raise HTTPException(404, "Arquivo não encontrado.")
    tipo = TIPOS_DE_ARQUIVO.get(alvo.suffix.lower(), "application/octet-stream")
    return FileResponse(
        alvo,
        media_type=tipo,
        filename=None if tipo == "image/png" else alvo.name,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/artefato/tarefas/{ident}/pacote.zip")
def pacote_da_tarefa(ident: str, request: Request, usuario: Usuario = Depends(exigir(ARTEFATO_EXECUTAR))):
    """A pasta de saída inteira, como a linha de comando a teria escrito."""
    bd = obter_bd(request)
    saida = _saida_concluida(request, ident)
    destino = saida.parent / "pacote.zip"
    if not destino.is_file():
        parcial = saida.parent / "pacote.zip.parcial"
        with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(saida.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(saida).as_posix())
        parcial.replace(destino)
    auditoria.registrar(bd, acao=auditoria.PACOTE_BAIXADO, usuario=usuario, alvo_tipo="tarefa", alvo_id=ident)
    bd.commit()
    comando = _tarefa(request, ident, NOMES_DO_ARTEFATO)["comando"]
    return FileResponse(
        destino,
        media_type="application/zip",
        filename=f"ela_preditivo_{comando}_{ident[:14]}.zip",
        headers={"Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------
# Rotas: arquivos de parâmetros em uso (para baixar, editar e reenviar como parâmetros alternativos)
# ---------------------------------------------------------------------------
@router.get("/parametros/arquivo")
def baixar_parametros(usuario: Usuario = Depends(exigir(MODELO_VER))):
    return FileResponse(
        CAMINHO_PADRAO,
        media_type="text/plain; charset=utf-8",
        filename=CAMINHO_PADRAO.name,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/parametros/tabela-variantes")
def baixar_tabela_variantes(usuario: Usuario = Depends(exigir(MODELO_VER))):
    return FileResponse(
        anotacao.CAMINHO_TABELA,
        media_type="text/csv; charset=utf-8",
        filename=anotacao.CAMINHO_TABELA.name,
        headers={"Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------
# Rotas: base de anotação (ClinVar dos quatro genes) e registro de versões
# ---------------------------------------------------------------------------
_identidades: dict[tuple, dict] = {}


def _identidade(caminho: Path) -> dict:
    """`anotacao.identificar_base` com memória por (arquivo, data, tamanho): o sha256 de uma base grande é caro."""
    st = caminho.stat()
    chave = (str(caminho), st.st_mtime_ns, st.st_size)
    if chave not in _identidades:
        _identidades[chave] = anotacao.identificar_base(caminho)
    return _identidades[chave]


def _versao_publica(v: dict) -> dict:
    return {k: x for k, x in v.items() if k != "caminho"}


def _dir_versoes(config: Configuracao) -> Path:
    return Path(config.dir_bases) / "versoes"


@router.get("/base")
def ver_base(request: Request, usuario: Usuario = Depends(exigir(BASE_VER))):
    """A base de anotação em uso, os arquivos da pasta de bases e as versões registradas."""
    config, registro = obter_config(request), request.app.state.tarefas
    d = Path(config.dir_bases)
    em_uso = anotacao.localizar_base_real(d)
    versoes = atualizacao.carregar_registro(_dir_versoes(config))
    registradas = {v.get("sha256"): v for v in versoes}
    arquivos = []
    for nome in nomes_bases(config):
        ident = _identidade(d / nome)
        arquivos.append(
            {
                "nome": nome,
                "tamanho": ident["tamanho_bytes"],
                "sha256": ident["sha256"],
                # a data vem do arquivo; quando ele não a traz, vale a informada ao registrar a versão
                "release": ident["release"] or (registradas.get(ident["sha256"]) or {}).get("release"),
                "em_uso": em_uso is not None and em_uso.name == nome,
                "registrada": ident["sha256"] in registradas,
            }
        )
    relatorios = (
        sorted(p.name for p in _dir_versoes(config).glob("atualizacao_*.md") if RE_RELATORIO_BASE.match(p.name))
        if _dir_versoes(config).is_dir()
        else []
    )
    baixando = next((t for t in registro.listar() if t["comando"] == "atualizar-base"), None)
    return {
        "pasta": d.name,
        "em_uso": next((a for a in arquivos if a["em_uso"]), None),
        "sem_base": (
            "Nenhuma base real na pasta de bases: as análises usam só a tabela curada." if em_uso is None else None
        ),
        "arquivos": arquivos,
        "nomes_aceitos": [*anotacao.ARQUIVOS_BASE_REAL, "clinvar*.vcf", "clinvar*.vcf.gz"],
        "versoes": [_versao_publica(v) for v in reversed(versoes)],
        "relatorios": relatorios,
        "pode_gerir": tem_permissao(usuario.papel, BASE_GERIR),
        "fonte_do_download": atualizacao.URL_CLINVAR_VCF,
        "tarefa": _publica(baixando, usuario, registro) if baixando is not None else None,
        "comando_baixar": _comando_publico(COMANDOS["atualizar-base"]),
    }


@router.get("/base/relatorios/{nome}")
def relatorio_de_atualizacao(nome: str, request: Request, usuario: Usuario = Depends(exigir(BASE_VER))):
    """Relatório do que mudou entre duas versões registradas da base."""
    p = _dir_versoes(obter_config(request)) / nome
    if not RE_RELATORIO_BASE.match(nome) or not p.is_file():
        raise HTTPException(404, "Relatório não encontrado.")
    return {"nome": nome, "texto": p.read_text(encoding="utf-8")}


def _release(texto: str | None, campos: dict) -> str | None:
    t = _texto(texto)
    if not t:
        return None
    try:
        if not RE_DATA.match(t):
            raise ValueError(t)
        _dt.date.fromisoformat(t)
    except ValueError:
        campos["release"] = "Use o formato AAAA-MM-DD."
        return None
    return t


def _registrar_versao(config: Configuracao, caminho: Path, release: str | None, origem: str) -> dict:
    """`ela-preditivo atualizar-base --base ARQUIVO [--release R]`: registra e compara com a versão anterior."""
    if release is None and _identidade(caminho)["release"] is None:
        raise ErroCampos(
            422,
            "Informe a release da base.",
            {"release": "Este arquivo não traz a data da release no cabeçalho nem no nome; informe-a (AAAA-MM-DD)."},
        )
    try:
        r = atualizacao.atualizar(caminho, diretorio=_dir_versoes(config), release=release, origem=origem)
    except Exception as e:  # noqa: BLE001
        raise ErroCampos(
            422, "Não foi possível registrar a base.", {"arquivo": f"Não foi possível ler a base ({type(e).__name__})."}
        ) from e
    return {
        "atual": _versao_publica(r["atual"]),
        "anterior": _versao_publica(r["anterior"]) if r["anterior"] else None,
        "relatorio": Path(r["relatorio"]).name if r["relatorio"] else None,
        "resumo": _sem_caminhos(atualizacao.resumo_texto(r), _dir_versoes(config), Path(config.dir_bases)),
    }


class RegistroDeVersao(BaseModel):
    arquivo: str | None = None
    release: str | None = None


@router.post("/base/versoes", status_code=201)
def registrar_versao_da_base(dados: RegistroDeVersao, request: Request, usuario: Usuario = Depends(exigir(BASE_GERIR))):
    """Registra a versão de uma base da pasta (padrão: a em uso) e compara com a registrada antes."""
    config, bd = obter_config(request), obter_bd(request)
    campos: dict[str, str] = {}
    release = _release(dados.release, campos)
    if dados.arquivo:
        if dados.arquivo not in nomes_bases(config):
            campos["arquivo"] = "Base de anotação desconhecida."
        caminho = Path(config.dir_bases) / dados.arquivo
    else:
        caminho = anotacao.localizar_base_real(config.dir_bases)
        if caminho is None:
            raise HTTPException(409, "Nenhuma base na pasta de bases: envie um arquivo ou baixe a release do ClinVar.")
    exigir_campos(campos)
    r = _registrar_versao(config, caminho, release, f"interface (usuário {usuario.id})")
    auditoria.registrar(
        bd,
        acao=auditoria.BASE_REGISTRADA,
        usuario=usuario,
        alvo_tipo="base",
        alvo_id=r["atual"]["sha256"][:12],
        detalhe=f"arquivo={caminho.name}; release={r['atual']['release']}",
    )
    bd.commit()
    return r


@router.post("/base/arquivos", status_code=201)
def enviar_base(
    request: Request,
    usuario: Usuario = Depends(exigir(BASE_GERIR)),
    arquivo: UploadFile | None = File(None),
    release: str | None = Form(None),
):
    """Envia uma base para a pasta de bases (o mesmo que copiá-la para lá) e registra a versão. Um arquivo de mesmo
    nome que já esteja na pasta é guardado em `anteriores/` antes de ser substituído."""
    config, bd = obter_config(request), obter_bd(request)
    campos: dict[str, str] = {}
    rel = _release(release, campos)
    nome = Path(arquivo.filename).name if arquivo is not None and arquivo.filename else ""
    if not nome:
        campos["arquivo"] = "Envie o arquivo da base."
    elif not nome_de_base_aceito(nome):
        campos["arquivo"] = (
            "Nome de arquivo não reconhecido. Use " + ", ".join(anotacao.ARQUIVOS_BASE_REAL) + " ou clinvar*.vcf(.gz)."
        )
    exigir_campos(campos)
    d = Path(config.dir_bases)
    chegada = d / "_envio" / secrets.token_hex(6)
    try:
        recebido = guardar_envio(arquivo, chegada / nome, "arquivo", campos, config.tamanho_maximo_base)
        exigir_campos(campos)
        try:
            n = len(anotacao.carregar_base_real(recebido))
        except Exception as e:  # noqa: BLE001
            raise ErroCampos(
                422,
                "Não foi possível ler a base.",
                {"arquivo": f"O conteúdo não é uma base do ClinVar que o artefato consiga ler ({type(e).__name__})."},
            ) from e
        if n == 0:
            exigir_campos({"arquivo": "A base não traz variantes dos quatro genes do artefato."})
        ident = anotacao.identificar_base(recebido)
        if rel is None and ident["release"] is None:
            exigir_campos(
                {"release": "Este arquivo não traz a data da release no cabeçalho nem no nome; informe-a (AAAA-MM-DD)."}
            )
        destino = d / nome
        substituida = None
        if destino.is_file() and _identidade(destino)["sha256"] != ident["sha256"]:
            (d / "anteriores").mkdir(exist_ok=True)
            substituida = f"{_identidade(destino)['sha256'][:8]}_{nome}"
            destino.replace(d / "anteriores" / substituida)
        recebido.replace(destino)
    finally:
        shutil.rmtree(chegada, ignore_errors=True)
        if (d / "_envio").is_dir() and not any((d / "_envio").iterdir()):
            (d / "_envio").rmdir()
    r = _registrar_versao(config, destino, rel, f"enviada pela interface (usuário {usuario.id})")
    em_uso = anotacao.localizar_base_real(d)
    r.update(arquivo=nome, variantes=n, substituida=substituida, em_uso=em_uso is not None and em_uso.name == nome)
    auditoria.registrar(
        bd,
        acao=auditoria.BASE_ENVIADA,
        usuario=usuario,
        alvo_tipo="base",
        alvo_id=ident["sha256"][:12],
        detalhe=f"arquivo={nome}; release={r['atual']['release']}; variantes={n}",
    )
    bd.commit()
    return r


class DownloadDaBase(BaseModel):
    release: str | None = None


@router.post("/base/baixar", status_code=201)
def baixar_base(dados: DownloadDaBase, request: Request, usuario: Usuario = Depends(exigir(BASE_GERIR))):
    """`ela-preditivo atualizar-base --baixar [--release R]`, em segundo plano."""
    t = _iniciar(request, usuario, COMANDOS["atualizar-base"], {"release": dados.release}, {})
    return _publica(t, usuario, request.app.state.tarefas)


@router.get("/base/tarefas/{ident}")
def ver_download_da_base(ident: str, request: Request, usuario: Usuario = Depends(exigir(BASE_VER))):
    return _publica(_tarefa(request, ident, ("atualizar-base",)), usuario, request.app.state.tarefas)


# ---------------------------------------------------------------------------
# Equivalência com a linha de comando
# ---------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class Cobertura:
    onde: str  # tela ou mecanismo que cobre a opção
    campo: str | None = None  # nome do campo do formulário, quando há um


TELA_ANALISE = "Nova análise sem registro"
TELA_FICHA = "Ficha do registro"
TELA_ARTEFATO = "Artefato"
TELA_BASE = "Base de anotação"
SERVIDOR = "gerida pelo servidor"
ARRANQUE = "arranque do serviço (docker compose)"
TELA_PRIMEIRO_ACESSO = "Primeiro acesso"


def cobertura_cli() -> dict[str, dict[str, Cobertura]]:
    """Para cada comando e opção da linha de comando, onde a interface oferece o mesmo."""
    cob: dict[str, dict[str, Cobertura]] = {}
    for c in COMANDOS_DO_ARTEFATO:
        flags = {"--saida": Cobertura(f"{SERVIDOR}: pasta da execução, baixada como pacote .zip")}
        for o in c.opcoes:
            for flag in (o.flag, *o.flags_extras):
                flags[flag] = Cobertura(f"{TELA_ARTEFATO} › {c.titulo}", o.nome)
        cob[c.nome] = flags
    cob["atualizar-base"] = {
        "--listar": Cobertura(f"{TELA_BASE} › Versões registradas"),
        "--base": Cobertura(f"{TELA_BASE} › Enviar base e Registrar versão", "arquivo"),
        "--baixar": Cobertura(f"{TELA_BASE} › Baixar a release do ClinVar"),
        "--release": Cobertura(f"{TELA_BASE} › campo Release", "release"),
        "--registro": Cobertura(f"{SERVIDOR}: pasta de versões dentro da pasta de bases"),
        "--destino": Cobertura(f"{SERVIDOR}: pasta de bases"),
    }
    analise = {
        "--vcf-mae": "vcf_mae",
        "--vcf-pai": "vcf_pai",
        "--sexo": "sexo",
        "--idade-atual": "idade_atual",
        "--n": "n",
        "--seed": "semente",
        "--motor": "motor",
        "--config": "config",
        "--tabela-variantes": "tabela_variantes",
        "--horizonte": "horizonte",
        "--rotulo": "rotulo",
        "--sem-figuras": "sem_figuras",
        "--c9orf72-mae": "c9orf72_mae",
        "--c9orf72-pai": "c9orf72_pai",
        "--amostra-mae": "amostra_mae",
        "--amostra-pai": "amostra_pai",
        "--c9-delta-mae": "c9_delta_mae",
        "--c9-delta-pai": "c9_delta_pai",
        "--c9-antecipacao": "c9_antecipacao",
        "--cox": "cox",
        "--tornado": "tornado",
        "--base-clinvar": "base",
        "--so-tabela-curada": "base",
    }
    executar = {flag: Cobertura(TELA_ANALISE, campo) for flag, campo in analise.items()}
    executar["--saida"] = Cobertura(f"{SERVIDOR}: resultado na tela e pacote .zip")
    for lado in ("da-mae", "do-pai"):
        for parente in ("pai", "mae", "irmao"):
            executar[f"--vcf-{parente}-{lado}"] = Cobertura(f"{TELA_FICHA} › Adicionar parente testado (VCF)")
            executar[f"--c9orf72-{parente}-{lado}"] = Cobertura(f"{TELA_FICHA} › Adicionar parente testado (laudo)")
    for lado in ("mae", "pai"):
        executar[f"--situacao-{lado}"] = Cobertura(f"{TELA_FICHA} › Situação clínica do genitor sem exame")
        executar[f"--idade-{lado}"] = Cobertura(f"{TELA_FICHA} › Situação clínica do genitor sem exame (idade)")
    executar["--vcf-filho-testado"] = Cobertura(f"{TELA_FICHA} › VCF do filho que já fez o teste")
    executar["--prior-avos"] = Cobertura(f"{TELA_FICHA} › Nova análise do registro", "prior_avos")
    cob["executar"] = executar
    cob["verificar-auditoria"] = {}
    cob["servir"] = {"--host": Cobertura(ARRANQUE), "--porta": Cobertura(ARRANQUE)}
    cob["gerar-chave"] = {}
    cob["popular-demo"] = {}
    criar = f"{TELA_PRIMEIRO_ACESSO} › Criar o administrador; depois, Usuários › Novo administrador"
    cob["criar-admin"] = {
        "--nome": Cobertura(criar, "nome"),
        "--cpf": Cobertura(criar, "cpf"),
        "--email": Cobertura(criar, "email"),
        "--senha": Cobertura(
            f"{TELA_PRIMEIRO_ACESSO}: a pessoa define a própria senha; em Usuários › Novo administrador a senha é "
            "temporária, gerada pelo sistema e trocada no primeiro login",
            "senha",
        ),
    }
    return cob


# Comandos sem opções: onde a interface faz o mesmo. Só subir o serviço e criar a chave ficam com o arranque.
COMANDOS_SEM_OPCOES = {
    "verificar-auditoria": "Auditoria › Verificar a cadeia",
    "gerar-chave": f"{ARRANQUE}: a chave é criada sozinha na primeira subida",
    "popular-demo": f"{TELA_PRIMEIRO_ACESSO} › Criar dados de demonstração (homologação); depois, Início do administrador",
}
