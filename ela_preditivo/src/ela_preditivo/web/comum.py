"""Utilitários partilhados pelas rotas: acesso ao banco e à configuração, erros com campos, serialização."""

from __future__ import annotations

import datetime as _dt
import re

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .config import Configuracao
from .seguranca import Cifra

MUTAVEIS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()


def obter_bd(request: Request) -> Session:
    return request.state.bd


def obter_config(request: Request) -> Configuracao:
    return request.app.state.config


def obter_cifra(request: Request) -> Cifra:
    return request.app.state.cifra


def origem(request: Request) -> str:
    return request.client.host if request.client else "desconhecida"


def iso(dt: _dt.datetime | None) -> str | None:
    return None if dt is None else dt.replace(microsecond=0).isoformat() + "Z"


class ErroCampos(HTTPException):
    """Erro de validação com mensagem por campo, para a interface associar o erro ao campo (WCAG)."""

    def __init__(self, status: int, mensagem: str, campos: dict[str, str] | None = None):
        super().__init__(status, {"mensagem": mensagem, "campos": campos or {}})


def exigir_campos(campos: dict[str, str], status: int = 422, mensagem: str = "Corrija os campos indicados.") -> None:
    if campos:
        raise ErroCampos(status, mensagem, campos)


def texto_curto(valor: str | None, maximo: int) -> str | None:
    if valor is None:
        return None
    v = str(valor).strip()
    return v[:maximo] if v else None


def interpretar_laudo(texto: str | None, campo: str, campos: dict):
    """Laudo do C9orf72: "45" → 45; "12,45" (ou "12 45") → (12, 45); vazio → None. Erros vão para `campos[campo]`."""
    if texto is None or not str(texto).strip():
        return None
    partes = [p for p in re.split(r"[,\s;/]+", str(texto).strip()) if p]
    try:
        valores = [int(p) for p in partes]
    except ValueError:
        campos[campo] = "Informe o nº de repetições (ex.: 45) ou os dois alelos (ex.: 12,45)."
        return None
    if not 1 <= len(valores) <= 2 or any(v < 0 or v > 5000 for v in valores):
        campos[campo] = "Informe um ou dois números inteiros entre 0 e 5000."
        return None
    return valores[0] if len(valores) == 1 else tuple(valores)


def laudo_texto(valor) -> str | None:
    """Inverso de `interpretar_laudo`, para guardar o laudo como texto curto ("45" ou "12,45")."""
    if valor is None:
        return None
    if isinstance(valor, (list, tuple)):
        return ",".join(str(int(v)) for v in valor)
    return str(int(valor))


def quantil_inicio(t: list, F: list, q: float) -> float | None:
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
