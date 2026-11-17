"""Arranque do serviço (é o ponto de entrada da imagem Docker): garante a chave de cifra, prepara o banco na primeira
subida e entrega o controle à linha de comando.

    python -m ela_preditivo.web.arranque            # prepara e sobe o servidor
    python -m ela_preditivo.web.arranque avaliar …  # prepara a chave e roda outro comando de `ela-preditivo`

Com isso ninguém precisa da linha de comando para pôr a plataforma no ar; o resto acontece no navegador:

- chave de cifra: a de `ELA_WEB_CHAVE`; sem ela, a guardada em `chave.env` ao lado do banco; sem nenhuma, cria uma e a
  guarda ali com permissão restrita. Sem essa chave o banco e os arquivos cifrados não se leem: faça cópia dela;
- administrador e dados de demonstração: criados na tela de primeiro acesso, que a interface abre enquanto não há
  administrador (`web/primeiro_acesso.py`); as senhas da demonstração aparecem na tela, uma única vez;
- `ELA_ADMIN_EMAIL`, `ELA_ADMIN_CPF` e `ELA_ADMIN_SENHA` (`ELA_ADMIN_NOME` é opcional): opcionais, criam o
  administrador já na subida. Servem a um servidor exposto, onde não convém deixar o primeiro acesso aberto;
- endereço e porta: `ELA_WEB_HOST` (padrão 127.0.0.1) e `ELA_WEB_PORTA` (padrão 8000).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ARQUIVO_DA_CHAVE = "chave.env"
VARIAVEL_DA_CHAVE = "ELA_WEB_CHAVE"


def _avisar(texto: str) -> None:
    """Escreve já: com a saída redirecionada para arquivo, o aviso não pode ficar preso até o servidor parar."""
    print(texto, flush=True)


def pasta_do_banco() -> Path:
    from .config import DIR_PADRAO_BD

    return Path(os.environ.get("ELA_WEB_BD") or DIR_PADRAO_BD / "ela_web.sqlite3").parent


def ler_chave(arquivo: Path) -> str | None:
    """Chave guardada em `chave.env` (linha `ELA_WEB_CHAVE=...`, com ou sem `export`)."""
    if not arquivo.is_file():
        return None
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip().removeprefix("export ").strip()
        if linha.startswith(VARIAVEL_DA_CHAVE + "="):
            valor = linha.split("=", 1)[1].strip().strip("'\"")
            return valor or None
    return None


def garantir_chave(pasta: Path, ambiente=os.environ, avisar=_avisar) -> str:
    """Deixa `ELA_WEB_CHAVE` definida em `ambiente`: a que já está lá, a do arquivo ou uma nova, guardada no arquivo."""
    from .config import gerar_chave

    if (ambiente.get(VARIAVEL_DA_CHAVE) or "").strip():
        return ambiente[VARIAVEL_DA_CHAVE].strip()
    arquivo = Path(pasta) / ARQUIVO_DA_CHAVE
    chave = ler_chave(arquivo)
    if chave is None:
        chave = gerar_chave()
        Path(pasta).mkdir(parents=True, exist_ok=True)
        descritor = os.open(arquivo, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descritor, "w", encoding="utf-8") as f:
            f.write(f"{VARIAVEL_DA_CHAVE}={chave}\n")
        avisar(
            f"[arranque] Chave de cifra criada em {arquivo.name}, ao lado do banco. Sem ela o banco e os arquivos "
            "cifrados não se leem: faça cópia."
        )
    ambiente[VARIAVEL_DA_CHAVE] = chave
    return chave


def preparar_banco(ambiente=os.environ, avisar=_avisar) -> list[str]:
    """Subida: cria o administrador vindo do ambiente, se ainda não existir, e avisa quando não há administrador
    (o primeiro acesso é feito no navegador). A senha do ambiente é temporária: fica num arquivo de configuração,
    então a conta só serve para definir a senha de uso no primeiro login. Devolve o que fez."""
    from sqlalchemy import func, select

    from . import demo
    from .bd import criar_engine, criar_tabelas, fabrica_sessoes
    from .config import Configuracao
    from .modelos import Usuario
    from .seguranca import Cifra

    config = Configuracao.do_ambiente()
    engine = criar_engine(config.bd)
    criar_tabelas(engine)

    def contar(*filtros) -> int:
        with fabrica_sessoes(engine)() as bd:
            return int(bd.scalar(select(func.count()).select_from(Usuario).where(*filtros)) or 0)

    feito = []
    email = (ambiente.get("ELA_ADMIN_EMAIL") or "").strip()
    if email and contar(Usuario.email == email) == 0:
        cpf, senha = (ambiente.get("ELA_ADMIN_CPF") or "").strip(), ambiente.get("ELA_ADMIN_SENHA") or ""
        if not cpf or not senha:
            avisar(
                "[arranque] ELA_ADMIN_EMAIL definido sem ELA_ADMIN_CPF ou ELA_ADMIN_SENHA: administrador não criado."
            )
        else:
            nome = (ambiente.get("ELA_ADMIN_NOME") or "").strip() or "Administrador"
            try:
                with fabrica_sessoes(engine)() as bd:
                    demo.criar_admin(
                        bd,
                        Cifra(config.chave),
                        nome,
                        cpf,
                        email,
                        senha,
                        detalhe="variáveis de ambiente, na subida; senha temporária",
                        trocar_senha=True,
                    )
                feito.append("criar-admin")
                avisar("[arranque] Administrador criado a partir do ambiente; a senha será trocada no primeiro login.")
            except ValueError as e:
                avisar(f"[arranque] Administrador do ambiente não criado: {e}.")
    if contar(Usuario.papel == "ADMIN") == 0:
        avisar(
            "[arranque] Ainda não há administrador: abra a plataforma no navegador e faça o primeiro acesso"
            + (" (em homologação, a mesma tela cria os dados de demonstração)." if config.demonstracao else ".")
        )
    engine.dispose()
    return feito


def main(argv=None) -> int:
    argumentos = list(sys.argv[1:] if argv is None else argv)
    garantir_chave(pasta_do_banco())
    from ..cli import main as executar

    if argumentos and argumentos[0] != "servir":
        return executar(argumentos)
    preparar_banco()
    sys.stdout.flush()  # as credenciais da demonstração saem antes de o servidor tomar o processo
    servir = ["servir", "--host", os.environ.get("ELA_WEB_HOST") or "127.0.0.1"]
    return executar([*servir, "--porta", os.environ.get("ELA_WEB_PORTA") or "8000", *argumentos[1:]])


if __name__ == "__main__":
    sys.exit(main())
