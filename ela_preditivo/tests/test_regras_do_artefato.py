"""Regras do artefato vindas do texto do TCC e da robustez do pipeline: genótipo não determinado, classes de
patogenicidade, calibração por estatísticas publicadas, limpeza da pasta de saída, limiares de qualidade, critério
da faixa de incidência, banda de credibilidade combinada, laudo do C9orf72 e reprodutibilidade dos VCFs."""

import datetime as _dt
import json

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
        v = genotipo.vetor_dosagem(mae, pai, parametros, tabela=curada).set_index("gene")
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
    )
    assert [l.gene for l in r["loci"]] == ["FUS"]
    texto = (tmp_path / "saida" / "relatorio.md").read_text(encoding="utf-8")
    assert "descartados por genótipo não determinado" in texto and "SOD1 A4V (p.A5V)" in texto and "Tabela 1b" in texto
    meta = json.loads((tmp_path / "saida" / "metadados.json").read_text(encoding="utf-8"))
    assert meta["loci_descartados"] == ["A4V (p.A5V)"] and meta["loci"] == ["FUS R521C"]
    # pai indeterminado no único lócus de risco: nenhum lócus utilizável, e o relatório diz por quê
    mae2 = vcf_minimo(tmp_path / "mae2.vcf", "MAE", [A5V + ("0/1",)])
    pai2 = vcf_minimo(tmp_path / "pai2.vcf", "PAI", [A5V + ("./.",)])
    r2 = pipeline.executar(mae2, pai2, tmp_path / "saida2", n=300, motor="numpy", figuras=False, base_clinvar=False)
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
        dir_cenarios / "cenario_5_mae.vcf",
        dir_cenarios / "cenario_5_pai.vcf",
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
        dir_cenarios / "cenario_1_mae.vcf",
        dir_cenarios / "cenario_1_pai.vcf",
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
        dir_cenarios / "cenario_1_mae.vcf",
        dir_cenarios / "cenario_1_mae.vcf",
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
        genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": 45}, tabela=curada), parametros, sexo="F"
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
    assert comb.F_inf_exato.item() == pytest.approx(res.resumo_combinado()["p_manifesta_qualquer_exato"])
    assert comb.risco_vitalicio_km.item() == pytest.approx(comb.F_inf_exato.item(), abs=0.03)


# ---------------------------------------------------------------------------
# B8 — uma única conta para a banda do risco combinado (percentil dos sorteios)
# ---------------------------------------------------------------------------
def test_banda_combinada_usa_o_percentil_dos_sorteios(anotados, parametros, curada):
    mae, pai = anotados[3]
    loci = monte_carlo.loci_de_vetor(
        genotipo.vetor_dosagem(mae, pai, parametros, laudo_c9orf72={"mae": 45}, tabela=curada), parametros, sexo="F"
    )
    res = monte_carlo.simular_numpy(loci, n=5000, seed=42)
    cb = res.resumo_combinado()
    cv = sobrevivencia.curvas_analiticas(res, t_max=1000)  # G(1000) = 1: F(∞) por sorteio, como na Figura 4
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
    for p in sorted((tmp_path / "a").glob("*.vcf")):
        assert p.read_text(encoding="utf-8").splitlines()[1] == f"##fileDate={data}"
        assert p.read_bytes() == (tmp_path / "b" / p.name).read_bytes()
    # os VCFs versionados em data/sinteticos são exatamente o que o gerador produz com a semente 2026
    cenarios.gerar_cenarios(tmp_path / "c", seed=2026)
    for p in sorted((tmp_path / "c").glob("*.vcf")):
        assert p.read_bytes() == (DIR_DADOS / "sinteticos" / p.name).read_bytes(), p.name
    with pytest.raises(ValueError, match="data"):
        cfg = tmp_path / "sem_data.yaml"
        cfg.write_text("versao: 1\n", encoding="utf-8")
        cenarios.data_fixa_vcf(cfg)
