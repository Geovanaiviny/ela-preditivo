# 03 — Plano de implementação do pacote `ela_preditivo`

> **Estado em 24/10/2026**: fases 1 a 7 implementadas (74 testes passando). Diferenças em relação ao plano original: módulo `pipeline.py` separado da CLI; `exato.py` como módulo próprio; Tabela 10 (Kaplan-Meier) e Tabela 9 (sensibilidade) acrescentadas; `tudo` executa cada cenário para os dois sexos. A apresentação do pacote está em `ela_preditivo/README.md`; o texto-base da seção 5 em `docs/07_resultados_secao5.md`. **Estado em 08/11/2026**: correções da revisão da autora/orientador (docs/04, D20 a D29), módulo `atualizacao.py`, 106 testes; `resultados/` ainda é o da execução de 03/11 (decisão em aberto nº 10).

Pré-requisitos: ler `01_analise_tcc.md`, `02_modelo_matematico.md`, `04_decisoes.md`, `05_ambiente.md`. Tudo em português (ver AGENTS.md).

## 1. Layout

```
ela_preditivo/
  pyproject.toml                      # nome ela_preditivo, Python >=3.11, deps pinadas (ver 05_ambiente.md), script ela-preditivo
  README.md                           # arquitetura, instalação, dicionário de dados, avisos legais
  config/
    parametros_literatura.yaml        # penetrância, IC, herança, G(t), δ_sexo, limiares, citações, confirmar
    regioes_genes_grch38.yaml         # intervalos dos 4 genes (+ flanco) em GRCh38
  data/
    variantes_curadas.csv             # tabela embutida (ClinVar/dbSNP) das variantes conhecidas
    sinteticos/                       # VCFs gerados (saída de `gerar-cenarios`; versionar os gerados com seed fixa)
  src/ela_preditivo/
    __init__.py                       # __version__
    ingestao.py                       # leitura VCF (pyvcf3), filtro de qualidade, máscara de regiões, decomposição multialélica
    anotacao.py                       # join com tabela curada ou subconjunto real; classificação; estrelas; expansão C9orf72
    genotipo.py                       # vetor de dosagem parental por gene (0/1/2), flags recessiva e heterozigose composta
    calibracao.py                     # Beta de ponto+IC; Weibull/log-normal de pontos KM/faixas etárias ou de estatísticas (média/dp, mediana/IQR) em forma fechada (D22)
    exato.py                          # CPT e fórmulas fechadas (referência)
    rede_bayesiana.py                 # modelo PyMC e sample_prior_predictive
    monte_carlo.py                    # amostrador NumPy equivalente; repetições; condicionamento por idade
    sobrevivencia.py                  # coorte sintética, KM, Weibull, MisturaCuraWeibullFitter, condicional
    cenarios.py                       # definição dos 5 cenários e gerador de VCF 4.2 sintético
    avaliacao.py                      # aderência, estabilidade, coerência, tempo
    relatorio.py                      # figuras PNG 300 dpi e tabelas CSV/Markdown com legendas prontas
    atualizacao.py                    # download da release mensal do ClinVar (4 genes), registro de versões (release, sha256, instantâneo) e comparação entre releases (D29)
    cli.py                            # argparse: gerar-cenarios | executar | avaliar | tudo | atualizar-base
  tests/
    test_exato.py test_calibracao.py test_cenarios_ingestao.py test_anotacao_genotipo.py test_nucleo_estocastico.py
    test_sobrevivencia.py test_pipeline.py test_dados_reais.py test_correcoes_revisao.py test_atualizacao.py
```

## 2. Configuração (`config/parametros_literatura.yaml`), esquema

```yaml
versao: 1
data: 2026-10-24
horizonte_anos: 90
limiar_repeticoes_c9orf72: {patogenico: 30, intermediario: 24, citacao: "ClinVar GGGGCC[>24]; conferir"}
genes:
  C9orf72:
    cromossomo: "9"
    heranca: dominante
    tipo_variante: repeticao          # expansão GGGGCC
    penetrancia: {valor: 0.33, ic95: [0.209, 0.532], citacao: "DOUGLAS; BARALLE, 2024, p. 294", confirmar: false}
    inicio:
      distribuicao: weibull           # ou lognormal
      pontos_km: [[35, 0.0], [58, 0.5], [80, 0.98]]   # Murphy et al. 2017; digitalizar mais pontos da figura
      citacao: "MURPHY et al., 2017"
      confirmar: true
    delta_sexo: {M: -1.0, F: 1.0, citacao: "GOUTMAN et al., 2022", confirmar: false}
  SOD1:
    cromossomo: "21"
    heranca: dominante
    excecoes_recessivas: ["rs80265967"]   # p.D91A (D90A)
    penetrancia: {valor: 0.54, ic95: [0.327, 0.886], citacao: "DOUGLAS; BARALLE, 2024", confirmar: false}
    inicio: {distribuicao: weibull, faixas_etarias: [[40, 0.20], [50, 0.50], [60, 0.80], [70, 0.95]], citacao: "RICHARD et al., 2026 (PLACEHOLDER)", confirmar: true}
    # implementado: `pontos: [[t, g], ...]` OU, em forma fechada (D22), `estatisticas: {media: 50.2, dp: 10.6}` / `estatisticas: {mediana: 58.30, iqr: 16.23}`
    delta_sexo: {M: 0.0, F: 0.0, confirmar: true}
  TARDBP: {...}   # 0.38 [0.211, 0.698]; início placeholder mediana ≈ 54
  FUS:    {...}   # 0.19 [0.130, 0.284]; início placeholder mediana ≈ 44
```

Regra: todo valor com `confirmar: true` aparece marcado nas tabelas de saída ("valor provisório"). A calibração grava (α, β, k, λ) derivados em `resultados/parametros_calibrados.csv`.

## 3. Tabela curada (`data/variantes_curadas.csv`)

Colunas: `gene, cromossomo, posicao_grch38, ref, alt, rs, variation_id_clinvar, hgvs_c, hgvs_p, clnsig, estrelas, heranca, tipo (snv|repeticao), repeticoes_min, citacao, conferido_em`.

Linhas iniciais (coordenadas GRCh38 **a conferir online antes de usar**, pelo rs em `https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/<id>` ou ClinVar):

| gene | variante | rs | clnsig | herança | observação |
|---|---|---|---|---|---|
| SOD1 | c.14C>T p.Ala5Val (A4V) | rs121912442 | Pathogenic | dominante | alta penetrância, progressão rápida |
| SOD1 | c.272A>C p.Asp91Ala (D90A) | rs80265967 | Pathogenic | **recessiva** | exceção documentada |
| SOD1 | chr21:31659509 G>T | rs17883296 | Likely_benign | — | exemplo literal do TCC; ruído para a anotação |
| TARDBP | c.1009A>G p.Met337Val | rs80356730 | Pathogenic | dominante | |
| FUS | c.1561C>T p.Arg521Cys | rs121909670 | Pathogenic | dominante | início mais precoce |
| C9orf72 | expansão GGGGCC chr9:27573529–27573534 | — | Pathogenic se ≥ 30 repetições | dominante | ClinVar: microssatélite GGGGCC[>24]; não endereçável por alelo |

Regiões (`config/regioes_genes_grch38.yaml`, conferir em `https://rest.ensembl.org/lookup/symbol/homo_sapiens/<GENE>?content-type=application/json`): SOD1 chr21:31.659.666–31.668.931; C9orf72 chr9:27.546.545–27.573.866; TARDBP chr1:11.012.654–11.030.528; FUS chr16:31.180.139–31.191.605; aplicar flanco de 5 kb (a benigna rs17883296 fica 157 pb acima do início do SOD1).

Carregador do subconjunto real (**implementado em 03/11/2026**, D17): `anotacao.tabela_anotacao()` → `carregar_base_real()` → `carregar_variant_summary()` (csv/txt, inclusive `base_consolidada_ela.csv`) ou `carregar_clinvar_vcf()`; antes previsto como `anotacao.carregar_clinvar_subconjunto(variant_summary_txt, clinvar_vcf, snp_result_txts)` lendo as chaves descritas em `01_analise_tcc.md` §7; mapa de classificação (D21): `Pathogenic`, `Likely_pathogenic`, `Pathogenic/Likely_pathogenic` → risco; `Uncertain_significance`, `VUS*` (inclusive VUS-high) → vus (sem risco, listado); `Conflicting_*` ou patogênico e benigno misturados no mesmo valor → conflitante (classe própria, sem risco, contada à parte); `Benign*` → benigna. Estrelas de `CLNREVSTAT`: practice_guideline 4, reviewed_by_expert_panel 3, criteria_provided,_multiple_submitters,_no_conflicts 2, criteria_provided,_single_submitter / conflicting 1, no_assertion* 0.

## 4. VCF sintético (`cenarios.py`)

VCF 4.2, GRCh38, uma amostra por arquivo (`MAE` ou `PAI`), colunas FORMAT `GT:DP:GQ`, cabeçalho com `##reference=GRCh38`, `##INFO`, `##FORMAT`, `##ALT=<ID=STR,...>`. Cada arquivo contém:
- as variantes do cenário (GT `0/1` ou `1/1`);
- ruído: 1 benigna (rs17883296), 1 VUS em FUS, 1 variante fora dos 4 genes (ex.: chr17), 1 registro com `DP=4` e `GQ=10` (reprovado no filtro `DP ≥ 20`, `GQ ≥ 30`, `FILTER=PASS`; TCC 4.3, D24), 1 multialélico `ALT=A,T`.
- INFO com `AC` (por ALT), `AN` e `DB` (Quadro 2 do TCC) e `##contig` com comprimento GRCh38 (conferência de montagem, D14); `##fileDate` fixo, igual à `data` do YAML, para reprodutibilidade byte a byte (D28).
- **(revisado em 03/11/2026, D16)** a expansão do C9orf72 **não vai no VCF**: entra pelo laudo (`Cenario.laudo_c9orf72`, `cenarios.csv` colunas `c9orf72_mae/pai`, CLI `--c9orf72-mae/--c9orf72-pai`). O parser do estilo ExpansionHunter (`<STR(\d+)>`, `REPCN`, contagem do motivo com `Bio.Seq`) continua como caminho secundário e é testado com `cenarios.c9orf72_expansao()`; patogênico se ≥ 30, intermediário 24–29.

Cenários (seed fixa 2026; gerar ambos os sexos do descendente nos relatórios):

| # | Pai | Mãe | P(C) exata | Objetivo |
|---|---|---|---|---|
| 1 | het SOD1 p.A5V | selvagem | 0,50 | caso-base dominante, alta penetrância |
| 2 | selvagem | laudo: expansão C9orf72 (45 rep.) | 0,50 | expansão pelo laudo, efeito do sexo, π = 0,33 |
| 3 | het SOD1 p.A5V | laudo: expansão C9orf72 | 0,50 e 0,50 (combinado 0,75 portador de ≥ 1) | **exemplo literal do TCC**, dois genes |
| 4 | het SOD1 p.D91A | het SOD1 p.D91A | 0,25 (recessiva) com a tabela curada; **sem lócus de risco com o ClinVar real** (conflitante, D18) | CPT recessiva (testes) e regra "conflitante não sustenta risco" (resultados) |
| 5 | het TARDBP p.M337V | het FUS p.R521C | 0,50 e 0,50 | penetrâncias menores, FUS precoce |

Testes unitários cobrem pais homozigotos e controle sem variantes (P = 0).

## 5. CLI

```
ela-preditivo gerar-cenarios --saida data/sinteticos [--seed 2026]
ela-preditivo executar --vcf-mae X --vcf-pai Y --sexo {M,F} --idade-atual 30 --n 10000 --seed 42 --motor {pymc,numpy} --saida resultados/cenario_1
ela-preditivo avaliar --cenarios todos --n 1000 10000 100000 --repeticoes 30 --saida resultados/avaliacao
ela-preditivo tudo --saida resultados   # gera cenários, executa os 5, avalia, monta índice Markdown
ela-preditivo atualizar-base [--baixar [--release AAAA-MM-DD]] [--base ARQUIVO] [--registro DIR] [--listar]   # registra a versão do ClinVar e compara com a anterior (D29)
```

`executar` grava: `variantes_anotadas.csv`, `dosagens.csv`, `resumo_risco.csv/.md`, `risco_condicional.csv`, `curvas.csv` (t, F, S, banda), `figuras/*.png`, `metadados.json` (seed, N, versões, data, aviso legal; desde 08/11/2026 também release e sha256 da base ClinVar, `loci_descartados` e `saida_limpa`). As três funções apagam no início as saídas de uma execução anterior na pasta de destino (`pipeline._limpar_saida`, só os nomes conhecidos; D23).

## 6. Saídas para a seção 5 (nomes em `relatorio.py`)

Tabelas: 1 variantes anotadas por cenário; 2 transmissão exata vs MC (PyMC e NumPy); 3 risco vitalício por gene e combinado com IC 95%; 4 risco condicional à idade atual (20, 30, 40, 50, 60) e sexo; 5 estabilidade numérica (N × 30 execuções, DP vs EP teórico); 6 calibração das priors Beta; 7 recuperação de parâmetros pela Lifelines; 8 tempo de processamento.

Figuras: 1 DAG da rede; 2 priors de penetrância por gene; 3 G(t) ajustadas vs pontos da literatura; 4 F(t)/S(t) por cenário com banda e KM; 5 idade de início por sexo; 6 aderência mendeliana (barras MC vs exato); 7 erro padrão vs N (log-log); 8 hazard h(t) com faixa 60–75 destacada. Legendas "Figura N — ... Fonte: elaborado pela autora (2026)."

## 7. Fases e critério de pronto

| Fase | Entrega | Pronto quando |
|---|---|---|
| 1 | scaffold, `pyproject`, YAML, regiões, tabela curada (coordenadas conferidas online) | `uv pip install -e ".[dev]"` e `python -c "import pymc, lifelines, vcf, Bio"` passam |
| 2 | `calibracao.py`, `exato.py` + testes | Beta reproduz IC (erro < 0,01); CPT soma 1; 1×0 → 0,5; recessiva 1×1 → 0,25 |
| 3 | `cenarios.py`, `ingestao.py`, `anotacao.py`, `genotipo.py` + testes | 10 VCFs gerados; dosagens dos 5 cenários batem com a tabela §4; ruído filtrado; laudo do C9orf72 vira lócus (D16); `<STR45>` ainda detectado no caminho secundário |
| 4 | `monte_carlo.py`, `rede_bayesiana.py` + testes | PyMC ≈ NumPy ≈ exato (< 4·EP) com N = 10.000, seed 42 |
| 5 | `sobrevivencia.py` + testes | `MisturaCuraWeibullFitter` recupera π, k, λ (< 5%); F(∞) ≈ P(C)·π |
| 6 | `avaliacao.py`, `relatorio.py`, `cli.py`; `ela-preditivo tudo` | 8 tabelas + 8 figuras em `resultados/`; DP ∝ N^−1/2 |
| 7 | README, `docs/07_resultados_secao5.md` (texto-base com números reais) | revisão pela autora |
| 8b | correções da revisão de 08/11/2026 (docs/04, D20 a D29), `atualizacao.py`, um teste por item | 106 testes; cada item de A e B com teste que falhava antes e passa depois; `baixar_clinvar` validado contra o NCBI (releases 2026-10-11 e 2026-11-01) |

## 8. Verificação

```bash
source .venv/bin/activate   # na raiz do repositório
pytest -q ela_preditivo/tests
ela-preditivo tudo --saida resultados --seed 42
ls resultados/tabelas resultados/figuras
```
Checar: aderência |P̂ − P| < 2·EP em todos os cenários; DP entre execuções cai ~√10 por década de N; F(∞) do KM ≈ P(C)·π; medianas de início coerentes com o YAML; aviso legal presente em cada relatório.
