"""VCFs dos genitores: validação do upload, guarda cifrada em disco (Fernet), decifragem só para a pasta temporária da
análise e VCF "sem variantes" para o genitor sem exame assumido não portador.

O nome do arquivo original nunca é guardado; o arquivo em disco tem nome aleatório e conteúdo cifrado; não há rota de
download. Só o hash SHA-256 do conteúdo em claro fica no banco, para reprodutibilidade dos metadados da análise.
"""

from __future__ import annotations

import gzip
import hashlib
import secrets
import shutil
import tempfile
from pathlib import Path

from fastapi import UploadFile

from .. import cenarios
from ..ingestao import MontagemDivergente, ler_vcf
from .bd import agora
from .config import Configuracao
from .modelos import Genitor
from .seguranca import Cifra

EXTENSOES_VCF = (".vcf", ".vcf.gz")


def guardar_upload(arquivo: UploadFile | None, destino: Path, campo: str, campos: dict, limite: int) -> Path | None:
    """Grava o upload em `destino` (com a extensão certa) conferindo extensão, tamanho e arquivo vazio."""
    if arquivo is None or not arquivo.filename:
        campos[campo] = "Envie o arquivo VCF."
        return None
    nome = arquivo.filename.lower()
    if not nome.endswith(EXTENSOES_VCF):
        campos[campo] = "Envie um arquivo .vcf (ou .vcf.gz)."
        return None
    destino = destino.with_suffix(".vcf.gz" if nome.endswith(".gz") else ".vcf")
    tamanho = 0
    with open(destino, "wb") as f:
        while True:
            parte = arquivo.file.read(1024 * 1024)
            if not parte:
                break
            tamanho += len(parte)
            if tamanho > limite:
                campos[campo] = f"Arquivo maior que {limite // (1024 * 1024)} MB."
                f.close()
                destino.unlink(missing_ok=True)
                return None
            f.write(parte)
    if tamanho == 0:
        campos[campo] = "Arquivo vazio."
        destino.unlink(missing_ok=True)
        return None
    return destino


def validar(caminho: Path) -> str | None:
    """Lê o VCF com a ingestão do artefato; devolve a mensagem de erro (sem caminho nem nome de arquivo) ou None."""
    try:
        ler_vcf(caminho)
    except MontagemDivergente as e:
        return "Montagem de referência diferente de GRCh38: " + str(e).split(":", 1)[-1].strip()[:200]
    except Exception as e:  # noqa: BLE001 - qualquer falha de leitura é "arquivo inválido"
        return f"Não foi possível ler o VCF ({type(e).__name__})."
    return None


def hash_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for parte in iter(lambda: f.read(1024 * 1024), b""):
            h.update(parte)
    return h.hexdigest()


def anexar(config: Configuracao, cifra: Cifra, genitor: Genitor, origem: Path) -> None:
    """Cifra `origem` para `config.dir_vcfs/<aleatório>.bin`, apaga o anexo anterior e atualiza o genitor."""
    config.dir_vcfs.mkdir(parents=True, exist_ok=True)
    sufixo = ".gz" if origem.name.endswith(".gz") else ""
    nome = secrets.token_hex(16) + sufixo + ".bin"
    dados = origem.read_bytes()
    (config.dir_vcfs / nome).write_bytes(cifra.cifrar_bytes(dados))
    remover(config, genitor)
    genitor.vcf_arquivo = nome
    genitor.vcf_tamanho = len(dados)
    genitor.vcf_hash = hashlib.sha256(dados).hexdigest()
    genitor.vcf_enviado_em = agora()
    genitor.atualizado_em = agora()


def remover(config: Configuracao, genitor: Genitor) -> None:
    if genitor.vcf_arquivo:
        (config.dir_vcfs / genitor.vcf_arquivo).unlink(missing_ok=True)
    genitor.vcf_arquivo = None
    genitor.vcf_tamanho = None
    genitor.vcf_hash = None
    genitor.vcf_enviado_em = None


def remover_todos(config: Configuracao, genitores: list[Genitor]) -> int:
    n = 0
    for g in genitores:
        if g.vcf_arquivo:
            n += 1
        remover(config, g)
    return n


def decifrar_para(config: Configuracao, cifra: Cifra, genitor: Genitor, pasta: Path, lado: str) -> Path:
    """Decifra o anexo para `pasta/<lado>.vcf[.gz]` (apagado pelo chamador ao fim da análise)."""
    if not genitor.vcf_arquivo:
        raise FileNotFoundError("genitor sem VCF anexado")
    bruto = (config.dir_vcfs / genitor.vcf_arquivo).read_bytes()
    destino = pasta / (f"{lado}.vcf.gz" if genitor.vcf_arquivo.endswith(".gz.bin") else f"{lado}.vcf")
    destino.write_bytes(cifra.decifrar_bytes(bruto))
    return destino


def texto_em_memoria(config: Configuracao, cifra: Cifra, dono) -> str:
    """Texto do VCF anexado (de genitor, parente ou filho), decifrado só em memória: nenhum arquivo é gravado.
    Serve a leituras internas que não entregam o arquivo a ninguém, como a que decide o que a ficha mostra."""
    if not dono.vcf_arquivo:
        raise FileNotFoundError("sem VCF anexado")
    dados = cifra.decifrar_bytes((config.dir_vcfs / dono.vcf_arquivo).read_bytes())
    if dono.vcf_arquivo.endswith(".gz.bin"):
        dados = gzip.decompress(dados)
    return dados.decode("utf-8", errors="replace")


def sem_variantes(destino: Path, amostra: str) -> Path:
    """VCF GRCh38 de uma amostra com um único registro homozigoto de referência (0/0) fora dos genes-alvo: representa
    o genitor sem exame assumido não portador (dosagem 0 em todos os lóci). O registro existe só para que a ingestão
    produza um quadro com colunas; a suposição é declarada no resultado e nos metadados."""
    return cenarios.escrever_vcf_sem_variantes(destino, amostra, "genitor sem exame: assumido sem variante de risco")


def pasta_temporaria(config: Configuracao) -> Path:
    config.dir_vcfs.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="envio_", dir=config.dir_vcfs))


def apagar_pasta(p: Path) -> None:
    shutil.rmtree(p, ignore_errors=True)
