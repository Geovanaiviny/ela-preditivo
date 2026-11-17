"""Tabelas da plataforma (SQLAlchemy ORM). Identificadores de atendidos, genitores, laudos, resumos de análise e CPF
ficam cifrados (Fernet) em repouso; os VCFs ficam cifrados em disco, fora do banco."""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

PAPEIS = ("MEDICO", "PESQUISADOR", "ADMIN")
PAPEIS_AUTOCADASTRO = ("MEDICO", "PESQUISADOR")
SITUACOES = ("PENDENTE", "VERIFICADO", "REPROVADO", "DESATIVADO", "INFORMACOES_SOLICITADAS")
ROTULO_SITUACAO = {
    "PENDENTE": "Pendente de verificação",
    "VERIFICADO": "Verificado",
    "REPROVADO": "Reprovado",
    "DESATIVADO": "Desativado",
    "INFORMACOES_SOLICITADAS": "Informações solicitadas",
}
ROTULO_PAPEL = {
    "MEDICO": "Médico(a) / aconselhador(a) genético(a)",
    "PESQUISADOR": "Pesquisador(a)",
    "ADMIN": "Administrador(a)",
}
TIPOS_MEDICO = ("CRM", "ACONSELHADOR")
TIPOS_PESQUISADOR = ("INSTITUCIONAL", "INDEPENDENTE")
SEXOS = ("M", "F")
TIPOS_ATENDIMENTO = ("PESSOA", "CASAL", "FAMILIA")
MOMENTOS = ("ANTES_DO_TESTE", "APOS_LAUDO", "ACOMPANHAMENTO")
PAPEIS_GENITOR = ("MAE", "PAI")
TITULARES = ("MAE", "PAI", "DESCENDENTE", "RESPONSAVEL")
TIPOS_DOCUMENTO = ("PRONTUARIO", "LAUDO_C9ORF72")
BASE_LEGAL_ATENDIMENTO = "LGPD, art. 11, II, f: tutela da saúde, em procedimento realizado por profissional de saúde"
DOCUMENTOS = ("AVISO_PRIVACIDADE", "TERMO_USO")


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    cpf_cifrado: Mapped[str] = mapped_column(Text)
    cpf_hmac: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[str] = mapped_column(String(20), index=True)
    situacao: Mapped[str] = mapped_column(String(30), index=True, default="PENDENTE")
    mensagem_admin: Mapped[str | None] = mapped_column(Text, default=None)
    resposta_usuario: Mapped[str | None] = mapped_column(Text, default=None)
    respondido_em: Mapped[_dt.datetime | None] = mapped_column(DateTime, default=None)
    tentativas_falhas: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_ate: Mapped[_dt.datetime | None] = mapped_column(DateTime, default=None)
    verificado_em: Mapped[_dt.datetime | None] = mapped_column(DateTime, default=None)
    verificado_por_id: Mapped[int | None] = mapped_column(Integer, default=None)
    encerramento_solicitado_em: Mapped[_dt.datetime | None] = mapped_column(DateTime, default=None)
    criado_em: Mapped[_dt.datetime] = mapped_column(DateTime)
    atualizado_em: Mapped[_dt.datetime] = mapped_column(DateTime)

    perfil_medico: Mapped["PerfilMedico | None"] = relationship(
        back_populates="usuario", uselist=False, cascade="all, delete-orphan", lazy="joined"
    )
    perfil_pesquisador: Mapped["PerfilPesquisador | None"] = relationship(
        back_populates="usuario", uselist=False, cascade="all, delete-orphan", lazy="joined"
    )
    aceites: Mapped[list["AceiteTermo"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", lazy="selectin", order_by="AceiteTermo.id"
    )

    @property
    def verificado(self) -> bool:
        return self.situacao == "VERIFICADO"


class PerfilMedico(Base):
    __tablename__ = "perfis_medico"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))  # CRM | ACONSELHADOR (sem CRM: formação e instituição)
    crm: Mapped[str | None] = mapped_column(String(20), default=None)
    uf: Mapped[str | None] = mapped_column(String(2), default=None)
    especialidade: Mapped[str | None] = mapped_column(String(120), default=None)
    formacao: Mapped[str | None] = mapped_column(String(200), default=None)
    instituicao: Mapped[str | None] = mapped_column(String(200), default=None)

    usuario: Mapped[Usuario] = relationship(back_populates="perfil_medico")


class PerfilPesquisador(Base):
    __tablename__ = "perfis_pesquisador"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))  # INSTITUCIONAL | INDEPENDENTE
    orcid: Mapped[str | None] = mapped_column(String(19), default=None)
    lattes_url: Mapped[str | None] = mapped_column(String(300), default=None)
    instituicao: Mapped[str | None] = mapped_column(String(200), default=None)
    grupo: Mapped[str | None] = mapped_column(String(200), default=None)
    cargo: Mapped[str | None] = mapped_column(String(200), default=None)
    linha_pesquisa: Mapped[str | None] = mapped_column(String(300), default=None)
    projetos: Mapped[str | None] = mapped_column(Text, default=None)
    evidencias: Mapped[str | None] = mapped_column(Text, default=None)  # texto e links; sem envio de arquivos

    usuario: Mapped[Usuario] = relationship(back_populates="perfil_pesquisador")


class AceiteTermo(Base):
    __tablename__ = "aceites_termos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    documento: Mapped[str] = mapped_column(String(30))
    versao: Mapped[str] = mapped_column(String(20))
    aceito_em: Mapped[_dt.datetime] = mapped_column(DateTime)

    usuario: Mapped[Usuario] = relationship(back_populates="aceites")


class Sessao(Base):
    __tablename__ = "sessoes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 do token do cookie
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    criado_em: Mapped[_dt.datetime] = mapped_column(DateTime)
    ultimo_acesso: Mapped[_dt.datetime] = mapped_column(DateTime)
    expira_em: Mapped[_dt.datetime] = mapped_column(DateTime)  # expiração absoluta
    encerrada_em: Mapped[_dt.datetime | None] = mapped_column(DateTime, default=None)


class Paciente(Base):
    """Registro de atendimento: uma pessoa assintomática (PESSOA), um casal que planeja filhos (CASAL) ou uma família
    com vários filhos (FAMILIA). Os genitores (mãe/pai ou os dois parceiros) e os descendentes ficam em tabelas próprias.
    """

    __tablename__ = "pacientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    medico_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(10), index=True)  # PESSOA | CASAL | FAMILIA
    nome_cifrado: Mapped[str] = mapped_column(Text)  # nome do registro (pessoa, "A e B" ou "Família X")
    prontuario_cifrado: Mapped[str] = mapped_column(Text)
    momento: Mapped[str | None] = mapped_column(
        String(20), default=None
    )  # ANTES_DO_TESTE | APOS_LAUDO | ACOMPANHAMENTO
    observacoes_cifradas: Mapped[str | None] = mapped_column(Text, default=None)
    base_legal: Mapped[str] = mapped_column(String(200), default=BASE_LEGAL_ATENDIMENTO)
    codigo_pesquisa: Mapped[str | None] = mapped_column(
        String(64), default=None
    )  # pseudônimo; nunca sai para médico/admin
    liberado_pesquisa_em: Mapped[_dt.datetime | None] = mapped_column(DateTime, default=None)
    criado_em: Mapped[_dt.datetime] = mapped_column(DateTime)
    atualizado_em: Mapped[_dt.datetime] = mapped_column(DateTime)

    genitores: Mapped[list["Genitor"]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan", lazy="selectin", order_by="Genitor.papel"
    )
    descendentes: Mapped[list["Descendente"]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan", lazy="selectin", order_by="Descendente.ordem"
    )
    consentimentos: Mapped[list["Consentimento"]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan", lazy="selectin", order_by="Consentimento.id"
    )
    analises: Mapped[list["AnalisePaciente"]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan", lazy="selectin", order_by="AnalisePaciente.id"
    )
    documentos: Mapped[list["Documento"]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan", lazy="selectin", order_by="Documento.id"
    )

    def genitor(self, papel: str) -> "Genitor | None":
        return next((g for g in self.genitores if g.papel == papel), None)


class Genitor(Base):
    """Mãe e pai do descendente (PESSOA/FAMILIA) ou os dois parceiros (CASAL). O VCF fica cifrado em disco, fora do
    banco; aqui só o nome aleatório do arquivo, o tamanho, o hash do conteúdo em claro e a data."""

    __tablename__ = "genitores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), index=True)
    papel: Mapped[str] = mapped_column(String(3))  # MAE | PAI
    nome_cifrado: Mapped[str] = mapped_column(Text)
    data_nascimento_cifrada: Mapped[str] = mapped_column(Text)
    laudo_c9orf72_cifrado: Mapped[str | None] = mapped_column(Text, default=None)
    vcf_arquivo: Mapped[str | None] = mapped_column(String(80), default=None)
    vcf_tamanho: Mapped[int | None] = mapped_column(Integer, default=None)
    vcf_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    vcf_enviado_em: Mapped[_dt.datetime | None] = mapped_column(DateTime, default=None)
    atualizado_em: Mapped[_dt.datetime] = mapped_column(DateTime)

    paciente: Mapped[Paciente] = relationship(back_populates="genitores")

    @property
    def tem_vcf(self) -> bool:
        return self.vcf_arquivo is not None


class Descendente(Base):
    """Pessoa cujo risco é estimado: o atendido (PESSOA) ou cada filho (FAMILIA). CASAL não tem descendente."""

    __tablename__ = "descendentes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), index=True)
    ordem: Mapped[int] = mapped_column(Integer, default=1)
    nome_cifrado: Mapped[str] = mapped_column(Text)
    data_nascimento_cifrada: Mapped[str] = mapped_column(Text)
    sexo: Mapped[str] = mapped_column(String(1))
    atualizado_em: Mapped[_dt.datetime] = mapped_column(DateTime)

    paciente: Mapped[Paciente] = relationship(back_populates="descendentes")


class Documento(Base):
    """Documento anexado ao registro (prontuário) ou a um genitor (laudo do C9orf72): PDF ou imagem, cifrado em disco
    com nome aleatório; só o médico dono abre. Nunca vai ao pesquisador."""

    __tablename__ = "documentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), index=True)
    genitor_id: Mapped[int | None] = mapped_column(
        ForeignKey("genitores.id", ondelete="CASCADE"), default=None, index=True
    )
    tipo: Mapped[str] = mapped_column(String(20))  # PRONTUARIO | LAUDO_C9ORF72
    nome_original_cifrado: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(String(40))
    arquivo: Mapped[str] = mapped_column(String(80))
    tamanho: Mapped[int] = mapped_column(Integer)
    hash: Mapped[str] = mapped_column(String(64))
    enviado_em: Mapped[_dt.datetime] = mapped_column(DateTime)

    paciente: Mapped[Paciente] = relationship(back_populates="documentos")


class Consentimento(Base):
    __tablename__ = "consentimentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), index=True)
    descendente_id: Mapped[int | None] = mapped_column(
        ForeignKey("descendentes.id", ondelete="CASCADE"), default=None, index=True
    )
    finalidade: Mapped[str] = mapped_column(String(30), default="PESQUISA")
    titular: Mapped[str] = mapped_column(String(20))  # MAE | PAI | DESCENDENTE | RESPONSAVEL
    nome_titular_cifrado: Mapped[str] = mapped_column(Text)
    versao_termo: Mapped[str] = mapped_column(String(20))
    concedido_em: Mapped[_dt.datetime] = mapped_column(DateTime)
    revogado_em: Mapped[_dt.datetime | None] = mapped_column(DateTime, default=None)
    registrado_por_id: Mapped[int] = mapped_column(Integer)
    revogado_por_id: Mapped[int | None] = mapped_column(Integer, default=None)

    paciente: Mapped[Paciente] = relationship(back_populates="consentimentos")

    @property
    def ativo(self) -> bool:
        return self.revogado_em is None


class AnalisePaciente(Base):
    """Resumo cifrado de uma análise executada a partir da ficha (nunca o VCF nem o relatório). Some com o registro."""

    __tablename__ = "analises_pacientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), index=True)
    descendente_id: Mapped[int | None] = mapped_column(
        ForeignKey("descendentes.id", ondelete="CASCADE"), default=None, index=True
    )
    medico_id: Mapped[int] = mapped_column(Integer)
    executado_em: Mapped[_dt.datetime] = mapped_column(DateTime, index=True)
    modo: Mapped[str] = mapped_column(String(10))  # vcf | cenario
    n: Mapped[int] = mapped_column(Integer)
    semente: Mapped[int] = mapped_column(Integer)
    motor: Mapped[str] = mapped_column(String(10))
    hipoteses: Mapped[bool] = mapped_column(Boolean, default=False)
    cox: Mapped[bool] = mapped_column(Boolean, default=False)
    sexo: Mapped[str | None] = mapped_column(String(1), default=None)
    idade_na_analise: Mapped[int | None] = mapped_column(Integer, default=None)
    suposicoes: Mapped[str | None] = mapped_column(Text, default=None)  # JSON sem dado pessoal
    vcf_hash_mae: Mapped[str | None] = mapped_column(String(64), default=None)
    vcf_hash_pai: Mapped[str | None] = mapped_column(String(64), default=None)
    resumo_cifrado: Mapped[str] = mapped_column(Text)
    resultado_arquivo: Mapped[str | None] = mapped_column(String(80), default=None)  # JSON completo, cifrado em disco
    pacote_arquivo: Mapped[str | None] = mapped_column(
        String(80), default=None
    )  # zip (relatório, tabelas, figuras), cifrado

    paciente: Mapped[Paciente] = relationship(back_populates="analises")


class Auditoria(Base):
    """Registro só de inclusão, encadeado por hash. Nunca guarda nome de paciente, CPF completo ou senha."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sequencia: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    ocorrido_em: Mapped[_dt.datetime] = mapped_column(DateTime, index=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    papel: Mapped[str | None] = mapped_column(String(20), default=None)
    acao: Mapped[str] = mapped_column(String(40), index=True)
    alvo_tipo: Mapped[str | None] = mapped_column(String(30), default=None)
    alvo_id: Mapped[str | None] = mapped_column(String(64), default=None)
    resultado: Mapped[str] = mapped_column(String(10), default="OK")  # OK | NEGADO | FALHA
    detalhe: Mapped[str | None] = mapped_column(String(300), default=None)
    hash_anterior: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
