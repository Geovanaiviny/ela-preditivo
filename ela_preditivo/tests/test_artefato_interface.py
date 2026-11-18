"""Paridade entre a linha de comando e a interface: cada comando e cada opção de `ela-preditivo` tem correspondente na
plataforma; as execuções do artefato (reprodução, avaliação, cenários) rodam em segundo plano com as mesmas opções e
as mesmas saídas; a base de anotação é enviada, registrada e comparada pela interface; e a análise sem registro aceita
as opções avançadas da linha de comando."""

from __future__ import annotations

import argparse
import inspect
import io
import json
import shutil
import time
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ela_preditivo import DIR_DADOS, anotacao, cenarios, cli, pipeline
from ela_preditivo.calibracao import CAMINHO_PADRAO
from ela_preditivo.web import analises, artefato, auditoria, demo, primeiro_acesso
from ela_preditivo.web.api import criar_app
from ela_preditivo.web.comum import ErroCampos
from ela_preditivo.web.config import Configuracao, gerar_chave
from ela_preditivo.web.seguranca import Cifra

DIR_STATIC = Path(__file__).resolve().parents[1] / "src" / "ela_preditivo" / "web" / "static"
SINT = DIR_DADOS / "sinteticos"
A5V = dict(
    allele_id="15",
    gene="SOD1",
    nome="NM_000454.5(SOD1):c.14C>T (p.Ala5Val)",
    rs="121912442",
    crom="21",
    pos=31659783,
    ref="C",
    alt="T",
    vid="13891",
)
X_TARDBP = dict(
    allele_id="18",
    gene="TARDBP",
    nome="NM_007375.4(TARDBP):c.1A>G (p.Met1Val)",
    rs="-1",
    crom="1",
    pos=11012700,
    ref="A",
    alt="G",
    vid="9999",
)
Y_FUS = dict(
    allele_id="19",
    gene="FUS",
    nome="NM_004960.4(FUS):c.1561C>T (p.Arg521Cys)",
    rs="121909668",
    crom="16",
    pos=31191418,
    ref="C",
    alt="T",
    vid="777",
)
MULTI = "criteria provided, multiple submitters, no conflicts"
SINGLE = "criteria provided, single submitter"


class ProcessoDeMentira:
    """Processo de faz de conta: fica rodando até o teste dizer com que código ele terminou."""

    def __init__(self):
        self.codigo, self.encerrado = None, False

    def poll(self):
        return self.codigo

    def terminate(self):
        self.encerrado, self.codigo = True, -15

    def kill(self):
        self.codigo = -9

    def wait(self, timeout=None):
        return self.codigo


@pytest.fixture(scope="module")
def servico(tmp_path_factory):
    d = tmp_path_factory.mktemp("artefato")
    cfg = Configuracao(
        chave=gerar_chave().encode(),
        bd=d / "ela_web.sqlite3",
        dir_vcfs=d / "vcfs",
        dir_bases=d / "bases",
        demonstracao=True,
        tarefas_guardadas=3,
    )
    app = criar_app(cfg)
    with app.state.sessoes() as bd:
        cred = {c["email"]: c for c in demo.popular(bd, Cifra(cfg.chave), cfg, analisar=False)["credenciais"]}
    lancados: list[dict] = []

    def lancar(argumentos, pasta, ambiente):
        lancados.append(
            {"argumentos": argumentos, "pasta": pasta, "ambiente": ambiente, "processo": ProcessoDeMentira()}
        )
        return lancados[-1]["processo"]

    def entrar(email: str) -> TestClient:
        c = TestClient(app)
        r = c.post("/api/contas/login", json={"email": email, "senha": cred[email]["senha"]})
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = r.json()["csrf"]
        return c

    def tarefas(de_mentira: bool):
        """Zera as execuções e troca o lançador: processos de faz de conta ou o comando de verdade."""
        app.state.tarefas.encerrar()
        shutil.rmtree(cfg.dir_tarefas, ignore_errors=True)
        lancados.clear()
        app.state.tarefas = artefato.RegistroTarefas(cfg, lancar=lancar if de_mentira else None)
        return app.state.tarefas

    yield {"app": app, "cfg": cfg, "entrar": entrar, "lancados": lancados, "tarefas": tarefas, "pasta": d}
    app.state.tarefas.encerrar()
    app.state.analises.encerrar()


def acoes(servico) -> list[dict]:
    from sqlalchemy import select

    with servico["app"].state.sessoes() as bd:
        return [
            auditoria.serializar(r)
            for r in bd.execute(select(auditoria.Auditoria).order_by(auditoria.Auditoria.sequencia)).scalars()
        ]


def subcomandos() -> dict:
    parser = cli.construir_parser()
    return next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices


def opcoes_de(sub) -> dict:
    return {
        a.option_strings[0]: a for a in sub._actions if a.option_strings and not isinstance(a, argparse._HelpAction)
    }


# ---------------------------------------------------------------------------
# Paridade: nada que a linha de comando faz fica fora da interface
# ---------------------------------------------------------------------------
def test_toda_opcao_da_linha_de_comando_tem_correspondente_na_interface():
    """Percorre o argparse: um comando ou uma opção nova sem lugar declarado na interface faz este teste falhar."""
    cobertura, sub = artefato.cobertura_cli(), subcomandos()
    assert set(sub) == set(cobertura)
    for nome, sp in sub.items():
        flags = set(opcoes_de(sp))
        assert flags == set(cobertura[nome]), f"{nome}: {sorted(flags ^ set(cobertura[nome]))}"
        if not flags:
            assert nome in artefato.COMANDOS_SEM_OPCOES
    # os campos declarados existem: no formulário da análise sem registro...
    campos_analise = {
        (p.default.alias or n)
        for n, p in inspect.signature(analises.executar_analise).parameters.items()
        if hasattr(p.default, "alias")
    }
    js = (DIR_STATIC / "app.js").read_text(encoding="utf-8")
    for flag, c in cobertura["executar"].items():
        if c.campo is not None:
            assert c.campo in campos_analise, flag
            assert f"'{c.campo}'" in js, f"a interface não envia o campo {c.campo} ({flag})"
        else:
            assert c.onde.startswith((artefato.TELA_FICHA, artefato.SERVIDOR)), flag
    # ...e nos formulários das execuções do artefato, com os mesmos padrões e as mesmas escolhas da linha de comando
    for c in artefato.COMANDOS.values():
        acoes_cli = opcoes_de(sub[c.nome])
        for o in c.opcoes:
            a = acoes_cli[o.flag]
            assert all(f in acoes_cli for f in o.flags_extras)
            if o.tipo in ("inteiro", "decimal", "escolha", "data"):
                assert a.default == o.padrao, (c.nome, o.flag)
            if o.tipo == "inteiros":
                assert (tuple(a.default) if a.default else None) == o.padrao, (c.nome, o.flag)
            if o.tipo == "escolha":
                assert set(a.choices) == set(o.opcoes), (c.nome, o.flag)
            if o.tipo == "marcacao":
                assert a.nargs == 0 and a.default is False, (c.nome, o.flag)
    for tipo in ("marcacao", "escolha", "base", "origem", "arquivo", "inteiros", "data"):
        assert f"o.tipo === '{tipo}'" in js, f"o formulário não desenha opções do tipo {tipo}"
    # só subir o serviço e criar a chave ficam com o arranque; administrador e demonstração têm tela
    assert all(c.onde == artefato.ARRANQUE for c in cobertura["servir"].values())
    assert artefato.COMANDOS_SEM_OPCOES["gerar-chave"].startswith(artefato.ARRANQUE)
    campos_admin = set(primeiro_acesso.NovoAdministrador.model_fields)
    for flag, c in cobertura["criar-admin"].items():
        assert c.campo in campos_admin and c.onde.startswith(artefato.TELA_PRIMEIRO_ACESSO), flag
    assert artefato.COMANDOS_SEM_OPCOES["popular-demo"].startswith(artefato.TELA_PRIMEIRO_ACESSO)
    for rota in (
        "/api/primeiro-acesso/administrador",
        "/api/primeiro-acesso/demonstracao",
        "/api/admin/administradores",
    ):
        assert f"'{rota}'" in js, f"a interface não usa {rota}"


def test_formulario_vira_os_mesmos_argumentos_da_linha_de_comando(servico, tmp_path):
    cfg, registro = servico["cfg"], servico["tarefas"](de_mentira=True)
    parser = cli.construir_parser()
    for c in artefato.COMANDOS_DO_ARTEFATO:
        # formulário intocado = comando sem opções: os dois chegam aos mesmos valores
        par, args, mostra = artefato.montar(c, {}, tmp_path, cfg, registro)
        pela_interface = vars(parser.parse_args(args))
        direto = vars(parser.parse_args([c.nome, "--saida", str(tmp_path / "saida")]))
        for chave in ("saida", "dir_cenarios"):
            pela_interface.pop(chave, None), direto.pop(chave, None)
        assert pela_interface == direto, c.nome
        assert mostra[:3] == [c.nome, "--saida", "saida"] and str(tmp_path) not in " ".join(mostra)
    par, args, mostra = artefato.montar(
        artefato.COMANDOS["tudo"],
        {"semente": "7", "ns": "500; 800", "motor": "numpy", "sem_cox": True, "mundos": 12, "base": "so_tabela_curada"},
        tmp_path,
        cfg,
        registro,
    )
    ns = parser.parse_args(args)
    assert (ns.seed, ns.ns, ns.motor, ns.sem_cox, ns.mundos, ns.so_tabela_curada, ns.sem_metricas) == (
        7,
        [500, 800],
        "numpy",
        True,
        12,
        True,
        False,
    )
    assert par["ns"] == [500, 800] and par["base"] == "so_tabela_curada" and ns.idade_atual == 30.0
    # o que a linha de comando recusaria (ou o que o servidor não aguenta) volta como erro do campo
    for comando, valores, campo in (
        ("tudo", {"mundos": 1}, "mundos"),
        ("tudo", {"motor": "outro"}, "motor"),
        ("tudo", {"ns": "mil, dois"}, "ns"),
        ("tudo", {"n": True}, "n"),
        ("tudo", {"base": "base_que_nao_existe.csv"}, "base"),
        ("avaliar", {"cenarios": "1, 9"}, "cenarios"),
        ("avaliar", {"origem_cenarios": "20260101000000-abcdef"}, "origem_cenarios"),
        ("avaliar", {"sexo": "X"}, "sexo"),
        ("atualizar-base", {"release": "2026-13-40"}, "release"),
        ("atualizar-base", {"release": "outubro"}, "release"),
    ):
        with pytest.raises(ErroCampos) as e:
            artefato.montar(artefato.COMANDOS[comando], valores, tmp_path, cfg, registro)
        assert campo in e.value.detail["campos"], (comando, valores)
    _, args, _ = artefato.montar(
        artefato.COMANDOS["atualizar-base"], {"release": "2026-10-05"}, tmp_path, cfg, registro
    )
    assert args == ["atualizar-base", "--baixar", "--release", "2026-10-05"]


# ---------------------------------------------------------------------------
# Execuções em segundo plano
# ---------------------------------------------------------------------------
def _saida_de_mentira(pasta: Path) -> None:
    saida = pasta / "saida"
    (saida / "tabelas").mkdir(parents=True, exist_ok=True)
    (saida / "figuras").mkdir(exist_ok=True)
    (saida / "tabelas" / "tabela_13_brier.csv").write_text("previsao,brier\naté o horizonte,0.1327\n", encoding="utf-8")
    (saida / "tabelas" / "tabela_13_brier.md").write_text(
        "**Tabela 13 — Brier score**\n\n| previsao | brier |\n|---|---|\n| até o horizonte | 0.1327 |\n\n"
        "*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*\n\nNota da tabela.\n",
        encoding="utf-8",
    )
    (saida / "figuras" / "figura_10_calibracao.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    (saida / "relatorio.md").write_text(
        "# Avaliação de teste\n\n> aviso\n\n## Leitura\n\nTexto da leitura.\n\n## Tabelas\n\n(tabelas)\n\n## Figuras\n\n"
        "![Figura 10 — Calibração](figuras/figura_10_calibracao.png)\n",
        encoding="utf-8",
    )
    (saida / "metadados.json").write_text(json.dumps({"seed": 1000, "aviso_legal": "x"}), encoding="utf-8")
    (pasta / "log.txt").write_text(f"Relatório: {saida / 'relatorio.md'}\n", encoding="utf-8")


def test_execucao_pela_interface_uma_por_vez_com_saida_registro_e_pacote(servico):
    cfg, registro = servico["cfg"], servico["tarefas"](de_mentira=True)
    pesquisador, medico, admin = (servico["entrar"](f"{x}@demo.local") for x in ("pesquisador", "medico", "admin"))
    assert admin.get("/api/artefato/comandos").status_code == 403
    ctx = pesquisador.get("/api/artefato/comandos").json()
    assert [c["nome"] for c in ctx["comandos"]] == ["tudo", "avaliar", "gerar-cenarios"] and ctx["em_andamento"] is None
    assert {x["comando"] for x in ctx["equivalencia"]} >= {"executar", "avaliar", "tudo", "atualizar-base", "servir"}
    # comando desconhecido, comando de outra permissão e parâmetros que não são objeto: recusados
    for dados in (
        {"comando": "servir"},
        {"comando": "atualizar-base"},
        {"comando": "avaliar", "parametros": "[1]"},
        {"comando": "avaliar", "parametros": "{"},
    ):
        assert pesquisador.post("/api/artefato/tarefas", data=dados).status_code == 422, dados
    r = pesquisador.post(
        "/api/artefato/tarefas", data={"comando": "avaliar", "parametros": json.dumps({"mundos": "40", "sexo": "M"})}
    )
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["estado"] == "executando" and t["minha"] is True and t["papel"] == "PESQUISADOR"
    assert t["linha_de_comando"].startswith("ela-preditivo avaliar --saida saida --dir-cenarios data/sinteticos")
    assert "--mundos 40" in t["linha_de_comando"] and "--sexo M" in t["linha_de_comando"]
    lancado = servico["lancados"][-1]
    assert lancado["argumentos"][:3] == ["avaliar", "--saida", str(lancado["pasta"] / "saida")]
    # o processo não recebe a chave de cifra e enxerga a pasta de bases do servidor
    assert "ELA_WEB_CHAVE" not in lancado["ambiente"] and lancado["ambiente"]["ELA_DADOS_BRUTOS"] == str(cfg.dir_bases)
    ident, base = t["id"], f"/api/artefato/tarefas/{t['id']}"
    # uma por vez; quem não disparou vê, mas não cancela; sem saída enquanto roda
    r = medico.post("/api/artefato/tarefas", data={"comando": "gerar-cenarios"})
    assert r.status_code == 409 and "andamento" in r.json()["mensagem"]
    visto = medico.get(base).json()
    assert visto["estado"] == "executando" and visto["minha"] is False and visto["decorrido_s"] >= 0
    assert medico.delete(base).status_code == 403
    assert pesquisador.get(f"{base}/relatorio").status_code == 409
    assert pesquisador.get(f"{base}/pacote.zip").status_code == 409
    assert pesquisador.get("/api/artefato/comandos").json()["em_andamento"] == ident
    # o comando termina: saída, registro sem caminho da máquina, relatório, arquivos e pacote
    _saida_de_mentira(lancado["pasta"])
    lancado["processo"].codigo = 0
    t = pesquisador.get(base).json()
    assert t["estado"] == "concluida" and t["codigo_saida"] == 0 and t["duracao_s"] >= 0
    assert t["saida"]["relatorios"] == [{"pasta": "", "titulo": "Avaliação de teste"}]
    assert str(servico["pasta"]) not in t["registro"] and t["registro"].strip() == "Relatório: relatorio.md"
    rel = pesquisador.get(f"{base}/relatorio").json()
    assert [s["titulo"] for s in rel["secoes"]] == ["Leitura"] and "aviso_legal" not in rel["metadados"]
    tab = rel["tabelas"][0]
    assert (tab["nome"], tab["legenda"], tab["nota"]) == (
        "tabela_13_brier",
        "Tabela 13 — Brier score",
        "Nota da tabela.",
    )
    assert tab["linhas"] == [{"previsao": "até o horizonte", "brier": 0.1327}] and tab["total_de_linhas"] == 1
    assert rel["figuras"] == [
        {
            "nome": "figura_10_calibracao.png",
            "legenda": "Figura 10 — Calibração",
            "caminho": "figuras/figura_10_calibracao.png",
        }
    ]
    fig = pesquisador.get(f"{base}/arquivo", params={"caminho": "figuras/figura_10_calibracao.png"})
    assert fig.status_code == 200 and fig.headers["content-type"] == "image/png"
    csv = pesquisador.get(f"{base}/arquivo", params={"caminho": "tabelas/tabela_13_brier.csv"})
    assert csv.status_code == 200 and "attachment" in csv.headers["content-disposition"]
    # nada fora da pasta de saída é servido
    for fora in (
        "",
        "../tarefa.json",
        "../log.txt",
        "figuras/../../tarefa.json",
        "/etc/passwd",
        "..\\tarefa.json",
        "tabelas",
    ):
        assert pesquisador.get(f"{base}/arquivo", params={"caminho": fora}).status_code == 404, fora
    for fora in ("..", "../..", "/tmp", "nao_existe"):
        assert pesquisador.get(f"{base}/relatorio", params={"pasta": fora}).status_code == 404, fora
    assert pesquisador.get("/api/artefato/tarefas/20260101000000-abcdef").status_code == 404
    assert pesquisador.get("/api/artefato/tarefas/..%2F..").status_code == 404
    z = pesquisador.get(f"{base}/pacote.zip")
    assert z.status_code == 200 and sorted(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == [
        "figuras/figura_10_calibracao.png",
        "metadados.json",
        "relatorio.md",
        "tabelas/tabela_13_brier.csv",
        "tabelas/tabela_13_brier.md",
    ]
    # falha e cancelamento
    r = pesquisador.post(
        "/api/artefato/tarefas", data={"comando": "gerar-cenarios", "parametros": '{"sem_ruido": true}'}
    )
    assert (
        r.status_code == 201
        and r.json()["linha_de_comando"] == "ela-preditivo gerar-cenarios --saida saida --seed 2026 --sem-ruido"
    )
    servico["lancados"][-1]["processo"].codigo = 2
    falhou = pesquisador.get(f"/api/artefato/tarefas/{r.json()['id']}").json()
    assert falhou["estado"] == "falhou" and falhou["codigo_saida"] == 2 and falhou["saida"] is None
    r = pesquisador.post("/api/artefato/tarefas", data={"comando": "tudo"})
    assert r.status_code == 201
    cancelada = pesquisador.delete(f"/api/artefato/tarefas/{r.json()['id']}").json()
    assert cancelada["estado"] == "cancelada" and servico["lancados"][-1]["processo"].encerrado is True
    # só ficam as execuções mais recentes; a removida some do disco
    r = pesquisador.post("/api/artefato/tarefas", data={"comando": "gerar-cenarios"})
    em_curso = r.json()["id"]
    lista = pesquisador.get("/api/artefato/tarefas").json()["tarefas"]
    assert len(lista) == cfg.tarefas_guardadas and lista[0]["id"] == em_curso and ident not in {x["id"] for x in lista}
    assert not registro.pasta(ident).exists()
    # reinício do servidor com uma execução em curso: ela aparece como interrompida, não como eterna
    servico["app"].state.tarefas = artefato.RegistroTarefas(cfg)
    assert pesquisador.get(f"/api/artefato/tarefas/{em_curso}").json()["estado"] == "interrompida"
    assert pesquisador.delete(f"/api/artefato/tarefas/{em_curso}").json() == {"removida": True}
    assert pesquisador.get(f"/api/artefato/tarefas/{em_curso}").status_code == 404
    feitas = [a for a in acoes(servico) if a["alvo_tipo"] == "tarefa"]
    assert {a["acao"] for a in feitas} == {"tarefa_iniciada", "pacote_baixado", "tarefa_cancelada", "tarefa_removida"}
    assert any(a["detalhe"] == "comando=avaliar" and a["papel"] == "PESQUISADOR" for a in feitas)


def test_avaliacao_pela_interface_da_as_mesmas_tabelas_da_linha_de_comando(servico, tmp_path):
    """O comando de verdade, num processo à parte: as métricas de verificação (Tabelas 12 a 20, Figuras 10 a 12) chegam
    à interface com os mesmos números de `pipeline.avaliar` chamado diretamente com as mesmas opções."""
    servico["tarefas"](de_mentira=False)
    pesquisador = servico["entrar"]("pesquisador@demo.local")
    opcoes = {
        "cenarios": "1",
        "n": "200, 400",
        "repeticoes": 2,
        "n_coerencia": 300,
        "mundos": 6,
        "por_estrato": 3,
        "base": "so_tabela_curada",
    }
    r = pesquisador.post("/api/artefato/tarefas", data={"comando": "avaliar", "parametros": json.dumps(opcoes)})
    assert r.status_code == 201, r.text
    base = f"/api/artefato/tarefas/{r.json()['id']}"
    limite = time.time() + 300
    while (t := pesquisador.get(base).json())["estado"] == "executando" and time.time() < limite:
        time.sleep(1)
    assert t["estado"] == "concluida", t["registro"]
    rel = pesquisador.get(f"{base}/relatorio").json()
    tabelas = {x["nome"]: x for x in rel["tabelas"]}
    assert {
        "tabela_12_coorte_verificacao",
        "tabela_13_brier",
        "tabela_14_calibracao_decis",
        "tabela_15_discriminacao",
        "tabela_16_erro_idade_inicio",
        "tabela_17_cobertura_monte_carlo",
        "tabela_17b_cobertura_bandas",
        "tabela_18_divergencia_curvas",
        "tabela_19_robustez_vcf",
        "tabela_20_tornado",
    } <= set(tabelas)
    assert {f["nome"] for f in rel["figuras"]} >= {
        "figura_10_calibracao.png",
        "figura_11_robustez_vcf.png",
        "figura_12_tornado.png",
    }
    assert {"Verificação com famílias sintéticas de desfecho conhecido", "Como ler as métricas de verificação"} <= {
        s["titulo"] for s in rel["secoes"]
    }
    assert (
        tabelas["tabela_13_brier"]["legenda"].startswith("Tabela 13") and rel["metadados"]["verificacao"]["mundos"] == 6
    )
    for f in rel["figuras"]:
        img = pesquisador.get(f"{base}/arquivo", params={"caminho": f["caminho"]})
        assert img.status_code == 200 and img.content[:4] == b"\x89PNG"
    direto = pipeline.avaliar(
        SINT,
        tmp_path / "direto",
        numeros=[1],
        ns=(200, 400),
        repeticoes=2,
        seed=1000,
        sexo="F",
        n_coerencia=300,
        base_clinvar=False,
        mundos=6,
        por_estrato=3,
    )
    for nome in ("tabela_13_brier", "tabela_15_discriminacao", "tabela_17b_cobertura_bandas", "tabela_19_robustez_vcf"):
        esperado = pd.read_csv(tmp_path / "direto" / "tabelas" / f"{nome}.csv")
        csv = pesquisador.get(f"{base}/arquivo", params={"caminho": f"tabelas/{nome}.csv"})
        pd.testing.assert_frame_equal(pd.read_csv(io.BytesIO(csv.content)), esperado, check_exact=False, rtol=1e-9)
    assert direto["verificacao"] is not None


# ---------------------------------------------------------------------------
# Base de anotação
# ---------------------------------------------------------------------------
def test_base_de_anotacao_enviada_registrada_e_comparada_pela_interface(
    servico, tmp_path, variant_summary_fake, linha_vs
):
    cfg = servico["cfg"]
    servico["tarefas"](de_mentira=True)
    pesquisador, medico, admin = (servico["entrar"](f"{x}@demo.local") for x in ("pesquisador", "medico", "admin"))
    v1 = variant_summary_fake(
        tmp_path / "v1.txt",
        [
            linha_vs(clnsig="Pathogenic", revstat=MULTI, **A5V),
            linha_vs(clnsig="Uncertain significance", revstat=SINGLE, **X_TARDBP),
        ],
    )
    v2 = variant_summary_fake(
        tmp_path / "v2.txt",
        [
            linha_vs(clnsig="Pathogenic", revstat="reviewed by expert panel", **A5V),
            linha_vs(clnsig="Likely pathogenic", revstat=SINGLE, **Y_FUS),
        ],
    )

    def enviar(cliente, conteudo: bytes, nome="variant_summary.txt", release=None):
        return cliente.post(
            "/api/base/arquivos",
            files={"arquivo": (nome, conteudo, "text/plain")},
            data={"release": release} if release else {},
        )

    # sem base: todos veem a situação; só o administrador gere
    b = medico.get("/api/base").json()
    assert b["em_uso"] is None and "só a tabela curada" in b["sem_base"] and b["pode_gerir"] is False
    assert admin.get("/api/base").json()["pode_gerir"] is True and pesquisador.get("/api/base").status_code == 200
    for cliente in (medico, pesquisador):
        assert enviar(cliente, v1.read_bytes(), release="2026-09-28").status_code == 403
        assert cliente.post("/api/base/versoes", json={}).status_code == 403
        assert cliente.post("/api/base/baixar", json={}).status_code == 403
    assert admin.post("/api/base/versoes", json={}).status_code == 409  # nada a registrar ainda
    # nome fora do que o artefato reconhece, release ausente ou torta, conteúdo que não é base
    r = enviar(admin, v1.read_bytes(), nome="minha_base.csv", release="2026-09-28")
    assert r.status_code == 422 and "Nome de arquivo" in r.json()["campos"]["arquivo"]
    r = enviar(admin, v1.read_bytes())
    assert r.status_code == 422 and "informe-a" in r.json()["campos"]["release"]
    assert (
        enviar(admin, v1.read_bytes(), release="28/09/2026").json()["campos"]["release"] == "Use o formato AAAA-MM-DD."
    )
    r = enviar(admin, b"isto nao e uma base\n", nome="clinvar_20260928.vcf")
    assert r.status_code == 422 and "arquivo" in r.json()["campos"]
    assert not list(cfg.dir_bases.glob("*.txt")) and not (cfg.dir_bases / "_envio").exists()
    # primeira versão: guardada na pasta de bases, vira a base em uso e fica registrada
    r = enviar(admin, v1.read_bytes(), release="2026-09-28")
    assert r.status_code == 201, r.text
    d = r.json()
    assert (d["arquivo"], d["variantes"], d["em_uso"], d["substituida"], d["anterior"]) == (
        "variant_summary.txt",
        2,
        True,
        None,
        None,
    )
    assert (
        d["atual"]["release"] == "2026-09-28" and "caminho" not in d["atual"] and str(cfg.dir_bases) not in d["resumo"]
    )
    assert (cfg.dir_bases / "variant_summary.txt").read_bytes() == v1.read_bytes()
    b = pesquisador.get("/api/base").json()
    assert b["em_uso"]["nome"] == "variant_summary.txt" and b["sem_base"] is None and len(b["versoes"]) == 1
    assert b["arquivos"][0]["registrada"] is True and b["arquivos"][0]["sha256"] == d["atual"]["sha256"]
    # segunda versão com o mesmo nome: a anterior vai para anteriores/ e sai o relatório do que mudou
    r = enviar(admin, v2.read_bytes(), release="2026-10-26")
    assert r.status_code == 201, r.text
    d2 = r.json()
    assert d2["substituida"] == f"{d['atual']['sha256'][:8]}_variant_summary.txt"
    assert (cfg.dir_bases / "anteriores" / d2["substituida"]).read_bytes() == v1.read_bytes()
    assert d2["relatorio"] == "atualizacao_2026-09-28_2026-10-26.md" and d2["anterior"]["release"] == "2026-09-28"
    b = medico.get("/api/base").json()
    assert [v["release"] for v in b["versoes"]] == ["2026-10-26", "2026-09-28"] and b["relatorios"] == [d2["relatorio"]]
    texto = medico.get(f"/api/base/relatorios/{d2['relatorio']}").json()["texto"]
    assert "2026-09-28" in texto and "2026-10-26" in texto
    for fora in ("versoes.json", "..%2Fvariant_summary.txt", "atualizacao_x.md"):
        assert medico.get(f"/api/base/relatorios/{fora}").status_code == 404, fora
    # registrar de novo a base em uso não duplica a versão; arquivo desconhecido é recusado
    assert admin.post("/api/base/versoes", json={"release": "2026-10-26"}).status_code == 201
    assert len(admin.get("/api/base").json()["versoes"]) == 2
    assert admin.post("/api/base/versoes", json={"arquivo": "outra.csv"}).json()["campos"]["arquivo"]
    # download da release: o mesmo comando da linha de comando, em segundo plano
    assert admin.post("/api/base/baixar", json={"release": "ontem"}).json()["campos"]["release"]
    r = admin.post("/api/base/baixar", json={"release": "2026-10-05"})
    assert (
        r.status_code == 201
        and r.json()["linha_de_comando"] == "ela-preditivo atualizar-base --baixar --release 2026-10-05"
    )
    assert servico["lancados"][-1]["argumentos"] == ["atualizar-base", "--baixar", "--release", "2026-10-05"]
    tid = r.json()["id"]
    assert medico.get(f"/api/base/tarefas/{tid}").json()["estado"] == "executando"
    assert medico.get("/api/base").json()["tarefa"]["id"] == tid
    assert medico.get(f"/api/artefato/tarefas/{tid}").status_code == 404  # não é execução do artefato
    assert tid not in {x["id"] for x in medico.get("/api/artefato/tarefas").json()["tarefas"]}
    servico["lancados"][-1]["processo"].codigo = 0
    assert medico.get(f"/api/base/tarefas/{tid}").json()["estado"] == "concluida"
    # a análise usa a base em uso e a declara; "só a tabela curada" continua disponível
    assert medico.get("/api/artefato/comandos").json()["base_em_uso"] == "variant_summary.txt"
    for base, esperado in ((None, "variant_summary.txt"), ("so_tabela_curada", "só a tabela curada")):
        dados = {"modo": "cenario", "cenario": "1", "n": "300", "cox": "0"}
        r = medico.post("/api/analises", data={**dados, "base": base} if base else dados)
        assert r.status_code == 201, r.text
        res = r.json()
        assert res["entrada"]["base"] == esperado and res["sem_locus"] is False
        assert bool(res["metadados"]["base_anotacao"]["base_real"]) is (base is None)
    r = medico.post("/api/analises", data={"modo": "cenario", "cenario": "1", "base": "nao_existe.csv"})
    assert r.status_code == 422 and "base" in r.json()["campos"]
    feitas = {a["acao"]: a for a in acoes(servico) if a["alvo_tipo"] == "base"}
    assert set(feitas) == {"base_enviada", "base_registrada"} and feitas["base_enviada"]["papel"] == "ADMIN"
    assert "variant_summary.txt" in feitas["base_enviada"]["detalhe"]


# ---------------------------------------------------------------------------
# Análise sem registro: as opções avançadas da linha de comando
# ---------------------------------------------------------------------------
def test_analise_sem_registro_aceita_as_opcoes_avancadas_da_linha_de_comando(servico, tmp_path):
    medico, admin = servico["entrar"]("medico@demo.local"), servico["entrar"]("admin@demo.local")
    comum = {
        "modo": "cenario",
        "cenario": "1",
        "n": "400",
        "semente": "42",
        "motor": "numpy",
        "base": "so_tabela_curada",
    }
    r = medico.post(
        "/api/analises", data={**comum, "horizonte": "70", "rotulo": "Caso de teste", "sem_figuras": "1", "cox": "1"}
    )
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["metadados"]["horizonte"] == 70 and res["figuras"] == [] and res["entrada"]["sem_figuras"] is True
    assert res["relatorio_md"].splitlines()[0].endswith("Caso de teste") and res["entrada"]["horizonte"] == 70
    assert res["entrada"]["parametros_alternativos"] is False and res["entrada"]["tabela_alternativa"] is False
    # o mesmo que `ela-preditivo executar ... --horizonte 70 --sem-figuras --so-tabela-curada --cox`
    direto = pipeline.executar(
        cenarios.vcf_cenario(SINT, 1, "mae"),
        cenarios.vcf_cenario(SINT, 1, "pai"),
        tmp_path / "direto",
        n=400,
        seed=42,
        motor="numpy",
        horizonte=70,
        figuras=False,
        base_clinvar=False,
        comparar_cox=True,
        rotulo="Caso de teste",
    )
    for chave in ("p_portador_qualquer_exato", "p_manifesta_qualquer_exato", "p_manifesta_qualquer_q975"):
        assert res["combinado"][chave] == pytest.approx(direto["combinado"][chave], rel=1e-12), chave
    padrao = medico.post("/api/analises", data=comum).json()
    assert padrao["metadados"]["horizonte"] == 90 and padrao["figuras"] and padrao["entrada"]["horizonte"] is None
    assert padrao["combinado"]["p_manifesta_qualquer_exato"] > res["combinado"]["p_manifesta_qualquer_exato"]
    # parâmetros alternativos (--config): aceitos se o artefato os lê, e declarados no resultado
    yaml_padrao = CAMINHO_PADRAO.read_text(encoding="utf-8")
    assert yaml_padrao.count("horizonte_anos: 90") == 1
    r = medico.post(
        "/api/analises",
        data=comum,
        files={
            "config": (
                "meus.yaml",
                yaml_padrao.replace("horizonte_anos: 90", "horizonte_anos: 80").encode(),
                "text/yaml",
            )
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["metadados"]["horizonte"] == 80 and r.json()["entrada"]["parametros_alternativos"] is True
    r = medico.post(
        "/api/analises", data=comum, files={"config": ("ruim.yaml", b"genes: [isto nao fecha", "text/yaml")}
    )
    assert r.status_code == 422 and "YAML" in r.json()["campos"]["config"]
    # tabela de variantes alternativa (--tabela-variantes)
    r = medico.post(
        "/api/analises",
        data=comum,
        files={"tabela_variantes": ("curada.csv", anotacao.CAMINHO_TABELA.read_bytes(), "text/csv")},
    )
    assert r.status_code == 201 and r.json()["entrada"]["tabela_alternativa"] is True
    r = medico.post("/api/analises", data=comum, files={"tabela_variantes": ("ruim.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code == 422 and "tabela_variantes" in r.json()["campos"]
    # amostra do VCF (--amostra-mae): a que existe passa, a que não existe é erro da análise
    amostra = next(
        linha.split("\t")[-1]
        for linha in (cenarios.vcf_cenario(SINT, 1, "mae")).read_text(encoding="utf-8").splitlines()
        if linha.startswith("#CHROM")
    )
    r = medico.post("/api/analises", data={**comum, "amostra_mae": amostra})
    assert r.status_code == 201 and r.json()["entrada"]["amostras"] == {"mae": amostra}
    assert medico.post("/api/analises", data={**comum, "amostra_mae": "AMOSTRA_QUE_NAO_EXISTE"}).status_code == 422
    assert medico.post("/api/analises", data={**comum, "horizonte": "500"}).json()["campos"]["horizonte"]
    # os arquivos em uso podem ser baixados por quem vê o modelo, para editar e reenviar
    r = medico.get("/api/parametros/arquivo")
    assert r.status_code == 200 and r.content == CAMINHO_PADRAO.read_bytes()
    assert medico.get("/api/parametros/tabela-variantes").content == anotacao.CAMINHO_TABELA.read_bytes()
    assert admin.get("/api/parametros/arquivo").status_code == 403
