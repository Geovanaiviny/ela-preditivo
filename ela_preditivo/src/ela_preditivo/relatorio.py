"""Relatório (TCC 4.6): figuras PNG (300 dpi) e tabelas CSV/Markdown com legendas prontas para a seção 5."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
from scipy import stats  # noqa: E402

from . import AVISO_LEGAL, __version__  # noqa: E402
from . import sobrevivencia  # noqa: E402
from .calibracao import Parametros  # noqa: E402
from .exato import DistribuicaoInicio  # noqa: E402
from .monte_carlo import Locus, ResultadoSimulacao  # noqa: E402

FONTE = "Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo."
CORES = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b"]


def preparar_estilo():
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.05)
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


# ---------------------------------------------------------------------------
# Tabelas
# ---------------------------------------------------------------------------
def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    if isinstance(v, (bool, np.bool_)):
        return "sim" if v else "não"
    if isinstance(v, (float, np.floating)):
        if abs(v) >= 1000:
            return f"{v:,.0f}".replace(",", ".")
        return f"{v:.4f}".rstrip("0").rstrip(".") if abs(v) >= 1e-4 or v == 0 else f"{v:.2e}"
    return str(v)


def df_para_markdown(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    linhas = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        linhas.append("| " + " | ".join(_fmt(r[c]).replace("|", "\\|") for c in cols) + " |")
    return "\n".join(linhas)


def salvar_tabela(df: pd.DataFrame, dir_saida: Path, nome: str, legenda: str, nota: str = "") -> dict:
    dir_saida = Path(dir_saida); dir_saida.mkdir(parents=True, exist_ok=True)
    csv = dir_saida / f"{nome}.csv"; md = dir_saida / f"{nome}.md"
    df.to_csv(csv, index=False)
    texto = f"**{legenda}**\n\n{df_para_markdown(df)}\n\n*{FONTE}*" + (f"\n\n{nota}" if nota else "") + "\n"
    md.write_text(texto, encoding="utf-8")
    return {"nome": nome, "legenda": legenda, "csv": str(csv), "md": str(md)}


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------
def _salvar(fig, caminho: Path, legenda: str) -> dict:
    caminho = Path(caminho); caminho.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(caminho, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return {"png": str(caminho), "legenda": legenda}


def figura_dag(loci: list[Locus], caminho: Path, legenda: str = "Figura 1 — Rede Bayesiana (DAG) do núcleo estocástico") -> dict:
    preparar_estilo()
    nos = {"Dose\nmaterna": (0, 2, "obs"), "Dose\npaterna": (0, 0, "obs"), "Alelo\nmaterno": (1.6, 2, "lat"), "Alelo\npaterno": (1.6, 0, "lat"),
           "Dose do\ndescendente": (3.2, 1, "det"), "Herança\n(dom./rec.)": (3.2, 2.7, "obs"), "Portador": (4.8, 1, "det"),
           "Penetrância\nπ ~ Beta(α, β)": (4.8, 2.7, "lat"), "Manifesta": (6.4, 1, "lat"), "Sexo": (6.4, 2.7, "obs"), "Idade de\ninício G(t)": (8.0, 1, "lat")}
    arestas = [("Dose\nmaterna", "Alelo\nmaterno"), ("Dose\npaterna", "Alelo\npaterno"), ("Alelo\nmaterno", "Dose do\ndescendente"),
               ("Alelo\npaterno", "Dose do\ndescendente"), ("Dose do\ndescendente", "Portador"), ("Herança\n(dom./rec.)", "Portador"),
               ("Portador", "Manifesta"), ("Penetrância\nπ ~ Beta(α, β)", "Manifesta"), ("Manifesta", "Idade de\ninício G(t)"), ("Sexo", "Idade de\ninício G(t)")]
    cor = {"obs": "#d9d9d9", "lat": "#ffffff", "det": "#cfe2f3"}
    fig, ax = plt.subplots(figsize=(11, 4.2))
    for nome, (x, y, tipo) in nos.items():
        ax.add_patch(FancyBboxPatch((x - 0.6, y - 0.38), 1.2, 0.76, boxstyle="round,pad=0.02", fc=cor[tipo], ec="black", lw=1.2))
        ax.text(x, y, nome, ha="center", va="center", fontsize=9)
    for a, b in arestas:
        xa, ya, _ = nos[a]; xb, yb, _ = nos[b]
        dx, dy = xb - xa, yb - ya
        ax.annotate("", xy=(xb - 0.62 * np.sign(dx) if abs(dx) > 0.1 else xb, yb - 0.4 * np.sign(dy) if abs(dx) <= 0.1 else yb),
                    xytext=(xa + 0.62 * np.sign(dx) if abs(dx) > 0.1 else xa, ya + 0.4 * np.sign(dy) if abs(dx) <= 0.1 else ya),
                    arrowprops=dict(arrowstyle="-|>", lw=1.2, color="black"))
    ax.set_xlim(-0.9, 8.9); ax.set_ylim(-0.7, 3.4); ax.axis("off")
    ax.text(0, 3.25, "cinza: evidência observada (VCF anotado, YAML)   branco: variável aleatória   azul: nó determinístico", fontsize=8)
    ax.set_title("Rede Bayesiana por lócus de risco: " + "; ".join(l.rotulo for l in loci), fontsize=10)
    return _salvar(fig, caminho, legenda)


def figura_priors(parametros: Parametros, caminho: Path, legenda: str = "Figura 2 — Priors Beta de penetrância vitalícia por gene, calibradas ao ponto e ao IC 95% de Douglas & Baralle (2024)") -> dict:
    preparar_estilo()
    fig, axes = plt.subplots(2, 2, figsize=(9, 6), sharex=True)
    x = np.linspace(0.001, 0.999, 500)
    for ax, (nome, g), cor in zip(axes.ravel(), parametros.genes.items(), CORES):
        ax.plot(x, stats.beta.pdf(x, g.alpha, g.beta), color=cor, lw=2, label=f"Beta({g.alpha:.1f}, {g.beta:.1f})")
        ax.axvspan(g.pen_ic95[0], g.pen_ic95[1], color=cor, alpha=0.12, label="IC 95% publicado")
        ax.axvline(g.pen_valor, color="black", ls="--", lw=1, label=f"ponto publicado {g.pen_valor:.2f}")
        q = stats.beta.ppf([0.025, 0.975], g.alpha, g.beta)
        ax.axvline(q[0], color=cor, ls=":", lw=1); ax.axvline(q[1], color=cor, ls=":", lw=1, label="IC 95% da Beta")
        ax.set_title(nome); ax.legend(fontsize=7, loc="upper right"); ax.set_ylabel("densidade")
    for ax in axes[-1]:
        ax.set_xlabel("penetrância vitalícia π")
    fig.tight_layout()
    return _salvar(fig, caminho, legenda)


def figura_curvas_inicio(parametros: Parametros, caminho: Path, legenda: str = "Figura 3 — Distribuição acumulada da idade de início G(t) ajustada aos pontos da literatura, por gene") -> dict:
    preparar_estilo()
    fig, axes = plt.subplots(2, 2, figsize=(9, 6), sharex=True, sharey=True)
    t = np.linspace(0, 90, 400)
    ex = parametros.sensibilidade.get("exemplo_professor", {}).get("genes", {})
    for ax, (nome, g), cor in zip(axes.ravel(), parametros.genes.items(), CORES):
        ax.plot(t, g.inicio.cdf(t), color=cor, lw=2, label=f"{g.inicio.tipo} ajustada (mediana {g.inicio.mediana:.1f} anos)")
        pts = np.array(g.inicio_pontos, float)
        if pts.size:
            ax.scatter(pts[:, 0], pts[:, 1], color="black", zorder=5, label="pontos da literatura" + (" (provisórios)" if g.inicio_confirmar else ""))
        elif g.inicio_estatisticas:    # G(t) em forma fechada a partir de estatísticas publicadas (sem pontos de curva)
            ax.axvline(g.inicio.mediana, color="black", ls=":", lw=1,
                       label="estatísticas publicadas: " + ", ".join(f"{k} {v:g}" for k, v in g.inicio_estatisticas.items()) + (" (provisórias)" if g.inicio_confirmar else ""))
        if nome in ex:
            d = DistribuicaoInicio("weibull", k=ex[nome]["weibull_k"], lam=ex[nome]["weibull_lam"])
            ax.plot(t, d.cdf(t), color="gray", ls="--", lw=1.2, label="Weibull do exemplo do orientador")
        ax.set_title(nome + ("  (confirmar com Richard et al., 2026)" if g.inicio_confirmar and nome != "C9orf72" else "")); ax.legend(fontsize=7, loc="upper left")
    for ax in axes[-1]:
        ax.set_xlabel("idade (anos)")
    fig.supylabel("G(t): fração acumulada entre os que manifestam", fontsize=10)
    fig.tight_layout()
    return _salvar(fig, caminho, legenda)


def figura_risco_temporal(curvas: pd.DataFrame, res: ResultadoSimulacao, caminho: Path, horizonte: float = 90.0, rotulo: str = "",
                          legenda: str = "Figura 4 — Risco acumulado de manifestação F(t) e sobrevivência S(t) do descendente, com banda de credibilidade de 95% e Kaplan-Meier da coorte simulada") -> dict:
    preparar_estilo()
    unidades = list(dict.fromkeys(curvas.unidade))
    coorte = sobrevivencia.coorte_sintetica(res, horizonte)
    fig, axes = plt.subplots(2, len(unidades), figsize=(4.2 * len(unidades), 7), squeeze=False)
    for j, u in enumerate(unidades):
        c = curvas[curvas.unidade == u]; cor = CORES[j % len(CORES)]
        km = sobrevivencia.ajustar_km(coorte[coorte.unidade == u], u)
        ax = axes[0, j]
        ax.fill_between(c.t, c.F_q025, c.F_q975, color=cor, alpha=0.18, label="banda 95% (incerteza de π)")
        ax.plot(c.t, c.F, color=cor, lw=2, label="F(t) = P(C)·π·G(t)")
        sf = km.survival_function_; ci = km.confidence_interval_
        ax.step(sf.index, 1 - sf.iloc[:, 0], where="post", color="black", lw=1, label="1 − S_KM(t) (Lifelines)")
        ax.fill_between(ci.index, 1 - ci.iloc[:, 1], 1 - ci.iloc[:, 0], step="post", color="black", alpha=0.08)
        ax.axhline(c.F.iloc[-1], color=cor, ls=":", lw=1)
        ax.set_title(u, fontsize=10); ax.set_ylabel("P(manifestou até a idade t)"); ax.set_ylim(0, max(0.05, min(1.0, c.F_q975.max() * 1.25)))
        ax.legend(fontsize=7, loc="upper left")
        ax2 = axes[1, j]
        ax2.plot(c.t, c.S, color=cor, lw=2, label="S(t) = 1 − F(t)")
        ax2.step(sf.index, sf.iloc[:, 0], where="post", color="black", lw=1, label="S_KM(t)")
        ax2.set_ylim(max(0.0, c.S.min() - 0.05), 1.0); ax2.set_xlabel("idade do descendente (anos)"); ax2.set_ylabel("P(assintomático até t)")
        ax2.legend(fontsize=7, loc="lower left")
    fig.suptitle(rotulo, fontsize=10); fig.tight_layout()
    return _salvar(fig, caminho, legenda)


def figura_hazard(curvas: pd.DataFrame, caminho: Path, legenda: str = "Figura 8 — Função de risco instantâneo h(t) por lócus; faixa sombreada = pico de incidência 60–75 anos (Feldman et al., 2022)") -> dict:
    preparar_estilo()
    fig, ax = plt.subplots(figsize=(8, 4))
    for j, u in enumerate(dict.fromkeys(curvas.unidade)):
        c = curvas[curvas.unidade == u]
        ax.plot(c.t, c.h, color=CORES[j % len(CORES)], lw=2, label=u)
    ax.axvspan(60, 75, color="gray", alpha=0.15, label="pico de incidência 60–75")
    ax.set_xlabel("idade (anos)"); ax.set_ylabel("h(t) por ano"); ax.legend(fontsize=8); ax.set_xlim(0, curvas.t.max())
    fig.tight_layout()
    return _salvar(fig, caminho, legenda)


def figura_idade_inicio(resultados: dict[str, ResultadoSimulacao], caminho: Path, legenda: str = "Figura 5 — Distribuição simulada da idade de início entre os descendentes que manifestam, por lócus e sexo") -> dict:
    preparar_estilo()
    loci = next(iter(resultados.values())).loci
    fig, axes = plt.subplots(1, len(loci), figsize=(4.5 * len(loci), 3.8), squeeze=False)
    t = np.linspace(0, 95, 400)
    for j, l in enumerate(loci):
        ax = axes[0, j]
        for (sexo, res), cor in zip(resultados.items(), ["#1f77b4", "#d62728"]):
            idades = res.idade[res.manifesta[:, j], j]
            lj = res.loci[j]
            ax.hist(idades, bins=30, density=True, alpha=0.35, color=cor, label=f"sexo {sexo}: mediana MC {np.median(idades):.1f}" if idades.size else f"sexo {sexo}")
            ax.plot(t, lj.dist.pdf(t), color=cor, lw=1.5, label=f"{lj.dist.tipo} (mediana {lj.dist.mediana:.1f})")
        ax.set_title(l.rotulo, fontsize=10); ax.set_xlabel("idade de início (anos)"); ax.legend(fontsize=7)
    axes[0, 0].set_ylabel("densidade")
    fig.tight_layout()
    return _salvar(fig, caminho, legenda)


def figura_aderencia(tab: pd.DataFrame, caminho: Path, legenda: str = "Figura 6 — Aderência teórica: probabilidades exatas vs Monte Carlo (PyMC e NumPy), com erro padrão") -> dict:
    preparar_estilo()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, met in zip(axes, ("portador", "manifesta")):
        x = np.arange(len(tab)); w = 0.26
        ax.bar(x - w, tab[f"p_{met}_exato"], w, color="black", alpha=0.75, label="exato")
        ax.bar(x, tab[f"p_{met}_pymc"], w, yerr=1.96 * tab[f"ep_{met}"].fillna(0), color=CORES[0], label="PyMC (±1,96 EP)", capsize=2)
        ax.bar(x + w, tab[f"p_{met}_numpy"], w, yerr=1.96 * tab[f"ep_{met}"].fillna(0), color=CORES[2], label="NumPy (±1,96 EP)", capsize=2)
        ax.set_xticks(x); ax.set_xticklabels(tab.variante, rotation=15, ha="right", fontsize=8)
        ax.set_ylabel("P(portador)" if met == "portador" else "P(manifestação vitalícia)"); ax.legend(fontsize=8)
    fig.tight_layout()
    return _salvar(fig, caminho, legenda)


def figura_estabilidade(resumos: pd.DataFrame, caminho: Path, legenda: str = "Figura 7 — Estabilidade numérica: desvio padrão entre execuções vs N (escala log-log) e erro padrão teórico √(p(1−p)/N)") -> dict:
    preparar_estilo()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for j, (cen, g) in enumerate(resumos.groupby("cenario")):
        g = g.sort_values("n")
        ax.plot(g.n, g.p_manifesta_qualquer_dp, "o-", color=CORES[j % len(CORES)], label=f"{cen}: DP observado")
        ax.plot(g.n, g.ep_teorico, "--", color=CORES[j % len(CORES)], alpha=0.6, label=f"{cen}: EP teórico")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("N (fecundações simuladas)"); ax.set_ylabel("DP de P(manifestação) entre execuções")
    ax.legend(fontsize=7, ncol=2); fig.tight_layout()
    return _salvar(fig, caminho, legenda)


# ---------------------------------------------------------------------------
# Relatório Markdown e metadados
# ---------------------------------------------------------------------------
def escrever_metadados(dir_saida: Path, **campos) -> Path:
    dir_saida = Path(dir_saida); dir_saida.mkdir(parents=True, exist_ok=True)
    meta = {"pacote": "ela_preditivo", "versao": __version__, "aviso_legal": AVISO_LEGAL, **campos}
    p = dir_saida / "metadados.json"
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return p


def escrever_relatorio(dir_saida: Path, titulo: str, secoes: list[tuple[str, str]], tabelas: list[dict], figuras: list[dict], nome: str = "relatorio.md") -> Path:
    dir_saida = Path(dir_saida)
    linhas = [f"# {titulo}", "", f"> {AVISO_LEGAL}", ""]
    for t, texto in secoes:
        linhas += [f"## {t}", "", texto, ""]
    if tabelas:
        linhas += ["## Tabelas", ""]
        for tb in tabelas:
            linhas += [Path(tb["md"]).read_text(encoding="utf-8"), ""]
    if figuras:
        linhas += ["## Figuras", ""]
        for f in figuras:
            rel = Path(f["png"]).relative_to(dir_saida) if str(f["png"]).startswith(str(dir_saida)) else f["png"]
            linhas += [f"![{f['legenda']}]({rel})", "", f"*{f['legenda']}. {FONTE}*", ""]
    p = dir_saida / nome
    p.write_text("\n".join(linhas), encoding="utf-8")
    return p
