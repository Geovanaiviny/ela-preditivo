"""Configuração da plataforma web, lida de variáveis de ambiente (nenhum segredo no código nem no repositório)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.fernet import Fernet

from .. import DIR_DADOS_BRUTOS, RAIZ_PROJETO

DIR_PADRAO_BD = RAIZ_PROJETO.parent / "dados_web"  # ignorada pelo git (.gitignore)
MEGABYTE = 1024 * 1024


class ConfiguracaoInvalida(RuntimeError):
    pass


def _bool(valor: str | None, padrao: bool) -> bool:
    if valor is None or valor == "":
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "yes", "on")


@dataclass
class Configuracao:
    chave: bytes  # chave Fernet (ELA_WEB_CHAVE); o HMAC do CPF é derivado dela por HKDF
    bd: Path = field(default_factory=lambda: DIR_PADRAO_BD / "ela_web.sqlite3")
    cookie_seguro: bool = False  # Secure no cookie de sessão; ligar atrás de HTTPS (ELA_WEB_COOKIE_SEGURO=1)
    sessao_minutos: int = 30  # expiração por inatividade
    sessao_maximo_horas: int = 12  # expiração absoluta
    ambiente: str = (
        "producao"  # "producao" (padrão: sem selo) ou "homologacao" (selo "dados fictícios" e cenários de exemplo)
    )
    demonstracao: bool = False  # derivado de `ambiente` (mantido por compatibilidade: True equivale a homologação)
    dir_vcfs: Path = field(default_factory=lambda: DIR_PADRAO_BD / "vcfs")  # VCFs cifrados (Fernet), fora do banco
    dir_documentos: Path | None = None  # prontuários e laudos cifrados (padrão: ao lado de dir_vcfs)
    dir_analises: Path | None = None  # resultados completos das análises, cifrados (padrão: ao lado de dir_vcfs)
    dir_tarefas: Path | None = None  # execuções do artefato pela interface (padrão: ao lado de dir_vcfs)
    dir_bases: Path | None = None  # bases de anotação e registro de versões (padrão: ELA_DADOS_BRUTOS)
    tarefas_guardadas: int = 12  # execuções do artefato mantidas em disco; as mais antigas saem
    tamanho_maximo_base: int = 300 * MEGABYTE
    tamanho_maximo_parametros: int = 2 * MEGABYTE  # YAML de parâmetros e tabela de variantes enviados
    tamanho_maximo_documento: int = 10 * MEGABYTE
    encarregado_nome: str = "(a definir pela instituição)"
    encarregado_contato: str = "(a definir pela instituição)"
    tentativas_login: int = 5
    bloqueio_minutos: int = 15
    tamanho_maximo_vcf: int = 20 * MEGABYTE
    analises_expiram_minutos: int = 120
    n_maximo_web: int = 200_000

    def __post_init__(self) -> None:
        self.dir_vcfs = Path(self.dir_vcfs)
        if self.dir_documentos is None:
            self.dir_documentos = self.dir_vcfs.parent / "documentos"
        if self.dir_analises is None:
            self.dir_analises = self.dir_vcfs.parent / "analises"
        self.dir_tarefas = Path(self.dir_tarefas) if self.dir_tarefas else self.dir_vcfs.parent / "tarefas"
        self.dir_bases = Path(self.dir_bases) if self.dir_bases else DIR_DADOS_BRUTOS
        self.ambiente = (self.ambiente or "producao").strip().lower()
        if self.ambiente not in ("producao", "homologacao"):
            raise ConfiguracaoInvalida("ELA_WEB_AMBIENTE deve ser 'producao' ou 'homologacao'")
        if self.demonstracao:
            self.ambiente = "homologacao"
        self.demonstracao = self.ambiente == "homologacao"

    @classmethod
    def do_ambiente(cls, **sobrescrever) -> "Configuracao":
        chave = sobrescrever.pop("chave", None) or os.environ.get("ELA_WEB_CHAVE", "").strip()
        if not chave:
            raise ConfiguracaoInvalida(
                "ELA_WEB_CHAVE não definida: gere uma chave com `ela-preditivo gerar-chave` e exporte-a antes de "
                "`ela-preditivo servir` (a mesma chave deve ser usada em todas as execuções sobre o mesmo banco)."
            )
        chave_b = chave.encode() if isinstance(chave, str) else chave
        try:
            Fernet(chave_b)
        except (ValueError, TypeError) as e:
            raise ConfiguracaoInvalida(
                "ELA_WEB_CHAVE inválida: precisa ser uma chave Fernet (base64 url-safe de 32 bytes)"
            ) from e
        cfg = cls(
            chave=chave_b,
            bd=Path(os.environ.get("ELA_WEB_BD") or DIR_PADRAO_BD / "ela_web.sqlite3"),
            cookie_seguro=_bool(os.environ.get("ELA_WEB_COOKIE_SEGURO"), False),
            sessao_minutos=int(os.environ.get("ELA_WEB_SESSAO_MINUTOS") or 30),
            ambiente=os.environ.get("ELA_WEB_AMBIENTE") or "producao",
            demonstracao=_bool(os.environ.get("ELA_WEB_DEMONSTRACAO"), False),  # alias antigo de homologação
            dir_vcfs=Path(os.environ.get("ELA_WEB_VCFS") or DIR_PADRAO_BD / "vcfs"),
            encarregado_nome=os.environ.get("ELA_ENCARREGADO_NOME") or cls.encarregado_nome,
            encarregado_contato=os.environ.get("ELA_ENCARREGADO_CONTATO") or cls.encarregado_contato,
        )
        for k, v in sobrescrever.items():
            setattr(cfg, k, v)
        cfg.__post_init__()
        return cfg


def gerar_chave() -> str:
    return Fernet.generate_key().decode()
