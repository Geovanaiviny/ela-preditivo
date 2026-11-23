"""Orquestração ponta a ponta: executar um caso (VCF materno + paterno), avaliar os cenários e rodar tudo."""

from __future__ import annotations

import datetime as _dt
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import (
    AVISO_LEGAL,
    __version__,
    anotacao,
    avaliacao,
    cenarios,
    comparacao,
    genotipo,
    ingestao,
    parentes as parentes_mod,
    relatorio,
    repeticoes,
    sobrevivencia,
)
from .calibracao import carregar_parametros
from .monte_carlo import loci_de_vetor, simular_numpy
from .rede_bayesiana import simular_pymc


def _p(x) -> str:
    return f"{100 * x:.1f}%"


def _n(x) -> str:
    """Inteiro com separador de milhar em português (10.000)."""
    return f"{int(x):,}".replace(",", ".")


def tempo_legivel(segundos: float | None) -> str:
    """Tempo de um motor para o texto: segundos com duas casas a partir de 10 ms, milissegundos com uma casa abaixo
    disso, "não executado" quando não houve medida. O `metadados.json` guarda o valor bruto."""
    if segundos is None or segundos != segundos:
        return "não executado"
    if segundos >= 0.01:
        return f"{segundos:.2f} s"
    return f"{segundos * 1000:.1f} ms"


def _montagem_txt(ind: dict) -> str:
    return f"montagem {ind['montagem']} ({'coerente' if ind['montagem_coerente'] else 'NÃO conferida'})"


def aviso_qualidade(ind: dict) -> str | None:
    """Aviso de um VCF válido sem nenhuma variante aproveitável (só cabeçalho, só registros fora dos genes avaliados ou
    todos reprovados no filtro de qualidade); `None` quando há registro aprovado ou quando o genitor não tem VCF
    próprio (assumido sem variante ou inferido por parentes: não há arquivo a avisar)."""
    if ind.get("sem_vcf") or ind["aprovados"]:
        return None
    lidos, nos_genes = ind["registros"], ind["registros_nas_regioes"]
    if not lidos:
        situacao = "nenhum registro no arquivo"
    elif not nos_genes:
        situacao = (
            "1 registro lido, fora dos genes avaliados"
            if lidos == 1
            else f"{lidos} registros lidos, todos fora dos genes avaliados"
        )
    else:
        situacao = (
            f"nenhum registro aprovado no filtro de qualidade ({lidos} {'lido' if lidos == 1 else 'lidos'}, "
            f"{nos_genes} {'no gene avaliado' if nos_genes == 1 else 'nos genes avaliados'})"
        )
    return (
        f"{_montagem_txt(ind)}; {situacao}; lido como genitor sem variante nos genes avaliados (o C9orf72 vem do laudo)"
    )


def _texto_qualidade(ind: dict) -> str:
    aviso = aviso_qualidade(ind)
    if aviso:
        return aviso
    rotulos = {
        "nao_anotada": ("não anotada", "não anotadas"),
        "nao_classificada": ("não classificada", "não classificadas"),
        "benigna": ("benigna", "benignas"),
        "normal": ("normal", "normais"),
        "risco": ("de risco", "de risco"),
        "vus": ("de significado incerto", "de significado incerto"),
        "conflitante": ("com classificação conflitante", "com classificação conflitante"),
        "intermediaria": ("intermediária", "intermediárias"),
    }
    classes = ", ".join(
        f"{n} {rotulos.get(classe, (classe, classe))[n != 1]}" for classe, n in ind["por_classe"].items()
    )
    est = ", ".join(f"{k}★: {v}" for k, v in ind["por_estrelas"].items()) or "—"
    return (
        f"montagem {ind['montagem']} ({'coerente' if ind['montagem_coerente'] else 'NÃO conferida'}); "
        f"{ind['aprovados']}/{ind['registros']} registros aprovados ({ind['taxa_aprovacao']:.0%}); "
        f"{ind['anotadas']} aprovados encontrados na base de anotação ({ind['taxa_anotacao']:.0%}; estado de revisão {est}); "
        f"classes: {classes}; significado incerto: {ind['n_vus']} ({ind['proporcao_vus']:.0%} das anotadas); "
        f"classificação conflitante: {ind['n_conflitante']} ({ind['proporcao_conflitante']:.0%}); "
        f"risco com frequência > 1%: {ind['risco_com_frequencia_acima_1pct']}"
        + (
            f"; {anotacao.OBS_RS_OUTRO_ALELO} (sem anotação): {'; '.join(ind['rs_com_outro_alelo'])}"
            if ind.get("rs_com_outro_alelo")
            else ""
        )
    )


# Nome da coluna de F(∞) na Tabela 3. "Risco vitalício" é sempre o risco até o horizonte; a fração que manifesta em
# algum momento fica só nesta coluna e nas verificações de coerência.
COLUNA_SEM_LIMITE = "fração que manifesta em algum momento (sem limite de idade)"
IDADES_TABELA_4 = (0, 20, 30, 40, 50, 60, 70)


def _idades_tabela_4(idade_atual: float | None) -> tuple:
    """Idades padrão da Tabela 4, mais a idade do atendido quando ela não está entre as padrão."""
    idades = list(IDADES_TABELA_4)
    if idade_atual is not None and idade_atual > 0:
        a = int(idade_atual) if float(idade_atual).is_integer() else float(idade_atual)
        if a not in idades:
            idades = sorted(idades + [a])
    return tuple(idades)


def _fora_da_anotacao_txt(fontes: dict) -> str:
    """Trecho do relatório para as linhas da base que ficaram fora do casamento (ref = alt); vazio quando não há."""
    n = int(fontes.get("n_fora_da_anotacao") or 0)
    if not n:
        return ""
    return f"; {n} registro{'s' if n > 1 else ''} da base fora da anotação, por ter alelo alternativo igual ao de referência"


def _vcf_txt(caminho, resumo: dict) -> str:
    if caminho is None:
        return "sem exame (genótipo inferido por parentes)"
    return f"`{Path(caminho).name}` (amostra {resumo['amostra']})"


def _qualidade_ou_sem_exame(indicadores: dict, com_vcf: bool) -> str:
    if indicadores.get("sem_vcf") == "assumido":
        return "sem VCF; genitor assumido sem variante de risco (limite inferior)"
    return _texto_qualidade(indicadores) if com_vcf else "sem VCF próprio; dosagem inferida a partir de parente testado"


def _dose_txt(d) -> str:
    """Dosagem parental para o texto: o número, ou "inferida" quando o genitor não foi testado."""
    return "inferida" if d is None or (isinstance(d, float) and np.isnan(d)) else str(int(d))


def _laudo_txt(laudo: dict | None) -> str:
    """Laudo do C9orf72 por genitor; genitor ausente = não testado (o lócus fica indeterminado)."""
    laudo = laudo or {}
    return "; ".join(
        f"{rotulo}: {laudo[lado]} repetições" if laudo.get(lado) is not None else f"{rotulo}: não testado"
        for lado, rotulo in (("mae", "mãe"), ("pai", "pai"))
    )


# Saídas que cada função grava em `saida`. São apagadas no início da execução para que a pasta reflita uma única
# execução (sem tabelas ou figuras de uma rodada anterior ao lado do relatório novo); outros arquivos ficam intactos.
ARTEFATOS_EXECUCAO = (
    "tabelas",
    "figuras",
    "relatorio.md",
    "metadados.json",
    "curvas.csv",
    "variantes_ingeridas_anotadas.csv",
    "_mae_sem_exame.vcf",
    "_pai_sem_exame.vcf",
)
ARTEFATOS_AVALIACAO = (
    "tabelas",
    "figuras",
    "relatorio.md",
    "metadados.json",
    "estabilidade_execucoes.csv",
    "_verificacao_tmp",
)
ARTEFATOS_TUDO = ("sinteticos", "cenarios", "avaliacao", "tabelas", "README.md")


def _limpar_saida(saida: Path, artefatos) -> list[str]:
    """Apaga em `saida` as saídas de uma execução anterior (só os nomes conhecidos em `artefatos`) e garante a pasta."""
    saida = Path(saida)
    removidos = []
    for nome in artefatos:
        p = saida / nome
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
            removidos.append(nome)
        elif p.exists() or p.is_symlink():
            p.unlink()
            removidos.append(nome)
    saida.mkdir(parents=True, exist_ok=True)
    return removidos


def executar(
    vcf_mae,
    vcf_pai,
    saida,
    sexo: str | None = None,
    idade_atual: float | None = None,
    n: int = 10_000,
    seed: int = 42,
    motor: str = "pymc",
    config=None,
    tabela_variantes=None,
    horizonte: float | None = None,
    rotulo: str = "",
    figuras: bool = True,
    laudo_c9orf72: dict | None = None,
    base_clinvar=None,
    amostra_mae: str | None = None,
    amostra_pai: str | None = None,
    hipoteses_c9orf72: dict | None = None,
    comparar_cox: bool = False,
    parentes: dict | None = None,
    tornado: bool = False,
    genitores_assumidos: tuple[str, ...] = (),
) -> dict:
    """Executa as três camadas para um casal e grava tabelas, figuras, relatório e metadados em `saida`.

    - `genitores_assumidos`: lados ("mae", "pai") que não têm VCF e entram assumidos sem variante de risco; o arquivo
      recebido para eles é só um marcador, e a qualidade deles não é relatada como a de um VCF vazio.
    - `laudo_c9orf72`: {"mae": repetições, "pai": repetições} do laudo laboratorial (TCC 4.2.1; a expansão não é lida do VCF).
    - `base_clinvar`: caminho da base real do ClinVar (padrão: procura em `ELA_DADOS_BRUTOS`/`dados_reais/`); `False` usa só a tabela curada.
    - `tabela_variantes`: CSV no formato da tabela curada (padrão: `data/variantes_curadas.csv`), que complementa a base real.
    - `amostra_mae`/`amostra_pai`: nome da coluna de amostra num VCF multiamostra.
    - `hipoteses_c9orf72`: {"delta_mae", "delta_pai", "antecipacao"} — transmissão do C9orf72 por repetições (extensão
      experimental, `repeticoes.py`). None (padrão) mantém o modelo por dosagem, sem qualquer mudança de resultado.
    - `comparar_cox`: ajusta CoxPHFitter na coorte de portadores e compara com a cura mista (`comparacao.py`; Tabela 11,
      Figura 9). Desligado por padrão; ligado em `tudo` e na interface web.
    - `parentes`: genótipo de parentes para o genitor que não pôde ser testado (`parentes.py`). Dicionário com, por
      genitor, `{"mae": {...}, "pai": {...}}`, cada um com `situacao` ("vivo_assintomatico", "falecido_sem_ela",
      "afetado" ou "desconhecido"), `idade`, os parentes dele `pai`, `mae` e `irmaos` (cada parente:
      `{"vcf": caminho, "laudo_c9orf72": repetições}`) e `prior_avos` ("nao_portador" ou "hardy_weinberg"); e
      `filhos_testados`: lista de `{"vcf": caminho}` de filhos já testados. O VCF do genitor inferido é `None`.
      Sem `parentes` o comportamento é o de sempre.
    - `tornado`: sensibilidade tipo tornado do caso, um parâmetro por vez dentro da faixa publicada (Tabela 20,
      Figura 12). Desligada por padrão.
    """
    t_ini = time.perf_counter()
    saida = Path(saida)
    removidos = _limpar_saida(saida, ARTEFATOS_EXECUCAO)
    (saida / "tabelas").mkdir(parents=True, exist_ok=True)
    (saida / "figuras").mkdir(exist_ok=True)
    par = carregar_parametros(config)
    horizonte = float(horizonte or par.horizonte_anos)
    regioes = ingestao.carregar_regioes()
    tabela = anotacao.tabela_anotacao(base_real=base_clinvar, curada=tabela_variantes, regra=par.regra_conflitante)
    fontes = tabela.attrs.get("fontes", {})
    laudo = {k: v for k, v in (laudo_c9orf72 or {}).items() if v is not None}
    familia = parentes_mod.Familia.de(parentes)
    # genitor sem VCF: só com parentes informados; a ingestão recebe um VCF sem registros (o genitor é inferido)
    com_vcf = {"mae": vcf_mae is not None, "pai": vcf_pai is not None}
    sem_exame = {}
    for lado, caminho in (("mae", vcf_mae), ("pai", vcf_pai)):
        if caminho is not None:
            continue
        if familia is None or not familia.tem_parente_com_vcf(lado):
            raise ValueError(
                f"VCF d{'a' if lado == 'mae' else 'o'} {parentes_mod.ROTULO_GENITOR[lado]} não informado: sem ele é "
                "preciso o VCF de um parente desse genitor (pai, mãe ou irmão) ou de um filho já testado"
            )
        sem_exame[lado] = cenarios.escrever_vcf_sem_variantes(
            saida / f"_{lado}_sem_exame.vcf", f"{lado.upper()}_SEM_EXAME", "genitor sem exame: inferido por parentes"
        )
    vcf_mae_lido, vcf_pai_lido = sem_exame.get("mae", vcf_mae), sem_exame.get("pai", vcf_pai)

    # Camada 1: ingestão e anotação
    mae = anotacao.anotar(
        ingestao.ler_vcf(vcf_mae_lido, regioes, par.filtro_qualidade, amostra=amostra_mae),
        tabela,
        par.limiar_repeticoes,
    )
    pai = anotacao.anotar(
        ingestao.ler_vcf(vcf_pai_lido, regioes, par.filtro_qualidade, amostra=amostra_pai),
        tabela,
        par.limiar_repeticoes,
    )
    for caminho in sem_exame.values():
        Path(caminho).unlink(missing_ok=True)
    perfil = genotipo.perfil_variantes(mae, pai)
    ing = {"mae": ingestao.resumo_ingestao(mae), "pai": ingestao.resumo_ingestao(pai)}
    ind = {"mae": anotacao.indicadores_qualidade(mae), "pai": anotacao.indicadores_qualidade(pai)}
    for lado in ("mae", "pai"):  # genitor sem VCF próprio: assumido ou inferido por parentes
        ind[lado]["sem_vcf"] = "assumido" if lado in genitores_assumidos else (None if com_vcf[lado] else "inferido")
    pessoas = []
    if familia is None:
        vetor = genotipo.vetor_dosagem(mae, pai, par, laudo_c9orf72=laudo, tabela=tabela)
    else:  # parentes do genitor sem exame: mesma ingestão e anotação; a dosagem do genitor passa a ser inferida
        pessoas = parentes_mod.ler_familia(familia, par, tabela, regioes)
        vetor = parentes_mod.vetor_familia(mae, pai, par, laudo, tabela, familia, pessoas, com_vcf)
        perfil = parentes_mod.perfil_com_parentes(perfil, pessoas)
    # extensão experimental: transmissão do C9orf72 por repetições → dosagem efetiva; só com hipóteses informadas
    hip = repeticoes.HipotesesC9orf72.de_dict(hipoteses_c9orf72) if hipoteses_c9orf72 else None
    transmissao = repeticoes.transmissao_c9orf72(laudo, hip, par, tabela) if hip is not None else None
    if transmissao is not None:
        attrs = dict(vetor.attrs)
        vetor = repeticoes.aplicar_ao_vetor(vetor, transmissao, par, tabela)
        vetor.attrs.update(attrs)
    descartados, uteis = vetor[vetor.descartado], vetor[~vetor.descartado]
    nota_descarte = (
        ""
        if descartados.empty
        else " Lóci de risco descartados por genótipo não determinado num dos genitores (TCC 4.3; não entram no "
        "cálculo nem valem como dosagem 0): "
        + "; ".join(f"{r.gene} {r.variante} — {r.observacao}" for r in descartados.itertuples())
        + "."
    )
    if (descartados.gene == genotipo.GENE_EXPANSAO).any():  # genitor sem laudo → o C9orf72 não é avaliado
        nota_descarte += (
            f" Resultado parcial para o {genotipo.GENE_EXPANSAO}: o lócus não foi avaliado porque falta o laudo de um "
            "genitor (não testado); o risco de transmissão da expansão não pode ser estimado nem afastado."
        )
    # Variantes e alelos que não sustentam atribuição de risco, mas que o aconselhamento precisa conhecer. Vale nos dois
    # ramos do relatório (com e sem lócus utilizável): antes só saía quando nenhum lócus era utilizável, e a informação
    # desaparecia justamente quando havia outro lócus de risco no caso.
    quase = perfil[(perfil.classe.isin(["vus", "conflitante", "intermediaria"])) & (perfil.dosagem.fillna(0) > 0)]
    nota_zona_cinzenta = ""
    if len(quase):
        itens = "; ".join(
            f"{r.amostra}: {r.gene} {r.nome_curto or (str(r.posicao) + ' ' + r.ref + '>' + r.alt)} ({r.clnsig or r.classe})"
            for r in quase.itertuples()
        )
        nota_zona_cinzenta += (
            " Foram encontradas variantes que não sustentam atribuição de risco pela regra do TCC 4.2.2 (significado "
            f"incerto, classificação conflitante ou faixa intermediária): {itens}."
        )
    if vetor.attrs.get("c9orf72_intermediario"):
        nota_zona_cinzenta += (
            f" No laudo do {genotipo.GENE_EXPANSAO}: "
            + "; ".join(vetor.attrs["c9orf72_intermediario"])
            + f". A transmissão do {genotipo.GENE_EXPANSAO} por repetições, com instabilidade na transmissão e "
            "antecipação, é a extensão experimental que trata esse alelo."
        )
    anotadas = genotipo.concatenar_anotadas(mae, pai)
    for p in pessoas:  # variantes dos parentes entram no mesmo arquivo, identificadas pelo parentesco
        if p.anotadas is not None:
            anotadas = genotipo.concatenar_anotadas(anotadas, p.anotadas.assign(amostra=p.rotulo))
    anotadas.to_csv(saida / "variantes_ingeridas_anotadas.csv", index=False)
    # variantes aprovadas cuja classe `risco` veio da regra qualificada para classificação conflitante
    pela_regra = anotadas[anotadas.aprovado & anotadas.regra_qualificada.eq(True)]
    pela_regra = pela_regra.drop_duplicates(["gene", "nome_curto"])
    nota_regra = (
        ""
        if pela_regra.empty
        else " Variantes aceitas pela regra qualificada para classificação conflitante (TCC 4.2.2): "
        + "; ".join(f"{r.gene} {r.nome_curto or r.id} — {r.nota_regra}" for r in pela_regra.itertuples())
        + "."
    )
    txt_regra = (
        " Classificação conflitante só sustenta risco pela regra qualificada: mais da metade das classificações "
        "patogênicas ou provavelmente patogênicas e fenótipo de ELA com herança declarada."
        if par.regra_conflitante
        else ""
    )
    tabelas = [
        relatorio.salvar_tabela(
            perfil,
            saida / "tabelas",
            "tabela_01_variantes_anotadas",
            "Tabela 1 — Variantes aprovadas no filtro de qualidade e sua anotação, por genitor",
            f"Registros lidos/aprovados: mãe {ing['mae']['registros']}/{ing['mae']['aprovados']}, pai {ing['pai']['registros']}/{ing['pai']['aprovados']}. "
            f"Reprovações: mãe {ing['mae']['por_motivo']}, pai {ing['pai']['por_motivo']}. Base de anotação: {fontes.get('base_real') or 'tabela curada'}"
            f"{' (' + str(fontes.get('n_real')) + ' variantes do ClinVar + ' + str(fontes.get('n_curada_extra')) + ' da tabela curada' + _fora_da_anotacao_txt(fontes) + ')' if fontes.get('base_real') else ''}.",
        )
    ]
    figs = []
    secoes = [
        (
            "Entrada",
            f"VCF materno: {_vcf_txt(vcf_mae, ing['mae'])}; VCF paterno: {_vcf_txt(vcf_pai, ing['pai'])}; "
            f"laudo do C9orf72: {_laudo_txt(laudo)}; sexo do descendente: {sexo or 'não informado'}; "
            f"idade atual sem sintomas: {idade_atual if idade_atual is not None else 'não informada'}; motor: {motor}; N = {_n(n)}; seed = {seed}; horizonte = {horizonte:.0f} anos.",
        ),
        (
            "Qualidade dos dados (TCC 4.2.3)",
            f"- Mãe: {_qualidade_ou_sem_exame(ind['mae'], com_vcf['mae'])}.\n"
            f"- Pai: {_qualidade_ou_sem_exame(ind['pai'], com_vcf['pai'])}.\n"
            + "".join(
                f"- {p.rotulo[0].upper() + p.rotulo[1:]}: {_texto_qualidade(anotacao.indicadores_qualidade(p.anotadas))}.\n"
                for p in pessoas
                if p.anotadas is not None
            )
            + f"- Base de anotação: {fontes.get('base_real') or 'apenas a tabela curada'}; "
            f"regra de classe: só Pathogenic/Likely pathogenic sustentam risco; significado incerto e classificações conflitantes não (TCC 4.2.2).{txt_regra}",
        ),
    ]
    meta_comum = dict(
        seed=seed,
        n=n,
        motor=motor,
        sexo=sexo,
        idade_atual=idade_atual,
        laudo_c9orf72=laudo or None,
        hipoteses_c9orf72=hip.como_dict() if hip is not None else None,
        transmissao_c9orf72=transmissao.resumo() if transmissao is not None else None,
        comparar_cox=comparar_cox,
        tornado=tornado,
        parametros=str(par.caminho),
        versao_parametros=par.versao,
        data_parametros=par.data,
        base_anotacao=fontes,
        vcf_mae=str(vcf_mae) if vcf_mae is not None else None,
        vcf_pai=str(vcf_pai) if vcf_pai is not None else None,
        montagem={"mae": ing["mae"]["montagem"], "pai": ing["pai"]["montagem"]},
        indicadores_qualidade=ind,
        loci_descartados=descartados.variante.tolist(),
        loci_regra_qualificada=[f"{r.gene} {r.nome_curto or r.id}" for r in pela_regra.itertuples()],
        regra_conflitante=par.regra_conflitante or None,
        saida_limpa=removidos,
    )
    if not vetor.empty:
        tabelas.append(
            relatorio.salvar_tabela(
                vetor,
                saida / "tabelas",
                "tabela_01b_vetor_dosagem",
                "Tabela 1b — Vetor genotípico parental: dosagem alélica (0/1/2) por lócus de risco e P(portador) exata; "
                "lócus com genótipo não determinado num genitor fica marcado como descartado e não entra no cálculo (TCC 4.3)",
            )
        )
    if transmissao is not None:
        tabelas.append(
            relatorio.salvar_tabela(
                transmissao.genotipos,
                saida / "tabelas",
                "tabela_01c_transmissao_c9orf72",
                "Tabela 1c — Transmissão do C9orf72 por repetições (hipótese experimental): genótipos possíveis do descendente, "
                "classe pelo limiar e probabilidade; dosagem efetiva por genitor",
                nota=repeticoes.ROTULO_EXPERIMENTAL,
            )
        )
    if uteis.empty:
        if descartados.empty:
            texto = (
                "Nenhum lócus de risco (classe patogênica/provavelmente patogênica) foi encontrado nos genes-alvo dos dois genitores. "
                "O risco de transmissão de variantes conhecidas é nulo neste recorte; o risco populacional de base não é modelado."
            )
        else:
            texto = (
                "Nenhum lócus de risco utilizável: os lóci de risco encontrados têm genótipo não determinado num dos genitores e foram descartados "
                "(TCC 4.3). O risco de transmissão dessas variantes não pode ser estimado sem um genótipo válido; o risco populacional de base não é modelado."
            )
        secoes.append(("Resultado", texto + nota_zona_cinzenta + nota_descarte + nota_regra))
        secoes.append(("Verificações", f"PyMC: {tempo_legivel(None)}; NumPy: {tempo_legivel(None)}."))
        if transmissao is not None:
            secoes.append(("Transmissão do C9orf72 por repetições (hipótese experimental)", transmissao.texto()))
        if familia is not None:
            secoes.append(("Genitor inferido por parentes", parentes_mod.texto_relatorio(vetor, [])))
        rel = relatorio.escrever_relatorio(saida, f"Relatório do artefato — {rotulo or 'caso'}", secoes, tabelas, figs)
        relatorio.escrever_metadados(
            saida,
            data=_dt.datetime.now().isoformat(timespec="seconds"),
            loci=0,
            tempo_motores_s={"pymc": None, "numpy": None},
            parentes=parentes_mod.resumo_metadados(vetor, []) if familia is not None else None,
            **meta_comum,
        )
        return {
            "saida": saida,
            "relatorio": rel,
            "vetor": vetor,
            "res": None,
            "tabelas": tabelas,
            "figuras": figs,
            "indicadores": ind,
            "transmissao_c9orf72": transmissao,
            "cox": None,
            "tornado": None,
            "parentes": parentes_mod.resumo_metadados(vetor, []) if familia is not None else None,
        }
    # Camada 2: Rede Bayesiana + Monte Carlo (motor principal + motor cruzado para a aderência)
    loci = loci_de_vetor(vetor, par, sexo=sexo, horizonte=horizonte)
    inferidos = [l for l in loci if l.inferencia is not None]
    if inferidos:
        tabelas.append(
            relatorio.salvar_tabela(
                parentes_mod.tabela_parentes(vetor, loci),
                saida / "tabelas",
                "tabela_01d_genitor_inferido",
                "Tabela 1d — Genitor inferido por parentes: parentes considerados e dosagem de cada um, e distribuição "
                "da dosagem do genitor só com os genótipos e depois do condicionamento pela situação clínica dele",
                "A penetrância é compartilhada pela família: o condicionamento atualiza ao mesmo tempo a dosagem do "
                "genitor e a penetrância do gene (colunas a priori e a posteriori).",
            )
        )
    mediana_c9_antes = next((l.dist.mediana for l in loci if l.gene == genotipo.GENE_EXPANSAO), None)
    if hip is not None and hip.antecipacao:
        loci = repeticoes.aplicar_antecipacao(loci, hip.antecipacao)
    mediana_c9_depois = next((l.dist.mediana for l in loci if l.gene == genotipo.GENE_EXPANSAO), None)
    principal = simular_pymc if motor == "pymc" else simular_numpy
    cruzado = simular_numpy if motor == "pymc" else simular_pymc
    res = principal(loci, n=n, seed=seed)
    res_x = cruzado(loci, n=n, seed=seed)
    nome_cruzado = "numpy" if motor == "pymc" else "pymc"
    tempos_motores = {motor: res.tempo_s, nome_cruzado: res_x.tempo_s}
    tempos_texto = "; ".join(f"{nome}: {tempo_legivel(tempo)}" for nome, tempo in tempos_motores.items())
    res.sexo = res_x.sexo = sexo
    resumo = res.resumo()
    comb = res.resumo_combinado()
    ader = avaliacao.aderencia(res if motor == "pymc" else res_x, res_x if motor == "pymc" else res)
    tabelas.append(
        relatorio.salvar_tabela(
            ader,
            saida / "tabelas",
            "tabela_02_aderencia",
            "Tabela 2 — Aderência teórica: probabilidades exatas vs Monte Carlo (PyMC e NumPy), erro padrão e qui-quadrado do genótipo do descendente",
        )
    )
    risco = resumo[
        [
            "gene",
            "variante",
            "heranca",
            "dosagem_mae",
            "dosagem_pai",
            "p_portador_exato",
            "p_portador_mc",
            "penetrancia_media",
            "penetrancia_q025",
            "penetrancia_q975",
            "p_manifesta_exato",
            "p_manifesta_mc",
            "p_manifesta_q025",
            "p_manifesta_q975",
            "p_manifesta_sem_limite",
            "idade_mediana_exata",
            "idade_mediana_mc",
            "idade_p10_mc",
            "idade_p90_mc",
        ]
    ].copy()
    risco.loc[len(risco)] = {
        "gene": "—",
        "variante": sobrevivencia.QUALQUER,
        "heranca": "independência",
        "dosagem_mae": "",
        "dosagem_pai": "",
        "p_portador_exato": comb["p_portador_qualquer_exato"],
        "p_portador_mc": comb["p_portador_qualquer_mc"],
        "penetrancia_media": np.nan,
        "penetrancia_q025": np.nan,
        "penetrancia_q975": np.nan,
        "p_manifesta_exato": comb["p_manifesta_qualquer_exato"],
        "p_manifesta_mc": comb["p_manifesta_qualquer_mc"],
        "p_manifesta_q025": comb["p_manifesta_qualquer_q025"],
        "p_manifesta_q975": comb["p_manifesta_qualquer_q975"],
        "p_manifesta_sem_limite": comb["p_manifesta_qualquer_sem_limite"],
        "idade_mediana_exata": np.nan,
        "idade_mediana_mc": comb["idade_mediana_primeiro_inicio"],
        "idade_p10_mc": np.nan,
        "idade_p90_mc": np.nan,
    }
    tabelas.append(
        relatorio.salvar_tabela(
            risco.rename(columns={"p_manifesta_sem_limite": COLUNA_SEM_LIMITE}),
            saida / "tabelas",
            "tabela_03_risco_vitalicio",
            f"Tabela 3 — Probabilidade de transmissão (portador), penetrância e risco vitalício de manifestação (até o horizonte de {horizonte:.0f} anos) por lócus e combinado, com intervalo de credibilidade de 95% (incerteza da penetrância) e idade de início",
            f'p_manifesta_* = risco vitalício: probabilidade de manifestar até os {horizonte:.0f} anos. A coluna "{COLUNA_SEM_LIMITE}" é '
            "F(∞) = P(portador)·E[π], usada só nas verificações de coerência.",
        )
    )

    # Camada 3: sobrevivência
    curvas = sobrevivencia.curvas_analiticas(res, horizonte)
    curvas.to_csv(saida / "curvas.csv", index=False)
    cond = sobrevivencia.tabela_risco_condicional(res, idades_atuais=_idades_tabela_4(idade_atual), horizonte=horizonte)
    tabelas.append(
        relatorio.salvar_tabela(
            cond,
            saida / "tabelas",
            "tabela_04_risco_condicional",
            f"Tabela 4 — Risco condicional à idade atual sem sintomas: P(portador | assintomático), risco nos próximos 10 e 20 anos e risco residual (da idade atual até os {horizonte:.0f} anos), com banda de 95%",
            "risco_residual: probabilidade de manifestar entre a idade atual e o horizonte, para quem chegou a essa idade "
            "sem sintomas. Na idade 0 é o risco vitalício da Tabela 3.",
        )
    )
    # indicadores principais condicionados à idade atual (mesmo cálculo exato da Tabela 4, na idade do atendido)
    condicionado = (
        sobrevivencia.indicadores_condicionados(res, idade_atual, horizonte)
        if idade_atual is not None and idade_atual > 0
        else None
    )
    km = sobrevivencia.tabela_km(res, horizonte)
    tabelas.append(
        relatorio.salvar_tabela(
            km,
            saida / "tabelas",
            "tabela_10_kaplan_meier",
            "Tabela 10 — Sobrevivência (assintomático) estimada por Kaplan-Meier na coorte simulada, com IC 95% (Greenwood); mediana não atingida quando o risco vitalício é inferior a 50%",
        )
    )
    rec = sobrevivencia.recuperacao_parametros(res, horizonte)
    tabelas.append(
        relatorio.salvar_tabela(
            rec,
            saida / "tabelas",
            "tabela_07_recuperacao_lifelines",
            "Tabela 7 — Recuperação dos parâmetros de entrada (π, λ, ρ) pelo ajustador de cura mista da Lifelines na coorte simulada de portadores",
        )
    )
    cox = comparacao.comparar(res, par, horizonte) if comparar_cox else None
    if cox is not None and not cox["tabela"].empty:
        tabelas.append(
            relatorio.salvar_tabela(
                cox["tabela"],
                saida / "tabelas",
                "tabela_11_cox_vs_cura_mista",
                "Tabela 11 — Modelo de Cox (CoxPHFitter) na coorte sintética de portadores: razões de risco, concordância, "
                "teste de riscos proporcionais e S(t) por Cox, cura mista, Kaplan-Meier e curva analítica",
            )
        )
    tab_tornado = avaliacao.tornado(vetor, par, sexo, horizonte, idade_atual) if tornado else None
    if tab_tornado is not None and not tab_tornado.empty:
        fora = tab_tornado.attrs.get("fora_do_tornado") or []
        tabelas.append(
            relatorio.salvar_tabela(
                tab_tornado,
                saida / "tabelas",
                "tabela_20_tornado",
                "Tabela 20 — Sensibilidade tipo tornado: um parâmetro por vez dentro da faixa publicada, com a variação do "
                + ("risco residual" if idade_atual is not None else "risco vitalício combinado")
                + " e da idade mediana de início",
                "Valores exatos; toda faixa vem de fonte publicada (coluna `fonte`). Fora do tornado, por não haver "
                "incerteza publicada: " + ("; ".join(fora) if fora else "nenhum gene deste caso") + ".",
            )
        )
    extra = ""
    if idade_atual is not None:
        res_c = res.condicionar_idade(idade_atual)
        kmc = sobrevivencia.risco_condicional_km(res, idade_atual, horizonte)
        tabelas.append(
            relatorio.salvar_tabela(
                kmc,
                saida / "tabelas",
                "tabela_04b_risco_condicional_km",
                f"Tabela 4b — Risco condicional não paramétrico (Kaplan-Meier) para um descendente assintomático aos {idade_atual:.0f} anos",
            )
        )
        ex_c = condicionado or sobrevivencia.indicadores_condicionados(res, idade_atual, horizonte)
        rr, ini = ex_c["risco_residual"], ex_c["inicio"]
        extra = (
            f" Condicionando ao descendente assintomático aos {idade_atual:.0f} anos, P(portador de ≥ 1 lócus) passa de "
            f"{_p(comb['p_portador_qualquer_exato'])} para {_p(ex_c['p_portador'])} e o risco residual (da idade atual até os {horizonte:.0f} anos) é "
            f"{_p(rr['valor'])} [{_p(rr['q025'])}–{_p(rr['q975'])}]"
            + (
                f"; idade provável de início a partir dessa idade: mediana {ini['mediana']:.1f} anos "
                f"(25–75 %: {ini['q25']:.1f}–{ini['q75']:.1f})"
                if ini.get("mediana") is not None
                else ""
            )
            + f". Valores exatos, os mesmos da Tabela 4 e dos indicadores; conferência por rejeição de {_n(res.n - res_c.n)} sorteios do "
            f"Monte Carlo: {_p(res_c.portador.any(axis=1).mean())} e {_p(res_c.manifesta_qualquer_h.mean())}."
        )

    # Figuras
    if figuras:
        figs.append(relatorio.figura_dag(loci, saida / "figuras" / "figura_01_dag.png"))
        figs.append(
            relatorio.figura_risco_temporal(
                curvas, res, saida / "figuras" / "figura_04_risco_temporal.png", horizonte, rotulo
            )
        )
        figs.append(relatorio.figura_aderencia(ader, saida / "figuras" / "figura_06_aderencia.png"))
        figs.append(relatorio.figura_hazard(curvas, saida / "figuras" / "figura_08_hazard.png"))
        figs.append(
            relatorio.figura_idade_inicio(
                {sexo or "—": res},
                saida / "figuras" / "figura_05_idade_inicio.png",
                legenda="Figura 5 — Distribuição simulada da idade de início entre os descendentes que manifestam, por lócus",
            )
        )
        if cox is not None and cox["curvas"] is not None:
            figs.append(
                comparacao.figura_cox_vs_cura_mista(
                    cox["curvas"], saida / "figuras" / "figura_09_cox_vs_cura_mista.png"
                )
            )
        if tab_tornado is not None and not tab_tornado.empty:
            figs.append(
                relatorio.figura_tornado({rotulo or "caso": tab_tornado}, saida / "figuras" / "figura_12_tornado.png")
            )

    # Texto do relatório
    linhas = [
        f"- **{l.variante}** ({l.heranca}; dosagens mãe/pai {_dose_txt(l.dosagem_mae)}/{_dose_txt(l.dosagem_pai)}): P(portador) = {_p(l.p_portador_exato)} (MC {_p(l.p_portador_mc)}); "
        f"penetrância média {_p(l.penetrancia_media)} [{_p(l.penetrancia_q025)}–{_p(l.penetrancia_q975)}]; risco vitalício (até os {horizonte:.0f} anos) {_p(l.p_manifesta_exato)} "
        f"[{_p(l.p_manifesta_q025)}–{_p(l.p_manifesta_q975)}]; idade mediana de início {l.idade_mediana_exata:.1f} anos (p10–p90 MC: {l.idade_p10_mc:.0f}–{l.idade_p90_mc:.0f})."
        for _, l in resumo.iterrows()
    ]
    linhas.append(
        f"- **Combinado (qualquer lócus, independência)**: P(portador de ≥ 1) = {_p(comb['p_portador_qualquer_exato'])}; risco vitalício (até os {horizonte:.0f} anos) {_p(comb['p_manifesta_qualquer_exato'])} "
        f"[{_p(comb['p_manifesta_qualquer_q025'])}–{_p(comb['p_manifesta_qualquer_q975'])}]; idade mediana do primeiro início {comb['idade_mediana_primeiro_inicio']:.1f} anos."
    )
    limite_inferior = familia is not None and any(
        familia.lado(n) is not None and familia.lado(n).situacao == "afetado" for n in parentes_mod.LADOS
    )
    nota_limite = (
        f" Resultado rotulado como {parentes_mod.LIMITE_INFERIOR_AFETADO} (o genitor sem exame é afetado, o que "
        "torna a variante nele mais provável do que o cálculo considera)."
        if limite_inferior and inferidos
        else ""
    )
    secoes.append(
        ("Resultado", "\n".join(linhas) + extra + nota_limite + nota_zona_cinzenta + nota_descarte + nota_regra)
    )
    if familia is not None:
        secoes.append(("Genitor inferido por parentes", parentes_mod.texto_relatorio(vetor, loci)))
    if transmissao is not None:
        secoes.append(
            (
                "Transmissão do C9orf72 por repetições (hipótese experimental)",
                transmissao.texto(mediana_c9_antes, mediana_c9_depois),
            )
        )
    if cox is not None:
        secoes.append(("Comparação com o modelo de Cox (CoxPHFitter)", cox["texto"]))
    if tab_tornado is not None and not tab_tornado.empty:
        topo = tab_tornado.iloc[0]
        fora = tab_tornado.attrs.get("fora_do_tornado") or []
        secoes.append(
            (
                "Sensibilidade tipo tornado",
                "Um parâmetro por vez, dentro da faixa publicada, com os demais no valor de base (Tabela 20"
                + (", Figura 12" if figuras else "")
                + f"). Maior efeito no risco: {topo.parametro}, de {_p(min(topo.risco_baixo, topo.risco_alto))} a "
                f"{_p(max(topo.risco_baixo, topo.risco_alto))} (base {_p(topo.risco_base)}). "
                + (
                    "Fora do tornado, por não haver incerteza publicada: " + "; ".join(fora) + "."
                    if fora
                    else "Todos os genes do caso têm faixa publicada."
                ),
            )
        )
    desvio_max = float(np.nanmax(ader[["desvio_manifesta_pymc_em_ep", "desvio_manifesta_numpy_em_ep"]].values))
    # o modelo de cura mista só é ajustado com ≥ 10 eventos e ≥ 1 censura por lócus (sobrevivencia.ajustar_mistura_cura):
    # com N pequeno a Lifelines pode não ajustar nenhum lócus e a coluna erro_rel_pi não existe
    erro_pi = (
        float(rec["erro_rel_pi"].max())
        if "erro_rel_pi" in rec.columns and rec["erro_rel_pi"].notna().any()
        else float("nan")
    )
    txt_rec = (
        f"erro relativo máximo em π = {erro_pi:.1%}"
        if np.isfinite(erro_pi)
        else "modelo de cura mista não ajustado em nenhum lócus (menos de 10 eventos ou nenhuma censura na coorte de portadores; aumente N)"
    )
    secoes.append(
        (
            "Verificações",
            f"Aderência: maior desvio entre Monte Carlo e valor exato = {desvio_max:.2f} erros padrão (limite usual: 4). "
            f"Coerência: risco vitalício por Kaplan-Meier = {', '.join(f'{r.unidade}: {_p(r.risco_vitalicio_km)}' for r in km.itertuples())}. "
            f"Recuperação Lifelines: {txt_rec}. Tempo: {time.perf_counter() - t_ini:.1f} s no total "
            f"({tempos_texto}).",
        )
    )
    provis = [g.nome for g in par.genes.values() if g.pen_confirmar or g.inicio_confirmar]
    # variante que a estimativa de penetrância do gene não cobre (YAML `penetrancia_excecoes`) → limitação declarada
    excecoes = []
    for _, l in uteis.iterrows():  # casa pelo nome da proteína (ClinVar) ou pelo rs (tabela curada: "D90A (p.D91A)")
        for exc in par.genes[l.gene].extras.get("penetrancia_excecoes") or []:
            variante, rs = str(exc.get("variante") or ""), str(exc.get("rs") or "")
            if (variante and variante in str(l.variante)) or (rs and rs == str(l.rs)):
                excecoes.append(
                    f"{l.gene} {l.variante}: {exc.get('nota', '')} (confirmar: {str(exc.get('confirmar', True)).lower()})"
                )
    info_parentes = parentes_mod.resumo_metadados(vetor, loci) if familia is not None else None
    secoes.append(
        (
            "Limitações desta execução",
            f"Parâmetros provisórios (confirmar: true) em: {', '.join(provis) or 'nenhum'}. Independência entre lóci; sem fatores modificadores; "
            "penetrância populacional de coortes europeias/norte-americanas; dados sintéticos."
            + (" Aproximação de penetrância: " + "; ".join(excecoes) + "." if excecoes else "")
            + (
                " Genitor inferido por parentes: só genótipos entram (o fenótipo de parente sem teste genético fica "
                "fora) e a variante dos parentes é suposta herdada."
                if inferidos
                else ""
            ),
        )
    )
    rel = relatorio.escrever_relatorio(saida, f"Relatório do artefato — {rotulo or 'caso'}", secoes, tabelas, figs)
    relatorio.escrever_metadados(
        saida,
        data=_dt.datetime.now().isoformat(timespec="seconds"),
        horizonte=horizonte,
        tabela_variantes=str(tabela_variantes or anotacao.CAMINHO_TABELA),
        loci=[l.rotulo for l in loci],
        indicadores_condicionados=condicionado,
        parentes=info_parentes,
        limite_inferior=bool(limite_inferior and inferidos),
        sorteios_rejeitados=(res.sorteados - res.n) if res.sorteados is not None else None,
        tempo_motores_s=tempos_motores,
        tempo_total_s=round(time.perf_counter() - t_ini, 2),
        **meta_comum,
    )
    return {
        "saida": saida,
        "relatorio": rel,
        "vetor": vetor,
        "loci": loci,
        "res": res,
        "res_cruzado": res_x,
        "resumo": resumo,
        "combinado": comb,
        "condicionado": condicionado,
        "horizonte": horizonte,
        "parentes": info_parentes,
        "limite_inferior": bool(limite_inferior and inferidos),
        "aderencia": ader,
        "curvas": curvas,
        "tabelas": tabelas,
        "figuras": figs,
        "indicadores": ind,
        "transmissao_c9orf72": transmissao,
        "cox": cox,
        "tornado": tab_tornado,
    }


def avaliar(
    dir_cenarios,
    saida,
    numeros=None,
    ns=(1_000, 10_000, 100_000),
    repeticoes: int = 30,
    seed: int = 1000,
    sexo: str = "F",
    n_coerencia: int = 10_000,
    config=None,
    base_clinvar=None,
    metricas: bool = True,
    mundos: int = 200,
    por_estrato: int = 10,
    seed_coorte: int | None = None,
) -> dict:
    """Avaliação transversal dos cenários: estabilidade, tempo, coerência, calibração e sensibilidade (Tabelas 5 a 9) e,
    com `metricas`, a verificação com famílias sintéticas de desfecho conhecido (Tabelas 12 a 20; Figuras 10 a 12):
    calibração, discriminação, erro da idade de início, cobertura, divergência entre curvas, robustez a erros no VCF e
    tornado. `mundos` e `por_estrato` dimensionam a coorte; `seed_coorte` é a semente própria dela, independente da
    semente das previsões (padrão: derivada de `seed`).
    Cenários sem lócus de risco na base de anotação usada (ex.: variante com classificação conflitante no ClinVar) são pulados e listados.
    """
    saida = Path(saida)
    removidos = _limpar_saida(saida, ARTEFATOS_AVALIACAO)
    (saida / "tabelas").mkdir(parents=True, exist_ok=True)
    (saida / "figuras").mkdir(exist_ok=True)
    par = carregar_parametros(config)
    dir_cenarios = Path(dir_cenarios)
    numeros = numeros or [c.numero for c in cenarios.CENARIOS]
    tabela = anotacao.tabela_anotacao(base_real=base_clinvar, regra=par.regra_conflitante)
    regioes = ingestao.carregar_regioes()
    brutos, resumos, tempos, coer, sens, recs, pulados = [], [], [], [], [], [], []
    vetores, loci_por_cenario, res_por_cenario = {}, {}, {}
    for num in numeros:
        c = cenarios.cenario_por_numero(num)
        mae = anotacao.anotar(
            ingestao.ler_vcf(cenarios.vcf_cenario(dir_cenarios, num, "mae"), regioes, par.filtro_qualidade),
            tabela,
            par.limiar_repeticoes,
        )
        pai = anotacao.anotar(
            ingestao.ler_vcf(cenarios.vcf_cenario(dir_cenarios, num, "pai"), regioes, par.filtro_qualidade),
            tabela,
            par.limiar_repeticoes,
        )
        vetor = genotipo.vetor_dosagem(mae, pai, par, laudo_c9orf72=c.laudo_c9orf72, tabela=tabela)
        if vetor[~vetor.descartado].empty:
            pulados.append(num)
            continue
        loci = loci_de_vetor(vetor, par, sexo=sexo)
        rot = f"cenário {num}"
        bruto, resumo = avaliacao.estabilidade(loci, ns=ns, repeticoes=repeticoes, seed_inicial=seed)
        bruto.insert(0, "cenario", rot)
        resumo.insert(0, "cenario", rot)
        brutos.append(bruto)
        resumos.append(resumo)
        t = avaliacao.tempos(loci, ns=ns)
        t.insert(0, "cenario", rot)
        tempos.append(t)
        res = simular_pymc(loci, n=n_coerencia, seed=seed)
        vetores[rot], loci_por_cenario[rot], res_por_cenario[rot] = vetor, loci, res
        co = avaliacao.coerencia(res, par.horizonte_anos)
        co.insert(0, "cenario", rot)
        coer.append(co)
        s = avaliacao.sensibilidade(vetor, par, sexo, n=n_coerencia, seed=seed)
        s.insert(0, "cenario", rot)
        sens.append(s)
    bruto = pd.concat(brutos, ignore_index=True)
    bruto.to_csv(saida / "estabilidade_execucoes.csv", index=False)
    resumo = pd.concat(resumos, ignore_index=True)
    cols_res = [
        "cenario",
        "motor",
        "n",
        "repeticoes",
        "p_manifesta_qualquer_exato",
        "p_manifesta_qualquer_media",
        "p_manifesta_qualquer_dp",
        "ep_teorico",
        "razao_dp_ep",
        "idade_mediana_media",
        "idade_mediana_dp",
        "tempo_medio_s",
    ]
    tabelas = [
        relatorio.salvar_tabela(
            resumo[cols_res],
            saida / "tabelas",
            "tabela_05_estabilidade",
            f"Tabela 5 — Estabilidade numérica: média e desvio padrão de P(manifestação) e da idade mediana entre {repeticoes} execuções com sementes distintas, por N, vs erro padrão teórico √(p(1−p)/N)",
            "DP/EP próximo de 1 indica que a variabilidade entre execuções é a esperada para o Monte Carlo; o DP cai por ≈√10 a cada década de N.",
        ),
        relatorio.salvar_tabela(
            par.tabela_calibracao(),
            saida / "tabelas",
            "tabela_06_calibracao",
            "Tabela 6 — Calibração das distribuições de penetrância (Beta e log-normal truncada em 1) e das distribuições de idade de início a partir da literatura",
            "valor_provisorio = sim: parâmetro marcado com confirmar: true no YAML, a validar na literatura. "
            "massa_truncada_lognormal: fração da log-normal acima de 1, retirada pelo truncamento.",
        ),
        relatorio.salvar_tabela(
            pd.concat(coer, ignore_index=True),
            saida / "tabelas",
            "tabela_07_coerencia",
            "Tabela 7 — Coerência das curvas: risco vitalício exato (até o horizonte) vs Kaplan-Meier, fração que manifesta em algum momento (sem limite de idade) vs a recuperada pelo modelo de cura mista, medianas de início (exata vs Weibull da Lifelines), parâmetros recuperados e idade do pico de h(t) por lócus e para o risco combinado",
            "A faixa de incidência populacional 60–75 anos (FELDMAN et al., 2022) é comparada só com o pico do risco combinado (linha 'qualquer lócus'); "
            "o pico de cada variante é propriedade da sua distribuição de início e não é critério de aprovação.",
        ),
        relatorio.salvar_tabela(
            pd.concat(tempos, ignore_index=True),
            saida / "tabelas",
            "tabela_08_tempos",
            "Tabela 8 — Tempo de processamento por motor (PyMC e NumPy) e por N, em segundos (média de execuções sucessivas)",
        ),
        relatorio.salvar_tabela(
            pd.concat(sens, ignore_index=True),
            saida / "tabelas",
            "tabela_09_sensibilidade",
            "Tabela 9 — Análise de sensibilidade: risco vitalício e idade mediana sob a calibração pela literatura, sob a distribuição alternativa da penetrância (log-normal truncada em 1), sob os parâmetros do exemplo do orientador e sob penetrância de coorte familiar para o C9orf72",
        ),
    ]
    figs = [
        relatorio.figura_priors(par, saida / "figuras" / "figura_02_priors.png"),
        relatorio.figura_curvas_inicio(par, saida / "figuras" / "figura_03_curvas_inicio.png"),
        relatorio.figura_estabilidade(resumo, saida / "figuras" / "figura_07_estabilidade.png"),
    ]
    verificacao = None
    if metricas:
        verificacao = _verificacao(
            saida,
            dir_cenarios,
            [n for n in numeros if n not in pulados],
            par,
            tabela,
            regioes,
            vetores,
            loci_por_cenario,
            res_por_cenario,
            sexo,
            n_coerencia,
            seed,
            mundos,
            por_estrato,
            seed_coorte if seed_coorte is not None else seed + 104_729,
        )
        tabelas += verificacao["tabelas"]
        figs += verificacao["figuras"]
    tt = pd.concat(tempos)
    fontes = tabela.attrs.get("fontes", {})
    co_all = pd.concat(coer, ignore_index=True)
    comb = co_all[co_all.variante == sobrevivencia.QUALQUER]
    picos = "; ".join(f"{r.cenario}: {r.idade_pico_hazard:.1f} anos" for r in comb.itertuples())
    n_faixa = int(comb.pico_combinado_na_faixa_60_75.astype(bool).sum())
    secoes = [
        (
            "Configuração",
            f"Cenários {[n for n in numeros if n not in pulados]}; N ∈ {list(ns)}; {repeticoes} repetições por N; seed inicial {seed}; sexo do descendente {sexo}; "
            f"coerência e sensibilidade com N = {_n(n_coerencia)}. Base de anotação: {fontes.get('base_real') or 'tabela curada'}."
            + (f" Cenários sem lócus de risco nesta base (pulados): {pulados}." if pulados else ""),
        ),
        (
            "Leitura",
            f"Razão DP/EP média = {resumo.razao_dp_ep.mean():.2f}. Idade do pico de h(t) do risco combinado por cenário: {picos}; "
            f"{n_faixa} de {len(comb)} dentro da faixa de incidência populacional 60–75 anos (FELDMAN et al., 2022), que é referência e não critério de "
            f"aprovação: variantes de início precoce (SOD1 p.Ala5Val, FUS) têm pico antes dela. "
            f"Tempo médio PyMC para N = {_n(max(ns))}: {tt[(tt.motor == 'pymc') & (tt.n == max(ns))].tempo_medio_s.mean():.2f} s; NumPy: {tt[(tt.motor == 'numpy') & (tt.n == max(ns))].tempo_medio_s.mean():.3f} s.",
        ),
    ]
    if verificacao is not None:
        secoes += verificacao["secoes"]
    rel = relatorio.escrever_relatorio(saida, "Avaliação do artefato (TCC 4.5)", secoes, tabelas, figs)
    relatorio.escrever_metadados(
        saida,
        data=_dt.datetime.now().isoformat(timespec="seconds"),
        seed=seed,
        ns=list(ns),
        repeticoes=repeticoes,
        sexo=sexo,
        cenarios=numeros,
        cenarios_pulados=pulados,
        base_anotacao=fontes,
        saida_limpa=removidos,
        verificacao=verificacao["metadados"] if verificacao is not None else None,
    )
    return {
        "saida": saida,
        "relatorio": rel,
        "estabilidade": resumo,
        "tempos": pd.concat(tempos),
        "coerencia": pd.concat(coer),
        "sensibilidade": pd.concat(sens),
        "tabelas": tabelas,
        "figuras": figs,
        "pulados": pulados,
        "verificacao": verificacao["dados"] if verificacao is not None else None,
    }


def _verificacao(
    saida: Path,
    dir_cenarios: Path,
    numeros: list,
    par,
    tabela,
    regioes,
    vetores: dict,
    loci_por_cenario: dict,
    res_por_cenario: dict,
    sexo: str,
    n: int,
    seed: int,
    mundos: int,
    por_estrato: int,
    seed_coorte: int,
) -> dict:
    """Verificação com famílias sintéticas de desfecho conhecido (Tabelas 12 a 20 e Figuras 10 a 12 da avaliação)."""
    tmp = saida / "_verificacao_tmp"
    h = float(par.horizonte_anos)
    # um cenário com genitor sem exame entra na mistura, para que a coorte cubra também a extensão de parentes
    casos = dict(vetores)
    caso_p = cenarios.gerar_cenarios_parentes(tmp / "parentes")[0]
    familia = parentes_mod.Familia.de(caso_p["parentes"])
    lidos = {}
    for lado in ("mae", "pai"):
        caminho = caso_p[f"vcf_{lado}"] or cenarios.escrever_vcf_sem_variantes(
            tmp / "parentes" / f"_{lado}_sem_exame.vcf", f"{lado.upper()}_SEM_EXAME"
        )
        lidos[lado] = anotacao.anotar(
            ingestao.ler_vcf(caminho, regioes, par.filtro_qualidade), tabela, par.limiar_repeticoes
        )
    rot_p = f"cenário de parentes {caso_p['numero']}"
    casos[rot_p] = parentes_mod.vetor_familia(
        lidos["mae"],
        lidos["pai"],
        par,
        caso_p["laudo_c9orf72"],
        tabela,
        familia,
        parentes_mod.ler_familia(familia, par, tabela, regioes),
        {lado: caso_p[f"vcf_{lado}"] is not None for lado in ("mae", "pai")},
    )
    loci_casos = dict(loci_por_cenario)
    loci_casos[rot_p] = loci_de_vetor(casos[rot_p], par, sexo=sexo)
    estratos = avaliacao.montar_estratos(casos, par)
    verd = avaliacao.verdades(par)
    comp, bri, cal, disc, erro, bandas, diverg, curvas_cal = [], [], [], [], [], [], [], {}
    for k, v in enumerate(verd):
        coorte = avaliacao.coorte_de_mundos(estratos, par, v, mundos=mundos, por_estrato=por_estrato, seed=seed_coorte)
        comp.append(avaliacao.descricao_coorte(estratos, coorte, v))
        for destino, tab in (
            (bri, avaliacao.brier(coorte)),
            (cal, avaliacao.curva_calibracao(coorte)),
            (disc, avaliacao.discriminacao(coorte)),
            (erro, avaliacao.erro_idade_inicio(coorte)),
        ):
            tab.insert(0, "verdade", v.rotulo)
            destino.append(tab)
        curvas_cal[v.rotulo] = cal[-1]
        bandas.append(
            avaliacao.cobertura_bandas(
                loci_casos,
                par,
                v,
                sexo=sexo,
                mundos=mundos,
                n_banda=n,
                seed_banda=seed,
                seed_mundos=seed_coorte + 1 + k,
            )
        )
        for rot, vetor in vetores.items():
            if v.nome == "modelo":  # sorteios do próprio artefato contra a curva teórica do modelo
                d = avaliacao.divergencia_curvas(
                    res_por_cenario[rot], None, h, "sorteios do artefato (verdade = modelo)"
                )
            else:  # mundo alternativo simulado contra a curva teórica do modelo
                alt = simular_numpy(avaliacao.loci_da_verdade(vetor, par, v, sexo, h), n=n, seed=seed_coorte + 50 + k)
                d = avaliacao.divergencia_curvas(alt, loci_por_cenario[rot], h, v.rotulo)
            d.insert(0, "cenario", rot)
            diverg.append(d)
    cob_mc = avaliacao.cobertura_monte_carlo(loci_casos, n=n, repeticoes=mundos, seed=seed_coorte + 10_000)
    robustez = avaliacao.robustez_vcf(dir_cenarios, numeros, par, tabela, tmp / "robustez", sexo)
    tornados = {rot: avaliacao.tornado(vetor, par, sexo, h) for rot, vetor in vetores.items()}
    fora = sorted({x for t in tornados.values() for x in t.attrs.get("fora_do_tornado", [])})
    tab_tornado = pd.concat([t.assign(cenario=rot) for rot, t in tornados.items()], ignore_index=True)
    tab_tornado = tab_tornado[["cenario"] + [c for c in tab_tornado.columns if c != "cenario"]]
    shutil.rmtree(tmp, ignore_errors=True)
    dados = {
        "coorte": pd.concat(comp, ignore_index=True),
        "brier": pd.concat(bri, ignore_index=True),
        "calibracao": pd.concat(cal, ignore_index=True),
        "discriminacao": pd.concat(disc, ignore_index=True),
        "erro_idade": pd.concat(erro, ignore_index=True),
        "cobertura_mc": cob_mc,
        "cobertura_bandas": pd.concat(bandas, ignore_index=True),
        "divergencia": pd.concat(diverg, ignore_index=True),
        "robustez": robustez,
        "tornado": tab_tornado,
    }
    nota_verificacao = "Verificação, não validação: " + avaliacao.ENQUADRAMENTO
    t_dir = saida / "tabelas"
    tabelas = [
        relatorio.salvar_tabela(
            dados["coorte"],
            t_dir,
            "tabela_12_coorte_verificacao",
            f"Tabela 12 — Coorte sintética de verificação: {mundos} mundos, {por_estrato} pessoas sorteadas por estrato e mundo (cenário × sexo × idade atual de 0 a 70 anos) e desfecho verdadeiro conhecido, por verdade e cenário",
            nota_verificacao
            + " Entram na coorte as pessoas que chegam sem sintomas à idade atual (e, com genitor inferido, as de "
            "famílias compatíveis com a evidência), de modo que cada mundo pesa pelo quanto é compatível com o que se "
            f"observa. Semente própria da coorte: {seed_coorte} (independente da semente das previsões, {seed}).",
        ),
        relatorio.salvar_tabela(
            dados["brier"],
            t_dir,
            "tabela_13_brier",
            "Tabela 13 — Brier score das previsões a 10 e 20 anos a partir da idade atual e até o horizonte, com verdade = modelo e com verdades alternativas",
            "brier_referencia = p̄(1 − p̄), de quem prevê a prevalência para todos; habilidade = 1 − Brier/referência.",
        ),
        relatorio.salvar_tabela(
            dados["calibracao"],
            t_dir,
            "tabela_14_calibracao_decis",
            "Tabela 14 — Curva de calibração: risco previsto médio contra fração observada por decil de risco previsto",
        ),
        relatorio.salvar_tabela(
            dados["discriminacao"],
            t_dir,
            "tabela_15_discriminacao",
            "Tabela 15 — Discriminação: C-index de Harrell e AUC dependente do tempo a 10 e 20 anos",
            "Tempo contado a partir da idade atual, com censura no horizonte. A verdade sintética não tem censura além "
            "do horizonte e as idades atuais vão até 70 anos, por isso a AUC não precisa de ponderação pela censura.",
        ),
        relatorio.salvar_tabela(
            dados["erro_idade"],
            t_dir,
            "tabela_16_erro_idade_inicio",
            "Tabela 16 — Erro absoluto médio da idade de início prevista (mediana condicional à idade atual) entre quem manifesta, por gene, com o piso teórico",
            "Piso teórico: desvio absoluto médio da distribuição de início em torno da sua mediana, condicionado à idade "
            "atual. Um modelo perfeito não fica abaixo dele, porque a idade de início é aleatória; razões um pouco "
            "abaixo de 1 são flutuação amostral (compare com `erro_padrao_anos`). Nos casos com dois lóci, a "
            "distribuição de cada gene é a do início daquele gene quando ele é o primeiro.",
        ),
        relatorio.salvar_tabela(
            dados["cobertura_mc"],
            t_dir,
            "tabela_17_cobertura_monte_carlo",
            f"Tabela 17 — Cobertura dos intervalos de 95 % do Monte Carlo: fração de {mundos} sementes em que o intervalo de P(portador) e de P(manifesta) contém o valor exato",
        ),
        relatorio.salvar_tabela(
            dados["cobertura_bandas"],
            t_dir,
            "tabela_17b_cobertura_bandas",
            "Tabela 17b — Cobertura das bandas de F(t): fração dos mundos em que o F(t) empírico do mundo cai dentro da banda de 95 % do artefato, aos 50, 60 e 70 anos",
            "Com verdade = modelo a cobertura fica perto de 95 % por construção (um pouco abaixo, pelo ruído amostral do "
            "F empírico de cada mundo); com a verdade alternativa aparece a subcobertura. `cobertura_sem_ruido_amostral` "
            "usa a F exata de cada mundo no lugar da empírica e mostra quanto da diferença é só ruído, que pesa mais "
            "onde a banda é estreita (genitor inferido). Com genitor inferido, cada mundo pesa pela probabilidade de a "
            "família ser compatível com a evidência.",
        ),
        relatorio.salvar_tabela(
            dados["divergencia"],
            t_dir,
            "tabela_18_divergencia_curvas",
            "Tabela 18 — Divergência entre curvas: distância de Kolmogorov-Smirnov entre o F(t) empírico e o teórico em [0, horizonte] e distância de Wasserstein (anos) entre as distribuições de idade de início dos que manifestam",
            "ks_referencia_amostral = 1,36/√N: ordem de grandeza do KS só por flutuação amostral.",
        ),
        relatorio.salvar_tabela(
            dados["robustez"],
            t_dir,
            "tabela_19_robustez_vcf",
            "Tabela 19 — Robustez a erros no VCF: variação de P(portador de ≥ 1 lócus) e do risco vitalício sob perturbações controladas, e o que o artefato reporta em cada caso",
        ),
        relatorio.salvar_tabela(
            dados["tornado"],
            t_dir,
            "tabela_20_tornado",
            "Tabela 20 — Sensibilidade tipo tornado: um parâmetro por vez dentro da faixa publicada, com a variação do risco vitalício combinado e da idade mediana de início",
            "Toda faixa vem de fonte publicada (coluna `fonte`). Fora do tornado, por não haver incerteza publicada: "
            + ("; ".join(fora) if fora else "nenhum gene dos cenários avaliados")
            + ".",
        ),
    ]
    f_dir = saida / "figuras"
    figuras = [
        relatorio.figura_calibracao(curvas_cal, f_dir / "figura_10_calibracao.png"),
        relatorio.figura_robustez(robustez, f_dir / "figura_11_robustez_vcf.png"),
        relatorio.figura_tornado(tornados, f_dir / "figura_12_tornado.png"),
    ]
    modelo = verd[0].rotulo
    b = dados["brier"][dados["brier"].verdade == modelo].set_index("previsao")
    dsc = dados["discriminacao"][dados["discriminacao"].verdade == modelo]
    ei = dados["erro_idade"][dados["erro_idade"].verdade == modelo]
    comb = ei[ei.gene.str.startswith("combinado")]
    cb = dados["cobertura_bandas"]
    leitura = (
        f"Com verdade = modelo: Brier até o horizonte {b.loc['até o horizonte', 'brier']:.4f} (referência "
        f"{b.loc['até o horizonte', 'brier_referencia']:.4f}); C-index {dsc.valor.iloc[0]:.3f}; AUC a 10 e 20 anos "
        f"{dsc.valor.iloc[1]:.3f} e {dsc.valor.iloc[2]:.3f}; cobertura média dos intervalos do Monte Carlo "
        f"{cob_mc.cobertura_p_manifesta.mean():.1%} (esperado 95 %); cobertura média das bandas de F(t) "
        f"{cb[cb.verdade == modelo].cobertura_da_banda.mean():.1%} "
        f"({cb[cb.verdade == modelo].cobertura_sem_ruido_amostral.mean():.1%} sem o ruído amostral do F empírico)"
        + (
            f"; erro absoluto médio da idade de início {comb.erro_absoluto_medio_anos.iloc[0]:.1f} anos para um piso "
            f"teórico de {comb.piso_teorico_anos.iloc[0]:.1f}"
            if len(comb)
            else ""
        )
        + ". "
        + " ".join(
            f"Com a {v.rotulo}: Brier até o horizonte "
            f"{dados['brier'][(dados['brier'].verdade == v.rotulo) & (dados['brier'].previsao == 'até o horizonte')].brier.iloc[0]:.4f} "
            f"e cobertura média das bandas {cb[cb.verdade == v.rotulo].cobertura_da_banda.mean():.1%}."
            for v in verd[1:]
        )
    )
    secoes = [
        ("Verificação com famílias sintéticas de desfecho conhecido", avaliacao.ENQUADRAMENTO + " " + leitura),
        (
            "Como ler as métricas de verificação",
            "Calibração (Tabelas 13 e 14, Figura 10): o risco previsto bate com a fração observada quando a verdade é o "
            "modelo e se afasta quando não é. Discriminação (Tabela 15): só existe porque a coorte mistura cenários, "
            "sexos e idades; dentro de um só cenário todos têm a mesma previsão. Idade de início (Tabela 16): o erro é "
            "comparado com o piso teórico, que nenhum modelo vence. Cobertura (Tabelas 17 e 17b): intervalos do Monte "
            "Carlo e bandas de F(t). Divergência (Tabela 18): distância entre curvas empíricas e teóricas. Robustez "
            "(Tabela 19, Figura 11): efeito de erros controlados no VCF, com o que o artefato declara. Tornado "
            "(Tabela 20, Figura 12): um parâmetro por vez, sempre dentro de faixa publicada.",
        ),
    ]
    metadados = {
        "enquadramento": avaliacao.ENQUADRAMENTO,
        "mundos": mundos,
        "pessoas_por_estrato": por_estrato,
        "estratos": len(estratos),
        "seed_coorte": seed_coorte,
        "seed_previsoes": seed,
        "idades_atuais": list(avaliacao.IDADES_COORTE),
        "verdades": [{"nome": v.nome, "rotulo": v.rotulo, "descricao": v.descricao} for v in verd],
        "cenarios_na_coorte": list(casos),
        "fora_do_tornado": fora,
    }
    return {"tabelas": tabelas, "figuras": figuras, "secoes": secoes, "dados": dados, "metadados": metadados}


def tudo(
    saida,
    seed: int = 42,
    n: int = 10_000,
    ns=(1_000, 10_000, 100_000),
    repeticoes: int = 30,
    motor: str = "pymc",
    config=None,
    idade_atual: float | None = 30.0,
    base_clinvar=None,
    comparar_cox: bool = True,
    metricas: bool = True,
    mundos: int = 200,
    por_estrato: int = 10,
    seed_coorte: int | None = None,
) -> dict:
    """Gera os cenários, executa cada um para os dois sexos (com o laudo do C9orf72 de cada cenário), avalia e escreve o índice `README.md` em `saida`."""
    saida = Path(saida)
    _limpar_saida(saida, ARTEFATOS_TUDO)
    t0 = time.perf_counter()
    tab = cenarios.gerar_cenarios(saida / "sinteticos", seed=2026)
    consolidado, indice, sem_locus = [], [], []
    for c in cenarios.CENARIOS:
        linha = tab[tab.numero == c.numero].iloc[0]
        por_sexo = {}
        for sexo in ("F", "M"):
            r = executar(
                linha.vcf_mae,
                linha.vcf_pai,
                saida / "cenarios" / f"cenario_{c.numero}_{sexo}",
                sexo=sexo,
                idade_atual=idade_atual,
                n=n,
                seed=seed,
                motor=motor,
                config=config,
                rotulo=f"Cenário {c.numero} ({sexo}): {c.descricao}",
                laudo_c9orf72=c.laudo_c9orf72,
                base_clinvar=base_clinvar,
                comparar_cox=comparar_cox,
            )
            indice.append(
                f"- Cenário {c.numero}, sexo {sexo}: [`cenarios/cenario_{c.numero}_{sexo}/relatorio.md`](cenarios/cenario_{c.numero}_{sexo}/relatorio.md)"
            )
            if r["res"] is None:
                sem_locus.append(f"cenário {c.numero} ({sexo})")
                continue
            por_sexo[sexo] = r
            for _, l in r["resumo"].iterrows():
                consolidado.append(
                    {
                        "cenario": c.numero,
                        "descricao": c.descricao,
                        "sexo": sexo,
                        "variante": l.variante,
                        "heranca": l.heranca,
                        "p_portador": l.p_portador_exato,
                        "p_manifesta": l.p_manifesta_exato,
                        "ic95": f"{l.p_manifesta_q025:.3f}–{l.p_manifesta_q975:.3f}",
                        COLUNA_SEM_LIMITE: l.p_manifesta_sem_limite,
                        "idade_mediana": l.idade_mediana_exata,
                    }
                )
            cb = r["combinado"]
            consolidado.append(
                {
                    "cenario": c.numero,
                    "descricao": c.descricao,
                    "sexo": sexo,
                    "variante": sobrevivencia.QUALQUER,
                    "heranca": "independência",
                    "p_portador": cb["p_portador_qualquer_exato"],
                    "p_manifesta": cb["p_manifesta_qualquer_exato"],
                    "ic95": f"{cb['p_manifesta_qualquer_q025']:.3f}–{cb['p_manifesta_qualquer_q975']:.3f}",
                    COLUNA_SEM_LIMITE: cb["p_manifesta_qualquer_sem_limite"],
                    "idade_mediana": cb["idade_mediana_primeiro_inicio"],
                }
            )
        if por_sexo:
            relatorio.figura_idade_inicio(
                {s: r["res"] for s, r in por_sexo.items()},
                saida / "cenarios" / f"figura_05_idade_inicio_cenario_{c.numero}.png",
            )
    cons = pd.DataFrame(consolidado)
    tabela3 = relatorio.salvar_tabela(
        cons,
        saida / "tabelas",
        "tabela_03_consolidada",
        "Tabela 3 (consolidada) — Probabilidade de transmissão, risco vitalício de manifestação até o horizonte (IC 95%), fração que manifesta em algum momento (sem limite de idade) e idade mediana de início por cenário, lócus e sexo do descendente",
    )
    av = avaliar(
        saida / "sinteticos",
        saida / "avaliacao",
        ns=ns,
        repeticoes=repeticoes,
        seed=seed + 958,
        config=config,
        n_coerencia=n,
        base_clinvar=base_clinvar,
        metricas=metricas,
        mundos=mundos,
        por_estrato=por_estrato,
        seed_coorte=seed_coorte,
    )
    fontes = anotacao.tabela_anotacao(base_real=base_clinvar).attrs.get("fontes", {})
    com_figura = [
        c for c in cenarios.CENARIOS if (saida / "cenarios" / f"figura_05_idade_inicio_cenario_{c.numero}.png").exists()
    ]
    linhas = [
        f"# Resultados do artefato ela_preditivo v{__version__}",
        "",
        f"> {AVISO_LEGAL}",
        "",
        f"Gerado em {_dt.datetime.now():%d/%m/%Y %H:%M} com seed {seed}, N = {_n(n)} por execução, avaliação com N ∈ {list(ns)} × {repeticoes} repetições. Tempo total: {time.perf_counter() - t0:.0f} s.",
        "",
        f"Base de anotação: {fontes.get('base_real') or 'tabela curada'}"
        + (
            f" ({fontes.get('n_real')} variantes do ClinVar dos quatro genes + {fontes.get('n_curada_extra')} da tabela curada"
            f"{_fora_da_anotacao_txt(fontes)})."
            if fontes.get("base_real")
            else "."
        ),
        "A expansão do C9orf72 entra pelo laudo laboratorial de cada cenário (TCC 4.2.1), não pelo VCF.",
        "",
        *(
            [f"Sem lócus de risco nesta base de anotação (relatório explica o motivo): {', '.join(sem_locus)}.", ""]
            if sem_locus
            else []
        ),
        "## Relatórios por cenário",
        "",
        *indice,
        "",
        "## Avaliação transversal",
        "",
        "- [`avaliacao/relatorio.md`](avaliacao/relatorio.md) (Tabelas 5 a 9 e 12 a 20; Figuras 2, 3, 7 e 10 a 12)",
        "",
        "## Tabela consolidada",
        "",
        Path(tabela3["md"]).read_text(encoding="utf-8"),
        "",
        "## Figuras de idade de início por sexo",
        "",
        *[f"![Cenário {c.numero}](cenarios/figura_05_idade_inicio_cenario_{c.numero}.png)" for c in com_figura],
        "",
    ]
    (saida / "README.md").write_text("\n".join(linhas), encoding="utf-8")
    return {"saida": saida, "consolidado": cons, "avaliacao": av, "sem_locus": sem_locus}
