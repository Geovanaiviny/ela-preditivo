"""Documentos fictícios para o roteiro de testes da plataforma: o documento do prontuário de cada registro e o laudo do
C9orf72 de cada genitor, em PDF, ao lado dos VCFs sintéticos.

São os dois tipos de documento que a plataforma guarda. Os registros (`FICHAS_DE_TESTE`) são inventados e não repetem
os da demonstração; cada um usa VCFs de `data/sinteticos` e o laudo que o cenário pede. Todo PDF traz a marca
"FICTÍCIO" e o aviso de que não é documento clínico.

Os PDFs são escritos aqui mesmo, sem biblioteca externa e sem data do dia, de modo que o mesmo código produz o mesmo
arquivo byte a byte (reprodutibilidade, TCC 3.4 e 4.5), como os VCFs de `cenarios.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import anotacao
from .calibracao import carregar_parametros
from .cenarios import PASTAS_CASO, data_fixa_vcf, pasta_caso

LARGURA, ALTURA, MARGEM = 595, 842, 50
ROTULO_CASO = {
    1: "Caso 1 · Pessoa assintomática com histórico familiar",
    2: "Caso 2 · Casal ou pessoa que planeja filhos",
    3: "Caso 3 · Família de genitor com variante confirmada",
}
ROTULO_LADO = {1: ("Mãe", "Pai"), 2: ("Parceira (futura mãe)", "Parceiro (futuro pai)"), 3: ("Mãe", "Pai")}
AVISO = "Documento fictício, gerado pelo artefato ela_preditivo para teste da plataforma. Sem valor clínico."
ORIGEM = "Nomes, datas e números inventados. Nenhum dado vem de uma pessoa."


# ---------------------------------------------------------------------------
# Fichas de teste
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PessoaFicticia:
    nome: str
    nascimento: str  # DD/MM/AAAA
    sexo: str = ""  # descendentes: Feminino ou Masculino
    repeticoes: int | None = None  # genitores: laudo do C9orf72; None = sem laudo
    vcf: str | None = None  # VCF sintético da pasta do caso; None = sem exame
    situacao: str = ""  # genitor sem exame: situação clínica informada na ficha
    parente: tuple = ()  # genitor sem exame: (parentesco, VCF, repetições do laudo) do parente testado
    observacao: str = ""


@dataclass(frozen=True)
class FichaDeTeste:
    codigo: str  # 1A, 1B, ..., 3B
    caso: int  # caso de atendimento (pasta em data/sinteticos)
    prontuario: str
    momento: str
    mae: PessoaFicticia
    pai: PessoaFicticia
    descendentes: tuple = ()
    registro: str = ""  # nome do casal ou da família
    observacoes: str = ""

    @property
    def nome_do_prontuario(self) -> str:
        return f"caso_{self.codigo}_prontuario_{self.prontuario}.pdf"

    def nome_do_laudo(self, lado: str) -> str:
        return f"caso_{self.codigo}_laudo_c9orf72_{lado}.pdf"

    def laudos(self) -> list[tuple[str, PessoaFicticia]]:
        """Genitores que têm laudo do C9orf72: (lado, pessoa)."""
        return [(lado, p) for lado, p in (("mae", self.mae), ("pai", self.pai)) if p.repeticoes is not None]


FICHAS_DE_TESTE: tuple[FichaDeTeste, ...] = (
    FichaDeTeste(
        "1A",
        1,
        "HML-1001",
        "Depois do laudo laboratorial",
        mae=PessoaFicticia("Sônia Fictícia Andrade", "08/03/1966", repeticoes=45, vcf="cenario_3_mae.vcf"),
        pai=PessoaFicticia("Roberto Fictício Andrade", "21/11/1963", repeticoes=23, vcf="cenario_3_pai.vcf"),
        descendentes=(PessoaFicticia("Beatriz Fictícia Andrade", "15/06/1994", "Feminino"),),
        observacoes="Registro fictício de homologação. Pai portador de SOD1 p.Ala5Val; mãe com expansão do C9orf72 "
        "em laudo.",
    ),
    FichaDeTeste(
        "1B",
        1,
        "HML-1002",
        "Antes do teste ou da consulta",
        mae=PessoaFicticia("Lúcia Fictícia Menezes", "30/07/1962", repeticoes=23, vcf="parentes_1_mae.vcf"),
        pai=PessoaFicticia(
            "Álvaro Fictício Menezes",
            "04/05/1958",
            situacao="Falecido sem ter tido ELA, aos 60 anos",
            parente=("Mãe do genitor (avó paterna)", "parentes_1_avo_paterna.vcf", 23),
        ),
        descendentes=(PessoaFicticia("Caio Fictício Menezes", "10/02/1990", "Masculino"),),
        observacoes="Registro fictício de homologação. Pai falecido aos 60 anos sem ter tido ELA, sem exame; avó "
        "paterna testada.",
    ),
    FichaDeTeste(
        "1C",
        1,
        "HML-1003",
        "Depois do laudo laboratorial",
        mae=PessoaFicticia("Glória Fictícia Rocha", "12/01/1971", repeticoes=23, vcf="cenario_5_mae.vcf"),
        pai=PessoaFicticia("Henrique Fictício Rocha", "02/08/1969", repeticoes=23, vcf="cenario_5_pai.vcf"),
        descendentes=(PessoaFicticia("Mateus Fictício Rocha", "23/09/1999", "Masculino"),),
        observacoes="Registro fictício de homologação. Pai com TARDBP p.Met337Val e mãe com FUS p.Arg521Cys.",
    ),
    FichaDeTeste(
        "2A",
        2,
        "HML-2001",
        "Antes do teste ou da consulta",
        mae=PessoaFicticia("Juliana Fictícia Prates", "19/04/1993", repeticoes=45, vcf="casal_1_mae.vcf"),
        pai=PessoaFicticia(
            "Eduardo Fictício Prates",
            "01/12/1991",
            observacao="Não fez exame genético: na análise, usar a suposição de não portador.",
        ),
        registro="Juliana Fictícia Prates e Eduardo Fictício Prates",
        observacoes="Registro fictício de homologação. Parceira com expansão do C9orf72 em laudo; parceiro não fez "
        "exame genético.",
    ),
    FichaDeTeste(
        "2B",
        2,
        "HML-2002",
        "Depois do laudo laboratorial",
        mae=PessoaFicticia("Patrícia Fictícia Lins", "05/10/1995", repeticoes=23, vcf="casal_2_mae.vcf"),
        pai=PessoaFicticia("Fábio Fictício Lins", "27/06/1992", repeticoes=23, vcf="casal_2_pai.vcf"),
        registro="Patrícia Fictícia Lins e Fábio Fictício Lins",
        observacoes="Registro fictício de homologação. Os dois parceiros são heterozigotos para SOD1 p.Asp91Ala.",
    ),
    FichaDeTeste(
        "3A",
        3,
        "HML-3001",
        "Depois do laudo laboratorial",
        mae=PessoaFicticia("Neusa Fictícia Bastos", "14/02/1950", repeticoes=23, vcf="cenario_4_mae.vcf"),
        pai=PessoaFicticia("Osvaldo Fictício Bastos", "09/09/1947", repeticoes=23, vcf="cenario_4_pai.vcf"),
        descendentes=(
            PessoaFicticia("Renata Fictícia Bastos", "03/05/1976", "Feminino"),
            PessoaFicticia("Sérgio Fictício Bastos", "30/11/1980", "Masculino"),
        ),
        registro="Família Fictícia Bastos",
        observacoes="Registro fictício de homologação. Os dois genitores são heterozigotos para SOD1 p.Asp91Ala.",
    ),
    FichaDeTeste(
        "3B",
        3,
        "HML-3002",
        "Acompanhamento de portador assintomático",
        mae=PessoaFicticia("Marta Fictícia Cardoso", "18/08/1966", repeticoes=23, vcf="parentes_2_mae.vcf"),
        pai=PessoaFicticia(
            "Wilson Fictício Cardoso",
            "25/03/1964",
            situacao="Vivo, sem sintomas de ELA, aos 62 anos",
            parente=("Mãe do genitor (avó paterna)", "parentes_2_avo_paterna.vcf", 23),
        ),
        descendentes=(
            PessoaFicticia(
                "Tiago Fictício Cardoso",
                "07/07/1989",
                "Masculino",
                vcf="parentes_2_filho_testado.vcf",
                observacao="já fez o teste e sai da lista de pessoas em risco",
            ),
            PessoaFicticia("Larissa Fictícia Cardoso", "26/01/1993", "Feminino"),
        ),
        registro="Família Fictícia Cardoso",
        observacoes="Registro fictício de homologação. Pai vivo sem sintomas aos 62 anos, sem exame; avó paterna "
        "portadora; Tiago já testado.",
    ),
)


# ---------------------------------------------------------------------------
# PDF de uma página, escrito à mão (Helvetica com acentos, faixas, linhas e marca-d'água)
# ---------------------------------------------------------------------------
def _largura(texto: str, tamanho: float, negrito: bool = False) -> float:
    """Largura aproximada do texto em Helvetica, o bastante para quebrar linhas com folga."""
    total = 0.0
    for c in texto:
        if c in " .,;:'|!ijlItf":
            total += 0.30
        elif c in "mwMW@":
            total += 0.86
        elif c.isupper() or c in "—%":
            total += 0.70
        else:
            total += 0.56
    return total * tamanho * (1.06 if negrito else 1.0)


def _quebrar(texto: str, tamanho: float, largura: float, negrito: bool = False) -> list[str]:
    linhas, atual = [], ""
    for palavra in texto.split():
        tentativa = f"{atual} {palavra}".strip()
        if atual and _largura(tentativa, tamanho, negrito) > largura:
            linhas.append(atual)
            atual = palavra
        else:
            atual = tentativa
    return linhas + ([atual] if atual else [])


class Pagina:
    """Operadores de uma página A4. As coordenadas são em pontos, com a origem no canto inferior esquerdo."""

    def __init__(self) -> None:
        self._ops: list[bytes] = []

    def _texto(self, s: str) -> bytes:
        bruto = s.encode("cp1252", "replace")
        return b"(" + bruto.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"

    def texto(self, x: float, y: float, s: str, tamanho: float = 10, negrito: bool = False, cinza: float = 0.0) -> None:
        fonte = b"/F2" if negrito else b"/F1"
        self._ops.append(b"%.2f g BT %s %.1f Tf %.1f %.1f Td %s Tj ET" % (cinza, fonte, tamanho, x, y, self._texto(s)))

    def paragrafo(
        self, x: float, y: float, s: str, tamanho: float = 10, largura: float = LARGURA - 2 * MARGEM, **estilo
    ) -> float:
        """Texto com quebra de linha; devolve a coordenada y da linha seguinte."""
        for linha in _quebrar(s, tamanho, largura, estilo.get("negrito", False)):
            self.texto(x, y, linha, tamanho, **estilo)
            y -= tamanho * 1.45
        return y

    def faixa(self, x: float, y: float, largura: float, altura: float, cinza: float) -> None:
        self._ops.append(b"%.2f g %.1f %.1f %.1f %.1f re f" % (cinza, x, y, largura, altura))

    def linha(self, x1: float, y1: float, x2: float, y2: float, cinza: float = 0.6) -> None:
        self._ops.append(b"%.2f G 0.6 w %.1f %.1f m %.1f %.1f l S" % (cinza, x1, y1, x2, y2))

    def marca(self, s: str) -> None:
        """Marca-d'água em diagonal, por baixo de tudo o que vier depois."""
        self._ops.append(b"q 0.90 g BT /F2 104 Tf 0.7071 0.7071 -0.7071 0.7071 150 210 Tm %s Tj ET Q" % self._texto(s))

    def campo(self, x: float, y: float, rotulo: str, valor: str, largura: float = LARGURA - 2 * MARGEM) -> float:
        """Rótulo pequeno em cinza e, abaixo, o valor; devolve a coordenada y do campo seguinte."""
        self.texto(x, y, rotulo.upper(), 7.5, negrito=True, cinza=0.45)
        return self.paragrafo(x, y - 13, valor, 10.5, largura) - 6

    def pdf(self, titulo: str) -> bytes:
        conteudo = b"\n".join(self._ops)
        fonte = b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>"
        objetos = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>" % (LARGURA, ALTURA),
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(conteudo), conteudo),
            fonte % b"Helvetica",
            fonte % b"Helvetica-Bold",
            b"<< /Title %s /Producer (ela_preditivo) >>" % self._texto(titulo),
        ]
        saida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        posicoes = []
        for i, obj in enumerate(objetos, start=1):
            posicoes.append(len(saida))
            saida += b"%d 0 obj\n%s\nendobj\n" % (i, obj)
        xref = len(saida)
        saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
        saida += b"".join(b"%010d 00000 n \n" % p for p in posicoes)
        saida += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(objetos) + 1,
            len(objetos),
            xref,
        )
        return bytes(saida)


def _cabecalho(p: Pagina, faixa: str, emissor: str) -> float:
    p.marca("FICTÍCIO")
    p.faixa(0, ALTURA - 46, LARGURA, 46, 0.22)
    p.texto(MARGEM, ALTURA - 29, faixa, 12.5, negrito=True, cinza=1.0)
    p.texto(MARGEM, ALTURA - 78, emissor, 13, negrito=True)
    p.texto(MARGEM, ALTURA - 94, ORIGEM, 8.5, cinza=0.40)
    p.linha(MARGEM, ALTURA - 104, LARGURA - MARGEM, ALTURA - 104)
    return ALTURA - 132


def _rodape(p: Pagina, ficha: FichaDeTeste, arquivo: str) -> None:
    p.linha(MARGEM, 62, LARGURA - MARGEM, 62)
    p.texto(MARGEM, 48, AVISO, 8, cinza=0.35)
    p.texto(MARGEM, 36, f"Ficha de teste {ficha.codigo} · {arquivo}", 8, cinza=0.35)


def _data(config=None) -> str:
    d = data_fixa_vcf(config)  # a data de versão dos parâmetros, como nos VCFs sintéticos
    return f"{d[6:8]}/{d[4:6]}/{d[0:4]}"


def interpretar_repeticoes(n: int, config=None) -> str:
    """Leitura de uma contagem de repetições pelos limiares do artefato (os mesmos que a análise aplica)."""
    limiar = {**anotacao.LIMIAR_PADRAO, **(carregar_parametros(config).limiar_repeticoes or {})}
    pat, inter = int(limiar["patogenico"]), int(limiar["intermediario"])
    classe = anotacao.classe_por_repeticoes(n, pat, inter)
    if classe == "risco":
        return f"Expansão na faixa patogênica ({pat} repetições ou mais)."
    if classe == "intermediaria":
        return f"Alelo na faixa intermediária ({inter} a {pat - 1} repetições)."
    return f"Sem expansão: alelo na faixa normal (até {inter - 1} repetições)."


def laudo_c9orf72(ficha: FichaDeTeste, lado: str, config=None) -> bytes:
    """Laudo fictício do C9orf72 de um genitor: a contagem de repetições que o profissional digita na plataforma."""
    pessoa = ficha.mae if lado == "mae" else ficha.pai
    if pessoa.repeticoes is None:
        raise ValueError(f"ficha {ficha.codigo}: {lado} não tem laudo do C9orf72")
    vinculo = ROTULO_LADO[ficha.caso][0 if lado == "mae" else 1]
    arquivo = ficha.nome_do_laudo(lado)
    p = Pagina()
    y = _cabecalho(p, "LAUDO FICTÍCIO — NÃO É DOCUMENTO CLÍNICO", "Laboratório Fictício de Genética Molecular")
    p.texto(MARGEM, y, "Laudo de análise molecular", 15, negrito=True)
    y = p.paragrafo(MARGEM, y - 19, "Pesquisa da expansão de hexanucleotídeos GGGGCC no gene C9orf72", 11) - 14
    meia = (LARGURA - 2 * MARGEM) / 2
    for esquerda, direita in (
        (("Pessoa examinada", pessoa.nome), ("Data de nascimento", pessoa.nascimento)),
        (("Vínculo no registro", vinculo), ("Prontuário", ficha.prontuario)),
        (("Exame", "Contagem de repetições GGGGCC do maior alelo"), ("Data de emissão", _data(config))),
    ):
        y_e = p.campo(MARGEM, y, *esquerda, largura=meia - 16)
        y_d = p.campo(MARGEM + meia, y, *direita, largura=meia - 16)
        y = min(y_e, y_d)
    y -= 6
    p.faixa(MARGEM, y - 76, LARGURA - 2 * MARGEM, 92, 0.94)
    p.texto(MARGEM + 14, y - 4, "RESULTADO", 7.5, negrito=True, cinza=0.45)
    p.texto(MARGEM + 14, y - 30, f"Maior alelo: {pessoa.repeticoes} repetições GGGGCC", 17, negrito=True)
    p.paragrafo(MARGEM + 14, y - 52, interpretar_repeticoes(pessoa.repeticoes, config), 10.5, LARGURA - 2 * MARGEM - 28)
    y -= 106
    y = p.campo(
        MARGEM,
        y,
        "Como usar no teste da plataforma",
        f'No cadastro, em "{vinculo}", informe {pessoa.repeticoes} no campo de repetições do C9orf72 e anexe este '
        "arquivo como laudo.",
    )
    p.campo(
        MARGEM,
        y,
        "Observação",
        "A expansão do C9orf72 não é lida do VCF: entra na análise por este número. Um genitor sem laudo é tratado "
        "como não testado para o gene.",
    )
    _rodape(p, ficha, arquivo)
    return p.pdf(f"Laudo fictício do C9orf72 - ficha de teste {ficha.codigo}, {vinculo.lower()}")


def _linha_do_genitor(pessoa: PessoaFicticia) -> str:
    partes = [f"{pessoa.nome}, nascimento em {pessoa.nascimento}."]
    if pessoa.repeticoes is not None:
        partes.append(f"Laudo do C9orf72: {pessoa.repeticoes} repetições.")
    else:
        partes.append("Sem laudo do C9orf72.")
    partes.append(f"VCF: {pessoa.vcf}." if pessoa.vcf else "Sem exame genético (sem VCF).")
    if pessoa.situacao:
        partes.append(f"Situação clínica: {pessoa.situacao}.")
    if pessoa.parente:
        parentesco, vcf, repeticoes = pessoa.parente
        partes.append(f"Parente testado: {parentesco}, VCF {vcf}, laudo do C9orf72 com {repeticoes} repetições.")
    if pessoa.observacao:
        partes.append(pessoa.observacao)
    return " ".join(partes)


def prontuario(ficha: FichaDeTeste, config=None) -> bytes:
    """Documento fictício do prontuário: os dados do registro, na ordem em que o cadastro da plataforma os pede."""
    arquivo = ficha.nome_do_prontuario
    rot_mae, rot_pai = ROTULO_LADO[ficha.caso]
    p = Pagina()
    y = _cabecalho(p, "PRONTUÁRIO FICTÍCIO — NÃO É DOCUMENTO CLÍNICO", "Serviço Fictício de Aconselhamento Genético")
    p.texto(MARGEM, y, f"Prontuário nº {ficha.prontuario}", 15, negrito=True)
    y = p.paragrafo(MARGEM, y - 19, ROTULO_CASO[ficha.caso], 11) - 14
    meia = (LARGURA - 2 * MARGEM) / 2
    y_e = p.campo(MARGEM, y, "Momento do aconselhamento", ficha.momento, largura=meia - 16)
    y_d = p.campo(MARGEM + meia, y, "Data de abertura", _data(config), largura=meia - 16)
    y = min(y_e, y_d)
    if ficha.registro:
        y = p.campo(MARGEM, y, "Nome do casal" if ficha.caso == 2 else "Nome da família", ficha.registro)
    y = p.campo(MARGEM, y, rot_mae, _linha_do_genitor(ficha.mae))
    y = p.campo(MARGEM, y, rot_pai, _linha_do_genitor(ficha.pai))
    if ficha.caso == 2:
        y = p.campo(MARGEM, y, "Pessoa analisada", "Futuro filho do casal: não há descendente a cadastrar.")
    for i, d in enumerate(ficha.descendentes, start=1):
        rotulo = "Pessoa atendida" if ficha.caso == 1 else f"Filho(a) {i}"
        linha = f"{d.nome}, nascimento em {d.nascimento}, sexo {d.sexo.lower()}. Sem sintomas de ELA."
        if d.vcf:
            linha += f" VCF próprio: {d.vcf}; {d.observacao}."
        y = p.campo(MARGEM, y, rotulo, linha)
    p.campo(MARGEM, y, "Observações", ficha.observacoes)
    _rodape(p, ficha, arquivo)
    return p.pdf(f"Prontuário fictício {ficha.prontuario} - ficha de teste {ficha.codigo}")


def documentos_da_ficha(ficha: FichaDeTeste, config=None) -> dict[str, bytes]:
    """Nome do arquivo → conteúdo: o prontuário e um laudo para cada genitor que tem laudo."""
    docs = {ficha.nome_do_prontuario: prontuario(ficha, config)}
    for lado, _ in ficha.laudos():
        docs[ficha.nome_do_laudo(lado)] = laudo_c9orf72(ficha, lado, config)
    return docs


def gerar_documentos(dir_saida: str | Path, config: str | Path | None = None) -> list[Path]:
    """Grava os documentos fictícios das fichas de teste na pasta do caso de cada uma, ao lado dos VCFs."""
    gravados = []
    for ficha in FICHAS_DE_TESTE:
        pasta = pasta_caso(dir_saida, ficha.caso)
        pasta.mkdir(parents=True, exist_ok=True)
        for nome, dados in documentos_da_ficha(ficha, config).items():
            (pasta / nome).write_bytes(dados)
            gravados.append(pasta / nome)
    return gravados


assert set(ROTULO_CASO) == set(PASTAS_CASO) == set(ROTULO_LADO)
