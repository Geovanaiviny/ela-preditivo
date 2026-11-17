"""Senha (Argon2id), cifra em repouso (Fernet), HMAC do CPF, tokens de sessão/CSRF, CPF e limite de tentativas."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SENHA_MINIMO = 10
_hasher = PasswordHasher()  # Argon2id, parâmetros padrão da biblioteca (RFC 9106, perfil de segundo nível)


# ---------------------------------------------------------------------------
# Senha
# ---------------------------------------------------------------------------
def validar_senha(senha: str, *proibidos: str) -> str | None:
    """Mensagem de erro ou None. Mínimo de 10 caracteres; não pode ser igual ao e-mail ou ao CPF."""
    if not isinstance(senha, str) or len(senha) < SENHA_MINIMO:
        return f"A senha precisa ter pelo menos {SENHA_MINIMO} caracteres."
    if len(senha) > 200:
        return "A senha é longa demais (máximo de 200 caracteres)."
    for p in proibidos:
        if p and senha.strip().lower() == str(p).strip().lower():
            return "A senha não pode ser igual ao e-mail nem ao CPF."
    return None


def hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def verificar_senha(hash_: str, senha: str) -> bool:
    try:
        return _hasher.verify(hash_, senha)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ---------------------------------------------------------------------------
# Cifra em repouso e HMAC do CPF
# ---------------------------------------------------------------------------
class Cifra:
    """Fernet (AES-128-CBC + HMAC-SHA256) para os identificadores; HMAC-SHA256 com chave derivada para o CPF
    (permite conferir duplicidade sem guardar o CPF em claro)."""

    def __init__(self, chave: bytes):
        self._fernet = Fernet(chave)
        bruta = base64.urlsafe_b64decode(chave)
        self._chave_hmac = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=b"ela_preditivo/web/cpf_hmac"
        ).derive(bruta)

    def cifrar(self, texto: str | None) -> str | None:
        if texto is None:
            return None
        return self._fernet.encrypt(str(texto).encode("utf-8")).decode("ascii")

    def decifrar(self, token: str | None) -> str | None:
        if token is None:
            return None
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as e:
            raise RuntimeError(
                "não foi possível decifrar: a chave ELA_WEB_CHAVE não é a mesma que cifrou o banco"
            ) from e

    def cifrar_bytes(self, dados: bytes) -> bytes:
        return self._fernet.encrypt(dados)

    def decifrar_bytes(self, dados: bytes) -> bytes:
        try:
            return self._fernet.decrypt(dados)
        except InvalidToken as e:
            raise RuntimeError(
                "não foi possível decifrar o arquivo: a chave ELA_WEB_CHAVE não é a mesma que o cifrou"
            ) from e

    def hmac_cpf(self, cpf: str) -> str:
        return hmac.new(self._chave_hmac, normalizar_cpf(cpf).encode("ascii"), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
def gerar_token(n_bytes: int = 32) -> str:
    return secrets.token_urlsafe(n_bytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def comparar_tokens(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---------------------------------------------------------------------------
# CPF
# ---------------------------------------------------------------------------
def normalizar_cpf(cpf: str | None) -> str:
    return re.sub(r"\D", "", cpf or "")


def validar_cpf(cpf: str | None) -> bool:
    """Confere os dois dígitos verificadores; rejeita sequências com todos os dígitos iguais."""
    d = normalizar_cpf(cpf)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for i in (9, 10):
        soma = sum(int(d[j]) * ((i + 1) - j) for j in range(i))
        dv = (soma * 10) % 11
        if dv == 10:
            dv = 0
        if dv != int(d[i]):
            return False
    return True


def mascarar_cpf(cpf: str | None) -> str:
    d = normalizar_cpf(cpf)
    if len(d) != 11:
        return "***.***.***-**"
    return f"***.{d[3:6]}.{d[6:9]}-**"


def formatar_cpf(cpf: str) -> str:
    d = normalizar_cpf(cpf)
    return f"{d[0:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}" if len(d) == 11 else cpf


def normalizar_email(email: str | None) -> str:
    return (email or "").strip().lower()


def normalizar_texto(texto: str | None) -> str:
    """Minúsculas, sem acentos e sem espaços repetidos (para buscar e para comparar a confirmação do nome)."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


# ---------------------------------------------------------------------------
# Limite de tentativas de login (por origem + e-mail), em memória
# ---------------------------------------------------------------------------
class LimiteTentativas:
    def __init__(self, maximo: int = 5, janela_s: int = 900):
        self.maximo = maximo
        self.janela_s = janela_s
        self._falhas: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _chave(self, origem: str, email: str) -> str:
        return hashlib.sha256(f"{origem}|{normalizar_email(email)}".encode()).hexdigest()

    def bloqueado(self, origem: str, email: str) -> int:
        """Segundos restantes de bloqueio (0 = livre)."""
        k = self._chave(origem, email)
        agora = time.monotonic()
        with self._lock:
            recentes = [t for t in self._falhas.get(k, []) if agora - t < self.janela_s]
            self._falhas[k] = recentes
            if len(recentes) >= self.maximo:
                return int(self.janela_s - (agora - recentes[0])) + 1
        return 0

    def registrar_falha(self, origem: str, email: str) -> None:
        k = self._chave(origem, email)
        with self._lock:
            self._falhas.setdefault(k, []).append(time.monotonic())

    def limpar(self, origem: str, email: str) -> None:
        with self._lock:
            self._falhas.pop(self._chave(origem, email), None)
