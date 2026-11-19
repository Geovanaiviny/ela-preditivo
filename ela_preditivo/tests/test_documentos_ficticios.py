"""Documentos fictícios das fichas de teste: o prontuário e o laudo do C9orf72 em PDF, ao lado dos VCFs sintéticos,
gerados pelo artefato sem biblioteca externa e aceitos pela plataforma."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from ela_preditivo import DIR_DADOS, cenarios, cli
from ela_preditivo import documentos_ficticios as docs
from ela_preditivo.web import arquivos, demo, textos
from ela_preditivo.web.api import criar_app
from ela_preditivo.web.config import Configuracao, gerar_chave
from ela_preditivo.web.seguranca import Cifra

SINT = DIR_DADOS / "sinteticos"


def cp(texto: str) -> bytes:
    return texto.encode("cp1252")


def texto_do_pdf(dados: bytes) -> bytes:
    """O conteúdo com os parênteses dos textos sem a barra de escape do PDF."""
    return dados.replace(b"\\(", b"(").replace(b"\\)", b")")


def iso(data: str) -> str:
    d, m, a = data.split("/")
    return f"{a}-{m}-{d}"


def test_documentos_sao_reproduziveis_e_iguais_aos_versionados(tmp_path):
    a = docs.gerar_documentos(tmp_path / "a")
    docs.gerar_documentos(tmp_path / "b")
    nomes = [p.name for p in a]
    assert len(nomes) == len(set(nomes)) == 18  # 7 prontuários e 11 laudos (três genitores não têm laudo)
    for p in a:
        rel = p.relative_to(tmp_path / "a")
        assert rel.parts[0] in cenarios.PASTAS_CASO.values()
        assert p.read_bytes() == (tmp_path / "b" / rel).read_bytes() == (SINT / rel).read_bytes(), rel
    # nenhum PDF versionado sem ficha, e cada um na pasta do caso da ficha
    assert {p.relative_to(SINT) for p in SINT.rglob("*.pdf")} == {p.relative_to(tmp_path / "a") for p in a}


def test_cada_pdf_e_valido_pequeno_e_marcado_como_ficticio():
    for ficha in docs.FICHAS_DE_TESTE:
        for nome, dados in docs.documentos_da_ficha(ficha).items():
            assert dados.startswith(arquivos.ASSINATURAS["application/pdf"]) and dados.rstrip().endswith(b"%%EOF"), nome
            assert len(dados) < 8_000, nome
            # a tabela de referências aponta para o começo de cada objeto
            inicio = int(dados.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
            assert dados[inicio : inicio + 5] == b"xref\n"
            linhas = dados[inicio:].split(b"\n")
            n = int(linhas[1].split()[1])
            for i in range(1, n):
                posicao = int(linhas[2 + i].split()[0])
                assert dados[posicao:].startswith(b"%d 0 obj" % i), (nome, i)
            for marca in ("FICTÍCIO", "NÃO É DOCUMENTO CLÍNICO", "Sem valor clínico", ficha.prontuario):
                assert cp(marca) in dados, (nome, marca)
            assert b"/Producer (ela_preditivo)" in dados and b"CreationDate" not in dados  # sem data do dia


def test_laudo_traz_as_repeticoes_e_a_leitura_pelos_limiares_do_artefato():
    ficha = next(f for f in docs.FICHAS_DE_TESTE if f.codigo == "1A")
    mae, pai = (texto_do_pdf(docs.laudo_c9orf72(ficha, lado)) for lado in ("mae", "pai"))
    for trecho in ("Sônia Fictícia Andrade", "08/03/1966", "Maior alelo: 45 repetições GGGGCC", "faixa patogênica"):
        assert cp(trecho) in mae, trecho
    assert cp("Maior alelo: 23 repetições GGGGCC") in pai and cp("faixa normal (até 23 repetições)") in pai
    assert docs.interpretar_repeticoes(45).startswith("Expansão na faixa patogênica (30 repetições ou mais)")
    assert docs.interpretar_repeticoes(26).startswith("Alelo na faixa intermediária (24 a 29 repetições)")
    assert docs.interpretar_repeticoes(cenarios.LAUDO_NORMAL).startswith("Sem expansão")
    sem_laudo = next(f for f in docs.FICHAS_DE_TESTE if f.codigo == "1B")
    assert [lado for lado, _ in sem_laudo.laudos()] == ["mae"]
    with pytest.raises(ValueError, match="não tem laudo"):
        docs.laudo_c9orf72(sem_laudo, "pai")
    pront = texto_do_pdf(docs.prontuario(sem_laudo))
    for trecho in ("Prontuário nº HML-1002", "Falecido sem ter tido ELA, aos 60 anos", "parentes_1_avo_paterna.vcf"):
        assert cp(trecho) in pront, trecho


def test_fichas_batem_com_os_cenarios_e_com_a_plataforma():
    fichas = docs.FICHAS_DE_TESTE
    assert [f.codigo for f in fichas] == ["1A", "1B", "1C", "2A", "2B", "3A", "3B"]
    assert len({f.prontuario for f in fichas}) == 7
    laudo_do_vcf = {}  # VCF sintético → repetições que o cenário dele declara
    for c in cenarios.CENARIOS:
        for lado in ("mae", "pai"):
            laudo_do_vcf[f"cenario_{c.numero}_{lado}.vcf"] = c.laudo_c9orf72.get(lado)
    for c in cenarios.CENARIOS_CASAL:
        for lado, n in c.laudos:
            laudo_do_vcf[f"casal_{c.numero}_{lado}.vcf"] = n
    demonstracao = set(demo.NOMES_FICTICIOS)
    for f in fichas:
        pessoas = [f.mae, f.pai, *f.descendentes]
        citados = [p.vcf for p in pessoas if p.vcf] + [p.parente[1] for p in pessoas if p.parente]
        for nome in citados:  # todo VCF citado existe na pasta do caso da ficha
            assert (cenarios.pasta_caso(SINT, f.caso) / nome).is_file(), (f.codigo, nome)
        for p in (f.mae, f.pai):
            if p.vcf in laudo_do_vcf:
                assert p.repeticoes == laudo_do_vcf[p.vcf], (f.codigo, p.vcf)
            elif p.repeticoes is not None:  # cenários de parentes: laudo normal
                assert p.repeticoes == cenarios.LAUDO_NORMAL
            assert (p.vcf is None) == (p.repeticoes is None)  # quem não fez exame também não tem laudo
        for p in pessoas:
            assert re.search(r"Fictíci[ao]", p.nome) and p.nome not in demonstracao, p.nome
            assert re.fullmatch(r"\d{2}/\d{2}/\d{4}", p.nascimento)
        assert docs.ROTULO_CASO[f.caso] == next(
            t["rotulo"] for t in textos.TIPOS_ATENDIMENTO.values() if t["numero"] == f.caso
        )
        assert f.momento in textos.MOMENTOS.values()
        assert (f.caso == 2) == (not f.descendentes)  # no casal a análise é do futuro filho


def test_comando_de_cenarios_grava_tambem_os_documentos(tmp_path, capsys):
    assert cli.main(["gerar-cenarios", "--saida", str(tmp_path / "s")]) == 0
    saida = capsys.readouterr().out
    assert "18 documentos fictícios das 7 fichas de teste" in saida
    assert len(list((tmp_path / "s").rglob("*.pdf"))) == 18 and len(list((tmp_path / "s").rglob("*.vcf"))) == 18


def test_ficha_1a_e_cadastrada_e_analisada_com_os_documentos_gerados(tmp_path):
    """O caminho do roteiro de testes, pela API: cadastro, prontuário, laudos, VCFs e análise da ficha 1A."""
    cfg = Configuracao(
        chave=gerar_chave().encode(), bd=tmp_path / "bd.sqlite3", dir_vcfs=tmp_path / "vcfs", demonstracao=True
    )
    app = criar_app(cfg)
    with app.state.sessoes() as bd:
        cred = {c["email"]: c for c in demo.popular(bd, Cifra(cfg.chave), cfg, analisar=False)["credenciais"]}
    medico = TestClient(app)
    r = medico.post(
        "/api/contas/login", json={"email": "medico@demo.local", "senha": cred["medico@demo.local"]["senha"]}
    )
    medico.headers["X-CSRF-Token"] = r.json()["csrf"]
    f = next(x for x in docs.FICHAS_DE_TESTE if x.codigo == "1A")
    pasta = cenarios.pasta_caso(SINT, f.caso)
    pessoa = f.descendentes[0]
    r = medico.post(
        "/api/pacientes",
        json={
            "tipo": "PESSOA",
            "prontuario": f.prontuario,
            "mae": {
                "nome": f.mae.nome,
                "data_nascimento": iso(f.mae.nascimento),
                "laudo_c9orf72": str(f.mae.repeticoes),
            },
            "pai": {
                "nome": f.pai.nome,
                "data_nascimento": iso(f.pai.nascimento),
                "laudo_c9orf72": str(f.pai.repeticoes),
            },
            "descendentes": [{"nome": pessoa.nome, "data_nascimento": iso(pessoa.nascimento), "sexo": pessoa.sexo[0]}],
        },
    )
    assert r.status_code == 201, r.text
    pid, did = r.json()["id"], r.json()["descendentes"][0]["id"]
    envios = [("PRONTUARIO", None, f.nome_do_prontuario)] + [
        ("LAUDO_C9ORF72", lado.upper(), f.nome_do_laudo(lado)) for lado, _ in f.laudos()
    ]
    for tipo, papel, nome in envios:  # a plataforma aceita os três PDFs
        dados = {"tipo": tipo, **({"papel": papel} if papel else {})}
        r = medico.post(
            f"/api/pacientes/{pid}/documentos",
            data=dados,
            files={"arquivo": (nome, (pasta / nome).read_bytes(), "application/pdf")},
        )
        assert r.status_code == 201, (nome, r.text)
    for papel, g in (("MAE", f.mae), ("PAI", f.pai)):
        r = medico.post(
            f"/api/pacientes/{pid}/genitores/{papel}/vcf",
            files={"vcf": (g.vcf, (pasta / g.vcf).read_bytes(), "text/plain")},
        )
        assert r.status_code == 201, r.text
    ficha = medico.get(f"/api/pacientes/{pid}").json()
    assert ficha["prontuario_documento"] and all(ficha["genitores"][p]["laudo_documento"] for p in ("MAE", "PAI"))
    r = medico.post(
        "/api/analises",
        data={
            "paciente_id": str(pid),
            "descendente_id": str(did),
            "n": "300",
            "cox": "0",
            "confirma_assintomatico": "1",
        },
    )
    assert r.status_code == 201, r.text
    res = r.json()
    assert sorted(x["gene"] for x in res["resumo"]) == ["C9orf72", "SOD1"] and res["c9orf72_indeterminado"] is False
    assert res["metadados"]["laudo_c9orf72"] == {"mae": 45, "pai": 23} and res["principais"]["condicionado"] is True
    app.state.analises.encerrar()
