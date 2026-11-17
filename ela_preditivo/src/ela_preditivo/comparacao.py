"""Comparação com o modelo de riscos proporcionais de Cox (extensão).

O artefato modela a manifestação com um modelo de cura mista, S(t) = 1 − π·G(t) entre portadores (TCC 4.4.C). Para
situar essa escolha diante do modelo clássico de sobrevivência, este módulo ajusta `CoxPHFitter` (Lifelines) na coorte
sintética **de portadores** e compara, na mesma coorte, a sobrevivência marginal prevista por Cox com a cura mista, o
Kaplan-Meier e a curva analítica.

Por que só portadores: no modelo, quem não porta a variante nunca manifesta, logo a covariável "portador" separa
perfeitamente eventos de não eventos e a verossimilhança parcial de Cox não tem máximo (Lifelines interrompe por
separação completa). Entre portadores há covariáveis com variação real: o sexo (os dois sexos são simulados com a mesma
semente) e, na unidade combinada, qual lócus cada descendente porta.

O que a comparação mostra: a função de base de Cox é não paramétrica e reproduz a sobrevivência observada, mas Cox não
separa quem nunca manifestará (fração de cura 1 − π) de quem ainda não manifestou, nem estima π; o efeito do sexo entra
como razão de riscos constante, embora no modelo ele seja um deslocamento de idade, o que o teste de riscos
proporcionais (resíduos de Schoenfeld) pode acusar.
"""

from __future__ import annotations

import warnings
from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter
from lifelines.exceptions import ConvergenceError
from lifelines.statistics import proportional_hazard_test

from . import relatorio, sobrevivencia
from .calibracao import Parametros
from .monte_carlo import Locus, ResultadoSimulacao, simular_numpy
from .sobrevivencia import QUALQUER

SEXOS = ("F", "M")
IDADES = (50, 60, 70)
MIN_EVENTOS = 10


def loci_por_sexo(res: ResultadoSimulacao, parametros: Parametros) -> dict[str, list[Locus]]:
    """Lóci de `res` com G(t) deslocada para cada sexo, relativamente ao sexo da execução (preserva outros
    deslocamentos já aplicados, como a antecipação de `repeticoes`)."""
    atual = res.sexo
    out: dict[str, list[Locus]] = {}
    for s in SEXOS:
        novos = []
        for l in res.loci:
            ds = parametros.genes[l.gene].delta_sexo
            rel = float(ds.get(s, 0.0)) - (float(ds.get(atual, 0.0)) if atual else 0.0)
            novos.append(replace(l, dist=l.dist.deslocar(rel)) if rel else l)
        out[s] = novos
    return out


def coorte_cox(res: ResultadoSimulacao, parametros: Parametros, horizonte: float = 90.0) -> pd.DataFrame:
    """Coorte sintética de portadores, simulada para os dois sexos com a mesma semente e o mesmo N de `res`.

    Uma linha por fecundação e unidade: `unidade`, `duracao`, `evento`, `sexo_masculino` e, na unidade combinada
    (só quando há mais de um lócus), `portador_<j>` para cada lócus j.
    """
    partes = []
    n = res.n_original or res.n
    for s, loci in loci_por_sexo(res, parametros).items():
        r = simular_numpy(loci, n=n, seed=res.seed)
        masc = int(s == "M")
        for j, l in enumerate(r.loci):
            m = r.portador[:, j]
            man = r.manifesta[m, j] & (r.idade[m, j] <= horizonte)
            partes.append(
                pd.DataFrame(
                    {
                        "unidade": l.rotulo,
                        "duracao": np.where(man, r.idade[m, j], horizonte),
                        "evento": man,
                        "sexo_masculino": masc,
                    }
                )
            )
        if len(r.loci) > 1:
            m = r.portador.any(axis=1)
            idade_q = r.idade_qualquer[m]
            man = r.manifesta_qualquer[m] & (np.nan_to_num(idade_q, nan=np.inf) <= horizonte)
            df = pd.DataFrame(
                {
                    "unidade": QUALQUER,
                    "duracao": np.where(man, idade_q, horizonte),
                    "evento": man,
                    "sexo_masculino": masc,
                }
            )
            for j in range(len(r.loci)):
                df[f"portador_{j}"] = r.portador[m, j].astype(int)
            partes.append(df)
    coorte = pd.concat(partes, ignore_index=True)
    for col in coorte.columns:
        if col.startswith("portador_"):
            coorte[col] = coorte[col].fillna(0).astype(int)
    return coorte


def ajustar_cox(coorte: pd.DataFrame, covariaveis: list[str]) -> dict | None:
    """CoxPHFitter numa unidade da coorte. None com poucos eventos; {"erro": ...} se não converge."""
    if coorte.evento.sum() < MIN_EVENTOS or (~coorte.evento.astype(bool)).sum() < 1:
        return None
    covs = [k for k in covariaveis if k in coorte.columns and coorte[k].nunique() > 1]
    if not covs:
        return None
    dados = coorte[["duracao", "evento", *covs]].astype(float).reset_index(drop=True)
    cph = CoxPHFitter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            cph.fit(dados, duration_col="duracao", event_col="evento")
        except (ConvergenceError, ValueError) as e:
            return {"erro": str(e).splitlines()[0]}
        try:
            p_rp = proportional_hazard_test(cph, dados, time_transform="rank").summary["p"].to_dict()
        except Exception:  # noqa: BLE001  (teste auxiliar; nunca derruba a comparação)
            p_rp = {}
    return {
        "cph": cph,
        "dados": dados,
        "covariaveis": covs,
        "summary": cph.summary,
        "concordancia": float(cph.concordance_index_),
        "log_verossimilhanca": float(cph.log_likelihood_),
        "p_riscos_proporcionais": p_rp,
        "n": int(len(dados)),
        "eventos": int(dados.evento.sum()),
    }


def _s_analitico(c: pd.DataFrame, unidade: str, loci_s: dict[str, list[Locus]], t: np.ndarray) -> np.ndarray:
    """Sobrevivência analítica média da coorte: por linha, ∏ sobre os lóci portados de (1 − π·G_sexo(t))."""
    S = np.ones((len(c), len(t)))
    masc = c.sexo_masculino.values.astype(int)
    for s, loci in loci_s.items():
        linhas = np.where(masc == int(s == "M"))[0]
        if linhas.size == 0:
            continue
        for j, l in enumerate(loci):
            if unidade == QUALQUER:
                port = c[f"portador_{j}"].values[linhas].astype(bool)
            elif l.rotulo == unidade:
                port = np.ones(linhas.size, dtype=bool)
            else:
                continue
            S[linhas[port]] *= 1.0 - l.pen_media * l.dist.cdf(t)
    return S.mean(axis=0)


def comparar(
    res: ResultadoSimulacao,
    parametros: Parametros,
    horizonte: float = 90.0,
    idades=IDADES,
    passo: float = 0.5,
) -> dict:
    """Tabela 11 (uma linha por unidade), curvas S(t) por método e texto do relatório."""
    coorte = coorte_cox(res, parametros, horizonte)
    loci_s = loci_por_sexo(res, parametros)
    t = np.arange(0, horizonte + passo, passo)
    linhas, curvas, mensagens = [], [], []
    for unidade, c in coorte.groupby("unidade", sort=False):
        covs = ["sexo_masculino"] + sorted(k for k in c.columns if k.startswith("portador_"))
        cox = ajustar_cox(c, covs)
        linha = {"unidade": unidade, "n_portadores": int(len(c)), "eventos": int(c.evento.sum())}
        if cox is None or "erro" in cox:
            motivo = (cox or {}).get("erro") or f"menos de {MIN_EVENTOS} eventos ou nenhuma censura (aumente N)"
            linha["cox"] = f"não ajustado: {motivo}"
            mensagens.append(f"{unidade}: Cox não ajustado ({motivo})")
            linhas.append(linha)
            continue
        linha["cox"] = "ajustado"
        s = cox["summary"]
        for k in cox["covariaveis"]:
            nome = {"sexo_masculino": "sexo masculino"}.get(k)
            if nome is None:
                j = int(k.split("_")[1])
                nome = f"portador {res.loci[j].rotulo}"
            linha[f"HR[{nome}]"] = float(s.loc[k, "exp(coef)"])
            linha[f"IC95 HR[{nome}]"] = f"{s.loc[k, 'exp(coef) lower 95%']:.3f}–{s.loc[k, 'exp(coef) upper 95%']:.3f}"
            linha[f"p[{nome}]"] = float(s.loc[k, "p"])
            linha[f"p_riscos_proporcionais[{nome}]"] = float(cox["p_riscos_proporcionais"].get(k, np.nan))
        linha["concordancia"] = cox["concordancia"]
        linha["log_verossimilhanca_parcial"] = cox["log_verossimilhanca"]
        cph = cox["cph"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s_cox = cph.predict_survival_function(cox["dados"][cox["covariaveis"]], times=t).mean(axis=1).values
        km = sobrevivencia.ajustar_km(c, unidade)
        s_km = km.survival_function_at_times(t).values
        mc = sobrevivencia.ajustar_mistura_cura(c)
        s_mc = mc.survival_function_at_times(t).values if mc is not None else np.full(len(t), np.nan)
        s_an = _s_analitico(c, unidade, loci_s, t)
        for a in idades:
            i = int(np.argmin(np.abs(t - a)))
            linha[f"S_cox({a})"] = float(s_cox[i])
            linha[f"S_cura_mista({a})"] = float(s_mc[i])
            linha[f"S_km({a})"] = float(s_km[i])
            linha[f"S_analitico({a})"] = float(s_an[i])
        linha["S_cox(horizonte)"] = float(s_cox[-1])
        linha["fracao_cura_lifelines"] = float(1 - mc.pi_) if mc is not None else np.nan
        linha["pi_lifelines"] = float(mc.pi_) if mc is not None else np.nan
        if unidade != QUALQUER:
            lj = next(l for l in res.loci if l.rotulo == unidade)
            linha["pi_entrada"] = lj.pen_media
        linha["dif_max_cox_cura_mista"] = float(np.nanmax(np.abs(s_cox - s_mc))) if mc is not None else np.nan
        linha["dif_max_cox_km"] = float(np.nanmax(np.abs(s_cox - s_km)))
        linhas.append(linha)
        curvas.append(
            pd.DataFrame(
                {"unidade": unidade, "t": t, "S_cox": s_cox, "S_cura_mista": s_mc, "S_km": s_km, "S_analitico": s_an}
            )
        )
    tabela = pd.DataFrame(linhas)
    df_curvas = pd.concat(curvas, ignore_index=True) if curvas else None
    return {"tabela": tabela, "curvas": df_curvas, "mensagens": mensagens, "texto": texto_relatorio(tabela, mensagens)}


def texto_relatorio(tabela: pd.DataFrame, mensagens: list[str]) -> str:
    """Parágrafo da seção "Comparação com o modelo de Cox" do relatório."""
    partes = [
        "`CoxPHFitter` (Lifelines) ajustado na coorte sintética de portadores (os dois sexos simulados com a mesma semente; "
        "não portadores ficam fora porque nunca manifestam e separariam completamente a verossimilhança parcial)."
    ]
    for r in tabela.to_dict(orient="records"):
        if r.get("cox") != "ajustado":
            partes.append(f"{r['unidade']}: {r.get('cox', 'não ajustado')}.")
            continue
        hrs = []
        for k, v in r.items():
            if k.startswith("HR[") and np.isfinite(v):
                nome = k[3:-1]
                hrs.append(
                    f"HR {nome} = {v:.2f} [{r.get(f'IC95 HR[{nome}]', '')}], p = {r.get(f'p[{nome}]', np.nan):.3f}, "
                    f"riscos proporcionais p = {r.get(f'p_riscos_proporcionais[{nome}]', np.nan):.3f}"
                )
        s60 = f"S(60): Cox {r['S_cox(60)']:.3f}, cura mista {r['S_cura_mista(60)']:.3f}, Kaplan-Meier {r['S_km(60)']:.3f}, analítico {r['S_analitico(60)']:.3f}"
        cura = (
            f"S_Cox(horizonte) = {r['S_cox(horizonte)']:.3f} vs fração de cura da Lifelines 1 − π̂ = {r['fracao_cura_lifelines']:.3f}"
            + (f" (π de entrada {r['pi_entrada']:.3f})" if np.isfinite(r.get("pi_entrada", np.nan)) else "")
        )
        partes.append(
            f"**{r['unidade']}** ({r['n_portadores']} portadores, {r['eventos']} eventos): {'; '.join(hrs)}; "
            f"concordância {r['concordancia']:.3f}; {s60}; {cura}; maior diferença Cox × cura mista "
            f"{r['dif_max_cox_cura_mista']:.3f}."
        )
    partes.append(
        "Leitura: a função de base de Cox é não paramétrica e acompanha o Kaplan-Meier, mas Cox não separa quem nunca "
        "manifestará (fração de cura) de quem ainda não manifestou nem estima π; o modelo de cura mista recupera π e G(t) "
        "separadamente (Tabela 7). O efeito do sexo entra em Cox como razão de riscos constante, embora no modelo seja um "
        "deslocamento de idade; na unidade combinada as HR entre lóci misturam diferenças de penetrância e de idade de início."
    )
    if mensagens:
        partes.append("Avisos: " + "; ".join(mensagens) + ".")
    return " ".join(partes)


def figura_cox_vs_cura_mista(
    curvas: pd.DataFrame,
    caminho,
    legenda: str = "Figura 9 — Sobrevivência (assintomático) entre portadores: Cox (marginal), cura mista, Kaplan-Meier e curva analítica, por unidade",
) -> dict:
    relatorio.preparar_estilo()
    unidades = list(dict.fromkeys(curvas.unidade))
    fig, axes = plt.subplots(1, len(unidades), figsize=(4.4 * len(unidades), 3.8), squeeze=False)
    for j, u in enumerate(unidades):
        c = curvas[curvas.unidade == u]
        ax = axes[0, j]
        ax.step(c.t, c.S_km, where="post", color="black", lw=1, label="Kaplan-Meier")
        ax.plot(c.t, c.S_cox, color=relatorio.CORES[1], lw=2, label="Cox (média dos perfis)")
        ax.plot(c.t, c.S_cura_mista, color=relatorio.CORES[0], lw=2, ls="--", label="cura mista (Lifelines)")
        ax.plot(c.t, c.S_analitico, color=relatorio.CORES[2], lw=1.2, ls=":", label="analítico 1 − πG(t)")
        ax.set_title(u, fontsize=10)
        ax.set_xlabel("idade do descendente (anos)")
        ax.set_ylim(max(0.0, float(np.nanmin(c[["S_km", "S_cox"]].values)) - 0.05), 1.0)
        ax.legend(fontsize=7, loc="lower left")
    axes[0, 0].set_ylabel("P(assintomático até t | portador)")
    fig.tight_layout()
    return relatorio._salvar(fig, caminho, legenda)
