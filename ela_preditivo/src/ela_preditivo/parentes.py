"""Genótipo de parentes para o genitor que não pôde ser testado (extensão de três gerações).

Quando um genitor faleceu, não está disponível ou não quer fazer o teste, o artefato aceita o VCF e o laudo do C9orf72
de parentes dele (pai, mãe ou irmão: avô, avó ou tio do atendido) e, no caso de família, o VCF de um filho já testado.
A dosagem do genitor deixa de ser observada e passa a ser uma variável latente, inferida pela tabela de segregação
(a mesma do núcleo) e condicionada à situação clínica do próprio genitor. O dado do parente é genótipo: não entra
nenhum parâmetro novo da literatura, só a segregação, a penetrância e a G(t) já calibradas.

Modelo, por lócus (G = genitor sem exame; A₁, A₂ = pais de G; T = irmão de G; c = filho já testado):

- avós com exame: P(d_G | d_A₁, d_A₂) pela convolução de duas Bernoulli;
- avô ou avó sem exame: suposto não portador (padrão, declarado) ou prior de Hardy-Weinberg com a frequência alélica
  da base de anotação, P(0) = (1−f)², P(1) = 2f(1−f), P(2) = f²;
- tio com exame e avós sem exame: inferência bayesiana completa, com prior de Hardy-Weinberg nos avós, verossimilhança
  da dosagem do tio e posterior dos avós. Sem frequência na base vale o limite de alelo raro dessa prior (f → 0⁺):
  um avô heterozigoto e o outro não portador quando o tio é heterozigoto, e "não portadores" quando nada exige a
  variante. Supõe-se a variante herdada, não surgida no parente;
- filho já testado: verossimilhança P(d_c | d_G, d_outro genitor) pela mesma tabela;
- situação clínica de G: vivo sem sintomas (ou falecido sem ELA) na idade a_G entra com verossimilhança
  1 − π·G_sexo(a_G) se G porta o genótipo de risco e 1 se não porta; afetado ou desconhecida não condiciona.

A penetrância π é do gene, não do indivíduo: em cada sorteio é sorteada uma vez e vale para toda a família. Um genitor
que chegou aos 60 anos sem sintomas torna menos prováveis a variante nele e os valores altos de π, e por isso o risco
do descendente não é o produto de médias separadas. O cálculo exato integra numericamente na distribuição de π; o
Monte Carlo sorteia, no mesmo sorteio, π, as dosagens latentes, o fenótipo do genitor e o descendente, e descarta os
sorteios incompatíveis com a situação do genitor. A evidência de genótipo (tio, filho testado) entra por
condicionamento exato na enumeração das dosagens: rejeitá-la por sorteio seria inviável com alelos raros.
"""

from __future__ import annotations

import math
import time
import warnings
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

from . import anotacao, genotipo, ingestao
from .calibracao import Parametros
from .exato import DistribuicaoInicio, cpt_segregacao, prob_portador
from .genotipo import CHAVE_EXPANSAO, GENE_EXPANSAO

LADOS = ("mae", "pai")
SITUACOES = ("vivo_assintomatico", "falecido_sem_ela", "afetado", "desconhecido")
SITUACOES_QUE_CONDICIONAM = ("vivo_assintomatico", "falecido_sem_ela")
PRIORS_AVOS = ("nao_portador", "hardy_weinberg")
SEXO_DO_LADO = {"mae": "F", "pai": "M"}
ROTULO_GENITOR = {"mae": "mãe", "pai": "pai"}
ROTULO_PARENTE = {
    ("mae", "pai"): "avô materno",
    ("mae", "mae"): "avó materna",
    ("mae", "irmao"): "tio(a) materno(a)",
    ("pai", "pai"): "avô paterno",
    ("pai", "mae"): "avó paterna",
    ("pai", "irmao"): "tio(a) paterno(a)",
}
ROTULO_SITUACAO = {
    "vivo_assintomatico": "vivo, sem sintomas",
    "falecido_sem_ela": "falecido sem ELA",
    "afetado": "afetado",
    "desconhecido": "situação desconhecida",
}
SUPOSICAO_HERDADA = (
    "a variante do parente é suposta herdada, não surgida nele (não há taxa de mutação nova nas fontes do modelo)"
)
LIMITE_INFERIOR_AFETADO = "limite inferior: o fenótipo do genitor não é modelado"


# ---------------------------------------------------------------------------
# Entrada: parentes de cada genitor sem exame e filhos já testados
# ---------------------------------------------------------------------------
@dataclass
class Parente:
    """Pessoa testada da família: VCF (variantes curtas) e, para o C9orf72, o laudo de repetições."""

    vcf: str | Path | None = None
    laudo_c9orf72: object = None  # inteiro (maior alelo) ou par de inteiros; None = sem laudo
    amostra: str | None = None

    @classmethod
    def de(cls, valor) -> "Parente | None":
        if valor is None or isinstance(valor, Parente):
            return valor
        if isinstance(valor, (str, Path)):
            return cls(vcf=valor)
        d = dict(valor)
        laudo = d.get("laudo_c9orf72", d.get("laudo"))
        if not d.get("vcf") and laudo is None:
            return None
        return cls(vcf=d.get("vcf") or None, laudo_c9orf72=laudo, amostra=d.get("amostra"))


@dataclass
class LadoFamilia:
    """O que se sabe de um genitor sem exame: a situação clínica dele e os parentes testados (pai, mãe e irmãos)."""

    situacao: str = "desconhecido"
    idade: float | None = None  # idade atual (vivo sem sintomas) ou ao falecer (falecido sem ELA)
    pai: Parente | None = None  # pai do genitor (avô do atendido)
    mae: Parente | None = None  # mãe do genitor (avó do atendido)
    irmaos: list[Parente] = field(default_factory=list)  # irmãos do genitor (tios do atendido)
    prior_avos: str = "nao_portador"

    def __post_init__(self):
        self.situacao = str(self.situacao or "desconhecido").lower()
        if self.situacao == "desconhecida":
            self.situacao = "desconhecido"
        if self.situacao not in SITUACOES:
            raise ValueError(f"situação clínica do genitor desconhecida: {self.situacao!r} (use uma de {SITUACOES})")
        if self.prior_avos not in PRIORS_AVOS:
            raise ValueError(f"prior dos avós desconhecida: {self.prior_avos!r} (use uma de {PRIORS_AVOS})")
        if self.idade is not None:
            self.idade = float(self.idade)
            if not 0 <= self.idade <= 120:
                raise ValueError(f"idade do genitor fora do intervalo 0–120: {self.idade}")
        if self.situacao in SITUACOES_QUE_CONDICIONAM and self.idade is None:
            raise ValueError(
                f"situação {ROTULO_SITUACAO[self.situacao]!r} exige a idade do genitor (atual ou ao falecer)"
            )

    @property
    def condiciona(self) -> bool:
        return self.situacao in SITUACOES_QUE_CONDICIONAM

    @property
    def parentes(self) -> list[tuple[str, Parente]]:
        itens = [("pai", self.pai), ("mae", self.mae)] + [("irmao", t) for t in self.irmaos]
        return [(k, p) for k, p in itens if p is not None]

    @classmethod
    def de(cls, valor) -> "LadoFamilia | None":
        if valor is None or isinstance(valor, LadoFamilia):
            return valor
        d = dict(valor)
        irmaos = d.get("irmaos") or d.get("irmao") or []
        if isinstance(irmaos, (str, Path, dict, Parente)):
            irmaos = [irmaos]
        return cls(
            situacao=d.get("situacao") or "desconhecido",
            idade=d.get("idade"),
            pai=Parente.de(d.get("pai")),
            mae=Parente.de(d.get("mae")),
            irmaos=[p for p in (Parente.de(x) for x in irmaos) if p is not None],
            prior_avos=d.get("prior_avos") or "nao_portador",
        )


@dataclass
class Familia:
    """Parentes informados: um `LadoFamilia` por genitor sem exame e os filhos já testados (caso de família)."""

    mae: LadoFamilia | None = None
    pai: LadoFamilia | None = None
    filhos_testados: list[Parente] = field(default_factory=list)

    @classmethod
    def de(cls, valor) -> "Familia | None":
        if valor is None or isinstance(valor, Familia):
            return valor
        d = dict(valor)
        filhos = d.get("filhos_testados") or d.get("filhos") or []
        if isinstance(filhos, (str, Path, dict, Parente)):
            filhos = [filhos]
        f = cls(
            mae=LadoFamilia.de(d.get("mae")),
            pai=LadoFamilia.de(d.get("pai")),
            filhos_testados=[p for p in (Parente.de(x) for x in filhos) if p is not None],
        )
        return f if f.em_uso else None

    @property
    def em_uso(self) -> bool:
        return bool(self.filhos_testados) or any(
            lado is not None and (lado.parentes or lado.situacao != "desconhecido") for lado in (self.mae, self.pai)
        )

    def lado(self, nome: str) -> LadoFamilia | None:
        return self.mae if nome == "mae" else self.pai

    def tem_parente_com_vcf(self, nome: str) -> bool:
        lado = self.lado(nome)
        return bool(lado and any(p.vcf for _, p in lado.parentes)) or any(f.vcf for f in self.filhos_testados)

    def tem_parente_com_laudo(self, nome: str) -> bool:
        lado = self.lado(nome)
        return bool(lado and any(p.laudo_c9orf72 is not None for _, p in lado.parentes))


# ---------------------------------------------------------------------------
# Enumeração das dosagens com a evidência de genótipo
# ---------------------------------------------------------------------------
# Cada peso é (ordem em f, coeficiente). Com frequência conhecida a prior de Hardy-Weinberg é numérica (ordem 0); sem
# ela vale o limite f → 0⁺, em que só os termos de menor ordem sobrevivem: é a conta exata do "suposto não portador"
# (quando nada exige a variante) e do "um avô heterozigoto e o outro não portador" (quando o tio é heterozigoto).
_ZERO = (math.inf, 0.0)


def _soma(a: tuple, b: tuple) -> tuple:
    if a[1] == 0:
        return b
    if b[1] == 0:
        return a
    if a[0] != b[0]:
        return a if a[0] < b[0] else b
    return (a[0], a[1] + b[1])


def _prod(a: tuple, b: tuple) -> tuple:
    if a[1] == 0 or b[1] == 0:
        return _ZERO
    return (a[0] + b[0], a[1] * b[1])


def _prior_avo(observado: int | None, modo: str, freq: float | None) -> dict[int, tuple]:
    """Prior da dosagem de um avô: observada (com exame), Hardy-Weinberg numérica ou limite de alelo raro."""
    if observado is not None:
        return {int(observado): (0, 1.0)}
    if modo == "hardy_weinberg" and freq:
        f = float(freq)
        return {0: (0, (1 - f) ** 2), 1: (0, 2 * f * (1 - f)), 2: (0, f * f)}
    return {0: (0, 1.0), 1: (1, 2.0), 2: (2, 1.0)}


@dataclass
class EvidenciaLado:
    """Evidência de genótipo sobre um genitor num lócus."""

    lado: str
    observado: int | None = None  # dosagem do próprio genitor, quando ele foi testado para este lócus
    avos: tuple = (None, None)  # (pai do genitor, mãe do genitor); None = sem exame para este lócus
    irmaos: tuple = ()  # dosagens dos irmãos testados
    modo_prior: str = "limite"  # "limite" (suposto não portador / alelo raro) ou "hardy_weinberg"
    freq: float | None = None
    situacao: str = "desconhecido"
    idade: float | None = None
    suposto_nao_portador: bool = False  # genitor sem exame e sem parentes, assumido sem variante (suposição declarada)

    @property
    def inferido(self) -> bool:
        return self.observado is None

    @property
    def condiciona(self) -> bool:
        return self.inferido and self.situacao in SITUACOES_QUE_CONDICIONAM and self.idade is not None

    def tabela(self) -> dict[tuple, tuple]:
        """{(a1, a2, d_G): (ordem, coeficiente)}: prior dos avós × verossimilhança dos irmãos × segregação."""
        if self.observado is not None:
            return {(None, None, int(self.observado)): (0, 1.0)}
        p1 = _prior_avo(self.avos[0], self.modo_prior, self.freq)
        p2 = _prior_avo(self.avos[1], self.modo_prior, self.freq)
        tab: dict[tuple, tuple] = {}
        for a1, w1 in p1.items():
            for a2, w2 in p2.items():
                cpt = cpt_segregacao(a1, a2)
                ver = 1.0
                for dt in self.irmaos:
                    ver *= float(cpt[int(dt)])
                if ver == 0:
                    continue
                base = _prod(w1, w2)
                for dg in range(3):
                    if cpt[dg] > 0:
                        tab[(a1, a2, dg)] = (base[0], base[1] * ver * float(cpt[dg]))
        return tab


@dataclass
class EvidenciaLocus:
    """Evidência de genótipo num lócus e a distribuição conjunta das dosagens parentais que ela determina."""

    heranca: str
    mae: EvidenciaLado
    pai: EvidenciaLado
    filhos: tuple = ()  # dosagens dos filhos já testados
    conjunta: np.ndarray | None = None  # (3, 3): P(d_mãe = i, d_pai = j | genótipos dos parentes)
    condicional_avos: dict = field(default_factory=dict)  # {lado: (3, 3, 3)}: P(a1, a2 | d_G) do lado inferido
    exige_variante: dict = field(default_factory=dict)  # {lado: True} se a evidência obrigou avó/avô portador
    compativel: bool = True

    def lado(self, nome: str) -> EvidenciaLado:
        return self.mae if nome == "mae" else self.pai

    @property
    def lados_inferidos(self) -> list[str]:
        return [n for n in LADOS if self.lado(n).inferido]

    def resolver(self) -> "EvidenciaLocus":
        """Enumera as dosagens e normaliza no menor grau em f. `compativel = False` quando nenhum estado explica os
        genótipos observados (ex.: filho homozigoto com um genitor sem a variante): o lócus não pode ser avaliado."""
        tabs = {n: self.lado(n).tabela() for n in LADOS}
        marg = {}
        for n in LADOS:
            m = {d: _ZERO for d in range(3)}
            for (_, _, dg), w in tabs[n].items():
                m[dg] = _soma(m[dg], w)
            marg[n] = m
        conj: dict[tuple, tuple] = {}
        for dm in range(3):
            for dp in range(3):
                w = _prod(marg["mae"][dm], marg["pai"][dp])
                if w[1] == 0:
                    continue
                cpt = cpt_segregacao(dm, dp)
                ver = 1.0
                for dc in self.filhos:
                    ver *= float(cpt[int(dc)])
                if ver > 0:
                    conj[(dm, dp)] = (w[0], w[1] * ver)
        if not conj:
            self.compativel, self.conjunta = False, None
            return self
        ordem = min(w[0] for w in conj.values())
        mat = np.zeros((3, 3))
        for (dm, dp), w in conj.items():
            if w[0] == ordem:
                mat[dm, dp] = w[1]
        self.conjunta = mat / mat.sum()
        self.compativel = True
        for n in LADOS:
            lado = self.lado(n)
            if not lado.inferido:
                continue
            cond = np.zeros((3, 3, 3))  # [d_G, a1, a2]
            for dg in range(3):
                fatia = {k: w for k, w in tabs[n].items() if k[2] == dg}
                if not fatia:
                    continue
                o = min(w[0] for w in fatia.values())
                for (a1, a2, _), w in fatia.items():
                    if w[0] == o:
                        cond[dg, a1, a2] = w[1]
                if cond[dg].sum() > 0:
                    cond[dg] /= cond[dg].sum()
            self.condicional_avos[n] = cond
            # a evidência obrigou a variante na família deste genitor apesar de avô/avó sem exame?
            p_portador_lado = float(self.marginal(n)[1:].sum())
            self.exige_variante[n] = bool(
                lado.modo_prior == "limite"
                and p_portador_lado > 0
                and any(a is None for a in lado.avos)
                and not any((a or 0) > 0 for a in lado.avos)
            )
        return self

    def marginal(self, nome: str) -> np.ndarray:
        """P(d_G | genótipos dos parentes) do genitor `nome`, antes do condicionamento pela situação clínica."""
        return self.conjunta.sum(axis=1) if nome == "mae" else self.conjunta.sum(axis=0)


# ---------------------------------------------------------------------------
# Inferência por lócus com penetrância compartilhada
# ---------------------------------------------------------------------------
def _portador(d: int, heranca: str) -> bool:
    return d == 2 if heranca == "recessiva" else d >= 1


class InferenciaLocus:
    """Posterior do lócus dado o genótipo dos parentes e a situação clínica dos genitores inferidos.

    Todas as contas integram na distribuição de π (quadratura), porque π é a mesma para o genitor e para o
    descendente. `p_portador` é P(descendente porta | evidência) e `pen_media` é a penetrância média entre os
    descendentes portadores, de modo que `p_portador · pen_media` = P(porta e manifesta em algum momento | evidência).
    """

    def __init__(self, evidencia: EvidenciaLocus, prior, pen_fixa: float | None, dists: dict[str, DistribuicaoInicio]):
        self.ev = evidencia
        self.heranca = evidencia.heranca
        self.conjunta = np.asarray(evidencia.conjunta, float)
        self.prior, self.pen_fixa = prior, pen_fixa
        self.dists = dists  # G(t) de cada genitor (deslocada pelo sexo dele), para a situação clínica
        # G_sexo(idade) de cada genitor cujo fenótipo condiciona (None = sem condicionamento)
        self.g = {
            n: (float(dists[n].cdf(evidencia.lado(n).idade)) if evidencia.lado(n).condiciona else None) for n in LADOS
        }
        self.c = np.array([[prob_portador(dm, dp, self.heranca) for dp in range(3)] for dm in range(3)])
        self.cpt = np.array([[cpt_segregacao(dm, dp) for dp in range(3)] for dm in range(3)])  # (3, 3, 3)
        if pen_fixa is not None:
            self._nos, self._pesos = np.array([float(pen_fixa)]), np.array([1.0])
        else:
            self._nos, self._pesos = prior.quadratura()
        z, nc = self._z_nc(self._nos)
        self.verossimilhanca = float(np.sum(self._pesos * z))  # P(situação clínica dos genitores | genótipos)
        self.p_portador = float(np.sum(self._pesos * nc) / self.verossimilhanca)
        self.p_manifesta_sem_limite = float(np.sum(self._pesos * self._nos * nc) / self.verossimilhanca)
        media_prior = float(pen_fixa) if pen_fixa is not None else float(prior.media)
        self.pen_media = self.p_manifesta_sem_limite / self.p_portador if self.p_portador > 0 else media_prior
        self.pen_media_posterior = float(np.sum(self._pesos * self._nos * z) / self.verossimilhanca)
        self._grade = None

    def _ver(self, nome: str, d: int, pi):
        """Verossimilhança da situação clínica do genitor `nome` com dosagem d: 1 − π·G(idade) se porta, 1 se não."""
        if self.g[nome] is None or not _portador(d, self.heranca):
            return 1.0
        return 1.0 - pi * self.g[nome]

    def _z_nc(self, pi):
        """Z(π) = P(situações clínicas | π, genótipos) e N(π) = P(situações, descendente portador | π, genótipos)."""
        pi = np.asarray(pi, float)
        z, nc = np.zeros_like(pi), np.zeros_like(pi)
        for dm in range(3):
            lm = self._ver("mae", dm, pi)
            for dp in range(3):
                w = self.conjunta[dm, dp]
                if w == 0:
                    continue
                termo = w * lm * self._ver("pai", dp, pi)
                z = z + termo
                nc = nc + termo * self.c[dm, dp]
        return z, nc

    def q_portador(self, pen):
        """P(descendente portador | π, evidência), para as bandas por sorteio de π."""
        z, nc = self._z_nc(pen)
        return nc / np.clip(z, 1e-300, None)

    def cpt_descendente(self) -> np.ndarray:
        pi = self._nos
        acc = np.zeros(3)
        for dm in range(3):
            lm = self._ver("mae", dm, pi)
            for dp in range(3):
                w = self.conjunta[dm, dp]
                if w == 0:
                    continue
                peso = float(np.sum(self._pesos * w * lm * self._ver("pai", dp, pi)))
                acc += peso * self.cpt[dm, dp]
        return acc / acc.sum()

    def dosagem_genitor(self, nome: str, condicionada: bool = True) -> np.ndarray:
        """P(d_G) do genitor `nome`: só com os genótipos dos parentes ou também com a situação clínica dos genitores."""
        if not condicionada:
            return self.ev.marginal(nome)
        pi = self._nos
        mat = np.zeros((3, 3))
        for dm in range(3):
            lm = self._ver("mae", dm, pi)
            for dp in range(3):
                w = self.conjunta[dm, dp]
                if w:
                    mat[dm, dp] = float(np.sum(self._pesos * w * lm * self._ver("pai", dp, pi)))
        mat /= mat.sum()
        return mat.sum(axis=1) if nome == "mae" else mat.sum(axis=0)

    def _grade_posterior(self):
        """Grade fina de π com pesos a posteriori (∝ densidade a priori × Z(π)), para quantis."""
        if self._grade is None:
            if self.pen_fixa is not None:
                pi, w = np.array([float(self.pen_fixa)]), np.array([1.0])
            else:
                u = (np.arange(4000) + 0.5) / 4000
                pi = np.asarray(self.prior.ppf(u), float)
                w = self._z_nc(pi)[0]
            self._grade = (pi, w / w.sum())
        return self._grade

    @staticmethod
    def _quantis(valores, pesos, q) -> tuple:
        ordem = np.argsort(valores)
        v, acum = np.asarray(valores)[ordem], np.cumsum(np.asarray(pesos)[ordem])
        return tuple(float(v[min(int(np.searchsorted(acum, x)), len(v) - 1)]) for x in q)

    def quantis_penetrancia(self, q=(0.025, 0.975)) -> tuple:
        pi, w = self._grade_posterior()
        return self._quantis(pi, w, q)

    def quantis_manifesta_sem_limite(self, q=(0.025, 0.975)) -> tuple:
        """Quantis de P(portador | π)·π sob o posterior de π: banda da fração que manifesta em algum momento."""
        pi, w = self._grade_posterior()
        return self._quantis(self.q_portador(pi) * pi, w, q)


def anexar_inferencias(
    loci: list, vetor: pd.DataFrame, parametros: Parametros, distribuicoes: dict | None = None
) -> list:
    """Liga a cada lócus a `InferenciaLocus` da evidência guardada no vetor (`vetor.attrs["parentes"]`), usando a
    distribuição de penetrância do próprio lócus (a em uso ou a de um cenário de sensibilidade) e, para a situação
    clínica de cada genitor, a G(t) do gene deslocada pelo sexo dele (`distribuicoes` troca a G(t) do gene)."""
    evidencias = (vetor.attrs.get("parentes") or {}).get("evidencias") or {}
    if not evidencias:
        return loci
    out = []
    for l in loci:
        ev = evidencias.get(l.rotulo)
        if ev is None or not ev.lados_inferidos:
            out.append(l)
            continue
        g = parametros.genes[l.gene]
        base = (distribuicoes or {}).get(l.gene, g.inicio)
        dists = {n: base.deslocar(g.delta_sexo.get(SEXO_DO_LADO[n], 0.0)) for n in LADOS}
        inf = InferenciaLocus(ev, l.prior, l.pen_fixa, dists)
        out.append(replace(l, dosagem_mae=ev.mae.observado, dosagem_pai=ev.pai.observado, inferencia=inf))
    return out


# ---------------------------------------------------------------------------
# Leitura dos VCFs dos parentes e dosagens por pessoa
# ---------------------------------------------------------------------------
def dosagens_do_vcf(anotadas: pd.DataFrame, parametros: Parametros) -> dict[str, dict]:
    """Lóci de risco de uma pessoa a partir do VCF anotado: {chave: {"dosagem": 0/1/2 ou None, metadados...}}.

    `dosagem = None`: sítio de risco com genótipo não determinado (o lócus não pode ser avaliado). A expansão do
    C9orf72 não é lida do VCF (TCC 4.2.1): o laudo é a única fonte."""
    out: dict[str, dict] = {}

    def meta(v) -> dict:
        freq = pd.to_numeric(pd.Series([v.get("freq_alfa")]), errors="coerce").iloc[0]
        return {
            "gene": v.gene,
            "variante": v.nome_curto or genotipo._chave(v),
            "rs": v.rs_tabela or v.id,
            "tipo": v.tipo,
            "heranca": v.heranca if isinstance(v.heranca, str) else parametros.genes[v.gene].heranca,
            "estrelas": int(v.estrelas) if pd.notna(v.estrelas) else 0,
            "clnsig": v.clnsig,
            "observacao": genotipo._nota_regra(v),
            "freq": float(freq) if pd.notna(freq) and freq > 0 else None,
        }

    sel = anotadas[anotadas.aprovado & (anotadas.classe == "risco") & anotadas.gene.notna()]
    for _, v in sel.iterrows():
        k = genotipo._chave(v)
        if k == CHAVE_EXPANSAO:
            continue
        d = out.setdefault(k, {**meta(v), "dosagem": 0})
        if d["dosagem"] is not None:
            d["dosagem"] = min(2, d["dosagem"] + (int(v.dosagem) if pd.notna(v.dosagem) else 0))
    indet = anotadas[genotipo._sem_genotipo(anotadas) & (anotadas.classe == "risco") & anotadas.gene.notna()]
    for _, v in indet.iterrows():
        k = genotipo._chave(v)
        if k == CHAVE_EXPANSAO:
            continue
        out.setdefault(k, meta(v))["dosagem"] = None
    return out


def dosagem_do_laudo(valor, parametros: Parametros, tabela: pd.DataFrame) -> tuple[int, int | None]:
    """Laudo do C9orf72 de uma pessoa → (dosagem de alelos expandidos, maior contagem de repetições)."""
    limiar = {**anotacao.LIMIAR_PADRAO, **(parametros.limiar_repeticoes or {})}
    pat = anotacao.limiar_patogenico_repeticao(tabela, GENE_EXPANSAO, limiar)
    inter = int(limiar.get("intermediario", 24))
    alelos = [int(x) for x in (valor if isinstance(valor, (list, tuple)) else [valor])]
    expandidos = [a for a in alelos if anotacao.classe_por_repeticoes(a, pat, inter) == "risco"]
    return min(2, len(expandidos)), (max(alelos) if alelos else None)


@dataclass
class PessoaLida:
    rotulo: str
    lado: str | None  # "mae"/"pai" (parentes de um genitor) ou None (filho testado)
    papel: str  # "pai", "mae", "irmao" ou "filho"
    snv: dict | None  # dosagens do VCF por lócus; None = sem VCF
    laudo: tuple | None  # (dosagem, repetições) do laudo do C9orf72; None = sem laudo
    anotadas: pd.DataFrame | None = None
    arquivo: str | None = None


def ler_familia(familia: Familia, parametros: Parametros, tabela: pd.DataFrame, regioes=None) -> list[PessoaLida]:
    """Lê, filtra e anota o VCF de cada parente (mesma ingestão dos genitores) e interpreta os laudos."""
    regioes = ingestao.carregar_regioes() if regioes is None else regioes
    pessoas: list[PessoaLida] = []

    def ler(p: Parente, rotulo: str, lado: str | None, papel: str) -> PessoaLida:
        anot = snv = None
        if p.vcf:
            lido = ingestao.ler_vcf(p.vcf, regioes, parametros.filtro_qualidade, amostra=p.amostra)
            anot = anotacao.anotar(lido, tabela, parametros.limiar_repeticoes)
            snv = dosagens_do_vcf(anot, parametros)
        laudo = dosagem_do_laudo(p.laudo_c9orf72, parametros, tabela) if p.laudo_c9orf72 is not None else None
        return PessoaLida(rotulo, lado, papel, snv, laudo, anot, Path(str(p.vcf)).name if p.vcf else None)

    for nome in LADOS:
        lado = familia.lado(nome)
        if lado is None:
            continue
        n_irmaos = 0
        for papel, p in lado.parentes:
            rotulo = ROTULO_PARENTE[(nome, papel)]
            if papel == "irmao":
                n_irmaos += 1
                if len(lado.irmaos) > 1:
                    rotulo += f" {n_irmaos}"
            pessoas.append(ler(p, rotulo, nome, papel))
    for i, p in enumerate(familia.filhos_testados, 1):
        rotulo = "filho(a) já testado(a)" + (f" {i}" if len(familia.filhos_testados) > 1 else "")
        pessoas.append(ler(p, rotulo, None, "filho"))
    return pessoas


def perfil_com_parentes(perfil: pd.DataFrame, pessoas: list[PessoaLida]) -> pd.DataFrame:
    """Tabela 1 com as variantes aprovadas dos parentes, identificadas pelo parentesco na coluna `amostra`."""
    partes = [perfil]
    for p in pessoas:
        if p.anotadas is None:
            continue
        ap = p.anotadas.loc[p.anotadas.aprovado, [c for c in perfil.columns if c in p.anotadas.columns]].copy()
        if ap.empty:
            continue
        ap["amostra"] = p.rotulo
        ap.loc[ap.dosagem.fillna(0) == 0, "repeticoes"] = np.nan
        partes.append(ap.sort_values(["cromossomo", "posicao"]))
    if len(partes) == 1:
        return perfil
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning)
        return pd.concat(partes, ignore_index=True)


# ---------------------------------------------------------------------------
# Vetor genotípico da família
# ---------------------------------------------------------------------------
COLUNAS_EXTRA = ["genitor_inferido", "p_dosagem_mae", "p_dosagem_pai"]


def _fmt_dist(p) -> str:
    return "; ".join(f"{d}: {float(x):.4f}" for d, x in enumerate(p))


def vetor_familia(
    anotadas_mae: pd.DataFrame,
    anotadas_pai: pd.DataFrame,
    parametros: Parametros,
    laudo_c9orf72: dict | None,
    tabela: pd.DataFrame,
    familia: Familia,
    pessoas: list[PessoaLida],
    com_vcf: dict[str, bool],
) -> pd.DataFrame:
    """Vetor genotípico (Tabela 1b) quando há parentes: as mesmas linhas de `genotipo.vetor_dosagem` para os lóci em
    que os dois genitores foram testados e, onde um genitor é inferido, a dosagem dele vazia, P(portador) do
    descendente calculada com a evidência e a distribuição inferida em `p_dosagem_mae`/`p_dosagem_pai`.

    `com_vcf[lado]`: o genitor tem VCF próprio (ou foi assumido não portador com um VCF sem variantes). Um genitor sem
    VCF só é inferido quando algum parente dele (ou um filho) tem VCF; para o C9orf72 vale o laudo: genitor sem laudo
    é inferido quando algum parente dele tem laudo e continua indeterminado quando nenhum tem.
    A evidência de cada lócus fica em `vetor.attrs["parentes"]`, de onde `anexar_inferencias` a liga aos lóci.
    """
    laudo = {k: v for k, v in (laudo_c9orf72 or {}).items() if k in LADOS and v is not None}
    with warnings.catch_warnings():  # os avisos de laudo ausente são refeitos aqui, já com os parentes considerados
        warnings.simplefilter("ignore")
        base = genotipo.vetor_dosagem(anotadas_mae, anotadas_pai, parametros, laudo_c9orf72=laudo, tabela=tabela)
    proprios = {"mae": dosagens_do_vcf(anotadas_mae, parametros), "pai": dosagens_do_vcf(anotadas_pai, parametros)}
    dos_lado = {n: [p for p in pessoas if p.lado == n] for n in LADOS}
    filhos = [p for p in pessoas if p.papel == "filho"]
    inferivel_snv = {
        n: (not com_vcf.get(n, True))
        and (any(p.snv is not None for p in dos_lado[n]) or any(f.snv is not None for f in filhos))
        for n in LADOS
    }
    for n in LADOS:
        if not com_vcf.get(n, True) and not inferivel_snv[n]:
            raise ValueError(
                f"{ROTULO_GENITOR[n]} sem VCF e sem parente com VCF: informe o VCF do genitor, o de um parente dele "
                "(pai, mãe ou irmão) ou assuma o genitor como não portador"
            )
    linhas: list[dict] = []
    evidencias: dict[str, EvidenciaLocus] = {}
    suposicoes: list[str] = []
    descartes: list[str] = []

    def lado_snv(n: str, chave: str, freq: float | None) -> tuple[EvidenciaLado | None, str | None]:
        """Evidência do genitor `n` num lócus de variante curta; (None, motivo) quando há genótipo indeterminado."""
        lf = familia.lado(n)
        if com_vcf.get(n, True):
            d = proprios[n].get(chave, {"dosagem": 0})["dosagem"]
            return (EvidenciaLado(n, observado=d), None) if d is not None else (None, f"{ROTULO_GENITOR[n]}")
        avos, irmaos = [None, None], []
        for p in dos_lado[n]:
            if p.snv is None:
                continue
            d = p.snv.get(chave, {"dosagem": 0})["dosagem"]
            if d is None:
                return None, p.rotulo
            if p.papel == "irmao":
                irmaos.append(d)
            else:
                avos[0 if p.papel == "pai" else 1] = d
        modo = "limite"
        if freq and ((lf and lf.prior_avos == "hardy_weinberg") or (irmaos and avos == [None, None])):
            modo = "hardy_weinberg"
        return (
            EvidenciaLado(
                n,
                avos=tuple(avos),
                irmaos=tuple(irmaos),
                modo_prior=modo,
                freq=freq,
                situacao=lf.situacao if lf else "desconhecido",
                idade=lf.idade if lf else None,
            ),
            None,
        )

    # ---- lóci de variante curta: os do vetor padrão e os que só aparecem em parentes ou filhos
    chaves: dict[str, dict] = {}
    for fonte in [proprios["mae"], proprios["pai"]] + [p.snv for p in pessoas if p.snv is not None]:
        for k, d in fonte.items():
            atual = chaves.setdefault(k, dict(d))
            if not atual.get("freq") and d.get("freq"):
                atual["freq"] = d["freq"]
    base_por_rotulo = {(r.gene, r.variante): r for r in base.itertuples(index=False)}
    usados = set()
    for chave, m in chaves.items():
        b = base_por_rotulo.get((m["gene"], m["variante"]))
        if b is not None:
            usados.add((m["gene"], m["variante"]))
        if not any(inferivel_snv.values()):
            if b is not None:
                linhas.append(b._asdict())
            continue
        d = {
            "gene": m["gene"],
            "variante": m["variante"],
            "rs": m["rs"],
            "tipo": m["tipo"],
            "heranca": m["heranca"],
            "dosagem_mae": None,
            "dosagem_pai": None,
            "repeticoes_mae": None,
            "repeticoes_pai": None,
            "clnsig": m["clnsig"],
            "estrelas": m["estrelas"],
            "fonte": "vcf",
            "p_portador_exato": np.nan,
            "descartado": False,
            "observacao": (b.observacao if b is not None else m.get("observacao") or ""),
        }
        lados, indet = {}, []
        for n in LADOS:
            ev, quem = lado_snv(n, chave, m.get("freq"))
            if ev is None:
                indet.append(quem)
            lados[n] = ev
        filhos_d, ok = [], True
        for f in filhos:
            if f.snv is None:
                continue
            df_ = f.snv.get(chave, {"dosagem": 0})["dosagem"]
            if df_ is None:
                indet.append(f.rotulo)
            else:
                filhos_d.append(df_)
        if indet or (b is not None and bool(b.descartado)):
            quem = " e ".join(dict.fromkeys(indet)) or "genitor"
            msg = f"genótipo não determinado no VCF ({quem}); lócus descartado do cálculo, sem atribuir dosagem 0 (TCC 4.3)"
            d.update(descartado=True, observacao=(d["observacao"] + "; " if d["observacao"] else "") + msg)
            for n in LADOS:
                if lados[n] is not None and lados[n].observado is not None:
                    d[f"dosagem_{n}"] = lados[n].observado
            warnings.warn(f"{d['gene']} {d['variante']}: {msg}", stacklevel=2)
            descartes.append(f"{d['gene']} {d['variante']}")
            linhas.append(d)
            continue
        ev = EvidenciaLocus(m["heranca"], lados["mae"], lados["pai"], tuple(filhos_d)).resolver()
        _registrar(d, ev, evidencias, suposicoes, descartes, linhas, parametros)

    # lóci do vetor padrão que não vieram dos VCFs (o do C9orf72, que vem do laudo)
    c9_base = next((r for r in base.itertuples(index=False) if r.gene == GENE_EXPANSAO and r.tipo == "repeticao"), None)
    _locus_c9orf72(c9_base, laudo, familia, dos_lado, parametros, tabela, evidencias, suposicoes, descartes, linhas)

    cols = list(base.columns) + COLUNAS_EXTRA
    df = pd.DataFrame(linhas, columns=cols)
    df["descartado"] = df["descartado"].fillna(False).astype(bool)
    for c in COLUNAS_EXTRA:
        df[c] = df[c].fillna("")
    dup = (~df.descartado) & df.gene.where(~df.descartado).duplicated(keep=False)
    if dup.any():
        nota = "mais de um lócus de risco no gene, tratados como independentes"
        df.loc[dup & ~df.observacao.str.contains(nota, regex=False), "observacao"] = df.loc[
            dup & ~df.observacao.str.contains(nota, regex=False), "observacao"
        ].map(lambda o: (o + "; " if o else "") + nota)
    df = df.reset_index(drop=True)
    if base.attrs.get("c9orf72_intermediario"):  # a nota vem de `genotipo.vetor_dosagem` e segue para o relatório
        df.attrs["c9orf72_intermediario"] = base.attrs["c9orf72_intermediario"]
    df.attrs["parentes"] = {
        "evidencias": evidencias,
        "suposicoes": list(dict.fromkeys(suposicoes)),
        "descartes": descartes,
        "pessoas": pessoas,
        "familia": familia,
    }
    return df


def _descrever_prior(ev: EvidenciaLocus, n: str) -> list[str]:
    """Suposições usadas para os avós sem exame do genitor `n`, em texto para o relatório e os metadados."""
    lado = ev.lado(n)
    if not lado.inferido:
        return []
    nomes = [ROTULO_PARENTE[(n, "pai")], ROTULO_PARENTE[(n, "mae")]]
    sem = [nomes[i] for i in (0, 1) if lado.avos[i] is None]
    out = []
    if sem and lado.modo_prior == "hardy_weinberg":
        out.append(
            f"{' e '.join(sem)} sem exame: prior de Hardy-Weinberg com a frequência alélica da base de anotação "
            f"(f = {lado.freq:.3g})"
        )
    elif sem and ev.exige_variante.get(n):
        out.append(
            f"{' e '.join(sem)} sem exame e sem frequência alélica na base: os genótipos dos parentes exigem a variante "
            "nessa família, e vale a configuração mínima compatível (um dos avós heterozigoto e o outro não portador, "
            "limite de alelo raro da prior de Hardy-Weinberg)"
        )
    elif sem:
        out.append(f"{' e '.join(sem)} sem exame: suposto(s) não portador(es)")
    if lado.irmaos or ev.filhos:
        out.append(SUPOSICAO_HERDADA)
    if lado.situacao == "afetado":
        out.append(f"{ROTULO_GENITOR[n]} afetado: {LIMITE_INFERIOR_AFETADO}")
    return out


def _registrar(d, ev, evidencias, suposicoes, descartes, linhas, parametros) -> None:
    """Fecha a linha de um lócus com evidência de parentes: incompatível → descartado; sem portador possível → fora."""
    if not ev.compativel:
        d.update(
            descartado=True,
            observacao=(d["observacao"] + "; " if d["observacao"] else "")
            + "genótipos dos parentes incompatíveis com a segregação mendeliana (variante suposta herdada); lócus "
            "descartado do cálculo",
        )
        warnings.warn(
            f"{d['gene']} {d['variante']}: genótipos dos parentes incompatíveis com a segregação mendeliana; lócus "
            "descartado",
            stacklevel=3,
        )
        descartes.append(f"{d['gene']} {d['variante']}")
        linhas.append(d)
        return
    inferidos = ev.lados_inferidos
    for n in LADOS:
        lado = ev.lado(n)
        if lado.observado is not None:
            d[f"dosagem_{n}"] = int(lado.observado)
        else:
            d[f"p_dosagem_{n}"] = _fmt_dist(ev.marginal(n))
    if not inferidos:  # os dois genitores testados neste lócus: linha padrão
        d["p_portador_exato"] = prob_portador(d["dosagem_mae"], d["dosagem_pai"], d["heranca"])
        if d["dosagem_mae"] + d["dosagem_pai"] > 0:
            linhas.append(d)
        return
    g = parametros.genes[d["gene"]]
    inf = InferenciaLocus(ev, g.penetrancia, None, {n: g.distribuicao_sexo(SEXO_DO_LADO[n]) for n in LADOS})
    if inf.p_portador <= 0:  # nenhum estado compatível transmite a variante: não é lócus informativo
        return
    d["p_portador_exato"] = inf.p_portador
    d["genitor_inferido"] = " e ".join(ROTULO_GENITOR[n] for n in inferidos)
    nota = "; ".join(
        f"dosagem d{'a' if n == 'mae' else 'o'} {ROTULO_GENITOR[n]} inferida por parentes" for n in inferidos
    )
    d["observacao"] = (d["observacao"] + "; " if d["observacao"] else "") + nota
    rotulo = f"{d['gene']} {d['variante']}"
    evidencias[rotulo] = ev
    for n in inferidos:
        suposicoes.extend(f"{rotulo}: {s}" for s in _descrever_prior(ev, n))
    linhas.append(d)


def _locus_c9orf72(c9_base, laudo, familia, dos_lado, parametros, tabela, evidencias, suposicoes, descartes, linhas):
    """Lócus do C9orf72 com parentes: o laudo é a única fonte. Genitor com laudo é observado; sem laudo, é inferido
    quando algum parente dele tem laudo e fica indeterminado (lócus descartado) quando nenhum tem."""
    sem_laudo = [n for n in LADOS if n not in laudo]
    inferivel = {n: any(p.laudo is not None for p in dos_lado[n]) for n in sem_laudo}
    if not sem_laudo or not any(inferivel.values()):
        if c9_base is not None:  # comportamento padrão: linha do laudo dos dois, ou descartada por falta de laudo
            linhas.append(c9_base._asdict())
            if bool(c9_base.descartado):
                warnings.warn(f"{GENE_EXPANSAO}: {c9_base.observacao}", stacklevel=3)
        return
    d = genotipo._locus_laudo_c9orf72(laudo, parametros, tabela, sempre=True)
    d.update(descartado=False, p_portador_exato=np.nan)
    faltam = [n for n in sem_laudo if not inferivel[n]]
    if faltam:  # um genitor sem laudo e sem parente com laudo: continua indeterminado
        for n in sem_laudo:
            d[f"dosagem_{n}"], d[f"repeticoes_{n}"] = None, None
        quem = " e ".join(genotipo.ARTIGO_LADO[n] for n in faltam)
        msg = f"laudo do C9orf72 não informado para {quem} nem para parentes: lócus indeterminado (TCC 4.3)"
        d.update(descartado=True, observacao=(d["observacao"] + "; " if d["observacao"] else "") + msg)
        warnings.warn(f"{GENE_EXPANSAO}: {msg}", stacklevel=3)
        descartes.append(f"{d['gene']} {d['variante']}")
        linhas.append(d)
        return
    lados = {}
    for n in LADOS:
        lf = familia.lado(n)
        if n in laudo:
            lados[n] = EvidenciaLado(n, observado=int(d[f"dosagem_{n}"]))
            continue
        d[f"dosagem_{n}"], d[f"repeticoes_{n}"] = None, None
        avos, irmaos = [None, None], []
        for p in dos_lado[n]:
            if p.laudo is None:
                continue
            if p.papel == "irmao":
                irmaos.append(p.laudo[0])
            else:
                avos[0 if p.papel == "pai" else 1] = p.laudo[0]
        lados[n] = EvidenciaLado(
            n,
            avos=tuple(avos),
            irmaos=tuple(irmaos),
            modo_prior="limite",  # a expansão não tem frequência alélica na base de anotação
            situacao=lf.situacao if lf else "desconhecido",
            idade=lf.idade if lf else None,
        )
    ev = EvidenciaLocus(d["heranca"], lados["mae"], lados["pai"], ()).resolver()
    _registrar(d, ev, evidencias, suposicoes, descartes, linhas, parametros)


# ---------------------------------------------------------------------------
# Monte Carlo com genitor inferido (NumPy e PyMC)
# ---------------------------------------------------------------------------
def _lados_condicionados(loci) -> list[str]:
    return [n for n in LADOS if any(l.inferencia is not None and l.inferencia.g[n] is not None for l in loci)]


def _montar_resultado(motor, loci, n, seed, partes, sorteados, t0):
    from .monte_carlo import ResultadoSimulacao

    junta = {k: np.concatenate([p[k] for p in partes])[:n] for k in partes[0]}
    return ResultadoSimulacao(
        motor,
        n,
        seed,
        None,
        loci,
        junta["alelo_mae"],
        junta["alelo_pai"],
        junta["dose"],
        junta["portador"],
        junta["pen"],
        junta["manifesta"],
        junta["idade"],
        tempo_s=time.perf_counter() - t0,
        dose_mae=junta["dose_mae"],
        dose_pai=junta["dose_pai"],
        sorteados=sorteados,
    )


def _lote_numpy(loci, m: int, rng: np.random.Generator) -> tuple[dict, np.ndarray]:
    """Um lote de m sorteios do DAG de três gerações e a máscara dos compatíveis com a situação dos genitores."""
    L = len(loci)
    dose_mae, dose_pai = np.empty((m, L), int), np.empty((m, L), int)
    pen, idade = np.empty((m, L)), np.full((m, L), np.nan)
    adoeceu = np.zeros(m, bool)  # algum genitor condicionado manifestou até a idade informada
    for j, l in enumerate(loci):
        inf = l.inferencia
        if inf is None:
            dose_mae[:, j], dose_pai[:, j] = l.dosagem_mae, l.dosagem_pai
        else:
            estado = rng.choice(9, size=m, p=inf.conjunta.ravel())
            dose_mae[:, j], dose_pai[:, j] = estado // 3, estado % 3
        pen[:, j] = l.pen_fixa if l.pen_fixa is not None else l.prior.amostrar(rng, m)
        if inf is not None:
            for nome, dose in (("mae", dose_mae[:, j]), ("pai", dose_pai[:, j])):
                lado = inf.ev.lado(nome)
                if not lado.condiciona:
                    continue
                porta = (dose == 2) if l.recessivo else (dose >= 1)
                manifestou = rng.random(m) < porta * pen[:, j]  # mesma π do descendente: compartilhada
                inicio = inf.dists[nome].amostrar(rng, m)
                adoeceu |= manifestou & (inicio <= lado.idade)
    alelo_mae = rng.random((m, L)) < dose_mae / 2
    alelo_pai = rng.random((m, L)) < dose_pai / 2
    dose = alelo_mae.astype(int) + alelo_pai.astype(int)
    rec = np.array([l.recessivo for l in loci])
    portador = np.where(rec, dose == 2, dose >= 1)
    manifesta = rng.random((m, L)) < portador * pen
    for j, l in enumerate(loci):
        k = int(manifesta[:, j].sum())
        if k:
            idade[manifesta[:, j], j] = l.dist.amostrar(rng, k)
    lote = {
        "alelo_mae": alelo_mae,
        "alelo_pai": alelo_pai,
        "dose": dose,
        "portador": portador,
        "pen": pen,
        "manifesta": manifesta,
        "idade": idade,
        "dose_mae": dose_mae,
        "dose_pai": dose_pai,
    }
    return lote, ~adoeceu


def _sorteios_ate_n(mascaras: list, n: int) -> int:
    """Quantos sorteios foram precisos para chegar ao n-ésimo aceito (os que sobram no último lote não contam)."""
    return int(np.flatnonzero(np.concatenate(mascaras))[n - 1]) + 1


def _taxa_aceitacao(loci) -> float:
    """P(situação clínica dos genitores | genótipos), produto sobre os lóci: taxa esperada de sorteios aceitos."""
    taxa = 1.0
    for l in loci:
        if l.inferencia is not None:
            taxa *= l.inferencia.verossimilhanca
    return max(taxa, 1e-3)


def simular_numpy_parentes(loci: list, n: int = 10_000, seed: int = 42):
    """Monte Carlo por rejeição com genitor inferido por parentes. No mesmo sorteio: π de cada gene (uma vez, para
    toda a família), as dosagens latentes dos genitores (dada a evidência de genótipo), o fenótipo de cada genitor
    condicionado até a idade dele, a dosagem do descendente e o resto como no núcleo. Sorteios em que um genitor
    "vivo sem sintomas" ou "falecido sem ELA" teria manifestado são descartados; sorteia-se em lotes até completar N.
    """
    t0 = time.perf_counter()
    rng = np.random.default_rng(seed)
    partes, mascaras, aceitos = [], [], 0
    taxa = _taxa_aceitacao(loci)
    while aceitos < n:
        m = int(math.ceil((n - aceitos) / taxa * 1.1)) + 16
        lote, ok = _lote_numpy(loci, m, rng)
        partes.append({k: v[ok] for k, v in lote.items()})
        mascaras.append(ok)
        aceitos += int(ok.sum())
    return _montar_resultado("numpy", loci, n, seed, partes, _sorteios_ate_n(mascaras, n), t0)


def construir_modelo_parentes(loci: list):
    """DAG de três gerações em PyMC: dosagens dos genitores (latentes onde inferidas), fenótipo de cada genitor
    condicionado, alelos transmitidos, descendente, penetrância compartilhada e idade de início."""
    import pymc as pm
    import pytensor.tensor as pt

    from .rede_bayesiana import no_idade, no_penetrancia

    lados = _lados_condicionados(loci)
    with pm.Model(coords={"locus": [l.rotulo for l in loci]}) as modelo:
        recessivo = pm.Data("recessivo", np.array([l.recessivo for l in loci], dtype=float), dims="locus")
        dm, dp, pens, idades = [], [], [], []
        idade_gen = {n: [] for n in lados}
        for i, l in enumerate(loci):
            inf = l.inferencia
            if inf is None:
                dm.append(pt.constant(float(l.dosagem_mae)))
                dp.append(pt.constant(float(l.dosagem_pai)))
            else:
                estado = pm.Categorical(f"dosagens_parentais_{i}", p=inf.conjunta.ravel())
                dm.append(pt.cast(estado // 3, "float64"))
                dp.append(pt.cast(estado % 3, "float64"))
            pens.append(no_penetrancia(f"penetrancia_{i}", l))
            idades.append(no_idade(f"idade_latente_{i}", l))
            for n in lados:  # idade de início latente do genitor, na G(t) do sexo dele
                d = inf.dists[n] if inf is not None else l.dist
                idade_gen[n].append(no_idade(f"idade_latente_{n}_{i}", replace(l, dist=d)))
        dose_m = pm.Deterministic("dose_materna", pt.stack(dm), dims="locus")
        dose_p = pm.Deterministic("dose_paterna", pt.stack(dp), dims="locus")
        pen = pm.Deterministic("penetrancia", pt.stack(pens), dims="locus")
        alelo_m = pm.Bernoulli("alelo_materno", p=dose_m / 2.0, dims="locus")
        alelo_p = pm.Bernoulli("alelo_paterno", p=dose_p / 2.0, dims="locus")
        dose = pm.Deterministic("dose_descendente", alelo_m + alelo_p, dims="locus")
        portador = pm.Deterministic(
            "portador", pt.switch(pt.eq(recessivo, 1.0), pt.eq(dose, 2), pt.ge(dose, 1)), dims="locus"
        )
        pm.Bernoulli("manifesta", p=portador * pen, dims="locus")
        pm.Deterministic("idade_inicio", pt.stack(idades), dims="locus")
        for n in lados:
            dose_g = dose_m if n == "mae" else dose_p
            porta_g = pt.switch(pt.eq(recessivo, 1.0), pt.eq(dose_g, 2), pt.ge(dose_g, 1))
            pm.Bernoulli(f"manifesta_{n}", p=porta_g * pen, dims="locus")  # mesma π: compartilhada pela família
            pm.Deterministic(f"idade_inicio_{n}", pt.stack(idade_gen[n]), dims="locus")
    return modelo


def simular_pymc_parentes(loci: list, n: int = 10_000, seed: int = 42):
    """Mesma semântica de `simular_numpy_parentes`, com a amostragem preditiva a priori do DAG em PyMC seguida da
    rejeição dos sorteios incompatíveis com a situação clínica dos genitores."""
    import pymc as pm

    t0 = time.perf_counter()
    lados = _lados_condicionados(loci)
    modelo = construir_modelo_parentes(loci)
    nomes = ["alelo_materno", "alelo_paterno", "dose_descendente", "portador", "penetrancia", "manifesta"]
    nomes += ["idade_inicio", "dose_materna", "dose_paterna"]
    for nome in lados:
        nomes += [f"manifesta_{nome}", f"idade_inicio_{nome}"]
    idades_gen = {
        nome: np.array(
            [
                (
                    l.inferencia.ev.lado(nome).idade
                    if l.inferencia is not None and l.inferencia.g[nome] is not None
                    else -1.0
                )
                for l in loci
            ]
        )
        for nome in lados
    }
    partes, mascaras, aceitos, rodada = [], [], 0, 0
    taxa = _taxa_aceitacao(loci)
    while aceitos < n:
        m = int(math.ceil((n - aceitos) / taxa * 1.1)) + 16
        # primeira rodada com a semente da execução; as seguintes (reposição dos rejeitados) com sementes derivadas
        semente = int(seed) if rodada == 0 else int(np.random.SeedSequence([int(seed), rodada]).generate_state(1)[0])
        with modelo:
            idata = pm.sample_prior_predictive(draws=m, random_seed=semente, var_names=nomes)
        pr = idata.prior
        v = lambda nome: np.asarray(pr[nome].values[0])  # noqa: E731  (cadeia única)
        ok = np.ones(m, bool)
        for nome in lados:  # o genitor não pode ter manifestado até a idade informada (só nos lóci em que é inferido)
            adoeceu = v(f"manifesta_{nome}").astype(bool) & (v(f"idade_inicio_{nome}") <= idades_gen[nome][None, :])
            ok &= ~adoeceu.any(axis=1)
        manifesta = v("manifesta").astype(bool)
        partes.append(
            {
                "alelo_mae": v("alelo_materno").astype(bool)[ok],
                "alelo_pai": v("alelo_paterno").astype(bool)[ok],
                "dose": v("dose_descendente").astype(int)[ok],
                "portador": v("portador").astype(bool)[ok],
                "pen": v("penetrancia").astype(float)[ok],
                "manifesta": manifesta[ok],
                "idade": np.where(manifesta, v("idade_inicio"), np.nan)[ok],
                "dose_mae": v("dose_materna").astype(int)[ok],
                "dose_pai": v("dose_paterna").astype(int)[ok],
            }
        )
        mascaras.append(ok)
        aceitos += int(ok.sum())
        rodada += 1
    return _montar_resultado("pymc", loci, n, seed, partes, _sorteios_ate_n(mascaras, n), t0)


# ---------------------------------------------------------------------------
# Relatório: Tabela 1d, texto e metadados
# ---------------------------------------------------------------------------
def tabela_parentes(vetor: pd.DataFrame, loci: list) -> pd.DataFrame:
    """Tabela 1d: por lócus com genitor inferido, os parentes considerados e a dosagem de cada um, e a distribuição
    inferida da dosagem do genitor antes (só genótipos) e depois do condicionamento pela situação clínica."""
    info = vetor.attrs.get("parentes") or {}
    pessoas, evidencias = info.get("pessoas") or [], info.get("evidencias") or {}
    por_rotulo = {l.rotulo: l for l in loci}
    linhas = []
    for rotulo, ev in evidencias.items():
        l = por_rotulo.get(rotulo)
        if l is None or l.inferencia is None:
            continue
        inf = l.inferencia
        for n in ev.lados_inferidos:
            lado = ev.lado(n)
            nomes = [ROTULO_PARENTE[(n, "pai")], ROTULO_PARENTE[(n, "mae")]]
            partes = [f"{nomes[i]}: {lado.avos[i] if lado.avos[i] is not None else 'sem exame'}" for i in (0, 1)]
            partes += [f"{ROTULO_PARENTE[(n, 'irmao')]}: {d}" for d in lado.irmaos]
            partes += [f"filho(a) já testado(a): {d}" for d in ev.filhos]
            outro = ev.lado("pai" if n == "mae" else "mae")
            partes.append(
                f"outro genitor ({ROTULO_GENITOR[outro.lado]}): "
                + (str(outro.observado) if outro.observado is not None else "também inferido")
            )
            antes, depois = inf.dosagem_genitor(n, False), inf.dosagem_genitor(n, True)
            port = lambda p: float(p[2] if ev.heranca == "recessiva" else p[1] + p[2])  # noqa: E731
            linhas.append(
                {
                    "variante": rotulo,
                    "genitor_inferido": ROTULO_GENITOR[n],
                    "parentes_e_dosagens": "; ".join(partes),
                    "prior_dos_avos_sem_exame": (
                        f"Hardy-Weinberg (f = {lado.freq:.3g})"
                        if lado.modo_prior == "hardy_weinberg"
                        else (
                            "configuração mínima (alelo raro)" if ev.exige_variante.get(n) else "suposto não portador"
                        )
                    ),
                    "situacao_clinica": ROTULO_SITUACAO[lado.situacao]
                    + (f" aos {lado.idade:.0f} anos" if lado.idade is not None and lado.condiciona else ""),
                    "p_dosagem_0_genotipos": float(antes[0]),
                    "p_dosagem_1_genotipos": float(antes[1]),
                    "p_dosagem_2_genotipos": float(antes[2]),
                    "p_genitor_portador_genotipos": port(antes),
                    "p_dosagem_0_condicionada": float(depois[0]),
                    "p_dosagem_1_condicionada": float(depois[1]),
                    "p_dosagem_2_condicionada": float(depois[2]),
                    "p_genitor_portador_condicionada": port(depois),
                    "penetrancia_media_a_priori": float(l.prior.media) if l.pen_fixa is None else float(l.pen_fixa),
                    "penetrancia_media_a_posteriori": inf.pen_media_posterior,
                    "p_descendente_portador": inf.p_portador,
                }
            )
    _ = pessoas
    return pd.DataFrame(linhas)


def resumo_metadados(vetor: pd.DataFrame, loci: list) -> dict | None:
    """O que vai para `metadados.json`: parentes lidos, situação de cada genitor inferido, suposições e, por lócus,
    a distribuição da dosagem do genitor antes e depois do condicionamento."""
    info = vetor.attrs.get("parentes")
    if not info:
        return None
    familia: Familia = info["familia"]
    tab = tabela_parentes(vetor, loci)
    return {
        "genitores": {
            n: {
                "situacao": familia.lado(n).situacao,
                "idade": familia.lado(n).idade,
                "prior_avos": familia.lado(n).prior_avos,
                "limite_inferior": familia.lado(n).situacao == "afetado",
            }
            for n in LADOS
            if familia.lado(n) is not None
        },
        "pessoas": [
            {
                "parente": p.rotulo,
                "vcf": p.arquivo,
                "laudo_c9orf72": (p.laudo[1] if p.laudo else None),
                "loci_de_risco": (
                    {f"{d['gene']} {d['variante']}": d["dosagem"] for d in p.snv.values()}
                    if p.snv is not None
                    else None
                ),
            }
            for p in info["pessoas"]
        ],
        "suposicoes": info["suposicoes"],
        "loci_inferidos": tab.to_dict(orient="records"),
        "penetrancia_compartilhada": True,
    }


def texto_relatorio(vetor: pd.DataFrame, loci: list) -> str:
    """Seção "Genitor inferido por parentes" do relatório."""
    info = vetor.attrs.get("parentes") or {}
    familia: Familia | None = info.get("familia")
    if familia is None:
        return ""
    tab = tabela_parentes(vetor, loci)
    partes = [
        "A dosagem de um genitor sem exame não é observada: é inferida pelos genótipos de parentes (tabela de "
        "segregação do núcleo) e condicionada à situação clínica do próprio genitor. A penetrância π de cada gene é "
        "sorteada uma vez e vale para toda a família; por isso um genitor que chegou a certa idade sem sintomas torna "
        "menos prováveis a variante nele e os valores altos de π."
    ]
    lidas = "; ".join(
        f"{p.rotulo}"
        + (f" (VCF `{p.arquivo}`" if p.arquivo else " (sem VCF")
        + (f", laudo do C9orf72: {p.laudo[1]} repetições)" if p.laudo else ", sem laudo do C9orf72)")
        for p in info.get("pessoas") or []
    )
    if lidas:
        partes.append(f"Parentes considerados: {lidas}.")
    for n in LADOS:
        lado = familia.lado(n)
        if lado is None:
            continue
        txt = f"Situação clínica d{'a' if n == 'mae' else 'o'} {ROTULO_GENITOR[n]}: {ROTULO_SITUACAO[lado.situacao]}"
        if lado.condiciona:
            txt += f" aos {lado.idade:.0f} anos (condiciona a dosagem e a penetrância)"
        elif lado.situacao == "afetado":
            txt += f" ({LIMITE_INFERIOR_AFETADO})"
        else:
            txt += " (sem condicionamento pelo fenótipo)"
        partes.append(txt + ".")
    for r in tab.itertuples(index=False):
        partes.append(
            f"**{r.variante}**, {r.genitor_inferido} inferid{'a' if r.genitor_inferido == 'mãe' else 'o'}: "
            f"P(genitor portador) = {100 * r.p_genitor_portador_genotipos:.1f}% só com os genótipos e "
            f"{100 * r.p_genitor_portador_condicionada:.1f}% com a situação clínica; penetrância média do gene de "
            f"{100 * r.penetrancia_media_a_priori:.1f}% a priori para {100 * r.penetrancia_media_a_posteriori:.1f}% a "
            f"posteriori; P(descendente portador) = {100 * r.p_descendente_portador:.2f}%."
        )
    sup = info.get("suposicoes") or []
    if sup:
        partes.append("Suposições usadas: " + "; ".join(sup) + ".")
    desc = info.get("descartes") or []
    if desc:
        partes.append("Lóci que a evidência dos parentes não permitiu avaliar: " + "; ".join(desc) + ".")
    return " ".join(partes)
