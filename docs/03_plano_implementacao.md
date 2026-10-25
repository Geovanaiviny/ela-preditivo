# 03 — Plano de implementação do pacote `ela_preditivo`

> **Estado em 24/10/2026**: fases 1 a 7 implementadas (74 testes passando). Diferenças em relação ao plano original: módulo `pipeline.py` separado da CLI; `exato.py` como módulo próprio; Tabela 10 (Kaplan-Meier) e Tabela 9 (sensibilidade) acrescentadas; `tudo` executa cada cenário para os dois sexos. A apresentação do pacote está em `ela_preditivo/README.md`; o texto-base da seção 5 em `docs/07_resultados_secao5.md`.

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
    calibracao.py                     # Beta de ponto+IC; Weibull/log-normal de pontos KM/faixas etárias
    exato.py                          # CPT e fórmulas fechadas (referência)
    rede_bayesiana.py                 # modelo PyMC e sample_prior_predictive
    monte_carlo.py                    # amostrador NumPy equivalente; repetições; condicionamento por idade
    sobrevivencia.py                  # coorte sintética, KM, Weibull, MisturaCuraWeibullFitter, condicional
    cenarios.py                       # definição dos 5 cenários e gerador de VCF 4.2 sintético
    avaliacao.py                      # aderência, estabilidade, coerência, tempo
    relatorio.py                      # figuras PNG 300 dpi e tabelas CSV/Markdown com legendas prontas
    cli.py                            # argparse: gerar-cenarios | executar | avaliar | tudo
  tests/
    test_exato.py test_calibracao.py test_ingestao.py test_anotacao.py test_genotipo.py
    test_monte_carlo.py test_rede_bayesiana.py test_sobrevivencia.py test_cenarios.py
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

Carregador do subconjunto real (opcional, quando a autora fornecer): `anotacao.carregar_clinvar_subconjunto(variant_summary_txt, clinvar_vcf, snp_result_txts)` lendo as chaves descritas em `01_analise_tcc.md` §7; mapa de classificação: `Pathogenic`, `Likely_pathogenic`, `Pathogenic/Likely_pathogenic` → risco; `Uncertain_significance`, `Conflicting_*` → VUS (sem risco, listado); `Benign*` → ignorado. Estrelas de `CLNREVSTAT`: practice_guideline 4, reviewed_by_expert_panel 3, criteria_provided,_multiple_submitters,_no_conflicts 2, criteria_provided,_single_submitter / conflicting 1, no_assertion* 0.

## 4. VCF sintético (`cenarios.py`)

VCF 4.2, GRCh38, uma amostra por arquivo (`MAE` ou `PAI`), colunas FORMAT `GT:DP:GQ`, cabeçalho com `##reference=GRCh38`, `##INFO`, `##FORMAT`, `##ALT=<ID=STR,...>`. Cada arquivo contém:
- as variantes do cenário (GT `0/1` ou `1/1`);
- ruído: 1 benigna (rs17883296), 1 VUS em FUS, 1 variante fora dos 4 genes (ex.: chr17), 1 registro com `DP=4` e `GQ=10` (reprovado no filtro `DP ≥ 10`, `GQ ≥ 20`, `FILTER=PASS`), 1 multialélico `ALT=A,T`.
- expansão do C9orf72 no estilo ExpansionHunter:
  `chr9  27573529  .  GGGGCC  <STR45>  .  PASS  END=27573534;RU=GGGGCC;REPID=C9ORF72;SVTYPE=STR  GT:REPCN:DP:GQ  0/1:2/45:30:60`
  Parser: ALT `<STR(\d+)>` ou `REPCN` dá a contagem por alelo; patogênico se ≥ 30, intermediário 24–29; anotação por gene + intervalo + contagem (nunca por string de alelo); `Bio.Seq` normaliza RU (GGGGCC ↔ GGCCCC).

Cenários (seed fixa 2026; gerar ambos os sexos do descendente nos relatórios):

| # | Pai | Mãe | P(C) exata | Objetivo |
|---|---|---|---|---|
| 1 | het SOD1 p.A5V | selvagem | 0,50 | caso-base dominante, alta penetrância |
| 2 | selvagem | expansão C9orf72 (45 rep.) | 0,50 | expansão, efeito do sexo, π = 0,33 |
| 3 | het SOD1 p.A5V | expansão C9orf72 | 0,50 e 0,50 (combinado 0,75 portador de ≥ 1) | **exemplo literal do TCC**, dois genes |
| 4 | het SOD1 p.D91A | het SOD1 p.D91A | 0,25 (recessiva) | CPT recessiva |
| 5 | het TARDBP p.M337V | het FUS p.R521C | 0,50 e 0,50 | penetrâncias menores, FUS precoce |

Testes unitários cobrem pais homozigotos e controle sem variantes (P = 0).

## 5. CLI

```
ela-preditivo gerar-cenarios --saida data/sinteticos [--seed 2026]
ela-preditivo executar --vcf-mae X --vcf-pai Y --sexo {M,F} --idade-atual 30 --n 10000 --seed 42 --motor {pymc,numpy} --saida resultados/cenario_1
ela-preditivo avaliar --cenarios todos --n 1000 10000 100000 --repeticoes 30 --saida resultados/avaliacao
ela-preditivo tudo --saida resultados   # gera cenários, executa os 5, avalia, monta índice Markdown
```

`executar` grava: `variantes_anotadas.csv`, `dosagens.csv`, `resumo_risco.csv/.md`, `risco_condicional.csv`, `curvas.csv` (t, F, S, banda), `figuras/*.png`, `metadados.json` (seed, N, versões, data, aviso legal).

## 6. Saídas para a seção 5 (nomes em `relatorio.py`)

Tabelas: 1 variantes anotadas por cenário; 2 transmissão exata vs MC (PyMC e NumPy); 3 risco vitalício por gene e combinado com IC 95%; 4 risco condicional à idade atual (20, 30, 40, 50, 60) e sexo; 5 estabilidade numérica (N × 30 execuções, DP vs EP teórico); 6 calibração das priors Beta; 7 recuperação de parâmetros pela Lifelines; 8 tempo de processamento.

Figuras: 1 DAG da rede; 2 priors de penetrância por gene; 3 G(t) ajustadas vs pontos da literatura; 4 F(t)/S(t) por cenário com banda e KM; 5 idade de início por sexo; 6 aderência mendeliana (barras MC vs exato); 7 erro padrão vs N (log-log); 8 hazard h(t) com faixa 60–75 destacada. Legendas "Figura N — ... Fonte: elaborado pela autora (2026)."

## 7. Fases e critério de pronto

| Fase | Entrega | Pronto quando |
|---|---|---|
| 1 | scaffold, `pyproject`, YAML, regiões, tabela curada (coordenadas conferidas online) | `uv pip install -e ".[dev]"` e `python -c "import pymc, lifelines, vcf, Bio"` passam |
| 2 | `calibracao.py`, `exato.py` + testes | Beta reproduz IC (erro < 0,01); CPT soma 1; 1×0 → 0,5; recessiva 1×1 → 0,25 |
| 3 | `cenarios.py`, `ingestao.py`, `anotacao.py`, `genotipo.py` + testes | 10 VCFs gerados; dosagens dos 5 cenários batem com a tabela §4; ruído filtrado; `<STR45>` detectado |
| 4 | `monte_carlo.py`, `rede_bayesiana.py` + testes | PyMC ≈ NumPy ≈ exato (< 4·EP) com N = 10.000, seed 42 |
| 5 | `sobrevivencia.py` + testes | `MisturaCuraWeibullFitter` recupera π, k, λ (< 5%); F(∞) ≈ P(C)·π |
| 6 | `avaliacao.py`, `relatorio.py`, `cli.py`; `ela-preditivo tudo` | 8 tabelas + 8 figuras em `resultados/`; DP ∝ N^−1/2 |
| 7 | README, `docs/07_resultados_secao5.md` (texto-base com números reais) | revisão pela autora |

## 8. Verificação

```bash
source .venv/bin/activate   # na raiz do repositório
pytest -q ela_preditivo/tests
ela-preditivo tudo --saida resultados --seed 42
ls resultados/tabelas resultados/figuras
```
Checar: aderência |P̂ − P| < 2·EP em todos os cenários; DP entre execuções cai ~√10 por década de N; F(∞) do KM ≈ P(C)·π; medianas de início coerentes com o YAML; aviso legal presente em cada relatório.
