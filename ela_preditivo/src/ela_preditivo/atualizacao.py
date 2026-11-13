"""Atualização e versionamento das bases de anotação (TCC 3.2: requisito não funcional de atualizar as bases de variantes
ao longo do tempo; 4.2.2: só a publicação mensal do ClinVar permite reproduzir uma estimativa depois).

- `baixar_clinvar`: baixa a release mensal do ClinVar (VCF GRCh38 do FTP do NCBI; a mais recente ou uma do arquivo) e
  guarda só os registros dos quatro genes em `DIR_DADOS_BRUTOS` (fora do versionamento) como `clinvar_ela_4genes_<release>.vcf`.
- `registrar_versao`: identifica uma base (release, sha256), guarda um instantâneo das classificações por variante em
  `DIR_DADOS_BRUTOS/versoes/` e a anota em `versoes.json`.
- `comparar_versoes`: variantes novas, removidas e reclassificadas entre dois instantâneos, com as transições de classe e o
  efeito sobre as variantes da tabela curada.
- `atualizar`: registra a base e, havendo versão anterior registrada, compara com ela e escreve `atualizacao_<anterior>_<atual>.md`.

O pipeline grava em `metadados.json` (`base_anotacao`) o arquivo, a release e o sha256 da base usada em cada execução
(`anotacao.identificar_base`), o que fecha a rastreabilidade: resultado → versão da base → diferenças para a versão seguinte.
"""

from __future__ import annotations

import datetime as _dt
import gzip
import io
import json
import re
import urllib.request
from pathlib import Path

import pandas as pd

from . import AVISO_LEGAL, DIR_DADOS_BRUTOS, GENES, __version__, anotacao
from .relatorio import df_para_markdown

URL_CLINVAR_VCF = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz"
URL_CLINVAR_ARQUIVO = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/archive_2.0/{ano}/clinvar_{release}.vcf.gz"
CHAVE = ["cromossomo", "posicao_grch38", "ref", "alt"]
COLUNAS_INSTANTANEO = [
    "gene",
    "cromossomo",
    "posicao_grch38",
    "ref",
    "alt",
    "rs",
    "variation_id_clinvar",
    "nome_curto",
    "clnsig",
    "classe",
    "estrelas",
    "revstat",
    "n_submissores",
]
ARQUIVO_REGISTRO = "versoes.json"


def dir_registro(diretorio: str | Path | None = None) -> Path:
    """Pasta do registro de versões: `diretorio` ou `DIR_DADOS_BRUTOS/versoes` (ignorada pelo git, como os dados reais)."""
    return Path(diretorio) if diretorio else DIR_DADOS_BRUTOS / "versoes"


# ---------------------------------------------------------------------------
# Download da release mensal do ClinVar, filtrada aos genes-alvo
# ---------------------------------------------------------------------------
def baixar_clinvar(
    release: str | None = None, destino: str | Path | None = None, genes=GENES, url: str | None = None
) -> dict:
    """Baixa `clinvar.vcf.gz` (GRCh38) do NCBI — a release mais recente ou, com `release` = AAAA-MM-DD, a do arquivo
    mensal — e grava só os registros cujo GENEINFO contém um dos genes-alvo, com o cabeçalho original, em
    `destino/clinvar_ela_4genes_<release>.vcf`. `url` substitui o endereço (inclusive `file://...`, para testes)."""
    if url is None:
        if release is None:
            url = URL_CLINVAR_VCF
        else:
            rel = anotacao._normalizar_data(release)
            if rel is None:
                raise ValueError(f"release inválida: {release!r} (use AAAA-MM-DD)")
            url = URL_CLINVAR_ARQUIVO.format(ano=rel[:4], release=rel.replace("-", ""))
    destino = Path(destino) if destino else DIR_DADOS_BRUTOS
    destino.mkdir(parents=True, exist_ok=True)
    parcial = destino / "clinvar_ela_4genes_baixando.vcf"
    n, release_cabecalho = 0, None
    with (
        urllib.request.urlopen(url, timeout=300) as resposta,
        gzip.GzipFile(fileobj=resposta) as gz,
        open(parcial, "w", encoding="utf-8") as saida,
    ):
        for linha in io.TextIOWrapper(gz, encoding="utf-8", errors="replace"):
            if linha.startswith("#"):
                if linha.startswith("##fileDate="):
                    release_cabecalho = anotacao._normalizar_data(linha.split("=", 1)[1])
                saida.write(linha)
                continue
            campos = linha.split("\t", 8)
            info = campos[7] if len(campos) > 7 else ""
            m = re.search(r"(?:^|;)GENEINFO=([^;\s]+)", info)
            if m and anotacao._gene_alvo(m.group(1).replace(":", "|").replace("|", ";"), genes):
                saida.write(linha)
                n += 1
    rel = release_cabecalho or (anotacao._normalizar_data(release) if release else None) or _dt.date.today().isoformat()
    final = destino / f"clinvar_ela_4genes_{rel.replace('-', '')}.vcf"
    parcial.replace(final)
    return {
        "arquivo": str(final),
        "release": rel,
        "release_fonte": ("##fileDate" if release_cabecalho else "parâmetro/data de hoje"),
        "n_registros": n,
        "url": url,
        "genes": list(genes),
    }


# ---------------------------------------------------------------------------
# Registro de versões e instantâneos
# ---------------------------------------------------------------------------
def carregar_registro(diretorio: str | Path | None = None) -> list[dict]:
    p = dir_registro(diretorio) / ARQUIVO_REGISTRO
    if not p.is_file():
        return []
    return list(json.loads(p.read_text(encoding="utf-8")).get("bases", []))


def _gravar_registro(diretorio: Path, versoes: list[dict]) -> Path:
    p = Path(diretorio) / ARQUIVO_REGISTRO
    p.write_text(
        json.dumps(
            {"pacote": "ela_preditivo", "versao": __version__, "bases": versoes},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return p


def instantaneo(base: pd.DataFrame) -> pd.DataFrame:
    """Colunas que identificam e classificam cada variante (o suficiente para comparar releases)."""
    t = base.copy()
    for c in COLUNAS_INSTANTANEO:
        if c not in t.columns:
            t[c] = None
    t = t[COLUNAS_INSTANTANEO].copy()
    t["cromossomo"] = t["cromossomo"].astype(str)
    t["posicao_grch38"] = pd.to_numeric(t["posicao_grch38"], errors="coerce").fillna(-1).astype(int)
    t["ref"], t["alt"] = t["ref"].astype(str).str.upper(), t["alt"].astype(str).str.upper()
    t["estrelas"] = pd.to_numeric(t["estrelas"], errors="coerce").fillna(0).astype(int)
    return t.sort_values(CHAVE).reset_index(drop=True)


def carregar_instantaneo(entrada: dict, diretorio: str | Path | None = None) -> pd.DataFrame:
    p = dir_registro(diretorio) / entrada["instantaneo"]
    t = pd.read_csv(
        p,
        dtype={
            "cromossomo": str,
            "rs": str,
            "variation_id_clinvar": str,
            "revstat": str,
            "nome_curto": str,
            "clnsig": str,
        },
    )
    return instantaneo(t)


def registrar_versao(
    caminho_base: str | Path, diretorio: str | Path | None = None, release: str | None = None, origem: str | None = None
) -> dict:
    """Carrega a base (`anotacao.carregar_base_real`: csv/txt/vcf, só os genes-alvo em GRCh38), identifica release e sha256,
    grava o instantâneo `clinvar_<release>_<sha8>.csv` e a entrada em `versoes.json`. A mesma base (mesmo sha256) não é
    registrada duas vezes. `release` (AAAA-MM-DD) é obrigatória quando o arquivo não a traz no cabeçalho nem no nome."""
    caminho = Path(caminho_base)
    base = anotacao.carregar_base_real(caminho)
    if base is None:
        raise FileNotFoundError(f"base não encontrada: {caminho}")
    ident = base.attrs.get("base") or anotacao.identificar_base(caminho)
    rel = anotacao._normalizar_data(release) if release else ident["release"]
    if rel is None:
        raise ValueError(
            f"{caminho.name}: release não identificada (sem ##fileDate e sem data no nome); informe `release='AAAA-MM-DD'`"
        )
    d = dir_registro(diretorio)
    d.mkdir(parents=True, exist_ok=True)
    inst = instantaneo(base)
    nome = f"clinvar_{rel.replace('-', '')}_{ident['sha256'][:8]}.csv"
    inst.to_csv(d / nome, index=False)
    entrada = {
        "release": rel,
        "release_fonte": ("parâmetro" if release else ident["release_fonte"]),
        "arquivo": ident["arquivo"],
        "caminho": ident["caminho"],
        "sha256": ident["sha256"],
        "tamanho_bytes": ident["tamanho_bytes"],
        "formato": (str(base.fonte.iloc[0]) if len(base) else None),
        "n_variantes": int(len(inst)),
        "por_classe": {str(k): int(v) for k, v in inst.classe.value_counts().sort_index().items()},
        "por_gene": {str(k): int(v) for k, v in inst.gene.value_counts().sort_index().items()},
        "instantaneo": nome,
        "registrado_em": _dt.datetime.now().isoformat(timespec="seconds"),
        "origem": origem,
        "versao_pacote": __version__,
    }
    versoes = [v for v in carregar_registro(d) if v.get("sha256") != entrada["sha256"]] + [entrada]
    versoes.sort(key=lambda v: (str(v.get("release", "")), str(v.get("registrado_em", ""))))
    _gravar_registro(d, versoes)
    return entrada


# ---------------------------------------------------------------------------
# Comparação entre releases
# ---------------------------------------------------------------------------
def comparar_versoes(anterior: pd.DataFrame, atual: pd.DataFrame, curada: pd.DataFrame | None = None) -> dict:
    """Diferenças entre dois instantâneos (chave: cromossomo, posição GRCh38, ref, alt).

    Devolve `resumo` (contagens e transições de classe), `novas`, `removidas`, `reclassificadas` (CLNSIG, classe ou estrelas
    diferentes) e `curadas_afetadas` (variantes da tabela curada entre as novas, removidas ou reclassificadas)."""
    a = instantaneo(anterior).set_index(CHAVE)
    b = instantaneo(atual).set_index(CHAVE)
    a, b = a[~a.index.duplicated(keep="first")], b[~b.index.duplicated(keep="first")]
    novas = b.loc[b.index.difference(a.index)].reset_index()
    removidas = a.loc[a.index.difference(b.index)].reset_index()
    comuns = a.index.intersection(b.index)
    ca, cb = a.loc[comuns], b.loc[comuns]
    mudou = (ca.clnsig.fillna("").astype(str) != cb.clnsig.fillna("").astype(str)) | (ca.estrelas != cb.estrelas)
    reclass = pd.DataFrame(
        {
            "gene": cb.gene,
            "nome_curto": cb.nome_curto,
            "rs": cb.rs,
            "variation_id_clinvar": cb.variation_id_clinvar,
            "clnsig_anterior": ca.clnsig,
            "clnsig_atual": cb.clnsig,
            "classe_anterior": ca.classe,
            "classe_atual": cb.classe,
            "estrelas_anterior": ca.estrelas,
            "estrelas_atual": cb.estrelas,
        }
    )[mudou].reset_index()
    mudou_classe = reclass.classe_anterior != reclass.classe_atual
    transicoes = reclass[mudou_classe].groupby(["classe_anterior", "classe_atual"]).size()
    resumo = {
        "n_anterior": int(len(a)),
        "n_atual": int(len(b)),
        "novas": int(len(novas)),
        "removidas": int(len(removidas)),
        "reclassificadas": int(mudou_classe.sum()),
        "mudanca_so_de_clnsig_ou_estrelas": int((~mudou_classe).sum()),
        "transicoes_de_classe": {f"{k[0]} → {k[1]}": int(v) for k, v in transicoes.items()},
        "por_classe_anterior": {str(k): int(v) for k, v in a.classe.value_counts().sort_index().items()},
        "por_classe_atual": {str(k): int(v) for k, v in b.classe.value_counts().sort_index().items()},
        "novas_por_classe": {str(k): int(v) for k, v in novas.classe.value_counts().sort_index().items()},
        "removidas_por_classe": {str(k): int(v) for k, v in removidas.classe.value_counts().sort_index().items()},
    }
    cur = curada if curada is not None else anotacao.carregar_tabela_curada()
    cur = instantaneo(cur[cur.tipo != "repeticao"]) if len(cur) else cur
    chaves_curadas = {tuple(k) for k in cur[CHAVE].itertuples(index=False)} if len(cur) else set()
    partes = []
    for evento, df in (
        ("nova", novas),
        ("removida", removidas),
        ("reclassificada", reclass[mudou_classe]),
        ("estrelas/clnsig", reclass[~mudou_classe]),
    ):
        if len(df):
            sel = df[[tuple(k) in chaves_curadas for k in df[CHAVE].itertuples(index=False)]]
            if len(sel):
                partes.append(sel.assign(evento=evento))
    afetadas = (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=CHAVE + ["gene", "nome_curto", "evento"])
    )
    return {
        "resumo": resumo,
        "novas": novas,
        "removidas": removidas,
        "reclassificadas": reclass,
        "curadas_afetadas": afetadas,
    }


def relatorio_atualizacao(
    comparacao: dict, anterior: dict, atual: dict, caminho: str | Path, maximo_linhas: int = 60
) -> Path:
    """Escreve o resumo da atualização em Markdown (contagens, transições de classe, variantes curadas afetadas e as
    reclassificações), com o aviso legal."""
    r = comparacao["resumo"]
    linhas = [
        f"# Atualização da base ClinVar: release {anterior['release']} → {atual['release']}",
        "",
        f"> {AVISO_LEGAL}",
        "",
        f"Gerado em {_dt.datetime.now():%d/%m/%Y %H:%M} por ela_preditivo v{__version__}.",
        "",
        "## Versões",
        "",
        f"- Anterior: `{anterior['arquivo']}` (release {anterior['release']}, sha256 {anterior['sha256'][:12]}…, {anterior['n_variantes']} variantes)",
        f"- Atual: `{atual['arquivo']}` (release {atual['release']}, sha256 {atual['sha256'][:12]}…, {atual['n_variantes']} variantes)",
        "",
        "## O que mudou",
        "",
        f"- Variantes novas: {r['novas']} {r['novas_por_classe']}",
        f"- Variantes removidas: {r['removidas']} {r['removidas_por_classe']}",
        f"- Reclassificadas (mudança de classe): {r['reclassificadas']} {r['transicoes_de_classe']}",
        f"- Só CLNSIG ou estrelas mudaram (mesma classe): {r['mudanca_so_de_clnsig_ou_estrelas']}",
        f"- Por classe, antes: {r['por_classe_anterior']}",
        f"- Por classe, agora: {r['por_classe_atual']}",
        "",
    ]
    afetadas = comparacao["curadas_afetadas"]
    linhas += ["## Variantes da tabela curada afetadas", ""]
    if len(afetadas):
        cols = [
            c
            for c in [
                "evento",
                "gene",
                "nome_curto",
                "cromossomo",
                "posicao_grch38",
                "ref",
                "alt",
                "clnsig",
                "classe",
                "clnsig_anterior",
                "clnsig_atual",
                "classe_anterior",
                "classe_atual",
                "estrelas_anterior",
                "estrelas_atual",
            ]
            if c in afetadas.columns
        ]
        linhas += [df_para_markdown(afetadas[cols]), ""]
    else:
        linhas += ["Nenhuma: as variantes de `data/variantes_curadas.csv` mantêm classificação e estrelas.", ""]
    rec = comparacao["reclassificadas"]
    rec = rec[rec.classe_anterior != rec.classe_atual]
    if len(rec):
        cols = [
            "gene",
            "nome_curto",
            "rs",
            "variation_id_clinvar",
            "clnsig_anterior",
            "clnsig_atual",
            "classe_anterior",
            "classe_atual",
            "estrelas_anterior",
            "estrelas_atual",
        ]
        linhas += [
            f"## Reclassificações ({len(rec)}; primeiras {min(len(rec), maximo_linhas)})",
            "",
            df_para_markdown(rec[cols].head(maximo_linhas)),
            "",
        ]
    for titulo, df in (("Variantes novas", comparacao["novas"]), ("Variantes removidas", comparacao["removidas"])):
        if len(df):
            cols = ["gene", "nome_curto", "rs", "variation_id_clinvar", "clnsig", "classe", "estrelas"]
            linhas += [
                f"## {titulo} ({len(df)}; primeiras {min(len(df), maximo_linhas)})",
                "",
                df_para_markdown(df[cols].head(maximo_linhas)),
                "",
            ]
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(linhas), encoding="utf-8")
    return p


def atualizar(
    caminho_base: str | Path,
    diretorio: str | Path | None = None,
    release: str | None = None,
    origem: str | None = None,
    curada: pd.DataFrame | None = None,
) -> dict:
    """Registra a base e, se houver versão anterior registrada (a de release mais recente, diferente desta), compara as duas
    e escreve o relatório `atualizacao_<anterior>_<atual>.md` na pasta do registro."""
    d = dir_registro(diretorio)
    anteriores = carregar_registro(d)
    atual = registrar_versao(caminho_base, d, release=release, origem=origem)
    anteriores = [
        v
        for v in anteriores
        if v.get("sha256") != atual["sha256"] and v.get("instantaneo") and (d / v["instantaneo"]).is_file()
    ]
    if not anteriores:
        return {"atual": atual, "anterior": None, "comparacao": None, "relatorio": None}
    anterior = max(anteriores, key=lambda v: (str(v.get("release", "")), str(v.get("registrado_em", ""))))
    comparacao = comparar_versoes(carregar_instantaneo(anterior, d), carregar_instantaneo(atual, d), curada)
    rel = relatorio_atualizacao(
        comparacao, anterior, atual, d / f"atualizacao_{anterior['release']}_{atual['release']}.md"
    )
    return {"atual": atual, "anterior": anterior, "comparacao": comparacao, "relatorio": rel}


def resumo_texto(resultado: dict) -> str:
    """Texto curto para a CLI."""
    a = resultado["atual"]
    linhas = [
        f"Registrada: {a['arquivo']} — release {a['release']} ({a['release_fonte']}), sha256 {a['sha256'][:12]}…, {a['n_variantes']} variantes {a['por_classe']}"
    ]
    if resultado["anterior"] is None:
        linhas.append("Primeira versão registrada: nada a comparar.")
    else:
        r = resultado["comparacao"]["resumo"]
        linhas.append(
            f"Desde a release {resultado['anterior']['release']}: {r['novas']} novas, {r['removidas']} removidas, {r['reclassificadas']} reclassificadas "
            f"{r['transicoes_de_classe']}, {r['mudanca_so_de_clnsig_ou_estrelas']} só com CLNSIG/estrelas alteradas; "
            f"variantes da tabela curada afetadas: {len(resultado['comparacao']['curadas_afetadas'])}."
        )
        linhas.append(f"Relatório: {resultado['relatorio']}")
    return "\n".join(linhas)
