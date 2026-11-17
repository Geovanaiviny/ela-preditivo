"""Arquivos cifrados em disco (Fernet), fora do banco: documentos (prontuário, laudo) e resultados completos das análises.

Nome aleatório no disco; o nome original fica cifrado no banco; só quem tem a chave decifra. O chamador apaga o arquivo
quando o registro, o genitor ou o descendente é removido.
"""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

from fastapi import UploadFile

from .seguranca import Cifra

MIMES_DOCUMENTO = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
ASSINATURAS = {"application/pdf": (b"%PDF",), "image/jpeg": (b"\xff\xd8\xff",), "image/png": (b"\x89PNG",)}


def guardar(pasta: Path, cifra: Cifra, dados: bytes, sufixo: str = ".bin") -> str:
    pasta.mkdir(parents=True, exist_ok=True)
    nome = secrets.token_hex(16) + sufixo
    (pasta / nome).write_bytes(cifra.cifrar_bytes(dados))
    return nome


def ler(pasta: Path, cifra: Cifra, nome: str) -> bytes:
    return cifra.decifrar_bytes((pasta / nome).read_bytes())


def apagar(pasta: Path, nome: str | None) -> bool:
    if not nome:
        return False
    caminho = pasta / nome
    existia = caminho.exists()
    caminho.unlink(missing_ok=True)
    return existia


def ler_upload_documento(
    arquivo: UploadFile | None, campo: str, campos: dict, limite: int
) -> tuple[bytes, str, str] | None:
    """Lê um PDF/JPG/PNG enviado, conferindo extensão, assinatura e tamanho. Devolve (bytes, mime, nome_original)."""
    if arquivo is None or not arquivo.filename:
        campos[campo] = "Envie o arquivo (PDF, JPG ou PNG)."
        return None
    nome = arquivo.filename
    ext = Path(nome.lower()).suffix
    mime = MIMES_DOCUMENTO.get(ext)
    if mime is None:
        campos[campo] = "Formato não aceito: envie PDF, JPG ou PNG."
        return None
    dados = arquivo.file.read(limite + 1)
    if len(dados) > limite:
        campos[campo] = f"Arquivo maior que {limite // (1024 * 1024)} MB."
        return None
    if not dados:
        campos[campo] = "Arquivo vazio."
        return None
    if not any(dados.startswith(assin) for assin in ASSINATURAS[mime]):
        campos[campo] = "O conteúdo do arquivo não corresponde ao formato informado."
        return None
    return dados, mime, nome[:200]


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()
