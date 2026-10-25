# 06 — O exemplo do orientador como base (`exemplo_maquina_tcc_ela.py`)

Arquivo enviado pelo orientador (exportação de um notebook Colab), guardado na raiz do repositório. **Não editar**; serve de referência de partida. Este documento mapeia o que ele faz para os módulos do pacote `ela_preditivo` e registra o que foi mantido, evoluído ou corrigido.

## O que o exemplo faz

| Classe do exemplo | O que faz | Módulo correspondente no pacote |
|---|---|---|
| `GenomicETL` | dicionário fixo gene → variante, rs, `penetrance_max`, Weibull (`weibull_alpha` = escala λ, `weibull_beta` = forma k); recebe dosagens dos pais (0/1/2) | `ingestao.py` (lê VCF real), `anotacao.py` (tabela curada ClinVar/dbSNP), `genotipo.py` (dosagens), `config/parametros_literatura.yaml` (parâmetros com citação) |
| `BayesianMonteCarloEngine` | transmissão mendeliana por `np.random.binomial(1, d/2)` para cada genitor, soma = dosagem do descendente; portador = dosagem > 0; manifestação = Bernoulli(portador × penetrância); N = 10.000 | `exato.py` (fórmulas), `monte_carlo.py` (NumPy, mesma lógica, vetorizada e com seed), `rede_bayesiana.py` (PyMC, DAG explícito) |
| `SurvivalAnalyzer` | idade de início `np.random.weibull(k) * λ` para os portadores; `WeibullFitter` da Lifelines; mediana | `sobrevivencia.py` (coorte sintética com censura, KM, Weibull, cura mista, condicional à idade) |
| gráfico final | risco acumulado = (1 − S(t) da Weibull ajustada) × taxa de portadores | `relatorio.py` (Figura 4) |

## Mantido

- As três camadas e a ordem: ETL/anotação → transmissão + Monte Carlo → sobrevivência → gráfico.
- A lógica de transmissão (Bernoulli(d/2) por genitor) e o uso de `WeibullFitter` da Lifelines.
- N = 10.000 simulações como padrão.
- Cenário A do exemplo (pai heterozigoto SOD1, mãe selvagem) é o cenário 1 do pacote.

## Evoluído

- Leitura de VCF real com PyVCF (`pyvcf3`), filtro de qualidade, máscara de regiões GRCh38 e decomposição multialélica (TCC 4.3), em vez de dosagens digitadas.
- Anotação por tabela curada (coordenadas conferidas em dbSNP/ClinVar em 24/10/2026) e carregador para o subconjunto real do ClinVar.
- Penetrância como prior Beta calibrada ao ponto e ao IC 95% de Douglas & Baralle (2024), em vez de um `penetrance_max` fixo: a incerteza do parâmetro chega às curvas (bandas de credibilidade).
- Herança recessiva (SOD1 p.D91A) e expansão de repetições do C9orf72 por contagem.
- Rede Bayesiana explícita em PyMC (`sample_prior_predictive`), além do amostrador NumPy equivalente.
- Condicionamento à idade atual sem sintomas e ao sexo; combinação de vários genes.
- Avaliação exigida pelo TCC (aderência, estabilidade com N = 1e3/1e4/1e5, coerência, tempo).

## Corrigido

- **Curva de risco**: o exemplo plota `(1 − S(t)) × taxa_de_portadores`, sem multiplicar pela penetrância, então a curva atinge P(portador) (50%) e não o risco global impresso no console (45%). No pacote, F(t) = P(C) · π · G(t), coerente com o "risco global de manifestação".
- **Idade de início só dos portadores**: o exemplo sorteia idade para todos e filtra portadores, mas ignora quem porta e nunca manifesta (penetrância incompleta). O pacote usa o modelo de cura mista: só quem manifesta recebe idade; os demais são censurados.
- **Parâmetros**: os valores do exemplo (penetrância 0,90/0,60/0,80/0,45; Weibull λ 50/62/57/44 e k 4,5/5,0/4,2/3,8) não têm citação e divergem de Douglas & Baralle (0,54/0,33/0,38/0,19). Ficaram no YAML como `sensibilidade.exemplo_professor`, para a seção 5 comparar os dois conjuntos.
- **Variantes e rs do exemplo** (ex.: SOD1 "c.148G>A (p.Ala5Val)" com rs121912438) não batem entre si; a tabela curada usa SOD1 c.14C>T p.Ala5Val rs121912442 (chr21:31659783 C>T, GRCh38), conferido no dbSNP.
- Sem seed e com `np.random` global: o pacote usa `numpy.random.default_rng(seed)` e grava a seed em cada saída.
