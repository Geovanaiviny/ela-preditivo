"""Cenários familiares sintéticos e gerador de VCF 4.2 (TCC, seções 3.4, 4.2.1 e 4.5).

Os dados são inteiramente sintéticos: as variantes de risco vêm da tabela curada (coordenadas públicas
do dbSNP/ClinVar), mas os genótipos, profundidades e qualidades são gerados por seed. Cada arquivo reproduz a
estrutura do Quadro 2 do TCC (CHROM, POS, ID, REF, ALT, QUAL, FILTER, INFO com AC/AN/DB, FORMAT GT:DP:GQ) e inclui
"ruído" (variante benigna, variante não anotada, variante fora dos genes-alvo, registro de baixa qualidade e
registro multialélico) para exercitar os filtros e a anotação.

A expansão do C9orf72 não aparece nos VCFs: conforme o TCC 4.2.1, ela entra como parâmetro do laudo laboratorial
(`Cenario.laudo_c9orf72`), porque o fluxo de variantes curtas não a detecta. `c9orf72_expansao()` continua
disponível para testar o caminho secundário (VCF no estilo ExpansionHunter). Todo genitor de cenário tem laudo: quem
não envolve o C9orf72 declara um laudo normal explícito (`LAUDO_NORMAL`, derivado do YAML), porque genitor sem laudo
é "não testado" e deixaria o lócus indeterminado (TCC 4.3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import __version__, anotacao
from .calibracao import CAMINHO_PADRAO
from .exato import prob_portador

ORDEM_CONTIGS = ["1", "9", "16", "17", "21"]
# Comprimentos GRCh38 (NCBI GRCh38.p14), declarados no cabeçalho para a conferência de montagem
COMPRIMENTOS_GRCH38 = {"1": 248956422, "9": 138394717, "16": 90338345, "17": 83257441, "21": 46709983}


def laudo_normal_c9orf72(config: str | Path | None = None) -> int:
    """Contagem de repetições de um laudo normal explícito do C9orf72, para os genitores que não envolvem o gene.

    Derivada do YAML, e não um número clínico fixo: um valor abaixo do limite inferior da faixa intermediária
    (`limiar_repeticoes_c9orf72.intermediario` − 1). Sem laudo o genitor seria "não testado" e o lócus do C9orf72
    ficaria indeterminado; o laudo normal declara que ele foi testado e não tem expansão.
    """
    caminho = Path(config) if config else CAMINHO_PADRAO
    with open(caminho, encoding="utf-8") as f:
        limiar = yaml.safe_load(f).get("limiar_repeticoes_c9orf72") or {}
    return int(limiar.get("intermediario", anotacao.LIMIAR_PADRAO["intermediario"])) - 1


LAUDO_NORMAL = laudo_normal_c9orf72()

# data/sinteticos tem uma pasta por caso de atendimento do TCC. Cada arquivo fica numa só pasta, a do caso em que é
# usado na demonstração e no roteiro de testes; o par de VCFs em si serve a qualquer caso.
PASTAS_CASO = {
    1: "caso_1_pessoa_com_historico",
    2: "caso_2_casal_ou_futuro_filho",
    3: "caso_3_familia_com_variante",
}


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
        return VarianteSintetica(
            self.gene,
            self.rs,
            self.cromossomo,
            self.posicao,
            self.ref,
            self.alt,
            dosagem,
            self.repeticoes,
            self.rotulo,
            self.baixa_qualidade,
        )


# Variantes de risco (tabela curada, coordenadas GRCh38 conferidas em 2026-10-24)
SOD1_A5V = VarianteSintetica("SOD1", "rs121912442", "21", 31659783, "C", "T", rotulo="SOD1 p.Ala5Val (A4V)")
SOD1_D91A = VarianteSintetica(
    "SOD1", "rs80265967", "21", 31667290, "A", "C", rotulo="SOD1 p.Asp91Ala (D90A), recessiva"
)
TARDBP_M337V = VarianteSintetica("TARDBP", "rs80356730", "1", 11022418, "A", "G", rotulo="TARDBP p.Met337Val")
FUS_R521C = VarianteSintetica("FUS", "rs121909668", "16", 31191418, "C", "T", rotulo="FUS p.Arg521Cys")


def c9orf72_expansao(repeticoes: int = 45, dosagem: int = 1) -> VarianteSintetica:
    return VarianteSintetica(
        "C9orf72",
        None,
        "9",
        27573529,
        "GGGGCC",
        f"<STR{repeticoes}>",
        dosagem,
        repeticoes,
        rotulo=f"C9orf72 expansão GGGGCC ({repeticoes} repetições)",
    )


# Ruído presente em todos os arquivos
RUIDO = [
    VarianteSintetica(
        "SOD1", "rs17883296", "21", 31659509, "G", "T", rotulo="SOD1 rs17883296 (provavelmente benigna; exemplo do TCC)"
    ),
    VarianteSintetica("FUS", None, "16", 31185000, "A", "G", rotulo="FUS intrônica não anotada"),
    VarianteSintetica("TP53", None, "17", 7675088, "C", "T", rotulo="fora dos genes-alvo (TP53)"),
    VarianteSintetica(
        "SOD1",
        None,
        "21",
        31663000,
        "T",
        "C",
        rotulo="SOD1 baixa qualidade (DP=4, GQ=10, LowQual)",
        baixa_qualidade=True,
    ),
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
    laudo_c9orf72: dict[str, int] = field(
        default_factory=dict
    )  # {"mae": repetições, "pai": repetições} do laudo laboratorial
    caso: int = 1  # caso de atendimento (pasta em data/sinteticos)

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
    Cenario(
        1,
        "pai_het_SOD1_A5V",
        "Pai heterozigoto SOD1 p.Ala5Val (alta penetrância) × mãe selvagem",
        pai=[SOD1_A5V],
        mae=[],
        laudo_c9orf72={"mae": LAUDO_NORMAL, "pai": LAUDO_NORMAL},
    ),
    Cenario(
        2,
        "mae_C9orf72_expansao",
        "Mãe com expansão de hexanucleotídeos no C9orf72 (45 repetições, laudo) × pai selvagem",
        pai=[],
        mae=[],
        laudo_c9orf72={"mae": 45, "pai": LAUDO_NORMAL},
    ),
    Cenario(
        3,
        "pai_SOD1_mae_C9orf72",
        "Pai heterozigoto SOD1 p.Ala5Val × mãe com expansão C9orf72 (45 repetições, laudo; exemplo literal do TCC, 4.5)",
        pai=[SOD1_A5V],
        mae=[],
        laudo_c9orf72={"mae": 45, "pai": LAUDO_NORMAL},
    ),
    Cenario(
        4,
        "SOD1_D91A_recessiva",
        "Ambos os pais heterozigotos para SOD1 p.Asp91Ala (herança recessiva)",
        pai=[SOD1_D91A],
        mae=[SOD1_D91A],
        herancas={"SOD1": "recessiva"},
        laudo_c9orf72={"mae": LAUDO_NORMAL, "pai": LAUDO_NORMAL},
        caso=3,
    ),
    Cenario(
        5,
        "pai_TARDBP_mae_FUS",
        "Pai heterozigoto TARDBP p.Met337Val × mãe heterozigota FUS p.Arg521Cys",
        pai=[TARDBP_M337V],
        mae=[FUS_R521C],
        laudo_c9orf72={"mae": LAUDO_NORMAL, "pai": LAUDO_NORMAL},
    ),
]


def cenario_por_numero(numero: int) -> Cenario:
    for c in CENARIOS:
        if c.numero == numero:
            return c
    raise KeyError(f"cenário {numero} não existe (1 a {len(CENARIOS)})")


def pasta_caso(dir_base: str | Path, caso: int) -> Path:
    """Pasta do caso de atendimento dentro de `dir_base` (por exemplo, data/sinteticos)."""
    return Path(dir_base) / PASTAS_CASO[caso]


def vcf_cenario(dir_base: str | Path, numero: int, lado: str) -> Path:
    """Caminho do VCF de um dos cinco cenários. Aceita também uma pasta antiga, sem as subpastas por caso."""
    nome = f"cenario_{numero}_{lado}.vcf"
    caminho = pasta_caso(dir_base, cenario_por_numero(numero).caso) / nome
    plano = Path(dir_base) / nome
    return plano if not caminho.exists() and plano.exists() else caminho


def vcf_sintetico(dir_base: str | Path, nome: str) -> Path:
    """Localiza um VCF sintético pelo nome (com ou sem `.vcf`) nas pastas dos casos, ou direto em `dir_base`."""
    nome = nome if nome.endswith(".vcf") else f"{nome}.vcf"
    for caso in PASTAS_CASO:
        caminho = pasta_caso(dir_base, caso) / nome
        if caminho.exists():
            return caminho
    plano = Path(dir_base) / nome
    if plano.exists():
        return plano
    raise FileNotFoundError(f"VCF sintético {nome} não encontrado em {dir_base}")


# ---------------------------------------------------------------------------
# Escrita de VCF 4.2
# ---------------------------------------------------------------------------
def _gt(dosagem: int, alt: str) -> str:
    if "," in alt:  # multialélico: dosagem indica o índice do ALT portado (0/2)
        return f"0/{dosagem}"
    return {0: "0/0", 1: "0/1", 2: "1/1"}[dosagem]


def data_fixa_vcf(config: str | Path | None = None) -> str:
    """`fileDate` dos VCFs sintéticos (AAAAMMDD): a data de versão (`data`) do YAML de parâmetros, e não a data de hoje,
    para que a mesma semente produza o mesmo arquivo byte a byte em qualquer dia (reprodutibilidade, TCC 3.4 e 4.5)."""
    caminho = Path(config) if config else CAMINHO_PADRAO
    with open(caminho, encoding="utf-8") as f:
        data = str(yaml.safe_load(f).get("data", "")).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
        raise ValueError(f"{caminho}: o YAML precisa de `data: AAAA-MM-DD` para fixar o fileDate dos VCFs sintéticos")
    return data.replace("-", "")


def _cabecalho(amostra: str, descricao: str, contagens_str: set[int], data_arquivo: str) -> list[str]:
    linhas = [
        "##fileformat=VCFv4.2",
        f"##fileDate={data_arquivo}",
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
    linhas += [
        f'##ALT=<ID=STR{n},Description="Expansao de repeticao curta em tandem com {n} copias">'
        for n in sorted(contagens_str)
    ]
    linhas.append("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t" + amostra)
    return linhas


def escrever_vcf(
    caminho: str | Path,
    amostra: str,
    variantes: list[VarianteSintetica],
    rng: np.random.Generator,
    descricao: str = "",
    incluir_ruido: bool = True,
    data_arquivo: str | None = None,
) -> Path:
    """Escreve um VCF 4.2 sintético. `data_arquivo` (AAAAMMDD) é o `##fileDate`; padrão: `data_fixa_vcf()`."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    data_arquivo = data_arquivo or data_fixa_vcf()
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
        ac = ",".join(str(gt.split("/").count(str(i))) for i in range(1, n_alt + 1))  # Number=A: um valor por ALT
        info = f"AC={ac};AN=2" + (";DB" if v.rs else "") + ";SINTETICO"
        formato, dados = "GT:DP:GQ", f"{gt}:{dp}:{gq}"
        if e_str:
            info = f"END={v.posicao + len(v.ref) - 1};RU={v.ref};REPID={v.gene.upper()};SVTYPE=STR;SINTETICO"
            repcn = {0: "2/2", 1: f"2/{v.repeticoes}", 2: f"{v.repeticoes}/{v.repeticoes}"}[v.dosagem]
            formato, dados = "GT:REPCN:DP:GQ", f"{_gt(v.dosagem, v.alt)}:{repcn}:{dp}:{gq}"
        registros.append(
            (
                ORDEM_CONTIGS.index(v.cromossomo),
                v.posicao,
                f"chr{v.cromossomo}\t{v.posicao}\t{v.rs or '.'}\t{v.ref}\t{v.alt}\t{qual}\t{filtro}\t{info}\t{formato}\t{dados}",
            )
        )
    registros.sort()
    # newline="\n": o VCF sai com LF em qualquer sistema operacional, para que a mesma semente produza
    # arquivos idênticos byte a byte no Windows e no Linux
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(
            "\n".join(_cabecalho(amostra, descricao, contagens_str, data_arquivo) + [r[2] for r in registros]) + "\n"
        )
    return caminho


def gerar_cenarios(
    dir_saida: str | Path, seed: int = 2026, incluir_ruido: bool = True, config: str | Path | None = None
) -> pd.DataFrame:
    """Gera os VCFs materno e paterno de cada cenário. Cada genitor recebe os lóci de risco do outro com GT 0/0.

    O índice `cenarios.csv` traz também `c9orf72_mae` e `c9orf72_pai` (repetições do laudo; vazio = sem laudo),
    que devem ser passados a `pipeline.executar(..., laudo_c9orf72=...)`. O `##fileDate` dos arquivos é fixo
    (`data_fixa_vcf(config)`), de modo que a mesma semente gera os mesmos bytes em qualquer dia.
    """
    dir_saida = Path(dir_saida)
    rng = np.random.default_rng(seed)
    data_arquivo = data_fixa_vcf(config)
    linhas = []
    for c in CENARIOS:
        loci = {v.rotulo: v for v in c.pai + c.mae}
        por_lado = {}
        for lado, lista in (("mae", c.mae), ("pai", c.pai)):
            proprias = {v.rotulo: v for v in lista}
            registros = [proprias.get(r, loci[r].com_dosagem(0)) for r in loci]
            caminho = escrever_vcf(
                pasta_caso(dir_saida, c.caso) / f"cenario_{c.numero}_{lado}.vcf",
                lado.upper(),
                registros,
                rng,
                descricao=f"cenario {c.numero}, {lado}: {c.descricao}",
                incluir_ruido=incluir_ruido,
                data_arquivo=data_arquivo,
            )
            por_lado[lado] = caminho
        linhas.append(
            {
                "numero": c.numero,
                "nome": c.nome,
                "descricao": c.descricao,
                "vcf_mae": str(por_lado["mae"]),
                "vcf_pai": str(por_lado["pai"]),
                "c9orf72_mae": c.laudo_c9orf72.get("mae"),
                "c9orf72_pai": c.laudo_c9orf72.get("pai"),
            }
        )
    df = pd.DataFrame(linhas)
    df["c9orf72_mae"] = df["c9orf72_mae"].astype("Int64")
    df["c9orf72_pai"] = df["c9orf72_pai"].astype("Int64")
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


def escrever_vcf_sem_variantes(destino: str | Path, amostra: str, descricao: str = "genitor sem exame") -> Path:
    """VCF GRCh38 de uma amostra com um único registro homozigoto de referência (0/0) fora dos genes-alvo: representa
    um genitor sem exame (assumido não portador, ou inferido por parentes). O registro existe só para que a ingestão
    produza um quadro com colunas; a suposição ou a inferência é declarada no resultado e nos metadados."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    linhas = _cabecalho(amostra, descricao, set(), "00000000")
    linhas.append("chr17\t7675088\t.\tC\tT\t99.0\tPASS\tAC=0;AN=2;SINTETICO\tGT:DP:GQ\t0/0:40:90")
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="\n")
    return destino


# ---------------------------------------------------------------------------
# Cenários com genitor sem exame, inferido por parentes (extensão de três gerações)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CenarioParentes:
    """Família sintética em que um genitor não foi testado e entram os genótipos de parentes dele."""

    numero: int
    nome: str
    descricao: str
    genitor_inferido: str  # "pai" ou "mae"
    situacao: str  # situação clínica do genitor sem exame
    idade: float | None
    testado: tuple  # variantes do outro genitor (com exame)
    avo: tuple | None = None  # variantes do pai do genitor sem exame (None = sem exame)
    avoh: tuple | None = None  # variantes da mãe do genitor sem exame
    tios: tuple = ()  # um conjunto de variantes por irmão testado
    filhos_testados: tuple = ()  # um conjunto de variantes por filho já testado
    laudos: tuple = ()  # pares (pessoa, repetições): "testado", "avo", "avoh"
    caso: int = 1  # caso de atendimento (pasta em data/sinteticos)

    @property
    def lado_testado(self) -> str:
        return "mae" if self.genitor_inferido == "pai" else "pai"


CENARIOS_PARENTES: list[CenarioParentes] = [
    CenarioParentes(
        1,
        "avo_paterna_SOD1_pai_falecido",
        "Pai sem exame, falecido sem ELA aos 60 anos; avó paterna heterozigota SOD1 p.Ala5Val; avô paterno sem "
        "exame; mãe testada, sem a variante",
        genitor_inferido="pai",
        situacao="falecido_sem_ela",
        idade=60,
        testado=(SOD1_A5V.com_dosagem(0),),
        avoh=(SOD1_A5V,),
        laudos=(("testado", LAUDO_NORMAL), ("avoh", LAUDO_NORMAL)),
    ),
    CenarioParentes(
        2,
        "filho_testado_negativo",
        "Pai sem exame, vivo sem sintomas aos 62 anos; avó paterna heterozigota SOD1 p.Ala5Val; mãe testada, sem a "
        "variante; um filho já testado, sem a variante",
        genitor_inferido="pai",
        situacao="vivo_assintomatico",
        idade=62,
        testado=(SOD1_A5V.com_dosagem(0),),
        avoh=(SOD1_A5V,),
        filhos_testados=((SOD1_A5V.com_dosagem(0),),),
        laudos=(("testado", LAUDO_NORMAL), ("avoh", LAUDO_NORMAL)),
        caso=3,
    ),
]


def cenario_parentes_por_numero(numero: int) -> CenarioParentes:
    for c in CENARIOS_PARENTES:
        if c.numero == numero:
            return c
    raise KeyError(f"cenário de parentes {numero} não existe (1 a {len(CENARIOS_PARENTES)})")


def gerar_cenarios_parentes(
    dir_saida: str | Path, seed: int = 2026, incluir_ruido: bool = True, config: str | Path | None = None
) -> list[dict]:
    """Gera os VCFs dos cenários com genitor sem exame e devolve, por cenário, os argumentos de `pipeline.executar`:
    `vcf_mae`, `vcf_pai` (None para o genitor inferido), `laudo_c9orf72` e `parentes`. O gerador de números é próprio
    (derivado da semente), de modo que os arquivos dos cinco cenários de `gerar_cenarios` não mudam."""
    dir_saida = Path(dir_saida)
    data_arquivo = data_fixa_vcf(config)
    saida = []
    for c in CENARIOS_PARENTES:
        rng = np.random.default_rng([int(seed), 1000 + c.numero])

        def vcf(sufixo: str, amostra: str, variantes) -> Path:
            return escrever_vcf(
                pasta_caso(dir_saida, c.caso) / f"parentes_{c.numero}_{sufixo}.vcf",
                amostra,
                list(variantes),
                rng,
                descricao=f"cenario de parentes {c.numero}, {sufixo}: {c.descricao}",
                incluir_ruido=incluir_ruido,
                data_arquivo=data_arquivo,
            )

        laudos = dict(c.laudos)
        g, t = c.genitor_inferido, c.lado_testado
        sufixo_lado = "paterno" if g == "pai" else "materno"
        lado = {"situacao": c.situacao, "idade": c.idade}
        if c.avo is not None:
            lado["pai"] = {"vcf": vcf(f"avo_{sufixo_lado}", "AVO", c.avo), "laudo_c9orf72": laudos.get("avo")}
        if c.avoh is not None:
            fem = "paterna" if g == "pai" else "materna"
            lado["mae"] = {"vcf": vcf(f"avo_{fem}", "AVOH", c.avoh), "laudo_c9orf72": laudos.get("avoh")}
        lado["irmaos"] = [{"vcf": vcf(f"tio_{i}", f"TIO{i}", v)} for i, v in enumerate(c.tios, 1)]
        parentes = {g: lado}
        if c.filhos_testados:
            parentes["filhos_testados"] = [
                {"vcf": vcf(f"filho_testado_{i}" if len(c.filhos_testados) > 1 else "filho_testado", f"FILHO{i}", v)}
                for i, v in enumerate(c.filhos_testados, 1)
            ]
        caminho_testado = vcf(t, t.upper(), c.testado)
        saida.append(
            {
                "numero": c.numero,
                "nome": c.nome,
                "descricao": c.descricao,
                "vcf_mae": caminho_testado if t == "mae" else None,
                "vcf_pai": caminho_testado if t == "pai" else None,
                "laudo_c9orf72": {t: laudos["testado"]} if "testado" in laudos else {},
                "parentes": parentes,
            }
        )
    return saida


# ---------------------------------------------------------------------------
# Cenários de casal que planeja filhos (caso 2): o resultado é para o futuro filho
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CenarioCasal:
    """Casal sintético do caso 2. `pai=None` representa o parceiro que não fez o exame genético."""

    numero: int
    nome: str
    descricao: str
    mae: tuple
    pai: tuple | None
    herancas: tuple = ()  # pares (gene, herança)
    laudos: tuple = ()  # pares (lado, repetições do laudo do C9orf72)


CENARIOS_CASAL: list[CenarioCasal] = [
    CenarioCasal(
        1,
        "parceira_C9orf72_parceiro_sem_exame",
        "Parceira com expansão C9orf72 (45 repetições, laudo); parceiro sem exame genético",
        mae=(),
        pai=None,
        laudos=(("mae", 45),),
    ),
    CenarioCasal(
        2,
        "casal_SOD1_D91A_recessiva",
        "Os dois parceiros heterozigotos para SOD1 p.Asp91Ala (herança recessiva)",
        mae=(SOD1_D91A,),
        pai=(SOD1_D91A,),
        herancas=(("SOD1", "recessiva"),),
        laudos=(("mae", LAUDO_NORMAL), ("pai", LAUDO_NORMAL)),
    ),
]


def gerar_cenarios_casal(
    dir_saida: str | Path, seed: int = 2026, incluir_ruido: bool = True, config: str | Path | None = None
) -> list[dict]:
    """Gera os VCFs dos casais do caso 2 e devolve, por casal, `vcf_mae`, `vcf_pai` (None para quem não fez o exame),
    `laudo_c9orf72` e `herancas`. O gerador de números é próprio (derivado da semente), de modo que os arquivos dos
    outros cenários não mudam."""
    pasta = pasta_caso(dir_saida, 2)
    data_arquivo = data_fixa_vcf(config)
    saida = []
    for c in CENARIOS_CASAL:
        rng = np.random.default_rng([int(seed), 2000 + c.numero])
        caminhos = {}
        for lado in ("mae", "pai"):
            proprias = getattr(c, lado)
            if proprias is None:
                caminhos[lado] = None
                continue
            caminhos[lado] = escrever_vcf(
                pasta / f"casal_{c.numero}_{lado}.vcf",
                lado.upper(),
                list(proprias),
                rng,
                descricao=f"casal {c.numero}, {lado}: {c.descricao}",
                incluir_ruido=incluir_ruido,
                data_arquivo=data_arquivo,
            )
        saida.append(
            {
                "numero": c.numero,
                "nome": c.nome,
                "descricao": c.descricao,
                "vcf_mae": caminhos["mae"],
                "vcf_pai": caminhos["pai"],
                "laudo_c9orf72": dict(c.laudos),
                "herancas": dict(c.herancas),
            }
        )
    return saida
