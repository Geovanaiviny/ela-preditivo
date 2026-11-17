"""Plataforma web do artefato: servidor mínimo das telas de acesso, cadastro de usuários com
aprovação, cadastro de pacientes pelo médico, navegação por papel (RBAC), auditoria e conformidade com a LGPD.

Depende do extra `web` do `pyproject.toml` (FastAPI, SQLAlchemy, argon2-cffi, cryptography, python-multipart).
Ponto de entrada: `ela_preditivo.web.api.criar_app()`; CLI `ela-preditivo servir`.
"""
