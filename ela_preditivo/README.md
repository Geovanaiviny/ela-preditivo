# ela_preditivo — protótipo de apoio ao aconselhamento genético preditivo da ELA

Artefato computacional do TCC **"Desenvolvimento de Sistema Preditivo de Herança e Manifestação Clínica para Esclerose Lateral Amiotrófica (ELA) Baseado em Modelagem Estocástica e Redes Bayesianas"** (Geovana Íviny Santos Lima; orientação de Fabricio Carneiro Costa). Implementa, em Python, as três camadas descritas nas seções 3.3 e 4.3 a 4.6 do TCC e gera as tabelas e figuras da seção 5 (Resultados).

> **Aviso.** Instrumento experimental de apoio à decisão no aconselhamento genético preditivo da ELA, construído com dados sintéticos e parâmetros populacionais da literatura. Não constitui diagnóstico, não substitui o julgamento clínico e não deve ser usado isoladamente em decisões sobre pacientes. Nenhum dado genômico real é lido, armazenado ou distribuído por este repositório (Lei 13.709/2018, art. 5º, II; TCC, seção 3.4).

Versão 0.1.0 — 24 de outubro de 2026; revisão de 8 de novembro de 2026 (correções da revisão da autora/orientador: `../docs/04_decisoes.md`, D20 a D29). Documentos de apoio em `../docs/` (análise do TCC, modelo matemático, plano, decisões, ambiente, relação com o exemplo do orientador).

---

## 1. O que o artefato faz

Dado o VCF da mãe e o VCF do pai, o artefato responde às três perguntas do aconselhamento (TCC, 4.1), separando o que os modelos clássicos de herança misturam:

| Pergunta | Saída do artefato | Camada |
|---|---|---|
| Qual a probabilidade de o descendente **herdar** a variante de risco? | P(portador) por lócus, exata (CPT mendeliana) e simulada (Monte Carlo) | 2 |
| Qual a probabilidade de ele **manifestar** a doença ao longo da vida? | risco vitalício = P(portador) × penetrância, com intervalo de credibilidade de 95 % que propaga a incerteza publicada da penetrância | 2 |
| **Quando** a doença tende a se manifestar? | curvas F(t) e S(t) por idade, idade mediana e percentis de início, risco nos próximos 10/20 anos condicionado à idade atual sem sintomas e ao sexo | 3 |

Fluxo (TCC, 4.3 e 4.4):

```
VCF materno + VCF paterno
   │  camada 1 — ingestao.py · anotacao.py · genotipo.py
   │  PyVCF (pyvcf3): leitura; conferência da montagem GRCh38 no cabeçalho; filtro de qualidade (FILTER = PASS, DP ≥ 20, GQ ≥ 30; TCC 4.3); máscara GRCh38
   │  dos genes SOD1, C9orf72, TARDBP, FUS; decomposição multialélica e normalização REF/ALT; AC/AN/DB do INFO;
   │  anotação ClinVar real (dados_reais/) + tabela curada; expansão GGGGCC do C9orf72 pelo laudo laboratorial (--c9orf72-mae/pai);
   │  vetor de dosagem alélica 0/1/2 por lócus de risco (só Pathogenic/Likely pathogenic; sítio com genótipo não determinado
   │  num genitor descarta o lócus inteiro, TCC 4.3); indicadores de qualidade (TCC 4.2.3)
   ▼
Rede Bayesiana (PyMC) + Monte Carlo (N = 10.000 fecundações hipotéticas)
   │  camada 2 — rede_bayesiana.py · monte_carlo.py · exato.py · calibracao.py
   │  Dose materna/paterna → alelo transmitido → dose do descendente → portador (dominante/recessiva)
   │  → manifesta (π ~ Beta calibrada ao IC 95 % da literatura) → idade de início (Weibull por gene, deslocada pelo sexo)
   ▼
Análise de sobrevivência (Lifelines)
   │  camada 3 — sobrevivencia.py
   │  coorte sintética censurada aos 90 anos; Kaplan-Meier com IC; Weibull; modelo de cura mista S(t) = 1 − π(1 − e^{−(t/λ)^ρ});
   │  F(t) = P(C)·π·G(t) com banda de credibilidade; risco condicional à idade atual e atualização bayesiana de P(portador)
   ▼
Relatório (relatorio.py · pipeline.py · cli.py): tabelas CSV/Markdown, figuras PNG 300 dpi, relatório Markdown, metadados JSON
```

O exemplo enviado pelo orientador (`../exemplo_maquina_tcc_ela.py`) tem as mesmas três camadas; o que foi mantido, evoluído e corrigido está em `../docs/06_base_exemplo_professor.md`.

## 2. Modelo probabilístico (resumo; detalhes em `../docs/02_modelo_matematico.md`)

Para cada lócus de risco g (um gene e uma variante), com dosagens parentais `d_m, d_f ∈ {0, 1, 2}` lidas dos VCFs:

- transmissão: `a_m ~ Bernoulli(d_m/2)`, `a_f ~ Bernoulli(d_f/2)`, dose do descendente `D = a_m + a_f`;
- portador: `C = 1[D ≥ 1]` (dominante) ou `C = 1[D = 2]` (recessiva, ex. SOD1 p.Asp91Ala);
- penetrância vitalícia `π ~ Beta(α, β)`, calibrada ao ponto e ao IC 95 % de Douglas & Baralle (2024): C9orf72 0,33 [0,209–0,532]; SOD1 0,54 [0,327–0,886]; TARDBP 0,38 [0,211–0,698]; FUS 0,19 [0,130–0,284];
- manifestação `M ~ Bernoulli(C · π)`; idade de início `T | M = 1 ~ Weibull(k, λ) + δ_sexo` (C9orf72: homens −1 ano, mulheres +1 ano; Goutman et al., 2022);
- cura mista: `F(t) = P(C) · π · G(t)`, `S(t) = 1 − F(t)`, `F(∞) = P(C)·π`;
- condicionamento ao descendente assintomático na idade a: `P(T ≤ t | T > a) = (F(t) − F(a)) / (1 − F(a))` e `P(C = 1 | assintomático em a) = q(1 − πG(a)) / (1 − qπG(a))`;
- vários lóci: independência, `P(qualquer) = 1 − ∏(1 − P_g)`.

Fórmulas exatas de referência: dominante `P(C) = 1 − (1 − d_m/2)(1 − d_f/2)`; recessiva `P(C) = (d_m/2)(d_f/2)`. O Monte Carlo é a amostragem preditiva a priori do DAG em PyMC (`pm.sample_prior_predictive`), com um amostrador NumPy de semântica idêntica usado nas execuções repetidas de estabilidade e como verificação cruzada.

## 3. Parâmetros e dados

| Fonte | Onde está | Observações |
|---|---|---|
| Penetrância, IC, herança, curvas de idade, efeito do sexo, limiares | `config/parametros_literatura.yaml` | cada valor tem `citacao` e `confirmar`; `confirmar: true` = provisório, a validar pela autora (hoje: curvas de idade de SOD1, TARDBP e FUS, à espera de Richard et al., 2026; pontos intermediários da curva de Murphy et al., 2017). A distribuição de início de cada gene aceita `pontos` (curva de Kaplan-Meier ou faixas etárias) ou `estatisticas` (`{media, dp}` ou `{mediana, iqr}`, resolvidas em forma fechada; `metodo_inicio` na Tabela 6) |
| Regiões dos genes (GRCh38) | `config/regioes_genes_grch38.yaml` | Ensembl REST, 24/10/2026, flanco de 5 kb |
| Variantes conhecidas (anotação) | `data/variantes_curadas.csv` | SOD1 p.Ala5Val (rs121912442, chr21:31659783 C>T), SOD1 p.Asp91Ala recessiva (rs80265967, chr21:31667290 A>C), TARDBP p.Met337Val (rs80356730, chr1:11022418 A>G), FUS p.Arg521Cys (rs121909668, chr16:31191418 C>T), expansão GGGGCC do C9orf72 (chr9:27573529–27573534), SOD1 rs17883296 benigna (exemplo do TCC). Coordenadas conferidas no dbSNP/ClinVar em 24/10/2026 |
| Subconjunto real do ClinVar/dbSNP (seção 4.2.2 do TCC) | `dados_reais/` na raiz do repositório (ignorada pelo git) ou `ELA_DADOS_BRUTOS` | `base_consolidada_ela.csv` (preferida), `clinvar_ela_4genes.csv`/`variant_summary.txt` ou `clinvar*.vcf`; encontrados automaticamente por `anotacao.tabela_anotacao()` e mesclados com a tabela curada (classificação do ClinVar prevalece; a curada contribui herança e a expansão do C9orf72). Sem eles o protótipo roda só com a tabela curada (`--so-tabela-curada`). `ela-preditivo atualizar-base` baixa a release mensal do ClinVar (quatro genes), registra release e sha256 em `dados_reais/versoes/` e compara com a release anterior; cada execução grava arquivo, release e sha256 da base em `metadados.json` |
| Cenários familiares | `data/sinteticos/` (gerados por `cenarios.py`, seed 2026) | VCF 4.2, GRCh38, uma amostra por arquivo, com ruído para exercitar filtros (benigna, não anotada, fora dos genes, baixa qualidade, multialélica) |

A expansão do C9orf72 **não é lida do VCF**: o fluxo de variantes curtas não a detecta e o TCC (4.2.1) a trata como parâmetro do laudo laboratorial. Informe o nº de repetições do maior alelo de cada genitor (`--c9orf72-mae 45`, `--c9orf72-pai 2 45` para os dois alelos). Limiar: ≥ 30 repetições patogênico, 24–29 intermediário (configurável). Um VCF no estilo ExpansionHunter (`ALT=<STRn>`, `REPCN`) ainda é lido como caminho secundário; se divergir do laudo, prevalece o laudo e a divergência fica no relatório.

## 4. Instalação

Requisitos: Python 3.11 ou 3.12 (recomendado 3.12 via `uv`), acesso ao PyPI. Sem g++ o PyTensor roda em modo Python, correto e suficiente para este modelo.

```bash
cd <raiz do repositório>
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e "./ela_preditivo[dev]"
export PYTENSOR_FLAGS=cxx=          # só se a máquina não tiver g++
python -c "import pymc, lifelines, vcf, Bio; print(pymc.__version__, lifelines.__version__)"   # 5.28.5 0.30.3
```

Dependências pinadas em `pyproject.toml`: pymc 5.28.5, lifelines 0.30.3 (versão citada no TCC), numpy 2.x, pandas 2.x, scipy, matplotlib, seaborn, pyvcf3 1.0.4 (fork mantido do PyVCF, `import vcf`), biopython, pyyaml; pytest para os testes.

## 5. Uso

```bash
# 1) gerar os VCFs sintéticos dos 5 cenários
ela-preditivo gerar-cenarios --saida ela_preditivo/data/sinteticos

# 2) executar um caso (as três camadas) e gravar relatório, tabelas e figuras
ela-preditivo executar --vcf-mae ela_preditivo/data/sinteticos/cenario_3_mae.vcf \
                       --vcf-pai ela_preditivo/data/sinteticos/cenario_3_pai.vcf \
                       --sexo F --idade-atual 30 --n 10000 --seed 42 --motor pymc --saida resultados/cenario_3_F

# 3) avaliação transversal (estabilidade, tempo, coerência, calibração, sensibilidade)
ela-preditivo avaliar --dir-cenarios ela_preditivo/data/sinteticos --saida resultados/avaliacao --n 1000 10000 100000 --repeticoes 30

# 4) tudo de uma vez: cenários → 5 casos × 2 sexos → avaliação → índice resultados/README.md
ela-preditivo tudo --saida resultados --seed 42

# 5) atualizar a base ClinVar: baixa a release mensal (4 genes) para dados_reais/, registra a versão e compara com a anterior
ela-preditivo atualizar-base --baixar                      # ou --base dados_reais/clinvar_ela_4genes.vcf --release 2026-09-28; --listar mostra o registro
```

Opções de `executar`: `--motor {pymc,numpy}` (o outro motor roda sempre como verificação cruzada), `--config` (YAML alternativo), `--tabela-variantes` (CSV de anotação alternativo), `--horizonte` (padrão 90 anos), `--sem-figuras`. A pasta de saída é limpa das saídas de uma execução anterior antes de gravar (só os nomes que o próprio artefato produz; outros arquivos ficam). Toda saída grava `metadados.json` com seed, N, versões, caminhos, release e sha256 da base ClinVar, lóci descartados e a limpeza feita, para reprodução.

Uso como biblioteca:

```python
from ela_preditivo import pipeline
r = pipeline.executar("mae.vcf", "pai.vcf", "saida/", sexo="M", idade_atual=40, n=10_000, seed=42)
r["resumo"]        # DataFrame por lócus: P(portador), penetrância, risco vitalício, IC 95 %, idade de início
r["combinado"]     # dicionário com o risco combinado (qualquer lócus)
r["curvas"]        # F(t), S(t), h(t) e bandas por unidade
```

## 6. Saídas

Por execução (`executar`):

| Arquivo | Conteúdo |
|---|---|
| `relatorio.md` | texto com aviso legal, entrada, resultado por lócus e combinado, verificações e limitações; incorpora as tabelas e figuras |
| `tabelas/tabela_01_variantes_anotadas` | variantes aprovadas no filtro, por genitor, com classe (risco, VUS, conflitante, benigna, não anotada), CLNSIG, estrelas, herança |
| `tabelas/tabela_01b_vetor_dosagem` | dosagens 0/1/2 por lócus de risco e P(portador) exata; lócus com genótipo não determinado num genitor aparece marcado como descartado, com a dosagem desconhecida vazia e o motivo em `observacao`, sem entrar no cálculo (TCC 4.3) |
| `tabelas/tabela_02_aderencia` | exato vs PyMC vs NumPy, erro padrão, desvio em EPs, qui-quadrado do genótipo |
| `tabelas/tabela_03_risco_vitalicio` | P(portador), penetrância (média e IC), risco vitalício (IC de credibilidade 95 %; no combinado, percentil dos sorteios de π, o mesmo cálculo da Figura 4), idade de início (mediana, p10, p90), combinado |
| `tabelas/tabela_04_risco_condicional` (+ `04b` Kaplan-Meier) | por idade atual (0 a 70): P(portador \| assintomático), risco em 10 e 20 anos, vitalício residual |
| `tabelas/tabela_07_recuperacao_lifelines` | parâmetros π, λ, ρ recuperados pelo modelo de cura mista |
| `tabelas/tabela_10_kaplan_meier` | S(t) com IC em 40–80 anos, mediana ("não atingida" sob cura mista), idade em que 90 % do risco já ocorreu |
| `figuras/figura_01_dag.png` | Rede Bayesiana |
| `figuras/figura_04_risco_temporal.png` | F(t) e S(t) com banda de credibilidade e Kaplan-Meier sobreposto |
| `figuras/figura_05_idade_inicio.png` | histograma da idade de início por lócus (por sexo em `tudo`) |
| `figuras/figura_06_aderencia.png` | barras exato vs Monte Carlo |
| `figuras/figura_08_hazard.png` | h(t) com a faixa 60–75 anos (pico de incidência populacional, só referência; comparada apenas com o pico do risco combinado) |
| `curvas.csv`, `variantes_ingeridas_anotadas.csv`, `metadados.json` | dados brutos e proveniência |

Avaliação (`avaliar`): Tabela 5 (estabilidade por N × 30 sementes vs erro padrão teórico), Tabela 6 (calibração das priors), Tabela 7 (coerência das curvas, com o pico de h(t) por lócus e do risco combinado; a faixa 60–75 anos só é comparada com o combinado, como referência), Tabela 8 (tempos PyMC × NumPy), Tabela 9 (sensibilidade: literatura × exemplo do orientador × C9orf72 de coorte familiar); Figuras 2 (priors), 3 (G(t) ajustadas vs literatura) e 7 (DP vs N, log-log).

Todas as legendas saem no padrão "Tabela N — ... / Figura N — ...; Fonte: elaborado pela autora (2026)". Números em tabelas usam ponto decimal (padrão do CSV); o texto do TCC pode converter para vírgula.

## 7. Cenários e resultados

Execução definitiva em 24/10/2026 (`ela-preditivo tudo --saida resultados --seed 42`): 5 cenários × 2 sexos com N = 10.000, avaliação com N ∈ {1.000, 10.000, 100.000} × 30 sementes; 5 min 22 s no total. Índice completo em `../resultados/README.md`; relatório de cada caso em `../resultados/cenarios/cenario_<n>_<sexo>/relatorio.md`; avaliação em `../resultados/avaliacao/relatorio.md`.

> **Nota de 08/11/2026.** Os números desta seção vêm de `resultados/` gerado em 03/11/2026, antes das correções D20 a D29. Ao regenerar (`ela-preditivo tudo`, numa máquina com `dados_reais/`), mudam: o IC do risco combinado, que passa a ser o percentil dos sorteios de π (cenário 3: 39,1 % [28,8–48,6] em vez de [24,9–52,1]; cenário 5: 26,9 % [18,5–35,9] em vez de [16,2–38,2]); a Tabela 7, que ganha a linha do risco combinado e perde a coluna de aprovação por lócus (pico de h(t) do combinado: cenário 1 53,0; cenário 2 62,0; cenário 3 57,5; cenário 5 54,0 anos); o rótulo `conflitante` da SOD1 p.Asp91Ala no cenário 4; e os metadados (release e sha256 da base, lóci descartados, limpeza da pasta). Os valores por lócus não mudam.

### 7.1 Os cinco cenários (Tabela 3 consolidada)

| Cenário (TCC, 4.5) | Lócus de risco | P(portador) | Risco vitalício [IC 95 %] | Idade mediana de início, anos (F / M) |
|---|---|---|---|---|
| 1. Pai heterozigoto SOD1 p.Ala5Val × mãe selvagem | SOD1 A4V | 0,50 | 26,9 % [16,3–37,2] | 50,3 |
| 2. Mãe com expansão C9orf72 (45 repetições) × pai selvagem | C9orf72 | 0,50 | 16,6 % [10,2–23,7] | 59,3 / 57,3 |
| 3. Pai het. SOD1 p.Ala5Val × mãe com expansão C9orf72 (exemplo literal do TCC) | C9orf72 | 0,50 | 16,6 % [10,2–23,7] | 59,3 / 57,3 |
| | SOD1 A4V | 0,50 | 26,9 % [16,3–37,2] | 50,3 |
| | qualquer lócus | 0,75 | 39,1 % [24,9–52,1] | 53,0 / 52,3 (primeiro início) |
| 4. Ambos os pais het. SOD1 p.Asp91Ala (recessiva) | SOD1 D91A | 0,25 | 13,5 % [8,2–18,6] | 50,3 |
| 5. Pai het. TARDBP p.Met337Val × mãe het. FUS p.Arg521Cys | TARDBP M337V | 0,50 | 19,2 % [10,5–28,7] | 54,2 |
| | FUS R521C | 0,50 | 9,6 % [6,3–13,3] | 42,8 |
| | qualquer lócus | 0,75 | 26,9 % [16,2–38,2] | 50,5 |

O que os números mostram:

- **Transmissão ≠ manifestação.** Nos cenários dominantes a probabilidade de herdar é sempre 50 %, mas o risco de adoecer vai de 9,6 % (FUS) a 26,9 % (SOD1), porque a penetrância é incompleta e varia por gene (TCC, 4.1). O intervalo de credibilidade carrega a incerteza publicada da penetrância até o resultado final.
- **Herança recessiva** (cenário 4): só o homozigoto está em risco, P(portador) cai para 25 % e o risco vitalício para 13,5 %, mesmo com os dois pais portadores.
- **Dois genes na família** (cenário 3): 75 % de chance de herdar pelo menos uma variante e 39,1 % de manifestar, sob independência entre lóci.
- **Sexo**: no C9orf72 o descendente masculino manifesta 2 anos antes (57,3 vs 59,3 anos); nos demais genes não há evidência no TCC e o efeito é nulo por construção.
- **Idade atual sem sintomas** (cenário 3, descendente feminina): aos 40 anos o risco nos próximos 20 anos é 23,5 % e o vitalício residual 35,0 %; aos 60 anos caem para 14,8 % e 14,9 %; a probabilidade de portar SOD1 p.Ala5Val, dado assintomático aos 60, cai de 50 % para 36,3 % (atualização bayesiana).
- **Kaplan-Meier** (cenário 3): a mediana de sobrevivência "não é atingida" em nenhum lócus, assinatura do modelo de cura mista (risco vitalício < 50 %); 90 % do risco do SOD1 já ocorreu aos 65 anos e o do C9orf72 aos 70.

### 7.2 Verificações (TCC, 4.5)

| Critério | Resultado |
|---|---|
| Aderência teórica (Tabela 2) | maior desvio entre Monte Carlo e valor exato nos 10 casos: 1,39 erros padrão (limite usual 4); qui-quadrado do genótipo sem rejeição; PyMC e NumPy concordam |
| Estabilidade numérica (Tabela 5, Figura 7) | razão DP observado / EP teórico média de 1,04 nos 5 cenários; no cenário 3 o DP de P(manifestação) cai de 0,0146 (N = 1.000) para 0,0054 (10.000) e 0,0017 (100.000), inclinação −½ em log-log |
| Coerência das curvas (Tabelas 7 e 10, Figura 4) | risco vitalício por Kaplan-Meier difere de P(C)·π em no máximo 0,006; mediana de início da Weibull da Lifelines difere da exata em até 1,2 ano; o modelo de cura mista recupera π com erro ≤ 3 % (ex.: SOD1 0,526–0,537 vs 0,539; FUS 0,194 vs 0,192), λ e ρ dentro de 4 %; pico de h(t): C9orf72 62 anos, SOD1 53, TARDBP 57, FUS 43,5 (início mais precoce, curvas provisórias); a faixa de incidência populacional 60–75 anos (Feldman et al., 2022) é comparada só com o pico do risco combinado, como referência, e não aprova nem reprova variantes |
| Tempo (Tabela 8) | NumPy: 0,007 s para N = 100.000; PyMC: 0,20 s (1.000), 1,7 s (10.000), 16,4 s (100.000) em modo Python sem g++; caso completo com figuras ≈ 4 s |
| Sensibilidade (Tabela 9, cenário 3) | risco combinado de 39,1 % com a literatura, 61,5 % com os parâmetros do exemplo do orientador (penetrância 0,90/0,60) e 59,8 % com C9orf72 de coorte familiar (π = 0,90): a escolha da penetrância domina o resultado |

## 8. Verificações que o artefato faz de si mesmo (TCC, 4.5)

| Critério do TCC | Como é verificado | Onde |
|---|---|---|
| Aderência teórica | P(portador) e P(manifesta) simuladas vs fórmulas exatas, em erros padrão; qui-quadrado das frequências de D ∈ {0,1,2} vs CPT; PyMC vs NumPy | Tabela 2, Figura 6, testes `test_nucleo_estocastico.py` |
| Estabilidade numérica | 30 execuções por N ∈ {1e3, 1e4, 1e5}; DP entre execuções vs √(p(1−p)/N); inclinação −½ em log-log | Tabela 5, Figura 7 |
| Coerência das curvas | F(∞) = P(C)·π vs Kaplan-Meier; mediana exata vs Weibull da Lifelines; cura mista recupera π, λ, ρ; pico de h(t) por lócus e do risco combinado (faixa 60–75 só como referência para o combinado) | Tabelas 7 e 10, Figura 4 |
| Tempo de processamento | por motor e por N | Tabela 8 |
| Sensibilidade | literatura × parâmetros do exemplo do orientador × C9orf72 familiar (π = 0,9) | Tabela 9 |

## 9. Estrutura do código

```
ela_preditivo/
  pyproject.toml  README.md
  config/parametros_literatura.yaml  config/regioes_genes_grch38.yaml
  data/variantes_curadas.csv  data/sinteticos/
  src/ela_preditivo/
    __init__.py        versão, caminhos, GENES, AVISO_LEGAL
    ingestao.py        ler_vcf, carregar_regioes, contar_repeticoes, resumo_ingestao          (camada 1)
    anotacao.py        anotar, classificar_clnsig, estrelas_de_revstat, carregadores ClinVar/dbSNP
    genotipo.py        vetor_dosagem, perfil_variantes
    calibracao.py      ajustar_beta, ajustar_weibull/lognormal (pontos), weibull_de_momentos/quantis (estatísticas), carregar_parametros (YAML → priors)
    exato.py           cpt_segregacao, prob_portador, DistribuicaoInicio, f_acumulada, risco_condicional, hazard
    monte_carlo.py     Locus, ResultadoSimulacao, simular_numpy, repetir, condicionar_idade   (camada 2)
    rede_bayesiana.py  construir_modelo (PyMC), simular_pymc, descrever_dag
    sobrevivencia.py   coorte_sintetica, ajustar_km, MisturaCuraWeibullFitter, curvas_analiticas, tabela_risco_condicional (camada 3)
    avaliacao.py       aderencia, estabilidade, tempos, coerencia, sensibilidade
    relatorio.py       figuras 1 a 8, salvar_tabela, escrever_relatorio, escrever_metadados
    atualizacao.py     baixar_clinvar, registrar_versao, comparar_versoes, atualizar (versões da base ClinVar)
    pipeline.py        executar, avaliar, tudo (limpam a pasta de saída no início)
    cli.py             ela-preditivo {gerar-cenarios | executar | avaliar | tudo | atualizar-base}
  tests/               106 testes (pytest)
```

## 10. Dicionário de dados (colunas principais)

| Tabela / DataFrame | Coluna | Significado |
|---|---|---|
| variantes ingeridas (`ingestao.ler_vcf`) | `cromossomo, posicao, ref, alt, indice_alt, n_alt` | coordenada GRCh38 sem prefixo "chr"; um registro por ALT após decomposição |
| | `tipo` | snv, indel, repeticao, simbolica |
| | `gt, dosagem` | genótipo e nº de cópias do ALT (0/1/2) |
| | `repeticoes` | cópias do motivo GGGGCC (ALT `<STRn>`, FORMAT REPCN ou contagem) — caminho secundário; o laudo entra em `vetor_dosagem` |
| | `posicao_vcf, ref_vcf, alt_vcf, normalizada` | representação original e se foi normalizada (prefixo/sufixo comuns removidos) |
| | `ac, an, no_dbsnp, montagem` | INFO AC (por ALT), AN e flag DB; montagem identificada no cabeçalho (GRCh38/GRCh37/desconhecida) |
| | `aprovado, motivo_reprovacao` | fora_das_regioes, genotipo_ausente, filtro_nao_pass, dp_baixo, gq_baixo |
| anotadas (`anotacao.anotar`) | `classe` | risco (P/LP), vus (significado incerto, inclusive VUS-high), conflitante (classificações conflitantes ou mistura de patogênico e benigno), benigna, nao_anotada, intermediaria/normal (repetições) |
| | `clnsig, estrelas, revstat, n_submissores, conflito, heranca, allele_id, freq_alfa, fonte_anotacao` | classificação ClinVar, estrelas, estado de revisão, nº de submissores, classificações conflitantes, herança (tabela curada), AlleleID, frequência ALFA, fonte e chave usadas no cruzamento (`clinvar_base_consolidada:posicao_alelos`, `tabela_curada:rs`, `rs_ambiguo:n_alelos`) |
| vetor de dosagem | `fonte` | `vcf`, `laudo` ou `laudo+vcf` (origem da dosagem do lócus) |
| vetor de dosagem (`genotipo.vetor_dosagem`) | `dosagem_mae, dosagem_pai, heranca, p_portador_exato, descartado, observacao` | entrada do nó inicial da Rede Bayesiana; `descartado = True` quando um genitor tem o sítio com genótipo não determinado (dosagem vazia, motivo em `observacao`; o lócus não entra no cálculo, TCC 4.3) |
| resumo (`ResultadoSimulacao.resumo`) | `p_portador_exato/mc, ep_portador` | transmissão exata, simulada e erro padrão |
| | `penetrancia_media/q025/q975` | prior Beta: média e IC 95 % |
| | `p_manifesta_exato/mc/q025/q975` | risco vitalício e intervalo de credibilidade |
| | `idade_mediana_exata/mc, idade_p10/p90_mc` | idade de início entre os que manifestam |
| curvas (`sobrevivencia.curvas_analiticas`) | `t, F, S, h, F_q025, F_mediana, F_q975` | curvas por unidade (lócus ou "qualquer lócus") |
| risco condicional | `idade_atual, p_portador_condicional, risco_10_anos, risco_20_anos, risco_vitalicio (+q025/q975)` | Tabela 4 |
| `metadados.json` | `base_anotacao (arquivo_base_real, release_base_real, sha256_base_real), loci_descartados, saida_limpa` | proveniência: versão da base usada, lóci descartados por genótipo indeterminado e o que foi apagado da pasta antes de gravar |

## 11. Testes

```bash
pytest -q ela_preditivo/tests        # 106 testes, ~15 s (5 deles só rodam com dados_reais/ presente)
```

Cobrem: CPT e fórmulas exatas; calibração (Beta reproduz ponto e limite inferior do IC; Weibull recupera parâmetros conhecidos e a mediana de 58 anos de Murphy); geração e leitura dos VCFs (normalização de cromossomo, regiões, multialélicos, expansão, filtros); anotação (classes, estrelas, cruzamento por posição e por rs, limiar de repetições, carregador de `variant_summary`); vetor de dosagem nos 5 cenários; aderência PyMC ≈ NumPy ≈ exato; recessividade; reprodutibilidade por seed; efeito do sexo; condicionamento por idade; Lifelines (censura, KM = F(∞), cura mista recupera π, λ, ρ; risco condicional KM ≈ analítico); pipeline e CLI de ponta a ponta; correções da revisão de 08/11/2026, um teste por item (`test_correcoes_revisao.py`: genótipo indeterminado, classe conflitante, estatísticas em forma fechada, N pequeno sem ajuste da Lifelines, DataFrame como tabela curada, limpeza da pasta, limiares do TCC 4.3, faixa 60–75 só no combinado, banda combinada, VUS-high e valores mistos, laudo sem linha de repetição, fileDate fixo); atualização de bases (`test_atualizacao.py`: registro, comparação entre releases, download filtrado a partir de um arquivo local e CLI).

## 12. Limitações e pontos a confirmar pela autora

1. **Curvas de idade de SOD1, TARDBP e FUS são placeholders** (`confirmar: true`) até a autora transcrever as faixas etárias de Richard et al. (2026). Os pontos intermediários da curva do C9orf72 (45 e 70 anos) foram lidos aproximadamente da figura de Murphy et al. (2017) e devem ser digitalizados. O YAML já aceita, no lugar dos pontos, as estatísticas publicadas — média e desvio padrão (Berdyński et al., 2022) ou mediana e IQR (McFarlane et al., 2025) — resolvidas em forma fechada; adotá-las é decisão da autora (`../docs/04_decisoes.md`, decisão em aberto nº 8).
2. **Prior Beta vs IC publicado**: os IC de Douglas & Baralle são simétricos em escala logarítmica; a Beta reproduz o ponto (mediana) e o limite inferior, mas subestima o limite superior (SOD1: 0,74 vs 0,886). O erro é reportado na Tabela 6; `calibracao_beta.peso_ponto: 0` no YAML inverte a prioridade (reproduz o IC e desloca a mediana).
3. **Penetrância do C9orf72**: nível populacional de Douglas & Baralle (0,33); a curva de Murphy (coortes familiares, quase completa aos 80 anos) entra só como forma etária. A Tabela 9 mostra o efeito de usar π = 0,9.
4. **Independência entre lóci** e ausência de fatores modificadores, oligogenia, mosaicismo, variantes de novo e faseamento.
5. **Efeito do sexo** documentado apenas para o C9orf72 (2 anos).
6. **Populações de referência** europeias/norte-americanas (TCC, Quadro 6); ausência de coortes brasileiras.
7. **Dados sintéticos**: o filtro de qualidade e a anotação foram exercitados com ruído controlado; o desempenho com arquivos VCF grandes (requisito não funcional) ainda não foi medido.
8. **Ferramentas citadas no TCC**: Biopython não lê VCF (aqui normaliza o motivo de repetição); PyVCF é usado pela distribuição mantida `pyvcf3`. Sugere-se ajustar o texto das seções 3.3 e 4.4.D. Ver `../docs/01_analise_tcc.md`, item 9, para os demais pontos (nomenclatura de F(t) e hazard, "segregação alélica", referências ausentes).

## 13. Trabalhos futuros

Versionamento do dbSNP e execução periódica automática de `atualizar-base` (o ClinVar já tem download, registro de versão e comparação entre releases, `atualizacao.py`); validação externa com dados de coortes (mediante aprovação ética); modelo oligogênico; fatores modificadores (idade dos pais, ancestralidade); interface clínica interativa; empacotamento com Docker.

## 14. Referências principais (ver lista completa no TCC)

Douglas & Baralle (2024) *J Med Genet* 61:294–297; Murphy et al. (2017) *Sci Rep* 7:2116; Feldman et al. (2022) *Lancet* 400:1363–1380; Goutman et al. (2022) *Lancet Neurol* 21:480–493; Richard et al. (2026) *Genes* 17(5):576; Danecek et al. (2011) *Bioinformatics* 27:2156–2158; Landrum et al. (2018) *NAR* 46:D1062–D1067; Sherry et al. (2001) *NAR* 29:308–311; Pearl (1988); Koller & Friedman (2009); Metropolis & Ulam (1949); Davidson-Pilon (2026) Lifelines 0.30.3; PyMC Development Team (2026); Chapman et al. (2000) CRISP-DM; Hevner et al. (2004); Peffers et al. (2007); Berdyński et al. (2022) *SOD1 mutations associated with ALS: analysis of variant severity* (média e desvio padrão da idade de início; a confirmar pela autora); McFarlane et al. (2025) *ALS & FTD* 26(sup. 1):41–49, DOI 10.1080/21678421.2025.2450805 (mediana e IQR; a confirmar pela autora).
