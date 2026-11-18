"""Regras do artefato vindas do texto do TCC e da robustez do pipeline: genótipo não determinado, classes de
patogenicidade, calibração por estatísticas publicadas, limpeza da pasta de saída, limiares de qualidade, critério
da faixa de incidência, banda de credibilidade combinada, laudo do C9orf72 e reprodutibilidade dos VCFs."""

import datetime as _dt
import json
import warnings

import numpy as np
import pandas as pd
import pytest
import yaml
from scipy import stats

from ela_preditivo import (
    DIR_DADOS,
    anotacao,
    avaliacao,
    calibracao,
    cenarios,
    exato,
    genotipo,
    ingestao,
    monte_carlo,
    pipeline,
    relatorio,
    sobrevivencia,
)
from ela_preditivo.exato import DistribuicaoInicio

A5V = ("21", 31659783, "rs121912442", "C", "T")  # SOD1 p.Ala5Val (tabela curada: "A4V (p.A5V)")
R521C = ("16", 31191418, "rs121909668", "C", "T")  # FUS p.Arg521Cys (tabela curada: "R521C")
D91A = dict(
    allele_id="17",
    gene="SOD1",
    nome="NM_000454.5(SOD1):c.272A>C (p.Asp91Ala)",
    rs="80265967",
    crom="21",
    pos=31667290,
    ref="A",
    alt="C",
    vid="13894",
)
LAUDO_NORMAL_2 = {
    "mae": cenarios.LAUDO_NORMAL,
    "pai": cenarios.LAUDO_NORMAL,
}  # os dois genitores testados, sem expansão
A5V_VS = dict(
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


# ---------------------------------------------------------------------------
# A1 — genótipo não determinado num genitor descarta o lócus inteiro (TCC 4.3)
# ---------------------------------------------------------------------------
def test_genotipo_indeterminado_descarta_o_locus_inteiro(tmp_path, parametros, curada, vcf_minimo):
    mae = anotacao.anotar(
        ingestao.ler_vcf(vcf_minimo(tmp_path / "mae.vcf", "MAE", [A5V + ("./.",), R521C + ("0/1",)])), curada
    )
    pai = anotacao.anotar(
        ingestao.ler_vcf(vcf_minimo(tmp_path / "pai.vcf", "PAI", [A5V + ("0/1",), R521C + ("0/0",)])), curada
    )
    with pytest.warns(UserWarning, match="não determinado"):
        v = genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72=LAUDO_NORMAL_2, tabela=curada).set_index("gene")
    # SOD1: mãe './.' → lócus descartado, dosagem da mãe vazia, pai 1, sem P(portador). Antes: dosagem 0 e P(portador) = 0,5.
    assert (
        bool(v.loc["SOD1", "descartado"])
        and pd.isna(v.loc["SOD1", "dosagem_mae"])
        and v.loc["SOD1", "dosagem_pai"] == 1
    )
    assert (
        pd.isna(v.loc["SOD1", "p_portador_exato"])
        and "mãe" in v.loc["SOD1", "observacao"]
        and "TCC 4.3" in v.loc["SOD1", "observacao"]
    )
    # FUS: determinado nos dois → segue normalmente
    assert not bool(v.loc["FUS", "descartado"]) and v.loc["FUS", "p_portador_exato"] == pytest.approx(0.5)
    assert [l.gene for l in monte_carlo.loci_de_vetor(v.reset_index(), parametros)] == ["FUS"]
    # pipeline: só o FUS entra no cálculo; o descarte vai para o relatório, a Tabela 1b e os metadados
    r = pipeline.executar(
        tmp_path / "mae.vcf",
        tmp_path / "pai.vcf",
        tmp_path / "saida",
        n=300,
        seed=1,
        motor="numpy",
        figuras=False,
        base_clinvar=False,
        laudo_c9orf72=LAUDO_NORMAL_2,
    )
    assert [l.gene for l in r["loci"]] == ["FUS"]
    texto = (tmp_path / "saida" / "relatorio.md").read_text(encoding="utf-8")
    assert "descartados por genótipo não determinado" in texto and "SOD1 A4V (p.A5V)" in texto and "Tabela 1b" in texto
    meta = json.loads((tmp_path / "saida" / "metadados.json").read_text(encoding="utf-8"))
    assert meta["loci_descartados"] == ["A4V (p.A5V)"] and meta["loci"] == ["FUS R521C"]
    # pai indeterminado no único lócus de risco: nenhum lócus utilizável, e o relatório diz por quê
    mae2 = vcf_minimo(tmp_path / "mae2.vcf", "MAE", [A5V + ("0/1",)])
    pai2 = vcf_minimo(tmp_path / "pai2.vcf", "PAI", [A5V + ("./.",)])
    r2 = pipeline.executar(
        mae2,
        pai2,
        tmp_path / "saida2",
        n=300,
        motor="numpy",
        figuras=False,
        base_clinvar=False,
        laudo_c9orf72=LAUDO_NORMAL_2,
    )
    assert r2["res"] is None and len(r2["vetor"]) == 1 and bool(r2["vetor"].descartado.all())
    assert "Nenhum lócus de risco utilizável" in (tmp_path / "saida2" / "relatorio.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A2 — classe "conflitante" existe e é contada à parte das incertas (Quadro 15 do TCC)
# ---------------------------------------------------------------------------
def test_classe_conflitante_contada_a_parte(tmp_path, variant_summary_fake, linha_vs):
    f = anotacao.classificar_clnsig
    assert "conflitante" in anotacao.CLASSES
    assert (
        f("Conflicting classifications of pathogenicity") == "conflitante"
        and f("Conflicting_interpretations_of_pathogenicity") == "conflitante"
    )
    assert f("Uncertain significance") == "vus"  # incerta continua "vus"; nenhuma das duas sustenta risco (TCC 4.2.2)
    df = pd.DataFrame(
        {
            "aprovado": True,
            "anotada": True,
            "classe": ["risco", "vus", "vus", "conflitante"],
            "estrelas": 1,
            "freq_alfa": np.nan,
        }
    )
    ind = anotacao.indicadores_qualidade(df)
    assert (
        ind["n_vus"] == 2
        and ind["n_conflitante"] == 1
        and ind["por_classe"]["conflitante"] == 1
        and ind["proporcao_conflitante"] == pytest.approx(0.25)
    )
    # SOD1 p.Asp91Ala conflitante no ClinVar: classe "conflitante" na tabela mesclada, e não "vus"
    vs = variant_summary_fake(
        tmp_path / "vs.txt",
        [
            linha_vs(
                clnsig="Conflicting classifications of pathogenicity",
                revstat="criteria provided, conflicting classifications",
                **D91A,
            )
        ],
    )
    with pytest.warns(UserWarning, match="prevalece o ClinVar"):
        t = anotacao.tabela_anotacao(base_real=vs)
    d = t[t.posicao_grch38 == 31667290].iloc[0]
    assert d.classe == "conflitante" and "(conflitante)" in d.divergencia_curada


# ---------------------------------------------------------------------------
# A3 — G(t) em forma fechada a partir de estatísticas publicadas (média/dp; mediana/IQR)
# ---------------------------------------------------------------------------
def test_weibull_em_forma_fechada_a_partir_de_estatisticas(tmp_path):
    m = calibracao.weibull_de_momentos(50.2, 10.6)  # Berdyński et al. (2022): média e desvio
    w = stats.weibull_min(c=m["k"], scale=m["lam"])
    assert (
        m["metodo"] == "momentos"
        and w.mean() == pytest.approx(50.2, abs=1e-6)
        and w.std() == pytest.approx(10.6, abs=1e-6)
    )
    q = calibracao.weibull_de_quantis(58.30, 16.23)  # McFarlane et al. (2025): mediana e IQR
    d = DistribuicaoInicio("weibull", k=q["k"], lam=q["lam"])
    assert (
        q["metodo"] == "quantis"
        and d.mediana == pytest.approx(58.30, abs=1e-6)
        and float(d.ppf(0.75) - d.ppf(0.25)) == pytest.approx(16.23, abs=1e-6)
    )
    ln = calibracao.lognormal_de_quantis(58.30, 16.23)
    lw = stats.lognorm(s=ln["sigma"], scale=np.exp(ln["mu"]))
    assert lw.median() == pytest.approx(58.30) and float(lw.ppf(0.75) - lw.ppf(0.25)) == pytest.approx(16.23, abs=1e-6)
    lm = calibracao.lognormal_de_momentos(50.2, 10.6)
    assert stats.lognorm(s=lm["sigma"], scale=np.exp(lm["mu"])).mean() == pytest.approx(50.2) and stats.lognorm(
        s=lm["sigma"], scale=np.exp(lm["mu"])
    ).std() == pytest.approx(10.6)
    # ramo do YAML: `inicio.estatisticas` no lugar de `inicio.pontos`
    cfg = yaml.safe_load(calibracao.CAMINHO_PADRAO.read_text(encoding="utf-8"))
    cfg["genes"]["SOD1"]["inicio"] = {
        "distribuicao": "weibull",
        "estatisticas": {"media": 50.2, "dp": 10.6},
        "citacao": "teste",
        "confirmar": True,
    }
    cfg["genes"]["TARDBP"]["inicio"] = {
        "distribuicao": "weibull",
        "estatisticas": {"mediana": 58.30, "iqr": 16.23},
        "citacao": "teste",
        "confirmar": True,
    }
    p = tmp_path / "parametros.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    par = calibracao.carregar_parametros(p)
    assert par.genes["SOD1"].inicio.media == pytest.approx(50.2) and par.genes[
        "TARDBP"
    ].inicio.mediana == pytest.approx(58.30)
    assert par.genes["SOD1"].inicio_pontos == [] and par.genes["SOD1"].inicio_estatisticas == {
        "media": 50.2,
        "dp": 10.6,
    }
    assert (
        par.genes["C9orf72"].inicio_ajuste["escolhido"]["metodo"] == "pontos"
    )  # os pontos continuam valendo para C9orf72 e FUS
    tab = par.tabela_calibracao().set_index("gene")
    assert (
        tab.loc["SOD1", "metodo_inicio"] == "momentos"
        and tab.loc["TARDBP", "metodo_inicio"] == "quantis"
        and tab.loc["FUS", "metodo_inicio"] == "pontos"
    )
    assert relatorio.figura_curvas_inicio(par, tmp_path / "figura_03.png")["png"].endswith(
        "figura_03.png"
    )  # figura sem pontos não quebra
    with pytest.raises(ValueError, match="exatamente um"):
        calibracao.ajustar_inicio(None)
    with pytest.raises(ValueError, match="exatamente um"):
        calibracao.ajustar_inicio([[40, 0.2], [60, 0.8]], estatisticas={"media": 50, "dp": 10})
    with pytest.raises(ValueError, match="estatisticas"):
        calibracao.ajustar_inicio(estatisticas={"media": 50})


# ---------------------------------------------------------------------------
# A4 — dois caminhos que travavam o programa
# ---------------------------------------------------------------------------
def test_n_pequeno_sem_ajuste_da_lifelines_nao_trava(dir_cenarios, tmp_path):
    # N = 30: menos de 10 eventos por lócus, a Lifelines não ajusta a cura mista e `erro_rel_pi` não existe (antes: AttributeError)
    r = pipeline.executar(
        cenarios.vcf_cenario(dir_cenarios, 5, "mae"),
        cenarios.vcf_cenario(dir_cenarios, 5, "pai"),
        tmp_path / "n30",
        n=30,
        seed=1,
        motor="numpy",
        figuras=False,
        base_clinvar=False,
    )
    assert r["res"] is not None and len(r["loci"]) == 2
    assert "não ajustado em nenhum lócus" in (tmp_path / "n30" / "relatorio.md").read_text(encoding="utf-8")


def test_tabela_anotacao_aceita_dataframe_como_curada(tmp_path, variant_summary_fake, linha_vs):
    cur = anotacao.carregar_tabela_curada()
    t = anotacao.tabela_anotacao(base_real=False, curada=cur)  # antes: ValueError ("truth value of a DataFrame")
    assert t.attrs["fontes"]["curada"].endswith("variantes_curadas.csv") and len(t) == len(cur)
    vs = variant_summary_fake(
        tmp_path / "vs.txt",
        [linha_vs(clnsig="Pathogenic", revstat="criteria provided, multiple submitters, no conflicts", **A5V_VS)],
    )
    t2 = anotacao.tabela_anotacao(base_real=vs, curada=cur)
    assert t2.attrs["fontes"]["curada"].endswith("variantes_curadas.csv") and t2.attrs["fontes"]["n_real"] == 1
    assert (
        len(t2.attrs["fontes"]["sha256_base_real"]) == 64 and t2.attrs["fontes"]["arquivo_base_real"] == "vs.txt"
    )  # rastreabilidade (item C12)
    sem_caminho = cur.copy()
    sem_caminho.attrs.clear()
    assert (
        anotacao.tabela_anotacao(base_real=False, curada=sem_caminho).attrs["fontes"]["curada"]
        == "DataFrame em memória"
    )


# ---------------------------------------------------------------------------
# A5 — a pasta de saída é limpa a cada execução
# ---------------------------------------------------------------------------
def test_pasta_de_saida_e_limpa_a_cada_execucao(dir_cenarios, tmp_path):
    saida = tmp_path / "saida"
    pipeline.executar(
        cenarios.vcf_cenario(dir_cenarios, 1, "mae"),
        cenarios.vcf_cenario(dir_cenarios, 1, "pai"),
        saida,
        n=200,
        motor="numpy",
        figuras=False,
        base_clinvar=False,
    )
    assert (saida / "tabelas" / "tabela_03_risco_vitalicio.csv").exists() and (saida / "curvas.csv").exists()
    (saida / "figuras" / "figura_antiga.png").write_bytes(b"x")
    (saida / "notas_do_usuario.txt").write_text("fica", encoding="utf-8")
    # segunda execução na mesma pasta, agora sem lócus de risco: nada da execução anterior sobrevive ao lado do relatório novo
    r = pipeline.executar(
        cenarios.vcf_cenario(dir_cenarios, 1, "mae"),
        cenarios.vcf_cenario(dir_cenarios, 1, "mae"),
        saida,
        n=200,
        motor="numpy",
        figuras=False,
        base_clinvar=False,
    )
    assert r["res"] is None
    restantes = sorted(p.relative_to(saida).as_posix() for p in saida.rglob("*") if p.is_file())
    assert (
        "tabelas/tabela_03_risco_vitalicio.csv" not in restantes
        and "curvas.csv" not in restantes
        and "figuras/figura_antiga.png" not in restantes
    )
    assert "notas_do_usuario.txt" in restantes and "relatorio.md" in restantes
    meta = json.loads((saida / "metadados.json").read_text(encoding="utf-8"))
    assert {"tabelas", "figuras", "relatorio.md", "metadados.json", "curvas.csv"} <= set(meta["saida_limpa"])
    # a mesma limpeza vale para `avaliar` e `tudo`, e só toca nomes conhecidos
    d = tmp_path / "t"
    (d / "cenarios").mkdir(parents=True)
    (d / "README.md").write_text("velho", encoding="utf-8")
    (d / "outro.txt").write_text("fica", encoding="utf-8")
    assert (
        sorted(pipeline._limpar_saida(d, pipeline.ARTEFATOS_TUDO)) == ["README.md", "cenarios"]
        and (d / "outro.txt").exists()
        and not (d / "cenarios").exists()
    )
    assert (
        pipeline._limpar_saida(tmp_path / "nova", pipeline.ARTEFATOS_AVALIACAO) == [] and (tmp_path / "nova").is_dir()
    )


# ---------------------------------------------------------------------------
# B6 — limiares de qualidade do VCF iguais aos do TCC 4.3 (GQ ≥ 30, DP ≥ 20)
# ---------------------------------------------------------------------------
def test_limiares_de_qualidade_do_tcc(tmp_path, parametros, vcf_minimo):
    fq = parametros.filtro_qualidade
    assert (
        fq["dp_minimo"] == 20
        and fq["gq_minimo"] == 30
        and "TCC 4.3" in fq["citacao"]
        and "30" in fq["citacao"]
        and "20" in fq["citacao"]
    )
    assert ingestao.FILTRO_PADRAO["dp_minimo"] == 20 and ingestao.FILTRO_PADRAO["gq_minimo"] == 30
    p = vcf_minimo(
        tmp_path / "q.vcf",
        "S1",
        [A5V + ("0/1", 15, 25), A5V + ("0/1", 20, 30), A5V + ("0/1", 19, 30), A5V + ("0/1", 20, 29)],
    )
    motivos = ingestao.ler_vcf(p, filtro=fq).motivo_reprovacao.fillna("").tolist()
    assert (
        set(motivos[0].split(";")) == {"dp_baixo", "gq_baixo"}
        and motivos[1] == ""
        and motivos[2] == "dp_baixo"
        and motivos[3] == "gq_baixo"
    )
    assert ingestao.ler_vcf(p).aprovado.tolist() == [False, True, False, False]  # padrão do módulo = YAML


# ---------------------------------------------------------------------------
# B7 — faixa 60–75 anos só para o risco combinado, sem soar como aprovação por lócus
# ---------------------------------------------------------------------------
def test_faixa_60_75_so_no_risco_combinado(anotados, parametros, curada):
    mae, pai = anotados[3]
    loci = monte_carlo.loci_de_vetor(
        genotipo.vetor_dosagem(
            mae, pai, parametros, laudo_c9orf72={"mae": 45, "pai": cenarios.LAUDO_NORMAL}, tabela=curada
        ),
        parametros,
        sexo="F",
    )
    res = monte_carlo.simular_numpy(loci, n=5000, seed=4)
    co = avaliacao.coerencia(res, 90.0)
    assert "pico_em_60_75" not in co.columns
    por_locus, comb = co[co.variante != sobrevivencia.QUALQUER], co[co.variante == sobrevivencia.QUALQUER]
    assert (
        len(por_locus) == 2
        and por_locus.pico_combinado_na_faixa_60_75.isna().all()
        and (por_locus.idade_pico_hazard > 0).all()
    )
    assert (
        len(comb) == 1
        and isinstance(comb.pico_combinado_na_faixa_60_75.item(), bool)
        and 30 < comb.idade_pico_hazard.item() < 90
    )
    # risco vitalício exato (até o horizonte) comparado com o Kaplan-Meier no horizonte; F(∞) em coluna própria
    assert comb.risco_vitalicio_exato.item() == pytest.approx(res.resumo_combinado()["p_manifesta_qualquer_exato"])
    assert comb.risco_vitalicio_km.item() == pytest.approx(comb.risco_vitalicio_exato.item(), abs=0.03)
    assert comb.fracao_manifesta_sem_limite.item() >= comb.risco_vitalicio_exato.item()
    assert (por_locus.fracao_sem_limite_recuperada - por_locus.fracao_manifesta_sem_limite).abs().max() < 0.05


# ---------------------------------------------------------------------------
# B8 — uma única conta para a banda do risco combinado (percentil dos sorteios)
# ---------------------------------------------------------------------------
def test_banda_combinada_usa_o_percentil_dos_sorteios(anotados, parametros, curada):
    mae, pai = anotados[3]
    loci = monte_carlo.loci_de_vetor(
        genotipo.vetor_dosagem(
            mae, pai, parametros, laudo_c9orf72={"mae": 45, "pai": cenarios.LAUDO_NORMAL}, tabela=curada
        ),
        parametros,
        sexo="F",
    )
    res = monte_carlo.simular_numpy(loci, n=5000, seed=42)
    cb = res.resumo_combinado()
    # risco vitalício = risco até o horizonte: a banda da Tabela 3 é a da curva F(t) no horizonte (Figura 4)
    cv = sobrevivencia.curvas_analiticas(res, t_max=res.horizonte)
    q = cv[cv.unidade == sobrevivencia.QUALQUER].iloc[-1]
    assert cb["p_manifesta_qualquer_q025"] == pytest.approx(q.F_q025, abs=1e-9) and cb[
        "p_manifesta_qualquer_q975"
    ] == pytest.approx(q.F_q975, abs=1e-9)
    assert cb["p_manifesta_qualquer_q025"] <= cb["p_manifesta_qualquer_exato"] <= cb["p_manifesta_qualquer_q975"]
    # a conta antiga (combinação dos quantis de cada lócus) dava uma banda mais larga do que a propagação dos sorteios
    antiga = tuple(
        exato.combinar_independentes(l.p_portador_exato * l.quantis_penetrancia()[i] for l in res.loci) for i in (0, 1)
    )
    assert (cb["p_manifesta_qualquer_q975"] - cb["p_manifesta_qualquer_q025"]) < (antiga[1] - antiga[0])


# ---------------------------------------------------------------------------
# B9 — "VUS-high" e valores mistos
# ---------------------------------------------------------------------------
def test_vus_high_e_valores_mistos():
    f = anotacao.classificar_clnsig
    assert (
        f("VUS-high") == "vus" and f("VUS") == "vus" and f("Uncertain risk allele") == "vus"
    )  # antes: nao_classificada
    assert f("Pathogenic/Likely pathogenic/Likely benign") == "conflitante"  # antes: benigna
    assert f("Likely pathogenic, low penetrance") == "risco" and f("Benign/Likely benign") == "benigna"
    assert f("not provided") == "nao_classificada" and f("-") == "nao_classificada"


# ---------------------------------------------------------------------------
# B10 — o laudo do C9orf72 não vira lócus sem a linha de repetição da tabela de anotação
# ---------------------------------------------------------------------------
def test_laudo_sem_linha_de_repeticao_falha_em_vez_de_assumir(anotados, parametros, curada):
    mae, pai = anotados[1]
    sem_linha = curada[curada.tipo != "repeticao"].reset_index(drop=True)
    with pytest.raises(ValueError, match="linha de repetição"):
        genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": 45}, tabela=sem_linha)
    duvidosa = curada.copy()
    duvidosa.loc[duvidosa.tipo == "repeticao", "clnsig"] = "Uncertain significance"
    with pytest.raises(ValueError, match="não sustenta risco"):
        genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": 45}, tabela=duvidosa)


# ---------------------------------------------------------------------------
# B11 — fileDate fixo, vindo do YAML: VCFs idênticos byte a byte em dias diferentes
# ---------------------------------------------------------------------------
def test_file_date_fixo_vindo_do_yaml(tmp_path):
    data = yaml.safe_load(calibracao.CAMINHO_PADRAO.read_text(encoding="utf-8"))["data"].replace("-", "")
    assert cenarios.data_fixa_vcf() == data
    hoje = _dt.date.today().strftime("%Y%m%d")
    if hoje != data:
        assert cenarios.data_fixa_vcf() != hoje
    cenarios.gerar_cenarios(tmp_path / "a", seed=7)
    cenarios.gerar_cenarios(tmp_path / "b", seed=7)
    for p in sorted((tmp_path / "a").rglob("*.vcf")):
        assert p.read_text(encoding="utf-8").splitlines()[1] == f"##fileDate={data}"
        assert p.read_bytes() == (tmp_path / "b" / p.relative_to(tmp_path / "a")).read_bytes()
    # os VCFs versionados em data/sinteticos são exatamente o que o gerador produz com a semente 2026
    cenarios.gerar_cenarios(tmp_path / "c", seed=2026)
    for p in sorted((tmp_path / "c").rglob("*.vcf")):
        rel = p.relative_to(tmp_path / "c")
        assert p.read_bytes() == (DIR_DADOS / "sinteticos" / rel).read_bytes(), rel
    with pytest.raises(ValueError, match="data"):
        cfg = tmp_path / "sem_data.yaml"
        cfg.write_text("versao: 1\n", encoding="utf-8")
        cenarios.data_fixa_vcf(cfg)


# ---------------------------------------------------------------------------
# Laudo ausente do C9orf72 = genitor não testado: lócus indeterminado e descartado como genótipo indeterminado (TCC 4.3)
# ---------------------------------------------------------------------------
def test_laudo_normal_dos_cenarios_vem_do_yaml():
    with open(calibracao.CAMINHO_PADRAO, encoding="utf-8") as f:
        inter = int(yaml.safe_load(f)["limiar_repeticoes_c9orf72"]["intermediario"])
    assert cenarios.LAUDO_NORMAL == inter - 1
    assert anotacao.classe_por_repeticoes(cenarios.LAUDO_NORMAL, 30, inter) == "normal"
    for c in cenarios.CENARIOS:
        assert set(c.laudo_c9orf72) == {"mae", "pai"}  # todo genitor de cenário tem laudo
    assert cenarios.cenario_por_numero(1).laudo_c9orf72 == LAUDO_NORMAL_2
    assert cenarios.cenario_por_numero(2).laudo_c9orf72 == {"mae": 45, "pai": cenarios.LAUDO_NORMAL}
    assert genotipo.interpretar_laudo_c9orf72(None) == (None, None)
    assert genotipo.interpretar_laudo_c9orf72(45) == (1, 45) and genotipo.interpretar_laudo_c9orf72((12, 45)) == (2, 45)


def test_genitor_sem_laudo_descarta_o_c9orf72(anotados, parametros, curada, tmp_path, dir_cenarios):
    mae, pai = anotados[1]  # cenário 1: só SOD1 no pai; VCFs sem C9orf72
    # pai sem laudo → lócus do C9orf72 descartado (dosagem do pai vazia, sem P(portador)), fora do Monte Carlo; SOD1 segue
    with pytest.warns(UserWarning, match="não informado para o pai"):
        v = genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": 45}, tabela=curada).set_index("gene")
    c9 = v.loc["C9orf72"]
    assert bool(c9.descartado) and c9.dosagem_mae == 1 and pd.isna(c9.dosagem_pai) and pd.isna(c9.p_portador_exato)
    assert "laudo do C9orf72 não informado para o pai: lócus indeterminado (TCC 4.3)" in c9.observacao
    assert [l.gene for l in monte_carlo.loci_de_vetor(v.reset_index(), parametros)] == ["SOD1"]
    # nenhum laudo → "a mãe e o pai"
    with pytest.warns(UserWarning, match="a mãe e o pai"):
        v2 = genotipo.vetor_dosagem(mae, pai, parametros, tabela=curada).set_index("gene")
    assert bool(v2.loc["C9orf72", "descartado"]) and pd.isna(v2.loc["C9orf72", "dosagem_mae"])
    # laudo normal nos dois (contagem abaixo da faixa intermediária) → nenhum lócus do C9orf72
    v3 = genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72=LAUDO_NORMAL_2, tabela=curada)
    assert v3.gene.tolist() == ["SOD1"]
    # cenários 1, 4 e 5 com o laudo normal derivado do YAML: mesmas dosagens e P(portador) exatas de antes
    for n in (1, 4, 5):
        m, p = anotados[n]
        c = cenarios.cenario_por_numero(n)
        vn = genotipo.vetor_dosagem(m, p, parametros, laudo_c9orf72=c.laudo_c9orf72, tabela=curada)
        e = c.esperado
        vn, e = vn.set_index("gene").sort_index(), e.set_index("gene").sort_index()
        assert vn.index.tolist() == e.index.tolist() and not vn.descartado.any()
        assert vn.p_portador_exato.tolist() == pytest.approx(e.p_portador_exato.tolist())
        assert vn.dosagem_mae.tolist() == e.dosagem_mae.tolist() and vn.dosagem_pai.tolist() == e.dosagem_pai.tolist()
    # pipeline: metadados registram o descarte e o relatório diz que o resultado é parcial
    r = pipeline.executar(
        cenarios.vcf_cenario(dir_cenarios, 1, "mae"),
        cenarios.vcf_cenario(dir_cenarios, 1, "pai"),
        tmp_path / "p",
        n=300,
        seed=1,
        motor="numpy",
        figuras=False,
        base_clinvar=False,
        laudo_c9orf72={"mae": 45},
    )
    assert [l.gene for l in r["loci"]] == ["SOD1"]
    meta = json.loads((tmp_path / "p" / "metadados.json").read_text(encoding="utf-8"))
    assert meta["loci_descartados"] == ["expansão GGGGCC"] and meta["laudo_c9orf72"] == {"mae": 45}
    texto = (tmp_path / "p" / "relatorio.md").read_text(encoding="utf-8")
    assert "Resultado parcial para o C9orf72" in texto and "pai: não testado" in texto and "mãe: 45 repetições" in texto
    # só o C9orf72 em jogo e um genitor sem laudo → nenhum lócus utilizável, e o relatório diz por quê
    r2 = pipeline.executar(
        cenarios.vcf_cenario(dir_cenarios, 2, "mae"),
        cenarios.vcf_cenario(dir_cenarios, 2, "pai"),
        tmp_path / "p2",
        n=300,
        motor="numpy",
        figuras=False,
        base_clinvar=False,
        laudo_c9orf72={"mae": 45},
    )
    assert r2["res"] is None and bool(r2["vetor"].descartado.all())
    texto2 = (tmp_path / "p2" / "relatorio.md").read_text(encoding="utf-8")
    assert "Nenhum lócus de risco utilizável" in texto2 and "Resultado parcial para o C9orf72" in texto2


def test_vcf_com_expansao_nao_substitui_o_laudo(tmp_path, parametros, curada):
    rng = np.random.default_rng(3)
    mae = anotacao.anotar(
        ingestao.ler_vcf(
            cenarios.escrever_vcf(tmp_path / "m.vcf", "MAE", [cenarios.c9orf72_expansao(45)], rng, incluir_ruido=False)
        ),
        curada,
    )
    pai = anotacao.anotar(
        ingestao.ler_vcf(
            cenarios.escrever_vcf(
                tmp_path / "p.vcf", "PAI", [cenarios.c9orf72_expansao(45, dosagem=0)], rng, incluir_ruido=False
            )
        ),
        curada,
    )
    with pytest.warns(UserWarning, match="caminho secundário"):
        v = genotipo.vetor_dosagem(mae, pai, parametros, tabela=curada)
    assert len(v) == 1 and bool(v.iloc[0].descartado)
    assert "sem laudo o genitor é indeterminado" in v.iloc[0].observacao


def test_hipotese_de_repeticoes_nao_recria_locus_indeterminado(anotados, parametros, curada):
    from ela_preditivo import repeticoes

    mae, pai = anotados[1]
    assert repeticoes.transmissao_c9orf72({"mae": 28}, {"delta_mae": 3}, parametros, curada) is None
    with pytest.warns(UserWarning, match="não informado"):
        vetor = genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": 45}, tabela=curada)
    tr = repeticoes.transmissao_c9orf72(
        {"mae": 45, "pai": cenarios.LAUDO_NORMAL}, {"delta_mae": -20}, parametros, curada
    )
    v2 = repeticoes.aplicar_ao_vetor(vetor, tr, parametros, curada)
    pd.testing.assert_frame_equal(v2, vetor)


# ---------------------------------------------------------------------------
# Regra qualificada: classificação conflitante com maioria patogênica e herança declarada passa a risco
# ---------------------------------------------------------------------------
CONFLITO_D91A = "Pathogenic (5)|Likely pathogenic (9)|Uncertain significance (5)|Likely benign (1)"
FENOTIPO_RECESSIVO = (
    "Amyotrophic lateral sclerosis type 1|Amyotrophic lateral sclerosis 1, autosomal recessive|not provided"
)
FENOTIPO_DOIS_MODOS = (
    "Amyotrophic lateral sclerosis 1, autosomal dominant|Amyotrophic lateral sclerosis 1, autosomal recessive"
)
CONFLITANTE = "Conflicting classifications of pathogenicity"
REVSTAT_CONFLITANTE = "criteria provided, conflicting classifications"
MULTI = "criteria provided, multiple submitters, no conflicts"


def _base_falsa(variant_summary_fake, linha_vs, caminho, conflito, fenotipo, extra=()):
    """variant_summary falso: D91A conflitante (abertura e fenótipo dados) + A5V patogênica (+ linhas extras)."""
    return variant_summary_fake(
        caminho,
        [
            linha_vs(clnsig=CONFLITANTE, revstat=REVSTAT_CONFLITANTE, fenotipo=fenotipo, conflito=conflito, **D91A),
            linha_vs(clnsig="Pathogenic", revstat=MULTI, **A5V_VS),
            *extra,
        ],
    )


def test_proporcao_patogenica_e_heranca_declarada():
    f = anotacao.proporcao_patogenica
    assert f(CONFLITO_D91A) == pytest.approx(0.7)
    assert f("Pathogenic(5)|Likely_pathogenic(9)|Uncertain_significance(5)|Likely_benign(1)") == pytest.approx(0.7)
    assert f("Pathogenic (7)|Benign (7)") == pytest.approx(0.5)
    assert f("Pathogenic, low penetrance (3)|Benign (1)") == pytest.approx(0.0)  # só os nomes exatos contam
    assert np.isnan(f("")) and np.isnan(f(None)) and np.isnan(f(float("nan"))) and np.isnan(f("sem contagens"))
    h = anotacao.heranca_declarada
    assert h(FENOTIPO_RECESSIVO) == "recessiva"
    assert h("Amyotrophic_lateral_sclerosis_1,_autosomal_dominant|not_provided") == "dominante"  # formato CLNDN
    assert h(FENOTIPO_DOIS_MODOS) == "ambas"
    assert h("Amyotrophic lateral sclerosis type 1") is None and h(None) is None
    assert h("Frontotemporal dementia, autosomal dominant") is None  # herança declarada em fenótipo que não é ELA
    regra = anotacao.regra_conflitante_padrao()
    assert regra["maioria_minima"] == 0.5 and regra["estrita"] is True and regra["exigir_heranca_declarada"] is True
    assert regra["confirmar"] is True and calibracao.carregar_parametros().regra_conflitante == regra


def test_regra_qualificada_para_conflitantes(tmp_path, dir_cenarios, variant_summary_fake, linha_vs):
    chave = ("21", 31667290, "A", "C")

    def d91a(nome, conflito, fenotipo, **kw):
        base = _base_falsa(variant_summary_fake, linha_vs, tmp_path / nome, conflito, fenotipo)
        t = anotacao.carregar_base_real(base, **kw)
        return t.set_index(["cromossomo", "posicao_grch38", "ref", "alt"]).loc[chave]

    # maioria patogênica sem herança declarada → continua conflitante (proporção registrada)
    so_maioria = d91a("a.txt", CONFLITO_D91A, "Amyotrophic lateral sclerosis type 1")
    assert so_maioria.classe == "conflitante" and not so_maioria.regra_qualificada
    assert so_maioria.proporcao_patogenica == pytest.approx(0.7) and pd.isna(so_maioria.heranca_declarada)
    # herança declarada sem maioria → continua conflitante; metade exata também (maioria estrita)
    assert d91a("b.txt", "Pathogenic (5)|Uncertain significance (9)", FENOTIPO_RECESSIVO).classe == "conflitante"
    assert d91a("c.txt", "Pathogenic (7)|Benign (7)", FENOTIPO_RECESSIVO).classe == "conflitante"
    # as duas condições → risco pela regra; herança declarada usada na falta da curada; nota com a abertura
    ambas = d91a("d.txt", CONFLITO_D91A, FENOTIPO_RECESSIVO)
    assert ambas.classe == "risco" and bool(ambas.regra_qualificada) and ambas.heranca == "recessiva"
    assert ambas.heranca_declarada == "recessiva" and CONFLITO_D91A in ambas.nota_regra and "70 %" in ambas.nota_regra
    # os critérios vêm do YAML: regra desligada, maioria não estrita e herança não exigida mudam o resultado
    assert d91a("e.txt", CONFLITO_D91A, FENOTIPO_RECESSIVO, regra={}).classe == "conflitante"
    nao_estrita = {"maioria_minima": 0.5, "estrita": False, "exigir_heranca_declarada": True}
    assert d91a("f.txt", "Pathogenic (7)|Benign (7)", FENOTIPO_RECESSIVO, regra=nao_estrita).classe == "risco"
    sem_heranca = {"maioria_minima": 0.5, "estrita": True, "exigir_heranca_declarada": False}
    assert d91a("g.txt", CONFLITO_D91A, "Amyotrophic lateral sclerosis type 1", regra=sem_heranca).classe == "risco"
    # mesclada com a curada: herança da curada, sem divergência nem aviso para a D91A
    base = _base_falsa(variant_summary_fake, linha_vs, tmp_path / "h.txt", CONFLITO_D91A, FENOTIPO_RECESSIVO)
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        t = anotacao.tabela_anotacao(base_real=base)
    assert not [a for a in avisos if "D91A" in str(a.message) or "Asp91Ala" in str(a.message)]
    d = t[(t.posicao_grch38 == 31667290) & (t.alt == "C")].iloc[0]
    assert d.classe == "risco" and bool(d.regra_qualificada) and d.heranca == "recessiva"
    assert pd.isna(d.divergencia_curada) and pd.isna(d.clnsig_curada)
    # `anotar` usa a classe final da tabela: as anotadas do cenário 4 saem como risco pela regra
    mae = anotacao.anotar(ingestao.ler_vcf(cenarios.vcf_cenario(dir_cenarios, 4, "mae")), t)
    linha = mae[mae.posicao == 31667290].iloc[0]
    assert linha.classe == "risco" and bool(linha.regra_qualificada) and "TCC 4.2.2" in linha.nota_regra
    # os dois modos declarados: com herança na curada → aceita (D91A); sem linha na curada → não aceita e reportada
    outra = dict(
        D91A, allele_id="99", nome="NM_000454.5(SOD1):c.100A>G (p.Xyz34Abc)", rs="999", pos=31660000, vid="99999"
    )
    extra = [
        linha_vs(
            clnsig=CONFLITANTE,
            revstat=REVSTAT_CONFLITANTE,
            fenotipo=FENOTIPO_DOIS_MODOS,
            conflito=CONFLITO_D91A,
            **outra,
        )
    ]
    base2 = _base_falsa(variant_summary_fake, linha_vs, tmp_path / "i.txt", CONFLITO_D91A, FENOTIPO_DOIS_MODOS, extra)
    with pytest.warns(UserWarning, match="dois modos"):
        t2 = anotacao.tabela_anotacao(base_real=base2)
    d2 = t2[(t2.posicao_grch38 == 31667290) & (t2.alt == "C")].iloc[0]
    assert d2.classe == "risco" and bool(d2.regra_qualificada) and "tabela curada: recessiva" in d2.nota_regra
    o = t2[t2.posicao_grch38 == 31660000].iloc[0]
    assert o.classe == "conflitante" and not o.regra_qualificada and pd.isna(o.heranca)
    assert o.nota_regra.startswith("não aceita") and o.heranca_declarada == "ambas"


def test_cenario_4_entra_pela_regra_qualificada(dir_cenarios, tmp_path, variant_summary_fake, linha_vs):
    base = _base_falsa(variant_summary_fake, linha_vs, tmp_path / "base.txt", CONFLITO_D91A, FENOTIPO_RECESSIVO)
    r = pipeline.executar(
        cenarios.vcf_cenario(dir_cenarios, 4, "mae"),
        cenarios.vcf_cenario(dir_cenarios, 4, "pai"),
        tmp_path / "c4",
        n=400,
        seed=2,
        motor="numpy",
        figuras=False,
        base_clinvar=base,
        laudo_c9orf72=LAUDO_NORMAL_2,
    )
    assert r["res"] is not None and [l.gene for l in r["loci"]] == ["SOD1"] and r["loci"][0].heranca == "recessiva"
    v = r["vetor"].iloc[0]
    assert v.p_portador_exato == pytest.approx(0.25) and "regra qualificada" in v.observacao
    assert CONFLITO_D91A in v.observacao
    texto = (tmp_path / "c4" / "relatorio.md").read_text(encoding="utf-8")
    assert "Variantes aceitas pela regra qualificada" in texto and CONFLITO_D91A in texto
    assert "Aproximação de penetrância" in texto and "p.Asp91Ala" in texto and "homozigotos D91A" in texto
    assert "só sustenta risco pela regra qualificada" in texto
    meta = json.loads((tmp_path / "c4" / "metadados.json").read_text(encoding="utf-8"))
    assert meta["loci_regra_qualificada"] == ["SOD1 p.Asp91Ala"] and meta["regra_conflitante"]["maioria_minima"] == 0.5
    tab1 = pd.read_csv(tmp_path / "c4" / "tabelas" / "tabela_01_variantes_anotadas.csv")
    assert "regra_qualificada" in tab1.columns and tab1[tab1.posicao == 31667290].regra_qualificada.all()
    # avaliação transversal: o cenário 4 deixa de ser pulado
    av = pipeline.avaliar(
        dir_cenarios,
        tmp_path / "av",
        numeros=[4],
        ns=(200,),
        repeticoes=2,
        n_coerencia=300,
        base_clinvar=base,
        mundos=6,
        por_estrato=3,
    )
    assert av["pulados"] == [] and set(av["estabilidade"].cenario) == {"cenário 4"}
    # as métricas de verificação rodam também com a base no formato real (regra qualificada no cenário 4)
    assert set(av["verificacao"]["robustez"].cenario) == {"cenário 4"}
    assert "cenário de parentes 1" in set(av["verificacao"]["coorte"].cenario)
