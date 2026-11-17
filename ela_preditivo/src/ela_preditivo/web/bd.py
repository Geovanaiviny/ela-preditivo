"""Conexão com o banco (SQLAlchemy 2; SQLite em arquivo, sem recurso exclusivo do SQLite)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .modelos import Base


def agora() -> _dt.datetime:
    """Instante atual em UTC, sem fuso (o SQLite não guarda fuso; serializar com sufixo Z)."""
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None, microsecond=0)


def criar_engine(caminho: str | Path) -> Engine:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite+pysqlite:///{caminho.as_posix()}", connect_args={"check_same_thread": False}, future=True
    )

    @event.listens_for(engine, "connect")
    def _chaves_estrangeiras(conexao, _registro):  # integridade referencial (o SQLite a desliga por padrão)
        conexao.execute("PRAGMA foreign_keys=ON")

    return engine


def criar_tabelas(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def fabrica_sessoes(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
