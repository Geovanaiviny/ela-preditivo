"""Cenários familiares sintéticos e gerador de VCF 4.2 (TCC, seções 3.4, 4.2.1 e 4.5).

Os dados são inteiramente sintéticos: as variantes de risco vêm da tabela curada (coordenadas públicas
do dbSNP/ClinVar), mas os genótipos, profundidades e qualidades são gerados por seed. Cada arquivo reproduz a
estrutura do Quadro 2 do TCC (CHROM, POS, ID, REF, ALT, QUAL, FILTER, INFO com AC/AN/DB, FORMAT GT:DP:GQ) e inclui
"ruído" (variante benigna, variante não anotada, variante fora dos genes-alvo, registro de baixa qualidade e
registro multialélico) para exercitar os filtros e a anotação.

A expansão do C9orf72 não aparece nos VCFs: conforme o TCC 4.2.1, ela entra como parâmetro do laudo laboratorial
(`Cenario.laudo_c9orf72`), porque o fluxo de variantes curtas não a detecta. `c9orf72_expansao()` continua
disponível para testar o caminho secundário (VCF no estilo ExpansionHunter).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__, anotacao
from .exato import prob_portador

ORDEM_CONTIGS = ["1", "9", "16", "17", "21"]
# Comprimentos GRCh38 (NCBI GRCh38.p14), declarados no cabeçalho para a conferência de montagem
COMPRIMENTOS_GRCH38 = {"1": 248956422, "9": 138394717, "16": 90338345, "17": 83257441, "21": 46709983}


@dataclass(frozen=True)
class VarianteSintetica:
    gene: str
    rs: str | None
    cromossomo: str
    posicao: int
    ref: str
    alt: str
    dosagem: int = 1
    repeticoes: int | None = None
    rotulo: str = ""
    baixa_qualidade: bool = False

    def com_dosagem(self, dosagem: int) -> "VarianteSintetica":
        return VarianteSintetica(self.gene, self.rs, self.cromossomo, self.posicao, self.ref, self.alt,
                                 dosagem, self.repeticoes, self.rotulo, self.baixa_qualidade)


# Variantes de risco (tabela curada, coordenadas GRCh38 conferidas em 2026-10-24)
SOD1_A5V = VarianteSintetica("SOD1", "rs121912442", "21", 31659783, "C", "T", rotulo="SOD1 p.Ala5Val (A4V)")
SOD1_D91A = VarianteSintetica("SOD1", "rs80265967", "21", 31667290, "A", "C", rotulo="SOD1 p.Asp91Ala (D90A), recessiva")
TARDBP_M337V = VarianteSintetica("TARDBP", "rs80356730", "1", 11022418, "A", "G", rotulo="TARDBP p.Met337Val")
FUS_R521C = VarianteSintetica("FUS", "rs121909668", "16", 31191418, "C", "T", rotulo="FUS p.Arg521Cys")


def c9orf72_expansao(repeticoes: int = 45, dosagem: int = 1) -> VarianteSintetica:
    return VarianteSintetica("C9orf72", None, "9", 27573529, "GGGGCC", f"<STR{repeticoes}>", dosagem,
                             repeticoes, rotulo=f"C9orf72 expansão GGGGCC ({repeticoes} repetições)")


# Ruído presente em todos os arquivos
RUIDO = [
    VarianteSintetica("SOD1", "rs17883296", "21", 31659509, "G", "T", rotulo="SOD1 rs17883296 (provavelmente benigna; exemplo do TCC)"),
    VarianteSintetica("FUS", None, "16", 31185000, "A", "G", rotulo="FUS intrônica não anotada"),
    VarianteSintetica("TP53", None, "17", 7675088, "C", "T", rotulo="fora dos genes-alvo (TP53)"),
    VarianteSintetica("SOD1", None, "21", 31663000, "T", "C", rotulo="SOD1 baixa qualidade (DP=4, GQ=10, LowQual)", baixa_qualidade=True),
    VarianteSintetica("TARDBP", None, "1", 11020000, "G", "A,T", dosagem=2, rotulo="TARDBP multialélica (GT 0/2)"),
]


@dataclass
class Cenario:
    numero: int
    nome: str
    descricao: str
    pai: list[VarianteSintetica]
    mae: list[VarianteSintetica]
    herancas: dict[str, str] = field(default_factory=dict)
    laudo_c9orf72: dict[str, int] = field(default_factory=dict)   # {"mae": repetições, "pai": repetições} do laudo laboratorial

    @property
    def esperado(self) -> pd.DataFrame:
        """Dosagens parentais e P(portador) exatas por lócus de risco, para os testes de aderência."""
        loci: dict[str, dict] = {}
        for lado, lista in (("mae", self.mae), ("pai", self.pai)):
            for v in lista:
                chave = v.rotulo
                loci.setdefault(chave, {"gene": v.gene, "variante": v.rotulo, "dosagem_mae": 0, "dosagem_pai": 0})
                loci[chave][f"dosagem_{lado}"] = v.dosagem
        if self.laudo_c9orf72:
            pat = anotacao.limiar_patogenico_repeticao(anotacao.carregar_tabela_curada(), "C9orf72")
            d = {"gene": "C9orf72", "variante": "C9orf72 expansão GGGGCC (laudo)", "dosagem_mae": 0, "dosagem_pai": 0}
            for lado, n in self.laudo_c9orf72.items():
                d[f"dosagem_{lado}"] = int(anotacao.classe_por_repeticoes(n, pat) == "risco")
            if d["dosagem_mae"] + d["dosagem_pai"] > 0:
                loci[d["variante"]] = d
        linhas = []
        for d in loci.values():
            heranca = self.herancas.get(d["gene"], "dominante")
            d["heranca"] = heranca
            d["p_portador_exato"] = prob_portador(d["dosagem_mae"], d["dosagem_pai"], heranca)
            linhas.append(d)
        return pd.DataFrame(linhas)


CENARIOS: list[Cenario] = [
    Cenario(1, "pai_het_SOD1_A5V", "Pai heterozigoto SOD1 p.Ala5Val (alta penetrância) × mãe selvagem",
            pai=[SOD1_A5V], mae=[]),
    Cenario(2, "mae_C9orf72_expansao", "Mãe com expansão de hexanucleotídeos no C9orf72 (45 repetições, laudo) × pai selvagem",
            pai=[], mae=[], laudo_c9orf72={"mae": 45}),
    Cenario(3, "pai_SOD1_mae_C9orf72", "Pai heterozigoto SOD1 p.Ala5Val × mãe com expansão C9orf72 (45 repetições, laudo; exemplo literal do TCC, 4.5)",
            pai=[SOD1_A5V], mae=[], laudo_c9orf72={"mae": 45}),
    Cenario(4, "SOD1_D91A_recessiva", "Ambos os pais heterozigotos para SOD1 p.Asp91Ala (herança recessiva)",
            pai=[SOD1_D91A], mae=[SOD1_D91A], herancas={"SOD1": "recessiva"}),
    Cenario(5, "pai_TARDBP_mae_FUS", "Pai heterozigoto TARDBP p.Met337Val × mãe heterozigota FUS p.Arg521Cys",
            pai=[TARDBP_M337V], mae=[FUS_R521C]),
]


def cenario_por_numero(numero: int) -> Cenario:
    for c in CENARIOS:
        if c.numero == numero:
            return c
    raise KeyError(f"cenário {numero} não existe (1 a {len(CENARIOS)})")


# ---------------------------------------------------------------------------
# Escrita de VCF 4.2
# ---------------------------------------------------------------------------
def _gt(dosagem: int, alt: str) -> str:
    if "," in alt:           # multialélico: dosagem indica o índice do ALT portado (0/2)
        return f"0/{dosagem}"
    return {0: "0/0", 1: "0/1", 2: "1/1"}[dosagem]


def _cabecalho(amostra: str, descricao: str, contagens_str: set[int]) -> list[str]:
    hoje = _dt.date.today().strftime("%Y%m%d")
    linhas = [
        "##fileformat=VCFv4.2",
        f"##fileDate={hoje}",
        f"##source=ela_preditivo v{__version__} (DADOS SINTETICOS: {descricao})",
        "##reference=GRCh38",
    ]
    linhas += [f"##contig=<ID=chr{c},length={COMPRIMENTOS_GRCH38[c]},assembly=GRCh38>" for c in ORDEM_CONTIGS]
    linhas += [
        '##INFO=<ID=AC,Number=A,Type=Integer,Description="Contagem do alelo alternativo nos genotipos">',
        '##INFO=<ID=AN,Number=1,Type=Integer,Description="Total de alelos nos genotipos">',
        '##INFO=<ID=DB,Number=0,Type=Flag,Description="Variante presente no dbSNP">',
        '##INFO=<ID=END,Number=1,Type=Integer,Description="Fim do intervalo da repeticao">',
        '##INFO=<ID=RU,Number=1,Type=String,Description="Unidade de repeticao">',
        '##INFO=<ID=REPID,Number=1,Type=String,Description="Identificador do locus de repeticao">',
        '##INFO=<ID=SVTYPE,Number=1,Type=String,Description="Tipo de variante estrutural">',
        '##INFO=<ID=SINTETICO,Number=0,Type=Flag,Description="Registro sintetico gerado por ela_preditivo">',
        '##FILTER=<ID=LowQual,Description="Qualidade de chamada baixa">',
        '##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotipo">',
        '##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Profundidade de leitura">',
        '##FORMAT=<ID=GQ,Number=1,Type=Integer,Description="Qualidade do genotipo">',
        '##FORMAT=<ID=REPCN,Number=1,Type=String,Description="Numero de repeticoes por alelo (ordem do GT)">',
    ]
    linhas += [f'##ALT=<ID=STR{n},Description="Expansao de repeticao curta em tandem com {n} copias">' for n in sorted(contagens_str)]
    linhas.append("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t" + amostra)
    return linhas


def escrever_vcf(caminho: str | Path, amostra: str, variantes: list[VarianteSintetica], rng: np.random.Generator,
                 descricao: str = "", incluir_ruido: bool = True) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    todas = list(variantes) + (list(RUIDO) if incluir_ruido else [])
    contagens_str = {v.repeticoes for v in todas if v.repeticoes}
    registros = []
    for v in todas:
        e_str = v.alt.startswith("<STR")
        if v.baixa_qualidade:
            qual, filtro, dp, gq = 8.3, "LowQual", 4, 10
        else:
            qual, filtro = round(float(rng.uniform(60, 500)), 1), "PASS"
            dp, gq = int(rng.integers(25, 61)), int(rng.integers(60, 100))
        gt = _gt(v.dosagem, v.alt)
        n_alt = v.alt.count(",") + 1
        ac = ",".join(str(gt.split("/").count(str(i))) for i in range(1, n_alt + 1))   # Number=A: um valor por ALT
        info = f"AC={ac};AN=2" + (";DB" if v.rs else "") + ";SINTETICO"
        formato, dados = "GT:DP:GQ", f"{gt}:{dp}:{gq}"
        if e_str:
            info = f"END={v.posicao + len(v.ref) - 1};RU={v.ref};REPID={v.gene.upper()};SVTYPE=STR;SINTETICO"
            repcn = {0: "2/2", 1: f"2/{v.repeticoes}", 2: f"{v.repeticoes}/{v.repeticoes}"}[v.dosagem]
            formato, dados = "GT:REPCN:DP:GQ", f"{_gt(v.dosagem, v.alt)}:{repcn}:{dp}:{gq}"
        registros.append((ORDEM_CONTIGS.index(v.cromossomo), v.posicao,
                          f"chr{v.cromossomo}\t{v.posicao}\t{v.rs or '.'}\t{v.ref}\t{v.alt}\t{qual}\t{filtro}\t{info}\t{formato}\t{dados}"))
    registros.sort()
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(_cabecalho(amostra, descricao, contagens_str) + [r[2] for r in registros]) + "\n")
    return caminho


def gerar_cenarios(dir_saida: str | Path, seed: int = 2026, incluir_ruido: bool = True) -> pd.DataFrame:
    """Gera os VCFs materno e paterno de cada cenário. Cada genitor recebe os lóci de risco do outro com GT 0/0.

    O índice `cenarios.csv` traz também `c9orf72_mae` e `c9orf72_pai` (repetições do laudo; vazio = sem laudo),
    que devem ser passados a `pipeline.executar(..., laudo_c9orf72=...)`.
    """
    dir_saida = Path(dir_saida)
    rng = np.random.default_rng(seed)
    linhas = []
    for c in CENARIOS:
        loci = {v.rotulo: v for v in c.pai + c.mae}
        por_lado = {}
        for lado, lista in (("mae", c.mae), ("pai", c.pai)):
            proprias = {v.rotulo: v for v in lista}
            registros = [proprias.get(r, loci[r].com_dosagem(0)) for r in loci]
            caminho = escrever_vcf(dir_saida / f"cenario_{c.numero}_{lado}.vcf", lado.upper(), registros, rng,
                                   descricao=f"cenario {c.numero}, {lado}: {c.descricao}", incluir_ruido=incluir_ruido)
            por_lado[lado] = caminho
        linhas.append({"numero": c.numero, "nome": c.nome, "descricao": c.descricao,
                       "vcf_mae": str(por_lado["mae"]), "vcf_pai": str(por_lado["pai"]),
                       "c9orf72_mae": c.laudo_c9orf72.get("mae"), "c9orf72_pai": c.laudo_c9orf72.get("pai")})
    df = pd.DataFrame(linhas)
    df["c9orf72_mae"] = df["c9orf72_mae"].astype("Int64"); df["c9orf72_pai"] = df["c9orf72_pai"].astype("Int64")
    df.to_csv(dir_saida / "cenarios.csv", index=False)
    return df


def laudo_da_linha(linha) -> dict[str, int]:
    """Reconstrói `laudo_c9orf72` a partir de uma linha de `cenarios.csv` (ou do DataFrame de `gerar_cenarios`)."""
    laudo = {}
    for lado in ("mae", "pai"):
        v = linha[f"c9orf72_{lado}"] if f"c9orf72_{lado}" in linha else None
        if v is not None and not pd.isna(v):
            laudo[lado] = int(v)
    return laudo
