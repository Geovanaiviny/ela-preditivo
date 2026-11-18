# ela_preditivo — protótipo de apoio ao aconselhamento genético preditivo da ELA

Artefato computacional do TCC **"Desenvolvimento de Sistema Preditivo de Herança e Manifestação Clínica para Esclerose Lateral Amiotrófica (ELA) Baseado em Modelagem Estocástica e Redes Bayesianas"** (Geovana Íviny Santos Lima; orientação de Fabricio Carneiro Costa). Implementa, em Python, as três camadas descritas nas seções 3.3 e 4.3 a 4.6 do TCC e gera as tabelas e figuras da seção 5 (Resultados).

> **Aviso.** Instrumento experimental de apoio à decisão no aconselhamento genético preditivo da ELA, construído com dados sintéticos e parâmetros populacionais da literatura. Não constitui diagnóstico, não substitui o julgamento clínico e não deve ser usado isoladamente em decisões sobre pacientes. Nenhum dado genômico real é lido, armazenado ou distribuído por este repositório (Lei 13.709/2018, art. 5º, II; TCC, seção 3.4).

Versão 0.1.0 — 24 de outubro de 2026; revisão de 8 de novembro de 2026 (correções da revisão do texto); revisão de 15 de novembro de 2026 (plataforma web, transmissão do C9orf72 por repetições e comparação com Cox); revisão de 16 de novembro de 2026 (laudo ausente do C9orf72 e regra qualificada para classificação conflitante); revisão de 17 de novembro de 2026 (indicadores condicionados à idade atual, risco vitalício até o horizonte, penetrância log-normal como alternativa, genótipo de parentes para o genitor sem exame e métricas de verificação; e, na mesma data, tudo o que a linha de comando faz passou a estar na interface, com execução em segundo plano, base de anotação gerida pela plataforma, primeiro acesso e administradores criados pela tela e subida por Docker).

---

## 1. O que o artefato faz

Dado o VCF da mãe e o VCF do pai, o artefato responde às três perguntas do aconselhamento (TCC, 4.1), separando o que os modelos clássicos de herança misturam:

| Pergunta | Saída do artefato | Camada |
|---|---|---|
| Qual a probabilidade de o descendente **herdar** a variante de risco? | P(portador) por lócus, exata (CPT mendeliana) e simulada (Monte Carlo) | 2 |
| Qual a probabilidade de ele **manifestar** a doença ao longo da vida? | risco vitalício = risco até o horizonte de 90 anos, P(portador) × penetrância × G(90), com intervalo de credibilidade de 95 % que propaga a incerteza publicada da penetrância | 2 |
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

**Pessoa atendida com idade informada.** As três respostas passam a ser condicionadas a "sem sintomas na idade atual": probabilidade de ter herdado dado que não manifestou, risco residual até os 90 anos (e nos próximos 10 e 20 anos) e idade provável de início entre quem ainda vai manifestar. É a mesma conta exata da Tabela 4. Sem idade (futuro filho de um casal), os valores são desde o nascimento.

**Genitor sem exame.** Quando um genitor faleceu, não está disponível ou não quer fazer o teste, o artefato aceita o VCF e o laudo do C9orf72 de parentes dele (pai, mãe ou irmão: avô, avó ou tio do atendido) e, numa família, o VCF de um filho já testado. A dosagem do genitor deixa de ser lida e passa a ser inferida pela tabela de segregação, condicionada à situação clínica dele (`parentes.py`; seção 2). Só o genótipo de parentes entra: o fenótipo de parente sem teste fica fora.

O exemplo enviado pelo orientador (`../exemplo_maquina_tcc_ela.py`) tem as mesmas três camadas.

## 2. Modelo probabilístico

Para cada lócus de risco g (um gene e uma variante), com dosagens parentais `d_m, d_f ∈ {0, 1, 2}` lidas dos VCFs:

- transmissão: `a_m ~ Bernoulli(d_m/2)`, `a_f ~ Bernoulli(d_f/2)`, dose do descendente `D = a_m + a_f`;
- portador: `C = 1[D ≥ 1]` (dominante) ou `C = 1[D = 2]` (recessiva, ex. SOD1 p.Asp91Ala);
- penetrância vitalícia `π ~ Beta(α, β)`, calibrada ao ponto e ao IC 95 % de Douglas & Baralle (2024): C9orf72 0,33 [0,209–0,532]; SOD1 0,54 [0,327–0,886]; TARDBP 0,38 [0,211–0,698]; FUS 0,19 [0,130–0,284];
- manifestação `M ~ Bernoulli(C · π)`; idade de início `T | M = 1 ~ Weibull(k, λ) + δ_sexo` (C9orf72: homens −1 ano, mulheres +1 ano; Goutman et al., 2022);
- cura mista: `F(t) = P(C) · π · G(t)`, `S(t) = 1 − F(t)`; **risco vitalício = F(H)**, o risco até o horizonte H (`horizonte_anos`, 90 anos), em todas as tabelas, curvas e indicadores; `F(∞) = P(C)·π` aparece só na coluna "fração que manifesta em algum momento (sem limite de idade)" da Tabela 3 e nas verificações de coerência (no FUS, 0,0960 sem limite contra 0,0918 até os 90 anos);
- condicionamento ao descendente assintomático na idade a: `P(T ≤ t | T > a) = (F(t) − F(a)) / (1 − F(a))` e `P(C = 1 | assintomático em a) = q(1 − πG(a)) / (1 − qπG(a))`; com a idade informada, os indicadores principais usam esses valores: risco residual `(F(H) − F(a)) / (1 − F(a))`, janelas de 10 e 20 anos limitadas ao horizonte e idade de início condicional (quantil p em `F(t) = F(a) + p·(F(H) − F(a))`);
- vários lóci: independência, `P(qualquer) = 1 − ∏(1 − P_g)`.
- penetrância alternativa: log-normal truncada em 1, com mediana e quantis de 2,5 % e 97,5 % ajustados aos valores publicados (erro máximo 0,004); escolhida em `calibracao_penetrancia.distribuicao` no YAML. O padrão continua Beta; a alternativa entra sempre como cenário da Tabela 9 e do tornado;
- genitor sem exame (três gerações): a evidência de genótipo dos parentes dá o peso `w(d_G, d_O)` das dosagens dos dois genitores (avós com exame pela segregação; avô ou avó sem exame suposto não portador ou com prior de Hardy-Weinberg; tio e filho testado como verossimilhança); o genitor sem sintomas na idade `a_G` entra com `1 − π·G_sexo(a_G)` se porta o genótipo de risco. **A penetrância π é do gene, não da pessoa**: é sorteada uma vez e vale para toda a família, e o cálculo exato integra na distribuição de π. Com `Z(π)` a verossimilhança da situação clínica e `N(π)` a mesma soma com o descendente portador, `P(descendente porta) = E[N]/E[Z]` e `P(porta e manifesta) = E[π·N]/E[Z]`. Exemplo: avó paterna heterozigota para SOD1 p.Ala5Val, mãe negativa, pai sem exame e sem sintomas aos 60 anos → P(neto portador) = 0,1792 e risco vitalício 0,0935 (com médias separadas por pessoa sairia 0,0966, que é errado).

Fórmulas exatas de referência: dominante `P(C) = 1 − (1 − d_m/2)(1 − d_f/2)`; recessiva `P(C) = (d_m/2)(d_f/2)`. O Monte Carlo é a amostragem preditiva a priori do DAG em PyMC (`pm.sample_prior_predictive`), com um amostrador NumPy de semântica idêntica usado nas execuções repetidas de estabilidade e como verificação cruzada.

## 3. Parâmetros e dados

| Fonte | Onde está | Observações |
|---|---|---|
| Penetrância, IC, herança, curvas de idade, efeito do sexo, limiares | `config/parametros_literatura.yaml` | cada valor tem `citacao` e `confirmar`; blocos `regra_conflitante` (critérios da regra qualificada para classificação conflitante) e `genes.SOD1.penetrancia_excecoes` (a estimativa de penetrância não cobre a p.Asp91Ala), os dois com `confirmar: true`; `confirmar: true` = provisório, a validar na literatura (hoje: curvas de idade de SOD1, TARDBP e FUS, à espera de Richard et al., 2026; pontos intermediários da curva de Murphy et al., 2017). A distribuição de início de cada gene aceita `pontos` (curva de Kaplan-Meier ou faixas etárias) ou `estatisticas` (`{media, dp}` ou `{mediana, iqr}`, resolvidas em forma fechada; `metodo_inicio` na Tabela 6) |
| Regiões dos genes (GRCh38) | `config/regioes_genes_grch38.yaml` | Ensembl REST, 24/10/2026, flanco de 5 kb |
| Distribuição da penetrância e faixas do tornado | `config/parametros_literatura.yaml` | `calibracao_penetrancia.distribuicao`: `beta` (padrão) ou `lognormal_truncada`; `sensibilidade.tornado`: faixa de cada parâmetro com a citação (média ± 1,96·dp/√n para o SOD1; mediana ± 1,96·EP para o TARDBP, aproximação com `confirmar: true`; medianas publicadas do C9orf72; FUS sem faixa, por não haver incerteza publicada para a idade de início) |
| Variantes conhecidas (anotação) | `data/variantes_curadas.csv` | SOD1 p.Ala5Val (rs121912442, chr21:31659783 C>T), SOD1 p.Asp91Ala recessiva (rs80265967, chr21:31667290 A>C), TARDBP p.Met337Val (rs80356730, chr1:11022418 A>G), FUS p.Arg521Cys (rs121909668, chr16:31191418 C>T), expansão GGGGCC do C9orf72 (chr9:27573529–27573534), SOD1 rs17883296 benigna (exemplo do TCC). Coordenadas conferidas no dbSNP/ClinVar em 24/10/2026 |
| Subconjunto real do ClinVar/dbSNP (seção 4.2.2 do TCC) | `dados_reais/` na raiz do repositório (ignorada pelo git) ou `ELA_DADOS_BRUTOS` | `base_consolidada_ela.csv` (preferida), `clinvar_ela_4genes.csv`/`variant_summary.txt` ou `clinvar*.vcf`; encontrados automaticamente por `anotacao.tabela_anotacao()` e mesclados com a tabela curada (classificação do ClinVar prevalece; a curada contribui herança e a expansão do C9orf72). Sem eles o protótipo roda só com a tabela curada (`--so-tabela-curada`). `ela-preditivo atualizar-base` baixa a release mensal do ClinVar (quatro genes), registra release e sha256 em `dados_reais/versoes/` e compara com a release anterior; cada execução grava arquivo, release e sha256 da base em `metadados.json` |
| Cenários familiares | `data/sinteticos/` (gerados por `cenarios.py`, seed 2026), uma pasta por caso de atendimento | VCF 4.2, GRCh38, uma amostra por arquivo, com ruído para exercitar filtros (benigna, não anotada, fora dos genes, baixa qualidade, multialélica). `caso_1_pessoa_com_historico/`: cenários 1, 2, 3 e 5 e `parentes_1_*` (pai falecido sem ELA aos 60 anos e avó paterna testada). `caso_2_casal_ou_futuro_filho/`: `casal_1_mae` (parceira com expansão do C9orf72 por laudo, parceiro sem exame) e `casal_2_*` (os dois parceiros heterozigotos SOD1 p.Asp91Ala). `caso_3_familia_com_variante/`: cenário 4 e `parentes_2_*` (pai sem exame, avó e um filho testados). Coordenadas e alelos das variantes de risco e da benigna vêm da base real do ClinVar/dbSNP; genótipos, profundidade e qualidade são gerados pela semente. O par de VCFs serve a qualquer caso: a pasta indica onde ele é usado na demonstração. `cenarios.vcf_cenario(dir, n, lado)` e `cenarios.vcf_sintetico(dir, nome)` localizam os arquivos e aceitam também uma pasta antiga, sem subpastas |

A expansão do C9orf72 **não é lida do VCF**: o fluxo de variantes curtas não a detecta e o TCC (4.2.1) a trata como parâmetro do laudo laboratorial. Informe o nº de repetições do maior alelo de cada genitor (`--c9orf72-mae 45`, `--c9orf72-pai 2 45` para os dois alelos). Limiar: ≥ 30 repetições patogênico, 24–29 intermediário (configurável). **Genitor sem laudo = não testado**: o C9orf72 desse genitor é indeterminado, o lócus inteiro sai do cálculo pelo mesmo critério do genótipo indeterminado no VCF, a linha fica na Tabela 1b com `descartado = True` e o motivo, `metadados.json` lista o descarte em `loci_descartados` e o relatório marca o resultado como **parcial para o C9orf72**; isso vale também quando só um genitor tem laudo. Um laudo normal é um laudo com contagem (ex.: `--c9orf72-pai 8`), e os cenários sintéticos declaram laudo normal explícito (`cenarios.LAUDO_NORMAL`, um abaixo da faixa intermediária do YAML) para os genitores sem envolvimento do gene. Um VCF no estilo ExpansionHunter (`ALT=<STRn>`, `REPCN`) continua legível como caminho secundário, mas não substitui o laudo: com laudo, a divergência fica no relatório e prevalece o laudo; sem laudo, o lócus é descartado e o registro do VCF vai para a observação.

## 4. Instalação

**Com Docker**, a partir da raiz do repositório, um comando sobe a plataforma em `http://localhost:8000`:

```bash
docker compose up --build
```

Na primeira subida o serviço cria a chave de cifra (guardada no volume, em `dados_web/chave.env`; faça cópia dela) e mais nada: o resto é feito no navegador. Enquanto não há administrador, a plataforma abre na tela **Primeiro acesso**, onde se cria o administrador e, em homologação (o padrão do `docker-compose.yml`), os dados de demonstração, com as senhas geradas mostradas na tela, uma única vez. Banco, chave, arquivos cifrados e execuções ficam no volume `elosense_dados`; `docker compose down -v` apaga tudo e a subida seguinte recomeça do zero. A base real do ClinVar entra pela tela **Base de anotação** (administrador) ou pela pasta `dados_reais/` da raiz, montada no contêiner. As opções ficam num arquivo `.env` ao lado do `docker-compose.yml` (modelo em `.env.exemplo`): `ELA_PORTA`, `ELA_ENDERECO` (o padrão `127.0.0.1` atende só a própria máquina), `ELA_WEB_AMBIENTE`, `ELA_WEB_CHAVE` e, opcionais, `ELA_ADMIN_NOME`, `ELA_ADMIN_CPF`, `ELA_ADMIN_EMAIL` e `ELA_ADMIN_SENHA`, que criam o administrador já na subida, com senha temporária. Servem a um servidor exposto, onde não convém deixar o primeiro acesso aberto a quem chegar primeiro. Qualquer comando da linha de comando também roda na imagem: `docker compose run --rm elosense avaliar --saida /app/dados_web/avaliacao`.

**Sem Docker.** Requisitos: Python 3.11 ou 3.12 (recomendado 3.12 via `uv`), acesso ao PyPI. Sem g++ o PyTensor roda em modo Python, correto e suficiente para este modelo.

```bash
cd <raiz do repositório>
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e "./ela_preditivo[dev]"
export PYTENSOR_FLAGS=cxx=          # só se a máquina não tiver g++
python -c "import pymc, lifelines, vcf, Bio; print(pymc.__version__, lifelines.__version__)"   # 5.28.5 0.30.3
```

No Windows, com PowerShell, a partir da raiz do repositório:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".\ela_preditivo[dev]"
.\.venv\Scripts\python.exe -m pytest -q ela_preditivo\tests
```

Chamar o `python.exe` pelo caminho completo evita a política de execução que costuma bloquear a ativação do ambiente. O aviso `g++ not available` é esperado e não impede a execução.

Dependências pinadas em `pyproject.toml`: pymc 5.28.5, lifelines 0.30.3 (versão citada no TCC), numpy 2.x, pandas 2.x, scipy, matplotlib, seaborn, pyvcf3 1.0.4 (fork mantido do PyVCF, `import vcf`), biopython, pyyaml; pytest para os testes.

> **Sem o subconjunto real do ClinVar.** `dados_reais/` fica fora do versionamento, então quem clona o repositório não a recebe. Sem ela o artefato continua funcionando, anotando apenas pela tabela curada (`data/variantes_curadas.csv`), e o relatório declara isso em "Qualidade dos dados". Diferenças: sete testes são pulados, e a SOD1 p.Asp91Ala (cenário 4) entra como risco recessivo pela tabela curada; com a base real ela entra pela **regra qualificada para classificação conflitante** (maioria patogênica na abertura do conflito e herança declarada no fenótipo), com o mesmo resultado. Os números de `resultados/` neste repositório foram gerados **com** a base real. Para reproduzi-los, coloque `base_consolidada_ela.csv` em `dados_reais/` na raiz ou aponte `ELA_DADOS_BRUTOS` para a pasta que a contém.

## 5. Uso

```bash
# 1) gerar os VCFs sintéticos (cinco cenários, parentes e casais), numa pasta por caso de atendimento
ela-preditivo gerar-cenarios --saida ela_preditivo/data/sinteticos

# 2) executar um caso (as três camadas) e gravar relatório, tabelas e figuras
ela-preditivo executar --vcf-mae ela_preditivo/data/sinteticos/caso_1_pessoa_com_historico/cenario_3_mae.vcf \
                       --vcf-pai ela_preditivo/data/sinteticos/caso_1_pessoa_com_historico/cenario_3_pai.vcf \
                       --c9orf72-mae 45 --c9orf72-pai 8 \
                       --sexo F --idade-atual 30 --n 10000 --seed 42 --motor pymc --saida resultados/cenario_3_F
# laudo do C9orf72 dos dois genitores: genitor sem laudo é "não testado" e o lócus fica indeterminado

# 2b) genitor sem exame: omita o VCF dele e informe o de parentes dele, com a situação clínica do genitor
ela-preditivo executar --vcf-mae ela_preditivo/data/sinteticos/caso_1_pessoa_com_historico/parentes_1_mae.vcf \
                       --vcf-mae-do-pai ela_preditivo/data/sinteticos/caso_1_pessoa_com_historico/parentes_1_avo_paterna.vcf \
                       --c9orf72-mae 2 --c9orf72-mae-do-pai 2 \
                       --situacao-pai falecido_sem_ela --idade-pai 60 \
                       --sexo M --idade-atual 35 --saida resultados/parentes_1_M

# 3) avaliação transversal (estabilidade, tempo, coerência, calibração, sensibilidade) e métricas de verificação (Tabelas 12 a 20)
ela-preditivo avaliar --dir-cenarios ela_preditivo/data/sinteticos --saida resultados/avaliacao --n 1000 10000 100000 --repeticoes 30
#    métricas de verificação: --mundos 200 --por-estrato 10 --seed-coorte N; --sem-metricas roda só as Tabelas 5 a 9

# 4) tudo de uma vez: cenários → 5 casos × 2 sexos → avaliação → índice resultados/README.md
ela-preditivo tudo --saida resultados --seed 42

# 5) atualizar a base ClinVar: baixa a release mensal (4 genes) para dados_reais/, registra a versão e compara com a anterior
ela-preditivo atualizar-base --baixar                      # ou --base dados_reais/clinvar_ela_4genes.vcf --release 2026-09-28; --listar mostra o registro
```

Opções de `executar`: `--motor {pymc,numpy}` (o outro motor roda sempre como verificação cruzada), `--config` (YAML alternativo), `--tabela-variantes` (CSV de anotação alternativo), `--horizonte` (padrão 90 anos), `--sem-figuras`; extensões experimentais: `--cox` (CoxPHFitter na coorte de portadores, Tabela 11 e Figura 9; ligado por padrão em `tudo`, `--sem-cox` desliga) e `--c9-delta-mae/--c9-delta-pai/--c9-antecipacao` (transmissão do C9orf72 por repetições, limiar e antecipação; Tabela 1c). A pasta de saída é limpa das saídas de uma execução anterior antes de gravar (só os nomes que o próprio artefato produz; outros arquivos ficam). Toda saída grava `metadados.json` com seed, N, versões, caminhos, release e sha256 da base ClinVar, lóci descartados e a limpeza feita, para reprodução.

Outras opções de `executar`: `--tornado` (sensibilidade tipo tornado do caso, Tabela 20 e Figura 12; desligada por padrão). Para o genitor sem exame, por lado: `--vcf-pai-do-pai`, `--vcf-mae-do-pai`, `--vcf-irmao-do-pai` (um ou mais), `--c9orf72-pai-do-pai`, `--c9orf72-mae-do-pai`, `--c9orf72-irmao-do-pai`, `--situacao-pai {vivo_assintomatico, falecido_sem_ela, afetado, desconhecido}` e `--idade-pai`; as mesmas com `-da-mae`, `--situacao-mae` e `--idade-mae`; `--vcf-filho-testado` (filho já testado, que entra como evidência sobre o genitor) e `--prior-avos {nao_portador, hardy_weinberg}` para o avô ou a avó sem exame. O relatório ganha a seção "Genitor inferido por parentes" e a Tabela 1d; com o genitor `afetado`, o resultado sai rotulado como limite inferior, porque o fenótipo dele não é modelado.

**Métricas de verificação e como rodá-las.** `ela-preditivo avaliar` (e `tudo`) calcula, além das Tabelas 5 a 9, as métricas com famílias sintéticas de desfecho conhecido: coorte de mundos (Tabela 12), Brier score e calibração por decis (Tabelas 13 e 14, Figura 10), C-index de Harrell e AUC dependente do tempo (Tabela 15), erro da idade de início com o piso teórico (Tabela 16), cobertura dos intervalos do Monte Carlo e das bandas de F(t) (Tabelas 17 e 17b), distâncias de Kolmogorov-Smirnov e de Wasserstein (Tabela 18), robustez a erros no VCF (Tabela 19, Figura 11) e sensibilidade tipo tornado (Tabela 20, Figura 12). Com dados sintéticos gerados pelo próprio modelo, elas medem **verificação** (a implementação reproduz o modelo especificado), não validação contra pacientes reais; por isso cada uma sai em dois mundos: verdade = modelo e verdade alternativa (parâmetros do exemplo do orientador e penetrância log-normal). `--mundos` (padrão 200) é o número de mundos, cada um com a penetrância de cada gene sorteada uma vez; `--por-estrato` (padrão 10) é o número de pessoas sorteadas por mundo em cada combinação de cenário, sexo e idade atual; `--seed-coorte` fixa a semente da coorte, que é própria e independente da semente das previsões; `--sem-metricas` desliga o bloco. Com os padrões o bloco leva cerca de 20 s.

**Tudo pela interface.** Cada comando acima tem lugar na plataforma (seção 5.1), com as mesmas opções e as mesmas saídas, porque a interface roda o próprio comando num processo à parte:

| Linha de comando | Na interface |
|---|---|
| `executar` | **Nova análise sem registro**, com as *Opções avançadas* (`--base-clinvar`/`--so-tabela-curada`, `--horizonte`, `--rotulo`, `--amostra-mae`, `--amostra-pai`, `--config`, `--tabela-variantes`, `--sem-figuras`); as opções de parentes ficam na **ficha do registro** (parente testado, situação clínica do genitor, VCF do filho testado) |
| `avaliar` | **Artefato › Avaliação transversal e métricas de verificação**: Tabelas 5 a 9 e 12 a 20 e Figuras 2, 3, 7 e 10 a 12 na tela |
| `tudo` | **Artefato › Reprodução completa**: índice, tabela consolidada, os dez relatórios por cenário e a avaliação; o pacote .zip é a pasta `resultados/` |
| `gerar-cenarios` | **Artefato › Gerar cenários sintéticos**; a execução pode ser a origem dos cenários de uma avaliação |
| `atualizar-base` | **Base de anotação**: enviar base, registrar versão, baixar a release do ClinVar, versões registradas e o que mudou entre elas |
| `verificar-auditoria` | **Auditoria › Verificar a cadeia** |
| `criar-admin` | **Primeiro acesso › Criar o administrador**, enquanto não há nenhum; depois, **Usuários › Novo administrador**, em que um administrador cria outro com senha temporária |
| `popular-demo` | **Primeiro acesso › Criar dados de demonstração**, em homologação; depois, no **Início** do administrador. As senhas aparecem na tela, uma única vez |
| `servir`, `gerar-chave` | arranque do serviço: `docker compose up` (ou `python -m ela_preditivo.web.arranque`) sobe o servidor e cria a chave sozinho |

A tela **Artefato** mostra a equivalência opção por opção e, em cada execução, o comando equivalente. Um teste percorre o `argparse` e falha se um comando ou uma opção nova ficar sem lugar na interface.

Uso como biblioteca:

```python
from ela_preditivo import pipeline
r = pipeline.executar("mae.vcf", "pai.vcf", "saida/", sexo="M", idade_atual=40, n=10_000, seed=42)
r["resumo"]        # DataFrame por lócus: P(portador), penetrância, risco vitalício, IC 95 %, idade de início
r["combinado"]     # dicionário com o risco combinado (qualquer lócus)
r["curvas"]        # F(t), S(t), h(t) e bandas por unidade
r = pipeline.executar(..., hipoteses_c9orf72={"delta_mae": 3, "antecipacao": 5}, comparar_cox=True)  # extensões
r["transmissao_c9orf72"].genotipos, r["cox"]["tabela"]
r = pipeline.executar("mae.vcf", None, "saida/", sexo="M", idade_atual=35,                   # pai sem exame
                      parentes={"pai": {"situacao": "falecido_sem_ela", "idade": 60, "mae": {"vcf": "avo_paterna.vcf"}}})
r["condicionado"], r["parentes"]   # indicadores condicionados à idade atual; parentes e suposições usados
r = pipeline.executar(..., tornado=True); r["tornado"]                                        # Tabela 20
av = pipeline.avaliar("data/sinteticos", "saida_avaliacao/", mundos=200, por_estrato=10)       # Tabelas 5 a 9 e 12 a 20
av["verificacao"]["brier"], av["verificacao"]["cobertura_bandas"]
```

### 5.1 Plataforma web EloSense: três casos, cadastros, RBAC e LGPD

Camada web (`src/ela_preditivo/web/`), com a marca **EloSense · Plataforma clínica**, para médicos e aconselhadores genéticos cadastrarem atendimentos, anexarem os VCFs dos genitores e executarem análises pela interface; para pesquisadores consultarem casos pseudonimizados e o modelo; e para o administrador aprovar cadastros, gerir usuários e consultar a auditoria. Pacientes e familiares não são usuários. O sistema é apresentado como apoio ao aconselhamento, lido por profissional; o aviso legal do artefato continua na API (`/api/sistema`) e no relatório baixado, mas não aparece como faixa na interface.

**Os três casos atendidos** (texto do orientador, 15/11/2026) são escolhidos na primeira pergunta do cadastro e aparecem como rótulo em todas as telas do registro, no CSV do pesquisador e como filtro:

| Caso | Registro | O que o resultado responde |
|---|---|---|
| 1 · Pessoa assintomática com histórico familiar | a pessoa atendida (descendente) e seus genitores | a partir da idade dela, sem sintomas: se herdou (P portador ≥ 1); chance de manifestar daqui em diante, até os 90 anos, com banda de 95 %, e nos próximos 10 e 20 anos; idade provável de início (mediana e faixa 25–75 %) |
| 2 · Casal ou pessoa que planeja filhos | os dois parceiros como genitores, sem descendente | as três respostas para um futuro filho, desde o nascimento (sexo escolhido ou os dois sexos lado a lado): chance de herdar, de manifestar até os 90 anos e aos 50/60/70 anos, e idade provável de início; decisões reprodutivas ficam fora do escopo |
| 3 · Família de genitor com variante confirmada | genitores e vários filhos | as três respostas para cada filho em risco, um por vez, condicionadas à idade dele, e o comparativo "risco por filho" na ficha; um filho que já fez o teste entra como evidência sobre o genitor sem exame e sai da lista de pessoas em risco |

Antes de rodar a análise de uma pessoa, o profissional marca "Confirmo que a pessoa analisada não apresenta sintomas de ELA": sem a confirmação a análise não roda, e só o sim e a data ficam guardados. Em cada genitor sem VCF, a ficha traz "Adicionar parente testado" (pai, mãe ou irmão do genitor, com VCF e laudo do C9orf72) e a situação clínica do genitor; o resultado diz que o genótipo foi inferido, por quais parentes e com quais suposições e, no caso 2, avisa que o cálculo revela indiretamente a chance de o parceiro ser portador. Ficam fora do escopo (página Ajuda, privacidade e limitações do resultado): pessoas já sintomáticas, números agregados da família ("chance de pelo menos um filho"), fenótipo de parente sem genótipo, ajuste por ancestralidade, pessoas sem histórico familiar e decisões reprodutivas.

```bash
uv pip install -e "./ela_preditivo[dev,web]"      # FastAPI, SQLAlchemy, argon2-cffi, cryptography, python-multipart
export ELA_WEB_CHAVE=$(ela-preditivo gerar-chave)  # chave Fernet; guarde-a: sem ela o banco e os VCFs não se decifram
export ELA_WEB_BD=dados_web/ela_web.sqlite3        # padrão; pasta ignorada pelo git
export ELA_WEB_VCFS=dados_web/vcfs                 # padrão: VCFs cifrados, fora do banco (documentos e resultados ficam ao lado: dados_web/documentos, dados_web/analises)
export ELA_WEB_AMBIENTE=homologacao                # selo "ambiente de homologação: pacientes fictícios" e cenários de exemplo; em produção, omitir
ela-preditivo popular-demo                         # usuários de cada papel, dois cadastros pendentes, oito registros fictícios (5 pessoas, 2 famílias, 1 casal; dois com o pai inferido por parentes), 16 VCFs sintéticos e 7 análises (antes de haver médico ou pesquisador; imprime as credenciais; na interface: Primeiro acesso)
ela-preditivo criar-admin --nome "Nome" --cpf 000.000.000-00 --email admin@exemplo.br   # na interface: Primeiro acesso ou Usuários › Novo administrador
ela-preditivo servir --host 127.0.0.1 --porta 8000 # abra http://127.0.0.1:8000
ela-preditivo verificar-auditoria                  # confere a cadeia de hash
```

Produção: HTTPS com `ELA_WEB_COOKIE_SEGURO=1`, `ELA_WEB_AMBIENTE` ausente (ou `producao`: sem selo e sem cenários de exemplo em registros; `homologacao` liga os dois), `ELA_ENCARREGADO_NOME` e `ELA_ENCARREGADO_CONTATO` (LGPD, art. 41; aparecem em Privacidade e Ajuda), `ELA_WEB_SESSAO_MINUTOS` (30), cópia de segurança do banco **e** das pastas de VCFs, documentos e análises, guarda da chave. O banco desta versão não migra o da entrega anterior (não havia dados reais): apague `dados_web/ela_web.sqlite3` e repopule.

| Papel | O que faz | O que nunca vê |
|---|---|---|
| Médico / aconselhador genético | cadastra, edita, exporta e exclui os próprios registros (pessoa, casal ou família) com número e documento do prontuário, genitores (nome, nascimento, laudo do C9orf72 como número de repetições e documento, VCF) e descendentes; anexa, substitui, abre e remove documentos e VCFs; registra e revoga consentimentos por titular; executa análises a partir da ficha (ou avulsas, sem registro); reabre qualquer resultado completo guardado e baixa o pacote; seção "Análises" com todas as execuções; busca com filtros; vê modelo e parâmetros; executa a reprodução, a avaliação e a geração de cenários (tela Artefato); vê a base de anotação em uso | registros de outro médico (404), painel do administrador, código de pesquisa |
| Pesquisador | registros de pesquisa, pseudonimizados (código, caso, momento, sexo, década de idade) com filtros e totais; cada registro expande para os dados completos: lóci de risco, variantes aprovadas por genitor (Tabela 1), vetor de dosagem, curva F(t) com banda, suposições e metadados; exportação em CSV (resumo e variantes) e JSON detalhado; modelo e parâmetros; executa a reprodução, a avaliação e a geração de cenários (tela Artefato); vê a base de anotação em uso | nome, prontuário, nascimento, nomes dos genitores, médico, ids internos, o arquivo VCF |
| Administrador | aprova, reprova, pede informações, desativa e reativa usuários; cria outros administradores, que recebem senha temporária e a trocam no primeiro login; auditoria completa com verificação da cadeia; gere a base de anotação (envia, registra a versão e baixa a release do ClinVar) | registros, dados clínicos, VCFs, resultados, parâmetros, execuções do artefato |

Dados e rotas (`web/pacientes.py`, `web/vcfs.py`, `web/analises.py`, `web/pesquisa.py`): registro `pacientes` (tipo, nome do registro, prontuário, momento do aconselhamento, observações) + `genitores` (MAE/PAI; nome, nascimento, laudo, metadados do VCF) + `descendentes` (nome, nascimento, sexo) + `consentimentos` (titular MAE/PAI/DESCENDENTE/RESPONSAVEL, por descendente) + `analises_pacientes` (resumo cifrado de cada análise: genes de risco, probabilidades por lócus e combinadas, F aos 50/60/70, idade de início, suposições, hash dos VCFs). O VCF anexado é validado pela ingestão do artefato (GRCh38, amostra), cifrado com Fernet em `ELA_WEB_VCFS` com nome aleatório, nunca pode ser baixado, é decifrado só na pasta temporária da análise e é apagado com o registro. Documentos (`web/arquivos.py`): prontuário e laudo do C9orf72 anexados como PDF, JPG ou PNG (até 10 MB, assinatura conferida), cifrados em `dados_web/documentos/` com nome aleatório; só o médico dono abre, e cada abertura fica na auditoria. Toda análise feita a partir de um registro guarda o resultado completo (JSON e zip com relatório, tabelas e figuras) cifrado em `dados_web/analises/`, reaberto em `GET /api/pacientes/{id}/analises/{aid}`; `GET /api/pacientes/analises` lista todas as execuções do médico. Genitor sem VCF: a análise só roda com a marcação "assumir não portador" (VCF de referência sem variante de risco), com a suposição em destaque no resultado, nos metadados, na ficha e no CSV; sem nenhum VCF, não roda. Busca e filtros do médico (`POST /api/pacientes/busca`: texto, caso, sexo, idade, menor de idade, momento, pesquisa, VCFs, gene de risco, com/sem análise, risco mínimo, laudo, suposição, datas, ordenação) decifram em memória a lista do próprio médico. Pesquisador: `GET /api/pesquisa/casos`, `POST .../busca` (caso, sexo, década, momento, gene, herança, risco, período, hipóteses, suposição) com totais, `GET .../casos/{codigo}` (detalhe completo por pseudônimo), `POST .../exportar` (CSV `;`, decimal com vírgula, uma linha por análise), `POST .../exportar-variantes` (CSV, uma linha por variante) e `POST .../exportar-detalhado` (JSON). Página pública `GET /api/ajuda`. Em "Minha conta", nome, CPF, tipo e número/UF do CRM e ORCID são imutáveis; o administrador não pede encerramento e analisa os cadastros pendentes um por vez.

Parentes na plataforma: tabela `parentes` (registro, genitor ao qual se liga, parentesco, VCF e laudo cifrados), situação clínica cifrada de cada genitor e VCF próprio opcional do descendente (filho testado). Rotas `PUT /api/pacientes/{id}/genitores/{papel}/situacao`, `POST /api/pacientes/{id}/genitores/{papel}/parentes`, `DELETE /api/pacientes/{id}/parentes/{pid}` e `POST|DELETE /api/pacientes/{id}/descendentes/{did}/vcf`. O VCF do parente segue as regras dos VCFs dos genitores: cifrado, sem download, com auditoria e apagado junto com o registro. O parente é titular de dado sensível, e a liberação para pesquisa passa a exigir também o consentimento de cada parente. A tela de análise traz ainda a opção "Sensibilidade tipo tornado", desligada por padrão. O esquema do banco mudou nesta revisão: apague o banco de demonstração e rode `popular-demo` de novo.

Artefato e base de anotação pela interface (`web/artefato.py`): cada execução é uma tarefa, um processo separado que roda `ela-preditivo <comando>` com as opções do formulário; não bloqueia as análises clínicas, não recebe a chave de cifra e só lida com dados sintéticos e com a base pública do ClinVar. Roda uma por vez; a saída fica em `dados_web/tarefas/<id>/` (ficam as doze mais recentes), de onde a tela lê relatório, tabelas e figuras e monta o pacote. Rotas: `GET /api/artefato/comandos` (opções de cada comando, as mesmas da linha de comando), `GET|POST /api/artefato/tarefas`, `GET|DELETE /api/artefato/tarefas/{id}` (cancela a que está em curso ou remove a encerrada; só quem a disparou), `GET /api/artefato/tarefas/{id}/relatorio?pasta=`, `.../arquivo?caminho=` e `.../pacote.zip`; nada fora da pasta de saída é servido. Um reinício do servidor deixa a execução em curso como interrompida. Base: `GET /api/base` (base em uso, arquivos da pasta, versões), `POST /api/base/arquivos` (envia; um arquivo de mesmo nome vai para `anteriores/` antes de ser substituído), `POST /api/base/versoes`, `POST /api/base/baixar` e `GET /api/base/relatorios/{nome}`. A base em uso é o primeiro arquivo reconhecido na pasta, na ordem `base_consolidada_ela.csv`, `clinvar_ela_4genes.csv`, `variant_summary.txt`, `clinvar_ela_4genes.vcf`, `clinvar*.vcf`. `GET /api/parametros/arquivo` e `/api/parametros/tabela-variantes` baixam o YAML e a tabela curada em uso, para editar e reenviar como arquivo alternativo; uma análise feita com arquivo alternativo declara isso no resultado. Na ficha do registro a análise usa sempre os parâmetros do artefato e a base em uso.

Primeiro acesso e senhas temporárias (`web/primeiro_acesso.py`): `GET /api/sistema` informa o que falta configurar. `POST /api/primeiro-acesso/administrador` cria o administrador só enquanto não existe nenhum; a pessoa define a própria senha e declara os aceites, como no cadastro. `POST /api/primeiro-acesso/demonstracao` existe só em homologação e com o banco sem usuário algum; depois que há administrador, a demonstração só é criada por ele (`POST /api/admin/demonstracao`), porque as senhas devolvidas incluem a de um administrador. Passado o primeiro acesso, as duas rotas respondem 409. `POST /api/admin/administradores` exige a senha de quem cria e devolve, uma única vez, uma senha temporária gerada pelo sistema: quem cria a conta não escolhe nem fica com a senha do colega. Conta com senha temporária (essa e a do administrador vindo de `ELA_ADMIN_*`) só alcança a troca de senha, a sessão e a saída; qualquer outra rota responde 403 e a tentativa vai para a auditoria. No primeiro acesso não se usa senha gerada: ela apareceria na mesma tela, para quem chegou primeiro, sem proteger nada.

Regras implementadas e testadas (`tests/test_web.py`): negação por padrão (toda rota `/api` fora de `sistema`, `privacidade`, `ajuda`, `cadastro`, `login` e das duas do primeiro acesso exige sessão e permissão; o teste percorre as rotas registradas); conta nova nasce PENDENTE e só a VERIFICADA usa o sistema; ninguém se cadastra como administrador, é promovido ou muda o próprio papel; senha Argon2id com mínimo de 10 caracteres; sessão em cookie HttpOnly/SameSite=Strict com 30 min de inatividade; CSRF em toda requisição que altera estado; 5 tentativas bloqueiam o login com erro genérico; CPF validado, único, cifrado e exibido mascarado; identificadores, laudos e resumos cifrados em repouso e VCFs cifrados em disco (o banco e os arquivos não contêm nome, cabeçalho de VCF nem nome original em claro); nada pessoal em URL, em erro ou no armazenamento do navegador; regras por caso (pessoa = exatamente um descendente; casal = nenhum; família ≥ 1); prontuário e genitores obrigatórios; cenário de exemplo em registro só em demonstração; consentimento por titular (genitores e cada descendente, ou responsável se menor de 18), nunca pré-marcado, revogável na mesma tela, e um descendente novo retira a liberação até consentir; liberação pseudonimizada com código aleatório que não é exibido; exclusão remove identificadores, VCFs, resumos e consentimentos e a auditoria permanece; auditoria só de inclusão, encadeada por hash, cobrindo também anexo e remoção de VCF, edição de descendente, consulta e exportação de casos; respostas e CSV do pesquisador sem nenhum dado identificável.

Interface (`web/static/`, conferida em seis resoluções: 1920, 1536, 1366, 1024, 820 e 390 px): HTML, CSS e JavaScript puros, sem framework, build ou recurso externo (CSP `default-src 'self'`); desktop-first, usando toda a largura da janela, com unidades relativas, `clamp()`, grades fluidas e container queries; barra lateral azul-marinho recolhível (só ícones; padrão recolhida entre 901 e 1200 px; gaveta abaixo de 900 px) com o menu do papel, topo com trilha de navegação, Ajuda e Sair; tela **Início** por papel (médico: totais, pendências, registros e análises recentes via `GET /api/pacientes/painel`; pesquisador: totais dos casos; administrador: pendentes, usuários e integridade da auditoria); tela de entrada dividida; formulários em seções numeradas com cartão de apoio; cartões de opção para o caso; indicadores com as três respostas; gráfico F(t) com banda e "ver dados em tabela"; filtros com chips; no celular, gaveta e tabelas em blocos rotulados. Operável por teclado, foco visível, rótulo em todo campo, erro associado ao campo e anunciado (`aria-live`), contraste ≥ 4,5:1. 401 volta para "Entrar" com aviso e 403 mostra que o perfil não tem acesso. O resultado completo fica disponível a quem o executou por duas horas; o resumo fica na ficha. Segundo fator e recuperação de senha por e-mail ficam para etapas seguintes.

## 6. Saídas

Por execução (`executar`):

| Arquivo | Conteúdo |
|---|---|
| `relatorio.md` | texto com aviso legal, entrada, resultado por lócus e combinado, verificações e limitações; incorpora as tabelas e figuras |
| `tabelas/tabela_01_variantes_anotadas` | variantes aprovadas no filtro, por genitor, com classe (risco, VUS, conflitante, benigna, não anotada), CLNSIG, estrelas, herança |
| `tabelas/tabela_01c_transmissao_c9orf72` | só com hipóteses `--c9-*`: genótipos possíveis do descendente por repetições, classes e dosagem efetiva (extensão experimental) |
| `tabelas/tabela_01b_vetor_dosagem` | dosagens 0/1/2 por lócus de risco e P(portador) exata; lócus com genótipo não determinado num genitor aparece marcado como descartado, com a dosagem desconhecida vazia e o motivo em `observacao`, sem entrar no cálculo (TCC 4.3) |
| `tabelas/tabela_01d_genitor_inferido` | só com parentes: parentes considerados e dosagem de cada um, distribuição da dosagem do genitor sem exame antes e depois do condicionamento pela situação clínica dele, penetrância a priori e a posteriori |
| `tabelas/tabela_02_aderencia` | exato vs PyMC vs NumPy, erro padrão, desvio em EPs, qui-quadrado do genótipo |
| `tabelas/tabela_03_risco_vitalicio` | P(portador), penetrância (média e IC), risco vitalício até o horizonte (IC de credibilidade 95 %; no combinado, percentil dos sorteios de π, o mesmo cálculo da Figura 4), fração que manifesta em algum momento (sem limite de idade), idade de início (mediana, p10, p90), combinado |
| `tabelas/tabela_04_risco_condicional` (+ `04b` Kaplan-Meier) | por idade atual (0 a 70, mais a idade do paciente quando informada): P(portador \| assintomático), risco em 10 e 20 anos (limitados ao horizonte) e risco residual, da idade atual até o horizonte (coluna `risco_residual`; na idade 0 é o risco vitalício da Tabela 3) |
| `tabelas/tabela_07_recuperacao_lifelines` | parâmetros π, λ, ρ recuperados pelo modelo de cura mista |
| `tabelas/tabela_10_kaplan_meier` | S(t) com IC em 40–80 anos, mediana ("não atingida" sob cura mista), idade em que 90 % do risco já ocorreu |
| `tabelas/tabela_11_cox_vs_cura_mista` | só com `--cox`: CoxPHFitter na coorte de portadores (HR, IC, concordância, riscos proporcionais) e S(t) por Cox, cura mista, Kaplan-Meier e analítico |
| `tabelas/tabela_20_tornado` | só com `--tornado`: um parâmetro por vez dentro da faixa publicada, com a variação do risco vitalício (residual, se a idade for informada) e da idade mediana de início, e a fonte de cada faixa |
| `figuras/figura_01_dag.png` | Rede Bayesiana |
| `figuras/figura_04_risco_temporal.png` | F(t) e S(t) com banda de credibilidade e Kaplan-Meier sobreposto |
| `figuras/figura_05_idade_inicio.png` | histograma da idade de início por lócus (por sexo em `tudo`) |
| `figuras/figura_06_aderencia.png` | barras exato vs Monte Carlo |
| `figuras/figura_08_hazard.png` | h(t) com a faixa 60–75 anos (pico de incidência populacional, só referência; comparada apenas com o pico do risco combinado) |
| `figuras/figura_09_cox_vs_cura_mista.png` | só com `--cox`: S(t) entre portadores por Cox, cura mista, Kaplan-Meier e curva analítica |
| `figuras/figura_12_tornado.png` | só com `--tornado`: barras horizontais ordenadas pelo efeito no risco |
| `curvas.csv`, `variantes_ingeridas_anotadas.csv`, `metadados.json` | dados brutos e proveniência |

Avaliação (`avaliar`): Tabela 5 (estabilidade por N × 30 sementes vs erro padrão teórico), Tabela 6 (calibração das priors), Tabela 7 (coerência das curvas, com o pico de h(t) por lócus e do risco combinado; a faixa 60–75 anos só é comparada com o combinado, como referência), Tabela 8 (tempos PyMC × NumPy), Tabela 9 (sensibilidade: literatura × penetrância log-normal truncada × exemplo do orientador × C9orf72 de coorte familiar); Figuras 2 (priors), 3 (G(t) ajustadas vs literatura) e 7 (DP vs N, log-log).

Verificação com famílias sintéticas (`avaliar`, salvo `--sem-metricas`): Tabela 12 (composição da coorte de mundos), Tabela 13 (Brier score a 10 e 20 anos e até o horizonte), Tabela 14 e Figura 10 (calibração por decis), Tabela 15 (C-index de Harrell e AUC dependente do tempo), Tabela 16 (erro absoluto médio da idade de início, por gene, com o piso teórico), Tabela 17 (cobertura dos intervalos de 95 % do Monte Carlo), Tabela 17b (cobertura das bandas de F(t) aos 50, 60 e 70 anos, com o F empírico e sem o ruído amostral), Tabela 18 (Kolmogorov-Smirnov e Wasserstein), Tabela 19 e Figura 11 (robustez a erros no VCF) e Tabela 20 e Figura 12 (tornado). Todas trazem a coluna `verdade` (modelo ou alternativa) quando se aplica; `metadados.json` guarda o bloco `verificacao` (mundos, pessoas por estrato, semente da coorte, verdades, cenários na coorte e o que ficou fora do tornado).

Todas as legendas saem no padrão "Tabela N — ... / Figura N — ...; Fonte: elaborado pela autora (2026)". Números em tabelas usam ponto decimal (padrão do CSV); o texto do TCC pode converter para vírgula.

## 7. Cenários e resultados

Execução completa de 17/11/2026 com o código desta revisão (`ela-preditivo tudo --seed 42 --so-tabela-curada`): 5 cenários × 2 sexos com N = 10.000 e idade atual de 30 anos, avaliação com N ∈ {1.000, 10.000, 100.000} × 30 sementes e verificação com 200 mundos; 6 min 29 s no total, numa máquina sem g++. A anotação usou só a tabela curada.

> **Pasta `resultados/`.** A pasta versionada ainda é a execução de 13/11/2026, anterior às correções desta revisão (nela o FUS aparece com 9,6 %). Ela será substituída pela execução completa com a base real do ClinVar: `ela-preditivo tudo --saida resultados --seed 42`, ou **Artefato › Reprodução completa** na plataforma. A base de anotação muda a origem da classificação de cada variante, não as dosagens dos cinco cenários; a conferência de que os números abaixo se repetem com a base real fica para essa execução.

### 7.1 Os cinco cenários (Tabela 3 consolidada)

| Cenário (TCC, 4.5) | Lócus de risco | P(portador) | Risco vitalício [IC 95 %] | Idade mediana de início, anos (F / M) |
|---|---|---|---|---|
| 1. Pai heterozigoto SOD1 p.Ala5Val × mãe selvagem | SOD1 A4V | 0,50 | 26,9 % [16,3–37,2] | 50,9 |
| 2. Mãe com expansão C9orf72 (45 repetições) × pai selvagem | C9orf72 | 0,50 | 16,6 % [10,2–23,7] | 59,3 / 57,3 |
| 3. Pai het. SOD1 p.Ala5Val × mãe com expansão C9orf72 (exemplo literal do TCC) | C9orf72 | 0,50 | 16,6 % [10,2–23,7] | 59,3 / 57,3 |
| | SOD1 A4V | 0,50 | 26,9 % [16,3–37,2] | 50,9 |
| | qualquer lócus | 0,75 | 39,1 % [28,8–48,6] | 52,8 / 52,2 (primeiro início) |
| 4. Ambos os pais het. SOD1 p.Asp91Ala (recessiva) | SOD1 D91A | 0,25 | 13,5 % [8,2–18,6] | 50,9 |
| 5. Pai het. TARDBP p.Met337Val × mãe het. FUS p.Arg521Cys | TARDBP M337V | 0,50 | 19,1 % [10,5–28,7] | 58,3 |
| | FUS R521C | 0,50 | 9,2 % [6,1–12,8] | 46,7 |
| | qualquer lócus | 0,75 | 26,6 % [18,2–35,6] | 55,8 |

Risco vitalício é o risco até os 90 anos. A fração que manifesta em algum momento, sem limite de idade, é maior onde a idade de início se estende além do horizonte: FUS 9,6 %, TARDBP 19,2 % e cenário 5 combinado 26,9 %; nos demais, a diferença não aparece na primeira casa.

O que os números mostram:

- **Transmissão ≠ manifestação.** Nos cenários dominantes a probabilidade de herdar é sempre 50 %, mas o risco de adoecer vai de 9,2 % (FUS) a 26,9 % (SOD1), porque a penetrância é incompleta e varia por gene (TCC, 4.1). O intervalo de credibilidade carrega a incerteza publicada da penetrância até o resultado final.
- **Herança recessiva** (cenário 4): só o homozigoto está em risco, P(portador) cai para 25 % e o risco vitalício para 13,5 %, mesmo com os dois pais portadores. Com a tabela curada a variante entra como recessiva pela própria tabela. Com a base real do ClinVar ela é *conflitante* e entra pela regra qualificada das conflitantes: 14 das 20 classificações são patogênicas ou provavelmente patogênicas e o fenótipo declara herança recessiva; o relatório registra a abertura do conflito e, como limitação, que a penetrância do SOD1 foi estimada sem essa variante.
- **Dois genes na família** (cenário 3): 75 % de chance de herdar pelo menos uma variante e 39,1 % de manifestar, sob independência entre lóci.
- **Sexo**: no C9orf72 o descendente masculino manifesta 2 anos antes (57,3 vs 59,3 anos); nos demais genes não há evidência no TCC e o efeito é nulo por construção.
- **Idade atual sem sintomas** (cenário 3, descendente feminina): aos 40 anos o risco nos próximos 20 anos é 25,0 % e o risco residual até os 90 anos 35,7 %; aos 60 anos caem para 14,2 % e 14,3 %; a probabilidade de portar SOD1 p.Ala5Val, dado assintomático aos 60, cai de 50 % para 35,8 % (atualização bayesiana).
- **Kaplan-Meier** (cenário 3): a mediana de sobrevivência "não é atingida" em nenhum lócus, assinatura do modelo de cura mista (risco vitalício < 50 %); 90 % do risco do SOD1 já ocorreu aos 63 anos e o do C9orf72 aos 71.

### 7.2 Verificações (TCC, 4.5)

| Critério | Resultado |
|---|---|
| Aderência teórica (Tabela 2) | maior desvio entre Monte Carlo e valor exato nos 10 casos: 1,54 erro padrão (limite usual 4); qui-quadrado do genótipo sem rejeição (maior valor 2,37); PyMC e NumPy concordam |
| Estabilidade numérica (Tabela 5, Figura 7) | razão DP observado / EP teórico média de 1,04 nos 5 cenários; no cenário 3 o DP de P(manifestação) cai de 0,0172 (N = 1.000) para 0,0046 (10.000) e 0,0015 (100.000), inclinação −½ em log-log |
| Coerência das curvas (Tabelas 7 e 10, Figura 4) | risco vitalício por Kaplan-Meier difere do exato em no máximo 0,006; mediana de início da Weibull da Lifelines difere da exata em até 0,4 ano, salvo no FUS (3,5 anos; é a distribuição mais larga e a curva é provisória); o modelo de cura mista recupera π com erro de até 2,5 % (SOD1 0,526 a 0,539 para 0,539; FUS 0,193 para 0,192), λ dentro de 1 % (FUS: 4,4 %) e ρ dentro de 5 %; pico de h(t): C9orf72 62 anos, SOD1 53,5, TARDBP 61, FUS 44; a faixa de incidência populacional 60–75 anos (Feldman et al., 2022) é comparada só com o pico do risco combinado (dentro dela nos cenários 2 e 5), como referência, e não aprova nem reprova variantes |
| Tempo (Tabela 8) | NumPy: 0,008 s para N = 100.000; PyMC: 0,23 s (1.000), 1,9 s (10.000), 17,6 s (100.000) em modo Python sem g++; reprodução completa em 6 min 29 s |
| Sensibilidade (Tabela 9, cenário 3) | risco combinado de 39,1 % com a literatura, 40,3 % com a penetrância log-normal truncada, 61,5 % com os parâmetros do exemplo do orientador (penetrância 0,90/0,60) e 59,8 % com C9orf72 de coorte familiar (π = 0,90): a escolha da penetrância domina o resultado, e a forma da distribuição pesa pouco |
| Comparação com Cox (Tabela 11, cenário 3, sementes independentes por sexo) | razão de riscos do sexo masculino: SOD1 0,96 [0,914–1,016], p = 0,17, sem efeito, como esperado (teste de riscos proporcionais p = 0,32); C9orf72 0,98 [0,921–1,053], p = 0,66, com o teste de riscos proporcionais rejeitando (p < 0,001); no modelo combinado, portar SOD1 2,98 [2,82–3,16] e portar C9orf72 1,49 [1,41–1,56], concordância 0,62. S(t) do Cox e da cura mista diferem em no máximo 0,004 por lócus |

### 7.3 Métricas de verificação com famílias sintéticas

Da mesma execução (a avaliação roda com semente 1000, N = 10.000, 200 mundos e 10 pessoas sorteadas por estrato): 360.000 pessoas sorteadas, 326.006 na coorte com verdade = modelo. Medem verificação, não validação contra pacientes reais.

| Métrica | Verdade = modelo | Verdade alternativa (parâmetros do exemplo do orientador) |
|---|---|---|
| Calibração até o horizonte (Tabelas 13 e 14, Figura 10) | prevalência 17,49 % para risco previsto 17,46 %; maior diferença num decil 0,6 ponto; Brier 0,1327 (referência 0,1443) | prevalência 29,9 % para 18,1 % previstos; diferença de até 24 pontos; Brier 0,1948 |
| Discriminação (Tabela 15) | C-index 0,630; AUC 0,806 em 10 anos e 0,787 em 20 anos | C-index 0,655; AUC 0,787 e 0,771 |
| Erro da idade de início (Tabela 16) | 7,9 anos para um piso teórico de 8,0 (razão 0,996) | 9,7 anos para um piso de 8,3 (razão 1,17; viés de −3,7 anos) |
| Cobertura dos intervalos do Monte Carlo (Tabela 17) | 92 % a 97,5 % em 200 sementes (esperado 95 %) | não se aplica |
| Cobertura das bandas de F(t) (Tabela 17b) | 94 % a 96 % nos cinco cenários; com genitor inferido, 87 % com o F empírico e 94 % sem o ruído amostral | 0 % nos cinco cenários |
| Divergência entre curvas (Tabela 18) | Kolmogorov-Smirnov de 0,003 a 0,010 (referência amostral 0,0136); Wasserstein de 0,2 a 1,6 ano | Kolmogorov-Smirnov de 0,09 a 0,28; Wasserstein de 2,4 a 8,0 anos |

Com a penetrância log-normal como verdade alternativa a degradação é pequena (prevalência 18,4 % para 17,5 % previstos; bandas com 86 % a 93 % de cobertura), porque as duas distribuições reproduzem os mesmos valores publicados.

- **Robustez a erros no VCF** (Tabela 19, Figura 11): genótipo indeterminado (./.) descarta o lócus e é declarado, nunca tratado como ausência da variante; GQ abaixo de 30 é reprovado e contado. Registro removido ou 0/1 trocado por 0/0 é falso negativo silencioso (cenário 1: portador de 50 % para 0), e uma variante patogênica inserida entra no cálculo sem aviso (cenário 1: portador de 50 % para 75 %, risco de 26,9 % para 40,9 %). São limites do dado de entrada.
- **Tornado** (Tabela 20, Figura 12): a penetrância domina o risco (cenário 1: de 16,4 % a 44,3 % em torno de 26,9 %) e não move a idade mediana de início com um só lócus; a incerteza da idade de início desloca a mediana em até 5,9 anos e quase não altera o risco vitalício; trocar a Beta pela log-normal muda o risco em cerca de 1 ponto. O FUS fica fora da idade de início por não ter incerteza publicada.

## 8. Verificações que o artefato faz de si mesmo (TCC, 4.5)

| Critério do TCC | Como é verificado | Onde |
|---|---|---|
| Aderência teórica | P(portador) e P(manifesta) simuladas vs fórmulas exatas, em erros padrão; qui-quadrado das frequências de D ∈ {0,1,2} vs CPT; PyMC vs NumPy | Tabela 2, Figura 6, testes `test_nucleo_estocastico.py` |
| Estabilidade numérica | 30 execuções por N ∈ {1e3, 1e4, 1e5}; DP entre execuções vs √(p(1−p)/N); inclinação −½ em log-log | Tabela 5, Figura 7 |
| Coerência das curvas | risco vitalício até o horizonte vs Kaplan-Meier; fração que manifesta sem limite de idade, P(C)·π, vs a recuperada pela cura mista; mediana exata vs Weibull da Lifelines; cura mista recupera π, λ, ρ; pico de h(t) por lócus e do risco combinado (faixa 60–75 só como referência para o combinado) | Tabelas 7 e 10, Figura 4 |
| Tempo de processamento | por motor e por N | Tabela 8 |
| Sensibilidade | literatura × penetrância log-normal truncada × parâmetros do exemplo do orientador × C9orf72 familiar (π = 0,9) | Tabela 9 |
| Calibração das probabilidades | Brier score e curva por decis numa coorte sintética de desfecho conhecido, com verdade = modelo e verdade alternativa | Tabelas 12 a 14, Figura 10, `test_metricas_verificacao.py` |
| Discriminação | C-index de Harrell e AUC dependente do tempo (Mann-Whitney) a 10 e 20 anos | Tabela 15 |
| Idade de início | erro absoluto médio por gene contra o piso teórico | Tabela 16 |
| Cobertura dos intervalos | intervalos do Monte Carlo contra o valor exato; bandas de F(t) contra o F de cada mundo | Tabelas 17 e 17b |
| Divergência entre curvas | Kolmogorov-Smirnov e Wasserstein, empírico contra teórico | Tabela 18 |
| Robustez a erros no VCF | seis perturbações controladas por cenário e o que o artefato reporta | Tabela 19, Figura 11 |
| Sensibilidade por parâmetro | tornado, um parâmetro por vez, só com faixas publicadas | Tabela 20, Figura 12 |
| Genitor inferido por parentes | valores exatos de referência com penetrância compartilhada; NumPy e PyMC contra o exato | Tabela 1d, `test_parentes.py` |

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
    calibracao.py      ajustar_beta, ajustar_lognormal_truncada, ajustar_weibull/lognormal (pontos), weibull_de_momentos/quantis (estatísticas), carregar_parametros (YAML → priors)
    exato.py           cpt_segregacao, prob_portador, DistribuicaoPenetrancia, DistribuicaoInicio, f_acumulada, risco_condicional, quantil_inicio_condicional, inicio_por_causa, hazard
    monte_carlo.py     Locus, ResultadoSimulacao, simular_numpy, repetir, condicionar_idade   (camada 2)
    rede_bayesiana.py  construir_modelo (PyMC), simular_pymc, descrever_dag
    sobrevivencia.py   coorte_sintetica, ajustar_km, MisturaCuraWeibullFitter, curvas_analiticas, tabela_risco_condicional, indicadores_condicionados (camada 3)
    avaliacao.py       aderencia, estabilidade, tempos, coerencia, sensibilidade; verificação: coorte_de_mundos, brier, curva_calibracao, discriminacao, erro_idade_inicio, cobertura_monte_carlo, cobertura_bandas, divergencia_curvas, robustez_vcf, tornado
    relatorio.py       figuras 1 a 8 e 10 a 12, salvar_tabela, escrever_relatorio, escrever_metadados
    atualizacao.py     baixar_clinvar, registrar_versao, comparar_versoes, atualizar (versões da base ClinVar)
    repeticoes.py      transmissão do C9orf72 por repetições, limiar e antecipação (extensão experimental)
    comparacao.py      CoxPHFitter na coorte de portadores vs cura mista (extensão)
    parentes.py        genitor sem exame inferido pelo genótipo de parentes, com penetrância compartilhada (três gerações)
    pipeline.py        executar, avaliar, tudo (limpam a pasta de saída no início)
    cli.py             ela-preditivo {gerar-cenarios | executar | avaliar | tudo | atualizar-base | servir | criar-admin | popular-demo | verificar-auditoria | gerar-chave}
    web/               plataforma (seção 5.1): api (app, guarda de sessão/CSRF), config, bd, modelos, seguranca, permissoes (RBAC),
                       auditoria, contas, admin, pacientes (registros, genitores, descendentes, consentimentos, filtros), vcfs (anexos cifrados),
                       pesquisa (casos pseudonimizados, totais, CSV), analises, artefato (execuções em segundo plano, base de anotação,
                       equivalência com a linha de comando), arranque (chave e, se o ambiente trouxer, o administrador),
                       primeiro_acesso (administrador e demonstração pela tela; senha temporária),
                       demo, textos; static/ (index.html, styles.css, app.js, icone.svg)
  tests/               251 testes (pytest; 7 só com dados_reais/)
Dockerfile  docker-compose.yml  .env.exemplo        na raiz do repositório (seção 4)
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
| | `fenotipos, proporcao_patogenica, heranca_declarada, regra_qualificada, nota_regra` | PhenotypeList/CLNDN; fração de Pathogenic + Likely pathogenic na abertura do conflito; herança declarada num fenótipo de ELA (dominante, recessiva, ambas); indicador e nota da regra qualificada para conflitantes |
| vetor de dosagem | `fonte` | `vcf`, `laudo` ou `laudo+vcf` (origem da dosagem do lócus) |
| vetor de dosagem (`genotipo.vetor_dosagem`) | `dosagem_mae, dosagem_pai, heranca, p_portador_exato, descartado, observacao` | entrada do nó inicial da Rede Bayesiana; `descartado = True` (genótipo indeterminado no VCF ou laudo do C9orf72 ausente num genitor) quando um genitor tem o sítio com genótipo não determinado (dosagem vazia, motivo em `observacao`; o lócus não entra no cálculo, TCC 4.3) |
| vetor com parentes (`parentes.vetor_familia`) | `genitor_inferido, p_dosagem_mae, p_dosagem_pai` | lado inferido por parentes (dosagem dele vazia) e a distribuição inferida da dosagem, só com os genótipos |
| resumo (`ResultadoSimulacao.resumo`) | `p_portador_exato/mc, ep_portador` | transmissão exata, simulada e erro padrão |
| | `penetrancia_media/q025/q975` | prior Beta: média e IC 95 % |
| | `p_manifesta_exato/mc/q025/q975`, `p_manifesta_sem_limite` | risco vitalício até o horizonte e intervalo de credibilidade; fração que manifesta em algum momento, sem limite de idade |
| | `idade_mediana_exata/mc, idade_p10/p90_mc` | idade de início entre os que manifestam |
| curvas (`sobrevivencia.curvas_analiticas`) | `t, F, S, h, F_q025, F_mediana, F_q975` | curvas por unidade (lócus ou "qualquer lócus") |
| risco condicional | `idade_atual, p_portador_condicional, risco_10_anos, risco_20_anos, risco_residual (+q025/q975)` | Tabela 4: valores para quem chegou à idade atual sem sintomas; `risco_residual` vai da idade atual até o horizonte (na Tabela 4b, `risco_residual_km`) |
| CSV do pesquisador (`pesquisa.csv_casos`) | `p_transmissao, risco_vitalicio (+q025/q975), F_50, F_60, F_70, inicio_mediana/q25/q75_desde_nascimento` | desde o nascimento, em toda análise |
| | `faixa_idade_referencia, p_portador_sem_sintomas, risco_residual (+q025/q975), risco_10_anos, risco_20_anos, inicio_mediana/q25/q75_a_partir_da_idade` | a partir da idade de referência (em década), para a pessoa sem sintomas; vazias quando a análise não tem idade |
| indicadores condicionados (`sobrevivencia.indicadores_condicionados`) | `idade_referencia, p_portador, risco_residual, janelas[10, 20], inicio (q25, mediana, q75)` | os três indicadores a partir da idade atual, sem sintomas; em `metadados.json` como `indicadores_condicionados` |
| coorte de verificação (`avaliacao.coorte_de_mundos`) | `mundo, cenario, sexo, idade_atual, evento, idade_inicio, tempo, gene_inicio, p_portador, risco_10, risco_20, risco_horizonte, mediana_prevista` | uma linha por pessoa: desfecho verdadeiro e previsão do artefato |
| `metadados.json` | `base_anotacao (arquivo_base_real, release_base_real, sha256_base_real), loci_descartados, saida_limpa` | proveniência: versão da base usada, lóci descartados por genótipo indeterminado e o que foi apagado da pasta antes de gravar |
| | `parentes, limite_inferior, sorteios_rejeitados, tornado, verificacao` | parentes e suposições do genitor inferido; rótulo de limite inferior (genitor afetado); sorteios descartados pela situação clínica do genitor; opção de tornado; bloco das métricas de verificação (só em `avaliar`) |

## 11. Testes

```bash
pytest -q ela_preditivo/tests        # 251 testes, ~3 min (7 deles só rodam com dados_reais/ presente); os da plataforma estão em test_web.py
```

Cobrem: CPT e fórmulas exatas; calibração (Beta reproduz ponto e limite inferior do IC; Weibull recupera parâmetros conhecidos e a mediana de 58 anos de Murphy); geração e leitura dos VCFs (normalização de cromossomo, regiões, multialélicos, expansão, filtros); anotação (classes, estrelas, cruzamento por posição e por rs, limiar de repetições, carregador de `variant_summary`); vetor de dosagem nos 5 cenários; aderência PyMC ≈ NumPy ≈ exato; recessividade; reprodutibilidade por seed; efeito do sexo; condicionamento por idade; Lifelines (censura, KM = F(∞), cura mista recupera π, λ, ρ; risco condicional KM ≈ analítico); pipeline e CLI de ponta a ponta; regras do artefato vindas do texto do TCC e da robustez do pipeline (`test_regras_do_artefato.py`: genótipo indeterminado, classe conflitante, estatísticas em forma fechada, N pequeno sem ajuste da Lifelines, DataFrame como tabela curada, limpeza da pasta, limiares do TCC 4.3, faixa 60–75 só no combinado, banda combinada, VUS-high e valores mistos, laudo sem linha de repetição, fileDate fixo); atualização de bases (`test_atualizacao.py`: registro, comparação entre releases, download filtrado a partir de um arquivo local e CLI); extensões (`test_repeticoes.py`: hipóteses zeradas não mudam nada, enumeração e dosagem efetiva, delta só em alelos instáveis, criação/remoção do lócus, antecipação, CLI; `test_comparacao.py`: coorte só de portadores nos dois sexos, Cox reproduz KM e fração de cura, poucos eventos não quebram, Tabela 11 e Figura 9); plataforma web (`test_web.py`: um teste por critério de aceite das revisões de 15/11/2026, autenticando antes de chamar a API; inclui os três casos, VCFs cifrados, suposição de não portador, resumo guardado, filtros do médico, casos pseudonimizados com CSV e a página Ajuda); laudo ausente do C9orf72 como genitor não testado e regra qualificada para classificação conflitante, com o impacto esperado na base real em `test_dados_reais.py`.

Dos textos e rótulos: `test_textos_e_rotulos.py` (nenhum texto fala de quem escreve em terceira pessoa; "risco vitalício" só nomeia o risco desde o nascimento, na Tabela 4, no CSV e na interface; nenhuma tela escreve valor ausente como "null"; o C9orf72 de genitor sem laudo aparece como inferido quando um parente tem laudo).

Da interface completa: `test_artefato_interface.py` (cada comando e cada opção do `argparse` tem lugar declarado na interface, com os mesmos padrões; o formulário vira os mesmos argumentos; uma execução por vez, com saída, registro, pacote, cancelamento e reinício; a avaliação disparada pela interface dá as mesmas Tabelas 13, 15, 17b e 19 de `pipeline.avaliar`; base enviada, registrada e comparada; opções avançadas da análise sem registro com o mesmo número de `pipeline.executar`) `test_arranque.py` (chave e administrador do ambiente na subida; arquivos do Docker) e `test_primeiro_acesso.py` (o administrador é criado pela tela uma única vez; a demonstração devolve as senhas uma vez e fecha; administrador criado por outro recebe senha temporária e só alcança a troca de senha; banco antigo ganha a coluna nova).

Desta revisão: `test_condicionamento_e_horizonte.py` (indicadores condicionados com os valores exatos de referência; um só risco vitalício, com o FUS igual a 0,0918 nas Tabelas 3 e 4 e no indicador); `test_parentes.py` (inferência exata com penetrância compartilhada, tio e filho testado, NumPy e PyMC contra o exato, regras do C9orf72, pipeline e linha de comando; sem parentes, resultado idêntico ao anterior); `test_metricas_verificacao.py` (coorte de mundos, calibração, discriminação, erro da idade de início no piso teórico, cobertura, divergência, robustez e tornado, sempre com verdade = modelo e com verdade alternativa); e, em `test_calibracao.py`, `test_comparacao.py` e `test_web.py`, a log-normal truncada, as sementes independentes por sexo no Cox, a confirmação de assintomático, os parentes pela interface e a demonstração sem menor de idade.

## 12. Regras e decisões do artefato, pelo nome

Este README é a documentação do artefato. As regras abaixo têm nome próprio; é por esse nome que o texto do TCC e o roteiro de apresentação as citam.

| Regra | O que diz | Onde está |
|---|---|---|
| **Filtro de qualidade do VCF** | só entram genótipos com FILTER = PASS, DP ≥ 20 e GQ ≥ 30; o que é reprovado é contado nos indicadores de qualidade | `ingestao.ler_vcf`; `filtro_qualidade` no YAML |
| **Regra do genótipo indeterminado** | sítio de risco com genótipo ausente ou `./.` num genitor tira o lócus inteiro do cálculo. Nunca vale como "sem a variante": o lócus fica na Tabela 1b marcado como descartado, com o motivo | `genotipo.vetor_dosagem` |
| **Regra do laudo ausente** | a expansão do C9orf72 vem só do laudo. Genitor sem laudo é genitor não testado: o lócus fica indeterminado, sai do cálculo e o resultado é declarado parcial para o gene. Nunca vale como "sem expansão". Se um parente desse genitor tem laudo, o C9orf72 dele é inferido e o lócus volta ao cálculo | `genotipo.vetor_dosagem`, `parentes.py` |
| **Limiares de repetição do C9orf72** | 30 repetições ou mais: patogênico; 24 a 29: intermediário | `limiar_repeticoes_c9orf72` no YAML |
| **Regra qualificada das conflitantes** | variante com classificações conflitantes no ClinVar só entra como risco se mais da metade das classificações na abertura do conflito é patogênica ou provavelmente patogênica e o fenótipo declara o modo de herança. Caso que motivou a regra: SOD1 p.Asp91Ala | `regra_conflitante` no YAML; `anotacao.py` |
| **Precedência do ClinVar** | quando a base real e a tabela curada classificam a mesma variante de modo diferente, vale o ClinVar e a divergência fica registrada; a tabela curada contribui com a herança e com a expansão do C9orf72 | `anotacao.tabela_anotacao` |
| **Suposição de não portador** | um genitor sem exame pode ser assumido sem variante de risco, por escolha do profissional; a suposição aparece no resultado, no resumo guardado e nos metadados | plataforma, `assumir_nao_portador` |
| **Risco vitalício até o horizonte** | "risco vitalício" tem um só significado: probabilidade de manifestar do nascimento até o horizonte de 90 anos. A fração que manifesta em algum momento, sem limite de idade, só aparece em coluna própria da Tabela 3. O risco contado a partir da idade atual chama-se **risco residual** | `monte_carlo.Locus`; Tabelas 3 e 4 |
| **Indicadores condicionados à idade atual** | com a idade informada, as três respostas valem para quem chegou a ela sem sintomas: probabilidade de portar dado que não manifestou, risco residual até o horizonte e nos próximos 10 e 20 anos, e idade provável de início entre quem ainda vai manifestar. É a conta exata da Tabela 4 | `sobrevivencia.indicadores_condicionados` |
| **Confirmação de assintomático** | a análise de uma pessoa só roda com a confirmação de que ela não apresenta sintomas; guarda-se o sim e a data. Não se aplica ao futuro filho de um casal | plataforma |
| **Penetrância Beta, com log-normal truncada como alternativa** | o padrão é a Beta calibrada ao ponto e ao intervalo publicados; a log-normal truncada em 1 reproduz ponto e intervalo e entra sempre como cenário de sensibilidade | `calibracao_penetrancia` no YAML |
| **Independência entre lóci** | com mais de um lócus de risco, P(qualquer) = 1 − ∏(1 − P_g) | `exato.py` |
| **Efeito do sexo só no C9orf72** | homens um ano antes, mulheres um ano depois; nos demais genes não há evidência e o efeito é nulo | `delta_sexo` no YAML |
| **Genitor sem exame inferido por parentes** | entram o VCF e o laudo de pai, mãe ou irmão do genitor e, numa família, o VCF de um filho já testado. Só o genótipo de parentes entra; o fenótipo de parente sem teste fica fora. A situação clínica do genitor condiciona a inferência | `parentes.py`; Tabela 1d |
| **Penetrância compartilhada na família** | a penetrância é do gene, não da pessoa: é sorteada uma vez e vale para o genitor e para o descendente | `parentes.py` |
| **Prior dos avós sem exame** | avô ou avó sem exame é suposto não portador (padrão) ou recebe a prior de Hardy-Weinberg com a frequência alélica da base; sem frequência, volta à suposição, e a saída diz qual valeu | `--prior-avos` |
| **Limite inferior com genitor afetado** | o fenótipo do genitor não é modelado: quando o genitor sem exame teve ELA, a variante nele é mais provável do que o cálculo considera, e o resultado sai rotulado como limite inferior | `parentes.py` |
| **Sementes independentes por sexo no Cox** | na comparação com o modelo de Cox, cada sexo é simulado com semente própria, derivada da semente da execução | `comparacao.sementes_por_sexo` |
| **Verificação, não validação** | as métricas das Tabelas 12 a 20 usam famílias sintéticas geradas pelo próprio modelo. Cada uma é calculada com verdade igual ao modelo e com uma verdade alternativa, para mostrar como degrada | `avaliacao.ENQUADRAMENTO` |
| **Coorte de mundos** | em cada mundo a penetrância de cada gene é sorteada uma vez; entram na coorte as pessoas que chegam sem sintomas à idade atual | `avaliacao.coorte_de_mundos`; Tabela 12 |
| **Tornado só com faixas publicadas** | cada parâmetro varia dentro de uma faixa com fonte; o FUS fica fora da idade de início por não ter incerteza publicada | `sensibilidade.tornado` no YAML; Tabela 20 |
| **Negação por padrão** | toda rota exige sessão e permissão do papel, salvo as públicas; o médico só vê os próprios registros, o pesquisador só casos pseudonimizados e o administrador não vê dados clínicos | `web/permissoes.py` |
| **Parâmetros do artefato na ficha** | a análise de um registro usa sempre os parâmetros do artefato e a base em uso; arquivos alternativos só na análise sem registro, declarados no resultado | `web/analises.py` |
| **Primeiro acesso e senha temporária** | o administrador é criado pela tela enquanto não há nenhum; conta criada por terceiro recebe senha temporária, trocada no primeiro login | `web/primeiro_acesso.py` |
| **Idade por década na pesquisa** | o pesquisador nunca recebe a idade exata, só a faixa de dez anos, inclusive a idade de referência dos valores condicionados | `web/pesquisa.py` |

## 13. Limitações e pontos a confirmar

1. **Curvas de idade de SOD1, TARDBP e FUS são placeholders** (`confirmar: true`) até a transcrição das faixas etárias de Richard et al. (2026). Os pontos intermediários da curva do C9orf72 (45 e 70 anos) foram lidos aproximadamente da figura de Murphy et al. (2017) e devem ser digitalizados. O YAML já aceita, no lugar dos pontos, as estatísticas publicadas — média e desvio padrão (Berdyński et al., 2022) ou mediana e IQR (McFarlane et al., 2025) — resolvidas em forma fechada; adotá-las é uma decisão em aberto.
2. **Prior Beta vs IC publicado**: os IC de Douglas & Baralle são simétricos em escala logarítmica; a Beta reproduz o ponto (mediana) e o limite inferior, mas subestima o limite superior (SOD1: 0,74 vs 0,886). O erro é reportado na Tabela 6; `calibracao_beta.peso_ponto: 0` no YAML inverte a prioridade (reproduz o IC e desloca a mediana). A alternativa `calibracao_penetrancia.distribuicao: lognormal_truncada` reproduz ponto e intervalo (erro máximo 0,004); o padrão continua Beta; trocar o padrão é uma decisão em aberto.
3. **Penetrância do C9orf72**: nível populacional de Douglas & Baralle (0,33); a curva de Murphy (coortes familiares, quase completa aos 80 anos) entra só como forma etária. A Tabela 9 mostra o efeito de usar π = 0,9.
4. **Independência entre lóci** e ausência de fatores modificadores, oligogenia, mosaicismo, variantes de novo e faseamento.
5. **Efeito do sexo** documentado apenas para o C9orf72 (2 anos).
6. **Populações de referência** europeias/norte-americanas (TCC, Quadro 6); ausência de coortes brasileiras.
7. **Dados sintéticos**: o filtro de qualidade e a anotação foram exercitados com ruído controlado; o desempenho com arquivos VCF grandes (requisito não funcional) ainda não foi medido.
8. **Ferramentas citadas no TCC**: Biopython não lê VCF (aqui normaliza o motivo de repetição); PyVCF é usado pela distribuição mantida `pyvcf3`. Sugere-se ajustar o texto das seções 3.3 e 4.4.D, e revisar a nomenclatura de F(t) e da função de risco instantâneo no texto do TCC.
9. **Regra qualificada para conflitantes e penetrância da p.Asp91Ala**: os critérios do bloco `regra_conflitante` e a nota `penetrancia_excecoes` ficam com `confirmar: true` até a atualização do texto da seção 4.2.2 do TCC; a penetrância usada para homozigotos D91A é a do gene, porque Douglas & Baralle (2024) excluíram essa variante. O impacto na base consolidada (73 conflitantes, 1 aceita) deve ser conferido na máquina com `dados_reais/`.
10. **Verificação não é validação**: as métricas das Tabelas 12 a 20 usam famílias sintéticas geradas pelo próprio modelo. Mostram que a implementação reproduz o modelo e como cada métrica degrada com outra verdade; não dizem como o modelo se sai com pacientes reais.
11. **Genitor inferido por parentes**: só o genótipo de parentes entra; o fenótipo de parente sem teste ("o tio teve ELA") não é usado. Supõe-se a variante herdada, não surgida no parente. Avô ou avó sem exame é suposto não portador, ou recebe a prior de Hardy-Weinberg quando a base traz a frequência; a saída registra qual valeu. Com o genitor afetado, o resultado é um limite inferior.
12. **Fora do escopo, de propósito**: pessoas sintomáticas (não há fluxo para elas; a análise exige a confirmação de que a pessoa está sem sintomas), números agregados da família, regras para menores de idade e ajuste por ancestralidade.
13. **Erros no VCF que o artefato não tem como ver** (Tabela 19): registro ausente ou genótipo trocado para 0/0 é falso negativo silencioso, e variante inserida por engano entra no cálculo. O resultado depende da qualidade do sequenciamento e do laudo.
14. **Faixas do tornado**: o erro padrão da mediana do TARDBP é uma aproximação e a lista de medianas do C9orf72 está com `confirmar: true`; o FUS não tem incerteza publicada para a idade de início e fica fora.
15. **Interface e linha de comando**: só subir o serviço fica fora da interface. O primeiro acesso é de quem chega primeiro ao endereço: por isso o serviço atende só a própria máquina por padrão, e num servidor exposto convém criar o administrador pelas variáveis `ELA_ADMIN_*`. Não há recuperação de senha esquecida, e a senha temporária não tem prazo de validade. As execuções do artefato rodam uma por vez e não sobrevivem a um reinício do servidor. Baixar a release do ClinVar exige que o servidor alcance o NCBI. A análise pela interface limita N a 200.000 (as execuções do artefato, a 1.000.000); a linha de comando não tem esse teto.

## 14. Trabalhos futuros

Versionamento do dbSNP e execução periódica automática de `atualizar-base` (o ClinVar já tem download, registro de versão e comparação entre releases, `atualizacao.py`); validação externa com dados de coortes (mediante aprovação ética); modelo oligogênico; fatores modificadores (idade dos pais, ancestralidade, histórico familiar); na plataforma (seção 5.1): histórico de análises por paciente, visão de pesquisa com casos pseudonimizados, segundo fator (TOTP), recuperação de senha por e-mail, laudo em PDF para o paciente e gestão da base ClinVar pelo painel; empacotamento com Docker.

## 15. Referências principais (ver lista completa no TCC)

Douglas & Baralle (2024) *J Med Genet* 61:294–297; Murphy et al. (2017) *Sci Rep* 7:2116; Feldman et al. (2022) *Lancet* 400:1363–1380; Goutman et al. (2022) *Lancet Neurol* 21:480–493; Richard et al. (2026) *Genes* 17(5):576; Danecek et al. (2011) *Bioinformatics* 27:2156–2158; Landrum et al. (2018) *NAR* 46:D1062–D1067; Sherry et al. (2001) *NAR* 29:308–311; Pearl (1988); Koller & Friedman (2009); Metropolis & Ulam (1949); Davidson-Pilon (2026) Lifelines 0.30.3; PyMC Development Team (2026); Chapman et al. (2000) CRISP-DM; Hevner et al. (2004); Peffers et al. (2007); Berdyński et al. (2022) *SOD1 mutations associated with ALS: analysis of variant severity* (média e desvio padrão da idade de início; a confirmar); McFarlane et al. (2025) *ALS & FTD* 26(sup. 1):41–49, DOI 10.1080/21678421.2025.2450805 (mediana e IQR; a confirmar).
