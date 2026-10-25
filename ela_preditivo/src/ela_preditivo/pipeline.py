"""Orquestração ponta a ponta: executar um caso (VCF materno + paterno), avaliar os cenários e rodar tudo."""
from __future__ import annotations

import datetime as _dt
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import AVISO_LEGAL, __version__, anotacao, avaliacao, cenarios, genotipo, ingestao, relatorio, sobrevivencia
from .calibracao import carregar_parametros
from .monte_carlo import loci_de_vetor, simular_numpy
from .rede_bayesiana import simular_pymc


def _p(x) -> str:
    return f"{100 * x:.1f}%"


def _n(x) -> str:
    """Inteiro com separador de milhar em português (10.000)."""
    return f"{int(x):,}".replace(",", ".")


def executar(vcf_mae, vcf_pai, saida, sexo: str | None = None, idade_atual: float | None = None, n: int = 10_000, seed: int = 42,
             motor: str = "pymc", config=None, tabela_variantes=None, horizonte: float | None = None, rotulo: str = "",
             figuras: bool = True) -> dict:
    """Executa as três camadas para um casal e grava tabelas, figuras, relatório e metadados em `saida`."""
    t_ini = time.perf_counter()
    saida = Path(saida); (saida / "tabelas").mkdir(parents=True, exist_ok=True); (saida / "figuras").mkdir(exist_ok=True)
    par = carregar_parametros(config)
    horizonte = float(horizonte or par.horizonte_anos)
    regioes = ingestao.carregar_regioes()
    tabela = anotacao.carregar_tabela_curada(tabela_variantes)

    # Camada 1: ingestão e anotação
    mae = anotacao.anotar(ingestao.ler_vcf(vcf_mae, regioes, par.filtro_qualidade), tabela, par.limiar_repeticoes)
    pai = anotacao.anotar(ingestao.ler_vcf(vcf_pai, regioes, par.filtro_qualidade), tabela, par.limiar_repeticoes)
    perfil = genotipo.perfil_variantes(mae, pai)
    ing = {"mae": ingestao.resumo_ingestao(mae), "pai": ingestao.resumo_ingestao(pai)}
    vetor = genotipo.vetor_dosagem(mae, pai, par)
    pd.concat([mae, pai], ignore_index=True).to_csv(saida / "variantes_ingeridas_anotadas.csv", index=False)
    tabelas = [relatorio.salvar_tabela(perfil, saida / "tabelas", "tabela_01_variantes_anotadas",
                                       "Tabela 1 — Variantes aprovadas no filtro de qualidade e sua anotação, por genitor",
                                       f"Registros lidos/aprovados: mãe {ing['mae']['registros']}/{ing['mae']['aprovados']}, pai {ing['pai']['registros']}/{ing['pai']['aprovados']}. Reprovações: mãe {ing['mae']['por_motivo']}, pai {ing['pai']['por_motivo']}.")]
    figs = []
    secoes = [("Entrada", f"VCF materno: `{Path(vcf_mae).name}`; VCF paterno: `{Path(vcf_pai).name}`; sexo do descendente: {sexo or 'não informado'}; "
                          f"idade atual sem sintomas: {idade_atual if idade_atual is not None else 'não informada'}; motor: {motor}; N = {_n(n)}; seed = {seed}; horizonte = {horizonte:.0f} anos.")]
    if vetor.empty:
        secoes.append(("Resultado", "Nenhum lócus de risco (classe patogênica/provavelmente patogênica) foi encontrado nos genes-alvo dos dois genitores. "
                                    "O risco de transmissão de variantes conhecidas é nulo neste recorte; o risco populacional de base não é modelado."))
        rel = relatorio.escrever_relatorio(saida, f"Relatório do artefato — {rotulo or 'caso'}", secoes, tabelas, figs)
        relatorio.escrever_metadados(saida, data=_dt.datetime.now().isoformat(timespec="seconds"), seed=seed, n=n, motor=motor, sexo=sexo,
                                     idade_atual=idade_atual, parametros=str(par.caminho), versao_parametros=par.versao, data_parametros=par.data, loci=0)
        return {"saida": saida, "relatorio": rel, "vetor": vetor, "res": None, "tabelas": tabelas, "figuras": figs}
    tabelas.append(relatorio.salvar_tabela(vetor, saida / "tabelas", "tabela_01b_vetor_dosagem",
                                           "Tabela 1b — Vetor genotípico parental: dosagem alélica (0/1/2) por lócus de risco e P(portador) exata"))

    # Camada 2: Rede Bayesiana + Monte Carlo (motor principal + motor cruzado para a aderência)
    loci = loci_de_vetor(vetor, par, sexo=sexo)
    principal = simular_pymc if motor == "pymc" else simular_numpy
    cruzado = simular_numpy if motor == "pymc" else simular_pymc
    res = principal(loci, n=n, seed=seed)
    res_x = cruzado(loci, n=n, seed=seed)
    res.sexo = res_x.sexo = sexo
    resumo = res.resumo(); comb = res.resumo_combinado()
    ader = avaliacao.aderencia(res if motor == "pymc" else res_x, res_x if motor == "pymc" else res)
    tabelas.append(relatorio.salvar_tabela(ader, saida / "tabelas", "tabela_02_aderencia",
                                           "Tabela 2 — Aderência teórica: probabilidades exatas vs Monte Carlo (PyMC e NumPy), erro padrão e qui-quadrado do genótipo do descendente"))
    risco = resumo[["gene", "variante", "heranca", "dosagem_mae", "dosagem_pai", "p_portador_exato", "p_portador_mc", "penetrancia_media", "penetrancia_q025", "penetrancia_q975",
                    "p_manifesta_exato", "p_manifesta_mc", "p_manifesta_q025", "p_manifesta_q975", "idade_mediana_exata", "idade_mediana_mc", "idade_p10_mc", "idade_p90_mc"]].copy()
    risco.loc[len(risco)] = {"gene": "—", "variante": sobrevivencia.QUALQUER, "heranca": "independência", "dosagem_mae": "", "dosagem_pai": "",
                             "p_portador_exato": comb["p_portador_qualquer_exato"], "p_portador_mc": comb["p_portador_qualquer_mc"],
                             "penetrancia_media": np.nan, "penetrancia_q025": np.nan, "penetrancia_q975": np.nan,
                             "p_manifesta_exato": comb["p_manifesta_qualquer_exato"], "p_manifesta_mc": comb["p_manifesta_qualquer_mc"],
                             "p_manifesta_q025": comb["p_manifesta_qualquer_q025"], "p_manifesta_q975": comb["p_manifesta_qualquer_q975"],
                             "idade_mediana_exata": np.nan, "idade_mediana_mc": comb["idade_mediana_primeiro_inicio"], "idade_p10_mc": np.nan, "idade_p90_mc": np.nan}
    tabelas.append(relatorio.salvar_tabela(risco, saida / "tabelas", "tabela_03_risco_vitalicio",
                                           "Tabela 3 — Probabilidade de transmissão (portador), penetrância e risco vitalício de manifestação por lócus e combinado, com intervalo de credibilidade de 95% (incerteza da penetrância) e idade de início"))

    # Camada 3: sobrevivência
    curvas = sobrevivencia.curvas_analiticas(res, horizonte)
    curvas.to_csv(saida / "curvas.csv", index=False)
    cond = sobrevivencia.tabela_risco_condicional(res, horizonte=horizonte)
    tabelas.append(relatorio.salvar_tabela(cond, saida / "tabelas", "tabela_04_risco_condicional",
                                           "Tabela 4 — Risco condicional à idade atual sem sintomas: P(portador | assintomático), risco nos próximos 10 e 20 anos e risco vitalício residual, com banda de 95%"))
    km = sobrevivencia.tabela_km(res, horizonte)
    tabelas.append(relatorio.salvar_tabela(km, saida / "tabelas", "tabela_10_kaplan_meier",
                                           "Tabela 10 — Sobrevivência (assintomático) estimada por Kaplan-Meier na coorte simulada, com IC 95% (Greenwood); mediana não atingida quando o risco vitalício é inferior a 50%"))
    rec = sobrevivencia.recuperacao_parametros(res, horizonte)
    tabelas.append(relatorio.salvar_tabela(rec, saida / "tabelas", "tabela_07_recuperacao_lifelines",
                                           "Tabela 7 — Recuperação dos parâmetros de entrada (π, λ, ρ) pelo ajustador de cura mista da Lifelines na coorte simulada de portadores"))
    extra = ""
    if idade_atual is not None:
        res_c = res.condicionar_idade(idade_atual)
        kmc = sobrevivencia.risco_condicional_km(res, idade_atual, horizonte)
        tabelas.append(relatorio.salvar_tabela(kmc, saida / "tabelas", "tabela_04b_risco_condicional_km",
                                               f"Tabela 4b — Risco condicional não paramétrico (Kaplan-Meier) para um descendente assintomático aos {idade_atual:.0f} anos"))
        extra = (f" Condicionando ao descendente assintomático aos {idade_atual:.0f} anos (rejeição de {_n(res.n - res_c.n)} sorteios), "
                 f"P(portador de ≥ 1 lócus) passa de {_p(res.portador.any(axis=1).mean())} para {_p(res_c.portador.any(axis=1).mean())} e o risco vitalício residual é "
                 f"{_p(res_c.manifesta_qualquer.mean())}.")

    # Figuras
    if figuras:
        figs.append(relatorio.figura_dag(loci, saida / "figuras" / "figura_01_dag.png"))
        figs.append(relatorio.figura_risco_temporal(curvas, res, saida / "figuras" / "figura_04_risco_temporal.png", horizonte, rotulo))
        figs.append(relatorio.figura_aderencia(ader, saida / "figuras" / "figura_06_aderencia.png"))
        figs.append(relatorio.figura_hazard(curvas, saida / "figuras" / "figura_08_hazard.png"))
        figs.append(relatorio.figura_idade_inicio({sexo or "—": res}, saida / "figuras" / "figura_05_idade_inicio.png",
                                                  legenda="Figura 5 — Distribuição simulada da idade de início entre os descendentes que manifestam, por lócus"))

    # Texto do relatório
    linhas = [f"- **{l.variante}** ({l.heranca}; dosagens mãe/pai {l.dosagem_mae}/{l.dosagem_pai}): P(portador) = {_p(l.p_portador_exato)} (MC {_p(l.p_portador_mc)}); "
              f"penetrância média {_p(l.penetrancia_media)} [{_p(l.penetrancia_q025)}–{_p(l.penetrancia_q975)}]; risco vitalício {_p(l.p_manifesta_exato)} "
              f"[{_p(l.p_manifesta_q025)}–{_p(l.p_manifesta_q975)}]; idade mediana de início {l.idade_mediana_exata:.1f} anos (p10–p90 MC: {l.idade_p10_mc:.0f}–{l.idade_p90_mc:.0f})."
              for _, l in resumo.iterrows()]
    linhas.append(f"- **Combinado (qualquer lócus, independência)**: P(portador de ≥ 1) = {_p(comb['p_portador_qualquer_exato'])}; risco vitalício {_p(comb['p_manifesta_qualquer_exato'])} "
                  f"[{_p(comb['p_manifesta_qualquer_q025'])}–{_p(comb['p_manifesta_qualquer_q975'])}]; idade mediana do primeiro início {comb['idade_mediana_primeiro_inicio']:.1f} anos.")
    secoes.append(("Resultado", "\n".join(linhas) + extra))
    desvio_max = float(np.nanmax(ader[["desvio_manifesta_pymc_em_ep", "desvio_manifesta_numpy_em_ep"]].values))
    secoes.append(("Verificações", f"Aderência: maior desvio entre Monte Carlo e valor exato = {desvio_max:.2f} erros padrão (limite usual: 4). "
                                   f"Coerência: risco vitalício por Kaplan-Meier = {', '.join(f'{r.unidade}: {_p(r.risco_vitalicio_km)}' for r in km.itertuples())}. "
                                   f"Recuperação Lifelines: erro relativo máximo em π = {rec.erro_rel_pi.max():.1%}. Tempo: {time.perf_counter() - t_ini:.1f} s no total "
                                   f"({motor}: {res.tempo_s:.2f} s; motor cruzado: {res_x.tempo_s:.2f} s)."))
    provis = [g.nome for g in par.genes.values() if g.pen_confirmar or g.inicio_confirmar]
    secoes.append(("Limitações desta execução", f"Parâmetros provisórios (confirmar: true) em: {', '.join(provis) or 'nenhum'}. Independência entre lóci; sem fatores modificadores; "
                                                "penetrância populacional de coortes europeias/norte-americanas; dados sintéticos."))
    rel = relatorio.escrever_relatorio(saida, f"Relatório do artefato — {rotulo or 'caso'}", secoes, tabelas, figs)
    relatorio.escrever_metadados(saida, data=_dt.datetime.now().isoformat(timespec="seconds"), seed=seed, n=n, motor=motor, sexo=sexo, idade_atual=idade_atual,
                                 horizonte=horizonte, parametros=str(par.caminho), versao_parametros=par.versao, data_parametros=par.data,
                                 tabela_variantes=str(tabela_variantes or anotacao.CAMINHO_TABELA), vcf_mae=str(vcf_mae), vcf_pai=str(vcf_pai),
                                 loci=[l.rotulo for l in loci], tempo_total_s=round(time.perf_counter() - t_ini, 2))
    return {"saida": saida, "relatorio": rel, "vetor": vetor, "loci": loci, "res": res, "res_cruzado": res_x, "resumo": resumo, "combinado": comb,
            "aderencia": ader, "curvas": curvas, "tabelas": tabelas, "figuras": figs}


def avaliar(dir_cenarios, saida, numeros=None, ns=(1_000, 10_000, 100_000), repeticoes: int = 30, seed: int = 1000, sexo: str = "F",
            n_coerencia: int = 10_000, config=None) -> dict:
    """Avaliação transversal dos cenários: estabilidade, tempo, coerência, calibração e sensibilidade (Tabelas 5 a 9)."""
    saida = Path(saida); (saida / "tabelas").mkdir(parents=True, exist_ok=True); (saida / "figuras").mkdir(exist_ok=True)
    par = carregar_parametros(config)
    dir_cenarios = Path(dir_cenarios)
    numeros = numeros or [c.numero for c in cenarios.CENARIOS]
    tabela = anotacao.carregar_tabela_curada()
    regioes = ingestao.carregar_regioes()
    brutos, resumos, tempos, coer, sens, recs = [], [], [], [], [], []
    for num in numeros:
        c = cenarios.cenario_por_numero(num)
        mae = anotacao.anotar(ingestao.ler_vcf(dir_cenarios / f"cenario_{num}_mae.vcf", regioes, par.filtro_qualidade), tabela, par.limiar_repeticoes)
        pai = anotacao.anotar(ingestao.ler_vcf(dir_cenarios / f"cenario_{num}_pai.vcf", regioes, par.filtro_qualidade), tabela, par.limiar_repeticoes)
        vetor = genotipo.vetor_dosagem(mae, pai, par)
        loci = loci_de_vetor(vetor, par, sexo=sexo)
        rot = f"cenário {num}"
        bruto, resumo = avaliacao.estabilidade(loci, ns=ns, repeticoes=repeticoes, seed_inicial=seed)
        bruto.insert(0, "cenario", rot); resumo.insert(0, "cenario", rot)
        brutos.append(bruto); resumos.append(resumo)
        t = avaliacao.tempos(loci, ns=ns); t.insert(0, "cenario", rot); tempos.append(t)
        res = simular_pymc(loci, n=n_coerencia, seed=seed)
        co = avaliacao.coerencia(res, par.horizonte_anos); co.insert(0, "cenario", rot); coer.append(co)
        s = avaliacao.sensibilidade(vetor, par, sexo, n=n_coerencia, seed=seed); s.insert(0, "cenario", rot); sens.append(s)
    bruto = pd.concat(brutos, ignore_index=True); bruto.to_csv(saida / "estabilidade_execucoes.csv", index=False)
    resumo = pd.concat(resumos, ignore_index=True)
    cols_res = ["cenario", "motor", "n", "repeticoes", "p_manifesta_qualquer_exato", "p_manifesta_qualquer_media", "p_manifesta_qualquer_dp", "ep_teorico", "razao_dp_ep",
                "idade_mediana_media", "idade_mediana_dp", "tempo_medio_s"]
    tabelas = [relatorio.salvar_tabela(resumo[cols_res], saida / "tabelas", "tabela_05_estabilidade",
                                       f"Tabela 5 — Estabilidade numérica: média e desvio padrão de P(manifestação) e da idade mediana entre {repeticoes} execuções com sementes distintas, por N, vs erro padrão teórico √(p(1−p)/N)",
                                       "DP/EP próximo de 1 indica que a variabilidade entre execuções é a esperada para o Monte Carlo; o DP cai por ≈√10 a cada década de N."),
               relatorio.salvar_tabela(par.tabela_calibracao(), saida / "tabelas", "tabela_06_calibracao",
                                       "Tabela 6 — Calibração das priors Beta de penetrância e das distribuições de idade de início a partir da literatura (docs/02, §2)",
                                       "valor_provisorio = sim: parâmetro marcado com confirmar: true no YAML, a validar pela autora."),
               relatorio.salvar_tabela(pd.concat(coer, ignore_index=True), saida / "tabelas", "tabela_07_coerencia",
                                       "Tabela 7 — Coerência das curvas: F(∞) exato vs Kaplan-Meier, medianas de início (exata vs Weibull da Lifelines), parâmetros recuperados pelo modelo de cura mista e idade do pico de risco"),
               relatorio.salvar_tabela(pd.concat(tempos, ignore_index=True), saida / "tabelas", "tabela_08_tempos",
                                       "Tabela 8 — Tempo de processamento por motor (PyMC e NumPy) e por N, em segundos (média de execuções sucessivas)"),
               relatorio.salvar_tabela(pd.concat(sens, ignore_index=True), saida / "tabelas", "tabela_09_sensibilidade",
                                       "Tabela 9 — Análise de sensibilidade: risco vitalício e idade mediana sob a calibração pela literatura, sob os parâmetros do exemplo do orientador e sob penetrância de coorte familiar para o C9orf72")]
    figs = [relatorio.figura_priors(par, saida / "figuras" / "figura_02_priors.png"),
            relatorio.figura_curvas_inicio(par, saida / "figuras" / "figura_03_curvas_inicio.png"),
            relatorio.figura_estabilidade(resumo, saida / "figuras" / "figura_07_estabilidade.png")]
    tt = pd.concat(tempos)
    secoes = [("Configuração", f"Cenários {numeros}; N ∈ {list(ns)}; {repeticoes} repetições por N; seed inicial {seed}; sexo do descendente {sexo}; coerência e sensibilidade com N = {_n(n_coerencia)}."),
              ("Leitura", f"Razão DP/EP média = {resumo.razao_dp_ep.mean():.2f}. Picos de risco entre 60 e 75 anos: {int(pd.concat(coer).pico_em_60_75.sum())} de {len(pd.concat(coer))} lóci. "
                          f"Tempo médio PyMC para N = {_n(max(ns))}: {tt[(tt.motor == 'pymc') & (tt.n == max(ns))].tempo_medio_s.mean():.2f} s; NumPy: {tt[(tt.motor == 'numpy') & (tt.n == max(ns))].tempo_medio_s.mean():.3f} s.")]
    rel = relatorio.escrever_relatorio(saida, "Avaliação do artefato (TCC 4.5)", secoes, tabelas, figs)
    relatorio.escrever_metadados(saida, data=_dt.datetime.now().isoformat(timespec="seconds"), seed=seed, ns=list(ns), repeticoes=repeticoes, sexo=sexo, cenarios=numeros)
    return {"saida": saida, "relatorio": rel, "estabilidade": resumo, "tempos": pd.concat(tempos), "coerencia": pd.concat(coer), "sensibilidade": pd.concat(sens), "tabelas": tabelas, "figuras": figs}


def tudo(saida, seed: int = 42, n: int = 10_000, ns=(1_000, 10_000, 100_000), repeticoes: int = 30, motor: str = "pymc", config=None, idade_atual: float | None = 30.0) -> dict:
    """Gera os cenários, executa cada um para os dois sexos, avalia e escreve o índice `README.md` em `saida`."""
    saida = Path(saida); saida.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    tab = cenarios.gerar_cenarios(saida / "sinteticos", seed=2026)
    consolidado, indice = [], []
    for c in cenarios.CENARIOS:
        linha = tab[tab.numero == c.numero].iloc[0]
        por_sexo = {}
        for sexo in ("F", "M"):
            r = executar(linha.vcf_mae, linha.vcf_pai, saida / "cenarios" / f"cenario_{c.numero}_{sexo}", sexo=sexo, idade_atual=idade_atual, n=n, seed=seed,
                         motor=motor, config=config, rotulo=f"Cenário {c.numero} ({sexo}): {c.descricao}")
            por_sexo[sexo] = r
            for _, l in r["resumo"].iterrows():
                consolidado.append({"cenario": c.numero, "descricao": c.descricao, "sexo": sexo, "variante": l.variante, "heranca": l.heranca,
                                    "p_portador": l.p_portador_exato, "p_manifesta": l.p_manifesta_exato, "ic95": f"{l.p_manifesta_q025:.3f}–{l.p_manifesta_q975:.3f}",
                                    "idade_mediana": l.idade_mediana_exata})
            cb = r["combinado"]
            consolidado.append({"cenario": c.numero, "descricao": c.descricao, "sexo": sexo, "variante": sobrevivencia.QUALQUER, "heranca": "independência",
                                "p_portador": cb["p_portador_qualquer_exato"], "p_manifesta": cb["p_manifesta_qualquer_exato"],
                                "ic95": f"{cb['p_manifesta_qualquer_q025']:.3f}–{cb['p_manifesta_qualquer_q975']:.3f}", "idade_mediana": cb["idade_mediana_primeiro_inicio"]})
            indice.append(f"- Cenário {c.numero}, sexo {sexo}: [`cenarios/cenario_{c.numero}_{sexo}/relatorio.md`](cenarios/cenario_{c.numero}_{sexo}/relatorio.md)")
        relatorio.figura_idade_inicio({s: r["res"] for s, r in por_sexo.items()}, saida / "cenarios" / f"figura_05_idade_inicio_cenario_{c.numero}.png")
    cons = pd.DataFrame(consolidado)
    tabela3 = relatorio.salvar_tabela(cons, saida / "tabelas", "tabela_03_consolidada",
                                      "Tabela 3 (consolidada) — Probabilidade de transmissão, risco vitalício de manifestação (IC 95%) e idade mediana de início por cenário, lócus e sexo do descendente")
    av = avaliar(saida / "sinteticos", saida / "avaliacao", ns=ns, repeticoes=repeticoes, seed=seed + 958, config=config, n_coerencia=n)
    linhas = [f"# Resultados do artefato ela_preditivo v{__version__}", "", f"> {AVISO_LEGAL}", "",
              f"Gerado em {_dt.datetime.now():%d/%m/%Y %H:%M} com seed {seed}, N = {_n(n)} por execução, avaliação com N ∈ {list(ns)} × {repeticoes} repetições. Tempo total: {time.perf_counter() - t0:.0f} s.", "",
              "## Relatórios por cenário", "", *indice, "", "## Avaliação transversal", "", "- [`avaliacao/relatorio.md`](avaliacao/relatorio.md) (Tabelas 5 a 9; Figuras 2, 3 e 7)", "",
              "## Tabela consolidada", "", Path(tabela3["md"]).read_text(encoding="utf-8"), "",
              "## Figuras de idade de início por sexo", "", *[f"![Cenário {c.numero}](cenarios/figura_05_idade_inicio_cenario_{c.numero}.png)" for c in cenarios.CENARIOS], ""]
    (saida / "README.md").write_text("\n".join(linhas), encoding="utf-8")
    return {"saida": saida, "consolidado": cons, "avaliacao": av}
