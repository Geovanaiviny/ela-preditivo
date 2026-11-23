"""Apresentação dos resultados: tempos dos motores, texto das classes, rótulos das tabelas e conversor numérico da tela.

O conversor e o dicionário de rótulos vivem em `app.js`; aqui eles rodam em Node, sem navegador (o teste é pulado se
não houver Node)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from ela_preditivo import DIR_DADOS, cenarios, cli, pipeline
from ela_preditivo.web import pacientes

APP_JS = Path(pacientes.__file__).parent / "static" / "app.js"
CASO_1 = DIR_DADOS / "sinteticos" / "caso_1_pessoa_com_historico"
precisa_node = pytest.mark.skipif(shutil.which("node") is None, reason="Node não está instalado")


def _node(roteiro: str):
    codigo = f"""
    const fs = require('fs');
    const fonte = fs.readFileSync({json.dumps(str(APP_JS))}, 'utf8');
    const trecho = (de, ate) => fonte.slice(fonte.indexOf(de), fonte.indexOf(ate));
    const modulo = new Function(
      trecho('function localizarNumeros', 'function fmtCelula') + ';' +
      trecho('const ROTULOS_TABELA_CLINICA', 'function tabelaRegistros') +
      ';return {{ localizarNumeros, rotuloTabelaClinica, semCitacaoTCC, ROTULOS_TABELA_CLINICA }};'
    )();
    {roteiro}
    """
    saida = subprocess.run(["node", "-e", codigo], capture_output=True, text=True, check=True, encoding="utf-8")
    return json.loads(saida.stdout)


# ---------------------------------------------------------------------------
# K3: tempos dos motores
# ---------------------------------------------------------------------------


def test_tempo_legivel_nos_tres_regimes():
    assert pipeline.tempo_legivel(0.973724) == "0.97 s"
    assert pipeline.tempo_legivel(12.3456) == "12.35 s"
    assert pipeline.tempo_legivel(0.01) == "0.01 s"  # a partir de 10 ms, segundos
    assert pipeline.tempo_legivel(0.000599549) == "0.6 ms"
    assert pipeline.tempo_legivel(0.0099) == "9.9 ms"
    assert pipeline.tempo_legivel(None) == "não executado"
    assert pipeline.tempo_legivel(float("nan")) == "não executado"


def test_relatorio_de_execucao_real_tem_tempos_legiveis_e_metadados_brutos(tmp_path):
    saida = tmp_path / "resultado"
    argumentos = [
        "executar",
        "--vcf-mae",
        str(CASO_1 / "cenario_1_mae.vcf"),
        "--vcf-pai",
        str(CASO_1 / "cenario_1_pai.vcf"),
    ]
    argumentos += ["--saida", str(saida), "--c9orf72-mae", "23", "--c9orf72-pai", "23", "--n", "300", "--sem-figuras"]
    assert cli.main(argumentos) == 0
    texto = (saida / "relatorio.md").read_text(encoding="utf-8")
    tempos = re.search(r"\(pymc: ([^;]+); numpy: ([^)]+)\)", texto) or re.search(
        r"\(numpy: ([^;]+); pymc: ([^)]+)\)", texto
    )
    assert tempos, texto
    for t in tempos.groups():
        assert re.fullmatch(r"\d+\.\d{2} s|\d+\.\d ms", t), t  # no máximo duas casas em segundos
    meta = json.loads((saida / "metadados.json").read_text(encoding="utf-8"))
    assert all(isinstance(v, float) and v > 0 for v in meta["tempo_motores_s"].values())  # valor bruto, ponto decimal
    assert "classes: " in texto
    linha = next(l for l in texto.splitlines() if "classes: " in l)
    trecho = linha.split("classes: ", 1)[1].split(";", 1)[0]
    assert "{" not in trecho and "'" not in trecho and '"' not in trecho


# ---------------------------------------------------------------------------
# C4: texto das classes
# ---------------------------------------------------------------------------


def _indicadores(por_classe: dict) -> dict:
    return {
        "montagem": "GRCh38", "montagem_coerente": True, "registros": 9, "registros_nas_regioes": 9, "aprovados": 9,
        "taxa_aprovacao": 1.0, "anotadas": 9, "taxa_anotacao": 1.0, "por_estrelas": {1: 3}, "por_classe": por_classe,
        "n_vus": 0, "proporcao_vus": 0.0, "n_conflitante": 0, "proporcao_conflitante": 0.0,
        "risco_com_frequencia_acima_1pct": 0,
    }  # fmt: skip


def test_texto_das_classes_com_singular_e_plural():
    texto = pipeline._texto_qualidade(_indicadores({"risco": 1, "benigna": 2, "vus": 1, "normal": 3, "nao_anotada": 1}))
    assert "classes: 1 de risco, 2 benignas, 1 de significado incerto, 3 normais, 1 não anotada;" in texto
    assert "{" not in texto and "'" not in texto
    texto = pipeline._texto_qualidade(_indicadores({"intermediaria": 1, "conflitante": 2, "nao_classificada": 2}))
    assert "1 intermediária, 2 com classificação conflitante, 2 não classificadas;" in texto


# ---------------------------------------------------------------------------
# C3 e K7: conversor numérico da tela
# ---------------------------------------------------------------------------

CASOS_NUMEROS = {
    "17.9%": "17,9 %",
    "0.982–0.987": "0,982–0,987",
    "1.70 erros padrão": "1,70 erros padrão",
    "0.000599549 s": "0,000599549 s",
    "0.6 ms": "0,6 ms",
    "0.97 s": "0,97 s",
    "N = 10.000": "N = 10.000",
    "3.250 sorteios": "3.250 sorteios",
    "5.10.4": "5.10.4",
    "0.1.0": "0.1.0",
    "TCC 4.2.3": "TCC 4.2.3",
    "cenario_1.vcf": "cenario_1.vcf",
    "2026-11-16": "2026-11-16",
    "1.5e-05": "1,5e-05",
    # milhar fora dos contextos previstos: três casas com parte inteira diferente de zero não viram decimal
    "1.457 registros": "1.457 registros",
    "foram 12.345 linhas": "foram 12.345 linhas",
    "1.457 s": "1,457 s",
}


@precisa_node
def test_conversor_de_numeros_da_tela():
    entradas = json.dumps(list(CASOS_NUMEROS))
    obtido = _node(f"console.log(JSON.stringify({entradas}.map((t) => modulo.localizarNumeros(t))));")
    assert dict(zip(CASOS_NUMEROS, obtido)) == CASOS_NUMEROS


@precisa_node
def test_conversor_aplicado_ao_texto_dos_tempos_do_relatorio():
    entradas = json.dumps(
        ["Tempo: 0.7 s no total (pymc: 0.11 s; numpy: 0.4 ms).", "pymc: não executado; numpy: não executado"]
    )
    obtido = _node(f"console.log(JSON.stringify({entradas}.map((t) => modulo.localizarNumeros(t))));")
    assert obtido == [
        "Tempo: 0,7 s no total (pymc: 0,11 s; numpy: 0,4 ms).",
        "pymc: não executado; numpy: não executado",
    ]


# ---------------------------------------------------------------------------
# K4: rótulos das tabelas e citações do TCC na tela
# ---------------------------------------------------------------------------


@precisa_node
def test_rotulos_legiveis_em_todas_as_tabelas_de_um_resultado_real(tmp_path):
    saida = tmp_path / "resultado"
    argumentos = [
        "executar",
        "--vcf-mae",
        str(CASO_1 / "cenario_1_mae.vcf"),
        "--vcf-pai",
        str(CASO_1 / "cenario_1_pai.vcf"),
    ]
    argumentos += ["--saida", str(saida), "--c9orf72-mae", "23", "--c9orf72-pai", "23", "--n", "300", "--sem-figuras"]
    argumentos += ["--idade-atual", "36", "--cox", "--tornado"]
    assert cli.main(argumentos) == 0
    colunas: dict[str, list[str]] = {}
    for csv in sorted((saida / "tabelas").glob("*.csv")):
        colunas[csv.stem] = csv.read_text(encoding="utf-8-sig").splitlines()[0].split(",")
    assert {"tabela_03_risco_vitalicio", "tabela_04_risco_condicional", "tabela_10_kaplan_meier"} <= set(colunas)
    entradas = json.dumps(sorted({c for cs in colunas.values() for c in cs}))
    rotulos = dict(
        zip(
            json.loads(entradas),
            _node(f"console.log(JSON.stringify({entradas}.map((c) => modulo.rotuloTabelaClinica(c))));"),
        )
    )
    assert rotulos
    dicionario = _node("console.log(JSON.stringify(Object.keys(modulo.ROTULOS_TABELA_CLINICA)));")
    for coluna, rotulo in rotulos.items():
        assert "_" not in rotulo, (coluna, rotulo)
        base = coluna.upper().removesuffix("_Q025").removesuffix("_Q975")
        assert (
            base in dicionario or not re.search(r"_", coluna) or re.search(r"[(\[]", coluna)
        ), f"{coluna} sem rótulo no dicionário"
        assert not (rotulo.isupper() and len(rotulo) > 3), (coluna, rotulo)
        assert rotulo[0].isupper() or rotulo[0].isdigit(), (coluna, rotulo)
    assert rotulos["risco_vitalicio_km"] == "Risco vitalício (Kaplan-Meier)"
    assert rotulos["ep_portador"] == "Erro padrão da probabilidade de ser portador"
    assert rotulos["risco_10_anos_q025"] == "Risco nos próximos 10 anos, limite inferior"
    assert rotulos["risco_10_anos_q975"] == "Risco nos próximos 10 anos, limite superior"


@precisa_node
def test_coluna_sem_rotulo_cai_no_texto_simples_e_nunca_em_caixa_alta():
    entradas = json.dumps(["coluna_nova_qualquer", "OUTRA_COLUNA_TECNICA", "Gene", "coluna simples"])
    obtido = _node(f"console.log(JSON.stringify({entradas}.map((c) => modulo.rotuloTabelaClinica(c))));")
    assert obtido == ["Coluna nova qualquer", "Outra coluna tecnica", "Gene", "Coluna simples"]


@precisa_node
def test_citacao_do_tcc_sai_do_texto_das_abas_clinicas():
    entradas = json.dumps(
        [
            "Qualidade dos dados (TCC 4.2.3)",
            "regra de classe: só Pathogenic sustentam risco (TCC 4.2.2).",
            "pela regra do TCC 4.2.2 (significado incerto)",
            "descartados (TCC 4.3; não entram no cálculo)",
        ]
    )
    obtido = _node(f"console.log(JSON.stringify({entradas}.map((t) => modulo.semCitacaoTCC(t))));")
    assert obtido == [
        "Qualidade dos dados",
        "regra de classe: só Pathogenic sustentam risco.",
        "pela regra do modelo (significado incerto)",
        "descartados (não entram no cálculo)",
    ]
    assert all("TCC" not in t for t in obtido)
