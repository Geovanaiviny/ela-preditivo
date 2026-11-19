"""Textos do repositório e rótulos da interface: nada escrito em terceira pessoa sobre quem fez o trabalho, "risco
vitalício" com um só significado (desde o nascimento, até o horizonte) e nenhum valor ausente escrito como "null"."""

from __future__ import annotations

import re
from pathlib import Path

from ela_preditivo import monte_carlo, sobrevivencia
from ela_preditivo.web import pesquisa

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "ela_preditivo"
JS = (PACOTE / "src" / "ela_preditivo" / "web" / "static" / "app.js").read_text(encoding="utf-8")
TEXTOS = (".py", ".js", ".html", ".css", ".yaml", ".yml", ".md", ".toml", ".exemplo")
FONTE_DAS_TABELAS = "elaborado pela autora"  # fonte de tabelas e figuras, como no texto do trabalho


def arquivos_de_texto():
    for p in sorted(PACOTE.rglob("*")):
        if p.is_file() and p.suffix in TEXTOS and "__pycache__" not in p.parts and p != Path(__file__).resolve():
            yield p
    for nome in ("README.md", "Dockerfile", "docker-compose.yml", ".env.exemplo", ".gitignore"):
        yield RAIZ / nome


def test_nenhum_texto_fala_de_quem_escreve_em_terceira_pessoa():
    """Comentários, mensagens e telas não se dirigem a "a autora" como a outra pessoa. A fonte das tabelas e figuras
    ("elaborado pela autora") é a forma do próprio trabalho e fica."""
    achados = []
    for p in arquivos_de_texto():
        for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bautora\b", linha.replace(FONTE_DAS_TABELAS, ""), flags=re.IGNORECASE):
                achados.append(f"{p.relative_to(RAIZ)}:{n}: {linha.strip()[:100]}")
    assert achados == []


def test_risco_vitalicio_so_nomeia_o_risco_desde_o_nascimento(anotados, parametros):
    mae, pai = anotados[3]
    from ela_preditivo import genotipo

    loci = monte_carlo.loci_de_vetor(genotipo.vetor_dosagem(mae, pai, parametros), parametros, sexo="F")
    res = monte_carlo.simular_numpy(loci, n=600, seed=1)
    # Tabela 4: o risco a partir da idade atual é residual; na idade 0 ele é o vitalício da Tabela 3
    t4 = sobrevivencia.tabela_risco_condicional(res, idades_atuais=(0, 40))
    assert {"risco_residual", "risco_residual_q025", "risco_residual_q975"} <= set(t4.columns)
    assert not [c for c in t4.columns if "vitalicio" in c]
    assert "risco_residual_km" in sobrevivencia.risco_condicional_km(res, idade_atual=40).columns
    # CSV do pesquisador: uma grandeza por coluna
    assert {"risco_vitalicio", "risco_residual", "p_transmissao", "p_portador_sem_sintomas"} <= set(
        pesquisa.COLUNAS_CSV
    )
    assert "p_manifesta_vida" not in pesquisa.COLUNAS_CSV and len(set(pesquisa.COLUNAS_CSV)) == len(
        pesquisa.COLUNAS_CSV
    )
    # interface: "vida" não rotula valor nenhum, e não existe "risco vitalício residual"
    for proibido in ("vida ${", "{ rotulo: 'Vida'", "(vida ou daqui em diante)", "vitalício residual", "risco_maximo"):
        assert proibido not in JS, proibido
    assert "risco_vitalicio_maximo" in JS and "a.risco_vitalicio" in JS and "l.risco_residual" in JS


def _argumentos(texto: str, pos: int) -> list[str]:
    """Argumentos de primeiro nível de uma chamada cujo '(' acabou em `pos`."""
    prof, i, ini, args, aspas = 0, pos, pos, [], None
    while i < len(texto):
        c = texto[i]
        if aspas:
            if c == "\\":
                i += 2
                continue
            if aspas == "`" and texto.startswith("${", i):
                abertas, i = 1, i + 2
                while abertas and i < len(texto):
                    abertas += {"{": 1, "}": -1}.get(texto[i], 0)
                    i += 1
                continue
            if c == aspas:
                aspas = None
        elif c in "'\"`":
            aspas = c
        elif c in "([{":
            prof += 1
        elif c in ")]}":
            if prof == 0:
                return args + [texto[ini:i]]
            prof -= 1
        elif c == "," and prof == 0:
            args.append(texto[ini:i])
            ini = i + 1
        i += 1
    return args


def _primeiro_nivel(arg: str) -> str:
    """O argumento sem o que está entre parênteses, colchetes, chaves e aspas."""
    out, prof, aspas, i = [], 0, None, 0
    while i < len(arg):
        c = arg[i]
        if aspas:
            if c == "\\":
                i += 2
                continue
            if c == aspas:
                aspas = None
        elif c in "'\"`":
            aspas = c
        elif c in "([{":
            prof += 1
        elif c in ")]}":
            prof -= 1
        elif prof == 0:
            out.append(c)
        i += 1
    return "".join(out)


def test_interface_nao_escreve_valor_ausente():
    """`no.append(null)` escreve "null" na tela (só o construtor `el` descarta filhos ausentes), e um valor nulo dentro
    de um texto também. Nenhuma chamada direta recebe argumento que possa ser nulo, e a dosagem do genitor sem exame
    tem rótulo próprio."""
    suspeitos = []
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_.]*)\.append\(", JS):
        if m.group(1).split(".")[-1] in ("fd", "q"):  # FormData e URLSearchParams
            continue
        for arg in _argumentos(JS, m.end()):
            topo = _primeiro_nivel(arg)
            if re.search(r":\s*null\s*$|\?\s*null\s*:|&&|^\s*null\s*$", topo):
                suspeitos.append(f"{m.group(1)}.append(… {arg.strip()[:80]} …)")
    assert suspeitos == []
    assert "function rotuloDosagem(" in JS and "rotuloDosagem(l.dosagem_mae, inf)" in JS
    assert "${l.dosagem_mae}/${l.dosagem_pai}" not in JS
    # genitor sem laudo do C9orf72: a tela usa a regra do servidor (inferido quando um parente tem laudo)
    # e nesse caso diz de quem é o laudo, em vez do aviso de lócus indeterminado
    assert "g.c9orf72_por_parentes" in JS and "C9orf72 inferido pelo laudo de ${parentes}" in JS
    assert "Sem laudo: C9orf72 inferido por parentes" not in JS
