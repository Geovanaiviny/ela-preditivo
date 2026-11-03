# 01 — Análise do TCC e do que o artefato precisa fazer

Fonte: `docs/00_tcc_texto_extraido.md` (extraído de `TCC II - Escrita.docx` em 24/10/2026).

## 1. Identificação

- **Título**: Desenvolvimento de Sistema Preditivo de Herança e Manifestação Clínica para Esclerose Lateral Amiotrófica (ELA) Baseado em Modelagem Estocástica e Redes Bayesianas.
- **Autoria**: Geovana Íviny Santos Lima; Fabricio Carneiro Costa. O texto usa "elaborado pela autora".
- **Área**: Sistemas de Informação aplicados à saúde; aconselhamento genético preditivo.
- **Metodologia**: Design Science Research (Hevner et al., 2004; Peffers et al., 2007) para a dimensão científica + CRISP-DM (Chapman et al., 2000) para a dimensão processual.

### Estado do documento por seção

| Seção | Estado | Implicação para o código |
|---|---|---|
| 1 Introdução, 2 Fundamentação, 3 Metodologia | escritas | definem requisitos e ferramentas |
| 4.1 Entendimento do Negócio | escrita | define as três perguntas do aconselhamento e os parâmetros epidemiológicos |
| 4.2 Entendimento dos Dados | **reescrita na revisão de 03/11/2026**: 4.2.1 entrada em VCF (Quadro 2, "quatro cuidados", C9orf72 como parâmetro do laudo), 4.2.2 ClinVar/dbSNP (só P/LP sustentam risco; rs complementar), 4.2.3 parâmetros epidemiológicos e indicadores de qualidade | a exploração bruta (Quadros 2 a 6 da revisão anterior) saiu do texto; os arquivos reais estão em `dados_reais/` desde 03/11/2026 (docs/05) |
| 4.3 Preparação, 4.4 Modelagem, 4.5 Avaliação, 4.6 Implantação | esquemáticas (tópicos) | o código precisa materializar o que está prometido |
| **5 Resultados** | **vazia** (só "Interpretação", "Conexão com a fundamentação", "Limitações") | **o código deve gerar as tabelas e figuras** |
| **6 Conclusão** | **vazia** | depende dos resultados |

## 2. Problema e objetivo

Questões de pesquisa (Introdução): (1) é viável um artefato que integre dados genômicos e modelos probabilísticos na mesma arquitetura? (2) é possível oferecer predição personalizada sobre transmissão genética, manifestação clínica ao longo da vida e idade provável de início?

Objetivo: artefato computacional de apoio à decisão no aconselhamento genético preditivo da ELA, em três camadas integradas:

1. Leitura e tratamento dos dados genômicos parentais (VCF) → variáveis estruturadas.
2. Modelos probabilísticos: Rede Bayesiana para dependências + Monte Carlo para propagar incerteza → risco de transmissão e manifestação.
3. Projeção temporal (análise de sobrevivência) → curvas de risco ao longo da vida e idade provável de início.

Seção 4.1 fixa que o cálculo deve **separar três variáveis**: mecanismo de herança (50% é só a transmissão do alelo), manifestação clínica (penetrância incompleta, condicionada a idade e sexo) e idade de início, **mantendo a incerteza dos parâmetros até os resultados finais** (intervalos de confiança registrados) e as versões das bases.

## 3. Requisitos (seção 3.2)

Funcionais:
- ler arquivos VCF dos pais;
- reconhecer variantes nos genes SOD1, C9orf72, TARDBP e FUS;
- consultar ClinVar e dbSNP para classificar a relevância clínica;
- calcular o risco de transmissão por Rede Bayesiana;
- simular cenários de herança por Monte Carlo;
- estimar a idade provável de início;
- apresentar resultados em gráficos.

Não funcionais: módulos independentes; bases de variantes atualizáveis; desempenho com arquivos grandes; clareza dos resultados.

## 4. Arquitetura prometida

Pipeline de preparação (4.3): `[VCF Materno/Paterno] → [Ingestão & Validação] → [Filtragem por Genes Alvo] → [Anotação ClinVar/dbSNP] → [Matriz de Variáveis Controladas]`, com: filtro de qualidade de leitura; máscara de coordenadas (exons e regiões intrônicas adjacentes dos 4 genes); decomposição de multialélicos; **vetor genotípico parental em dosagem alélica (0 = homozigoto selvagem, 1 = heterozigoto, 2 = homozigoto mutante)** que alimenta o nó inicial da Rede Bayesiana.

Núcleo estocástico (4.4): `Redes Bayesianas → Monte Carlo → Análise de Sobrevivência (Lifelines)`.
- A. RB: DAG (Pearl 1988; Koller & Friedman 2009). Nós de entrada Genótipo Materno e Paterno; nó intermediário Genótipo do Descendente com CPT de segregação alélica; nó de saída Status de Portador/Expressão = probabilidade de portar × fator de penetrância incompleta do gene.
- B. MC: **N = 10.000** eventos de fecundação e transmissão hipotética; distribuição empírica do fenótipo da prole sob penetrância incerta.
- C. Sobrevivência: S(t) = probabilidade de portador permanecer assintomático até t; F(t) = 1 − S(t) = penetrância acumulada; idade provável de início por distribuições paramétricas calibradas pela literatura.
- D. Tecnologias: Biopython e PyVCF (VCF); pandas e NumPy; PyMC (RB + MC); Lifelines; matplotlib e seaborn.

Implantação (4.6): protótipo funcional empacotado; interface de visualização clínica (perfil de variantes, probabilidade de transmissão, curvas de risco por idade); documentação técnica (arquitetura, APIs internas, dicionário de dados, instalação); avisos legais (caráter preditivo-experimental, apoio à decisão, não diagnóstico).

## 5. Avaliação exigida (3.4 e 4.5)

- Dados sintéticos (razões: LGPD/comitê de ética e controle de cenários). **5 cenários familiares**, exemplo literal: "Pai heterozigoto para variante de alta penetrância no SOD1 vs. Mãe portadora da expansão de hexanucleotídeos no C9orf72".
- **Aderência teórica**: frequências do MC vs distribuições esperadas pela genética populacional.
- **Estabilidade numérica**: desvio padrão e erro padrão em execuções sucessivas com **N = 1.000, 10.000 e 100.000**.
- **Coerência das curvas**: comportamento assintótico das curvas de sobrevivência/manifestação vs idades de início de Douglas e Baralle (2024).
- Tempo de processamento (3.4).

## 6. Parâmetros da literatura que constam no texto

| Gene | Cromossomo | Penetrância vitalícia (Douglas & Baralle 2024) | IC 95% | Herança | Curva etária disponível |
|---|---|---|---|---|---|
| C9orf72 | 9 | 0,33 | 0,209–0,532 | dominante; expansão GGGGCC (ClinVar: GGGGCC[>24], GGCCCC[24_30]) em chr9:27.573.529–27.573.534 GRCh38 | Kaplan-Meier de Murphy et al. 2017 (n = 1.170) |
| SOD1 | 21 | 0,54 | 0,327–0,886 | dominante; p.D91A (D90A) recessiva | faixas etárias, Richard et al. 2026 (**valores não constam no texto**) |
| TARDBP | 1 | 0,38 | 0,211–0,698 | dominante | idem |
| FUS | 16 | 0,19 | 0,130–0,284 | dominante | idem |

Outros: forma familiar 10–15% dos casos; os 4 genes ≈ 55% das famílias de ascendência europeia; pico de incidência 60–75 anos; homens com expansão C9orf72 manifestam ~2 anos antes das mulheres (Goutman 2022); período já vivido sem sintomas e sexo entram como variáveis de cálculo (4.1).

Murphy et al. 2017 (resumo do artigo, conferir com a figura): penetrância ~0% aos 35 anos, 50% aos 58 e quase completa aos 80, em coortes familiares. Isso conflita com os 33% populacionais de Douglas & Baralle; ver reconciliação em `02_modelo_matematico.md`.

## 7. Fontes de dados descritas na seção 4.2 (a autora tem; esta máquina não)

| Arquivo | Tamanho | Uso previsto |
|---|---|---|
| `clinvar.vcf` (release 28/09/2026, GRCh38, VCF 4.1) | 1,98 GB | interpretação clínica nas chaves INFO |
| `variant_summary.txt` | 4,04 GB | uma linha por alelo e montagem, 43 colunas |
| `submission_summary.txt` | 3,62 GB | uma linha por submissão |
| `hgvs4variation.txt`, `var_citations.txt`, `cross_references.txt`, `gene_specific_summary.txt`, `organization_summary.txt` | 112 MB a 4,71 GB | HGVS, citações, ids externos, totais |
| `snp_result_*.txt` (4 arquivos, exportação tabular do dbSNP por gene) | 0,9–2,3 MB | validar rs e frequências |

Fatos do subconjunto (1.463 variantes nos 4 genes; 698 FUS, 331 SOD1, 311 TARDBP, 123 C9orf72) relevantes para o carregador:
- Chaves INFO do ClinVar: `CLNSIG`, `CLNREVSTAT`, `CLNSIGCONF`, `CLNVC`/`CLNVCSO`, `RS`, `AF_ESP`, `AF_EXAC`, `AF_TGP`, `GENEINFO` (ex.: `SOD1:6647`). `QUAL` e `FILTER` nulos; sem `FORMAT`/amostras; coluna `ID` = id de variação do ClinVar (não rs).
- Linha de exemplo do TCC (benigna, útil como ruído nos VCFs sintéticos): `21 31659509 1207199 G T . . AF_TGP=0.00739;CLNSIG=Likely_benign;GENEINFO=SOD1:6647;RS=17883296`.
- `variant_summary`: `RS# (dbSNP)` = −1 quando ausente (380 linhas); `PositionVCF` = −1 e `ReferenceAlleleVCF` = "na" em 5 registros do C9orf72 (4 microssatélites + 1 inserção patogênica, id 183034).
- Classificação por gene (Quadro 4): patogênicas + provavelmente patogênicas = 219 (138 SOD1, 54 FUS, 24 TARDBP, 3 C9orf72).
- Estado de revisão: 962 submissor único, 288 vários sem conflito, 73 conflitantes, 52 sem critério (zero estrelas), 88 sem classificação.
- dbSNP (exportação): campos `variation`, `variant_type`, `snp_id`, `clinical_significance` (vazio em 97%), `function_class`, `frequency` no formato `alelo:freq:contagem:estudo` (ex.: `T:0.242812:1216:1000Genomes`), múltiplos estudos por registro; 355 linhas duplicadas a remover; cabeçalhos repetidos pela paginação.
- Correspondência ClinVar↔dbSNP: 1.082 pelo rs; 85 com deslocamento de 1 base (deleções/duplicações/microssatélites, convenção de ancoragem); 176 sem contrapartida (29 patogênicas).
- Controle de consistência: patogênicas têm frequência ALFA máxima 0,000417 (nenhuma > 1%); benignas chegam a 0,46.
- Limitações (Quadro 6): coortes europeias/norte-americanas; interpretação concentrada nos EUA; evidência de submissor único; C9orf72 não endereçável por coordenada + alelo.

**Implicação**: o pacote traz uma tabela curada mínima e um carregador que aceita, quando fornecidos, `variant_summary.txt` filtrado e `clinvar.vcf` recortado pelos 4 genes, mais os `snp_result_*.txt`.

## 8. Ferramentas declaradas e viabilidade (verificado em 24/10/2026)

| Ferramenta | Papel no TCC | Situação | Versão alvo |
|---|---|---|---|
| Python | linguagem | 3.9 (sistema), 3.11 (sistema), 3.12 (uv, já baixado) | **3.12** |
| Biopython | "leitura e tratamento de VCF" | **não possui parser de VCF**; usar `Bio.Seq` apenas para o motivo GGGGCC/GGCCCC (complemento reverso) no gerador e no parser da expansão | 1.8x |
| PyVCF | parsing de VCF | original abandonado (2016) e quebra em Python ≥ 3.10; usar o fork **`pyvcf3`** (`import vcf`) | 1.0.4 |
| pandas, NumPy | matrizes e CPTs | OK (Lifelines exige `pandas<3`) | pandas 2.x, numpy 2.x (<2.5) |
| PyMC | RB + Monte Carlo | DAG com `pm.Bernoulli`/`pm.Beta`/`pm.Weibull`/`pm.Deterministic`; MC = `pm.sample_prior_predictive(draws=N)`; não é biblioteca de RB discreta (isso seria `pgmpy`), mas representa o DAG e carrega a incerteza do IC via prior Beta | 5.28.5 (pytensor 2.38.x) |
| Lifelines | sobrevivência | `KaplanMeierFitter`, `WeibullFitter`, `ParametricUnivariateFitter` customizado (cura mista), `conditional_time_to_event_`, `percentile` | **0.30.3** (mesma versão citada na referência Davidson-Pilon 2026) |
| matplotlib, seaborn | figuras | OK | atuais |
| scipy, PyYAML, pytest | não citados; infraestrutura | calibração (optimize), configuração, testes | atuais |

Sem g++ na máquina (só gcc): PyTensor cai para o modo Python/NumPy, correto e suficiente para este modelo; ver `05_ambiente.md`.

## 9. Inconsistências do texto que a autora deve corrigir (não alterar o .docx por conta própria)

1. **Biopython não lê VCF** (3.3 e 4.4.D). Reescrever como: PyVCF (fork pyvcf3) para parsing; Biopython para manipulação de sequências (motivo de repetição do C9orf72).
2. **PyVCF** está desatualizado; citar o fork `pyvcf3` ou descrever como "PyVCF (distribuição pyvcf3)". Biopython, PyVCF, pandas, NumPy, matplotlib e seaborn não aparecem nas Referências.
3. **Penetrância do C9orf72**: Murphy 2017 (quase completa aos 80, coortes familiares) vs Douglas & Baralle 2024 (33% populacional). O modelo usa D&B para o nível e Murphy só para a forma etária; o texto da 4.4.C deveria dizer isso.
4. **Richard et al. 2026**: o texto cita faixas etárias para SOD1/TARDBP/FUS mas não traz valores. O YAML terá placeholders `confirmar: true`; a autora precisa preencher.
5. "segregação **alemática**" (4.4.A) → "segregação alélica".
6. 2.4: "artefatos voltados à solução de problemas **fáceis**" → provavelmente "relevantes/complexos".
7. "WESTENENG., 2017" (2.1) não corresponde à referência (2018).
8. 4.4.C descreve F(t) como "Função de Risco Incondicional / Penetrância"; no modelo, F(t) é a função de distribuição acumulada do início (penetrância acumulada) e a função de risco (hazard) é h(t) = f(t)/S(t). Vale alinhar os termos.
9. 4.3 "Filtro de qualidade de leitura": aplicável aos VCFs parentais (QUAL/DP/GQ), não ao ClinVar (QUAL nulo). Os VCFs sintéticos trarão esses campos para que o filtro seja exercitado.

## 10. O que a seção 5 precisa receber do código

Tabelas (CSV + Markdown): variantes anotadas por cenário; transmissão exata vs MC (PyMC e NumPy); risco vitalício por gene e combinado com IC 95%; risco condicional à idade atual e sexo; estabilidade numérica (N × repetições); calibração das priors Beta; recuperação de parâmetros pela Lifelines; tempo de processamento.

Figuras (PNG 300 dpi): DAG da rede; priors de penetrância; curvas G(t) ajustadas vs pontos da literatura; F(t)/S(t) por cenário com bandas de credibilidade e KM sobreposto; idade de início por sexo; aderência mendeliana; erro padrão vs N (log-log).
