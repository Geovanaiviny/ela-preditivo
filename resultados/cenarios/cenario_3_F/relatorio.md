# Relatório do artefato — Cenário 3 (F): Pai heterozigoto SOD1 p.Ala5Val × mãe com expansão C9orf72 (45 repetições, laudo; exemplo literal do TCC, 4.5)

> AVISO: instrumento experimental de apoio à decisão no aconselhamento genético preditivo da ELA, construído com dados sintéticos e parâmetros populacionais da literatura. Não constitui diagnóstico, não substitui o julgamento clínico e não deve ser usado isoladamente em decisões sobre pacientes.

## Entrada

VCF materno: `cenario_3_mae.vcf` (amostra MAE); VCF paterno: `cenario_3_pai.vcf` (amostra PAI); laudo do C9orf72: mae: 45 repetições; sexo do descendente: F; idade atual sem sintomas: 30.0; motor: pymc; N = 10.000; seed = 42; horizonte = 90 anos.

## Qualidade dos dados (TCC 4.2.3)

- Mãe: montagem GRCh38 (coerente); 5/7 registros aprovados (71%); 2 aprovados encontrados na base de anotação (40%; estado de revisão 2★: 2); classes {'nao_anotada': 3, 'benigna': 1, 'risco': 1}; significado incerto: 0 (0% das anotadas); classificação conflitante: 0 (0%); risco com frequência > 1%: 0.
- Pai: montagem GRCh38 (coerente); 5/7 registros aprovados (71%); 2 aprovados encontrados na base de anotação (40%; estado de revisão 2★: 2); classes {'nao_anotada': 3, 'benigna': 1, 'risco': 1}; significado incerto: 0 (0% das anotadas); classificação conflitante: 0 (0%); risco com frequência > 1%: 0.
- Base de anotação: clinvar_base_consolidada; regra de classe: só Pathogenic/Likely pathogenic sustentam risco; significado incerto e classificações conflitantes não (TCC 4.2.2).

## Resultado

- **SOD1 p.Ala5Val** (dominante; dosagens mãe/pai 0/1): P(portador) = 50.0% (MC 49.5%); penetrância média 53.9% [32.7%–74.4%]; risco vitalício 26.9% [16.3%–37.2%]; idade mediana de início 50.9 anos (p10–p90 MC: 36–63).
- **C9orf72 expansão GGGGCC** (dominante; dosagens mãe/pai 1/0): P(portador) = 50.0% (MC 50.4%); penetrância média 33.3% [20.5%–47.5%]; risco vitalício 16.6% [10.2%–23.7%]; idade mediana de início 59.3 anos (p10–p90 MC: 45–71).
- **Combinado (qualquer lócus, independência)**: P(portador de ≥ 1) = 75.0%; risco vitalício 39.1% [28.8%–48.6%]; idade mediana do primeiro início 52.8 anos. Condicionando ao descendente assintomático aos 30 anos (rejeição de 113 sorteios), P(portador de ≥ 1 lócus) passa de 74.8% para 74.5% e o risco vitalício residual é 38.1%.

## Verificações

Aderência: maior desvio entre Monte Carlo e valor exato = 1.26 erros padrão (limite usual: 4). Coerência: risco vitalício por Kaplan-Meier = SOD1 p.Ala5Val: 26.4%, C9orf72 expansão GGGGCC: 16.9%, qualquer lócus: 38.8%. Recuperação Lifelines: erro relativo máximo em π = 1.2%. Tempo: 6.5 s no total (pymc: 3.17 s; motor cruzado: 0.00 s).

## Limitações desta execução

Parâmetros provisórios (confirmar: true) em: C9orf72, TARDBP. Independência entre lóci; sem fatores modificadores; penetrância populacional de coortes europeias/norte-americanas; dados sintéticos.

## Tabelas

**Tabela 1 — Variantes aprovadas no filtro de qualidade e sua anotação, por genitor**

| amostra | gene | cromossomo | posicao | ref | alt | id | tipo | dosagem | repeticoes | classe | clnsig | estrelas | nome_curto | heranca | fonte_anotacao |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MAE | TARDBP | 1 | 11020000 | G | A |  | snv | 0 |  | nao_anotada |  |  |  |  |  |
| MAE | TARDBP | 1 | 11020000 | G | T |  | snv | 1 |  | nao_anotada |  |  |  |  |  |
| MAE | FUS | 16 | 31185000 | A | G |  | snv | 1 |  | nao_anotada |  |  |  |  |  |
| MAE | SOD1 | 21 | 31659509 | G | T | rs17883296 | snv | 1 |  | benigna | Likely benign | 2 | rs17883296 |  | clinvar_base_consolidada:posicao_alelos |
| MAE | SOD1 | 21 | 31659783 | C | T | rs121912442 | snv | 0 |  | risco | Pathogenic | 2 | p.Ala5Val | dominante | clinvar_base_consolidada:posicao_alelos |
| PAI | TARDBP | 1 | 11020000 | G | A |  | snv | 0 |  | nao_anotada |  |  |  |  |  |
| PAI | TARDBP | 1 | 11020000 | G | T |  | snv | 1 |  | nao_anotada |  |  |  |  |  |
| PAI | FUS | 16 | 31185000 | A | G |  | snv | 1 |  | nao_anotada |  |  |  |  |  |
| PAI | SOD1 | 21 | 31659509 | G | T | rs17883296 | snv | 1 |  | benigna | Likely benign | 2 | rs17883296 |  | clinvar_base_consolidada:posicao_alelos |
| PAI | SOD1 | 21 | 31659783 | C | T | rs121912442 | snv | 1 |  | risco | Pathogenic | 2 | p.Ala5Val | dominante | clinvar_base_consolidada:posicao_alelos |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

Registros lidos/aprovados: mãe 7/5, pai 7/5. Reprovações: mãe {'fora_das_regioes': 1, 'filtro_nao_pass': 1, 'dp_baixo': 1, 'gq_baixo': 1}, pai {'fora_das_regioes': 1, 'filtro_nao_pass': 1, 'dp_baixo': 1, 'gq_baixo': 1}. Base de anotação: clinvar_base_consolidada (1458 variantes do ClinVar + 1 da tabela curada).


**Tabela 1b — Vetor genotípico parental: dosagem alélica (0/1/2) por lócus de risco e P(portador) exata; lócus com genótipo não determinado num genitor fica marcado como descartado e não entra no cálculo (TCC 4.3)**

| gene | variante | rs | tipo | heranca | dosagem_mae | dosagem_pai | repeticoes_mae | repeticoes_pai | clnsig | estrelas | fonte | p_portador_exato | descartado | observacao |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 | p.Ala5Val | rs121912442 | snv | dominante | 0 | 1 |  |  | Pathogenic | 2 | vcf | 0.5 | não |  |
| C9orf72 | expansão GGGGCC |  | repeticao | dominante | 1 | 0 | 45 |  | Pathogenic | 1 | laudo | 0.5 | não |  |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 2 — Aderência teórica: probabilidades exatas vs Monte Carlo (PyMC e NumPy), erro padrão e qui-quadrado do genótipo do descendente**

| variante | n | p_portador_exato | p_portador_pymc | p_portador_numpy | ep_portador | desvio_portador_pymc_em_ep | desvio_portador_numpy_em_ep | p_manifesta_exato | p_manifesta_pymc | p_manifesta_numpy | ep_manifesta | desvio_manifesta_pymc_em_ep | desvio_manifesta_numpy_em_ep | qui2_genotipo_pymc | valor_p_genotipo_pymc | qui2_genotipo_numpy | valor_p_genotipo_numpy | idade_mediana_exata | idade_mediana_pymc | idade_mediana_numpy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 p.Ala5Val | 10000 | 0.5 | 0.4954 | 0.4986 | 0.005 | 0.92 | 0.28 | 0.2694 | 0.2638 | 0.2645 | 0.0044 | 1.2624 | 1.1026 | 0.8464 | 0.3576 | 0.0784 | 0.7795 | 50.8673 | 50.4383 | 50.6986 |
| C9orf72 expansão GGGGCC | 10000 | 0.5 | 0.5042 | 0.4985 | 0.005 | 0.84 | 0.3 | 0.1664 | 0.1694 | 0.1691 | 0.0038 | 0.8115 | 0.732 | 0.7056 | 0.4009 | 0.09 | 0.7642 | 59.3045 | 59.5757 | 59.32 |
| qualquer lócus | 10000 | 0.75 | 0.7483 | 0.7463 |  |  |  | 0.3909 | 0.3877 | 0.3865 | 0.0049 | 0.6586 | 0.9055 |  |  |  |  |  | 52.8451 | 53.0744 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 3 — Probabilidade de transmissão (portador), penetrância e risco vitalício de manifestação por lócus e combinado, com intervalo de credibilidade de 95% (incerteza da penetrância) e idade de início**

| gene | variante | heranca | dosagem_mae | dosagem_pai | p_portador_exato | p_portador_mc | penetrancia_media | penetrancia_q025 | penetrancia_q975 | p_manifesta_exato | p_manifesta_mc | p_manifesta_q025 | p_manifesta_q975 | idade_mediana_exata | idade_mediana_mc | idade_p10_mc | idade_p90_mc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 | SOD1 p.Ala5Val | dominante | 0 | 1 | 0.5 | 0.4954 | 0.5387 | 0.3267 | 0.7436 | 0.2694 | 0.2638 | 0.1633 | 0.3718 | 50.8673 | 50.4383 | 35.6503 | 63.0457 |
| C9orf72 | C9orf72 expansão GGGGCC | dominante | 1 | 0 | 0.5 | 0.5042 | 0.3327 | 0.2048 | 0.4746 | 0.1664 | 0.1694 | 0.1024 | 0.2373 | 59.3045 | 59.5757 | 45.2364 | 70.8388 |
| — | qualquer lócus | independência |  |  | 0.75 | 0.7483 |  |  |  | 0.3909 | 0.3877 | 0.2879 | 0.4861 |  | 52.8451 |  |  |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 4 — Risco condicional à idade atual sem sintomas: P(portador | assintomático), risco nos próximos 10 e 20 anos e risco vitalício residual, com banda de 95%**

| unidade | idade_atual | p_portador_condicional | risco_10_anos | risco_10_anos_q025 | risco_10_anos_q975 | risco_20_anos | risco_20_anos_q025 | risco_20_anos_q975 | risco_vitalicio | risco_vitalicio_q025 | risco_vitalicio_q975 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 p.Ala5Val | 0 | 0.5 | 2.57e-05 | 1.55e-05 | 3.54e-05 | 0.0011 | 0.0007 | 0.0016 | 0.2694 | 0.1626 | 0.3708 |
| C9orf72 expansão GGGGCC | 0 | 0.5 | 3.29e-07 | 2.04e-07 | 4.68e-07 | 5.42e-05 | 3.36e-05 | 7.72e-05 | 0.1664 | 0.103 | 0.2368 |
| qualquer lócus | 0 |  | 2.61e-05 | 1.59e-05 | 3.57e-05 | 0.0012 | 0.0007 | 0.0016 | 0.3909 | 0.2879 | 0.4861 |
| SOD1 p.Ala5Val | 20 | 0.4994 | 0.0091 | 0.0055 | 0.0125 | 0.0447 | 0.027 | 0.0616 | 0.2685 | 0.162 | 0.3699 |
| C9orf72 expansão GGGGCC | 20 | 0.5 | 0.0009 | 0.0006 | 0.0013 | 0.0072 | 0.0044 | 0.0102 | 0.1663 | 0.103 | 0.2367 |
| qualquer lócus | 20 |  | 0.01 | 0.0064 | 0.0134 | 0.0516 | 0.0338 | 0.0685 | 0.3902 | 0.2874 | 0.4853 |
| SOD1 p.Ala5Val | 30 | 0.4948 | 0.0359 | 0.0216 | 0.0497 | 0.117 | 0.0703 | 0.1617 | 0.2618 | 0.1574 | 0.3619 |
| C9orf72 expansão GGGGCC | 30 | 0.4995 | 0.0063 | 0.0039 | 0.0089 | 0.0307 | 0.019 | 0.0438 | 0.1655 | 0.1025 | 0.2357 |
| qualquer lócus | 30 |  | 0.042 | 0.0276 | 0.0558 | 0.1442 | 0.0978 | 0.1887 | 0.384 | 0.2825 | 0.4784 |
| SOD1 p.Ala5Val | 40 | 0.476 | 0.0841 | 0.0498 | 0.1179 | 0.1832 | 0.1085 | 0.2568 | 0.2343 | 0.1387 | 0.3285 |
| C9orf72 expansão GGGGCC | 40 | 0.4964 | 0.0246 | 0.0152 | 0.0352 | 0.0813 | 0.0502 | 0.116 | 0.1603 | 0.099 | 0.2288 |
| qualquer lócus | 40 |  | 0.1067 | 0.0721 | 0.1408 | 0.2496 | 0.1759 | 0.3216 | 0.357 | 0.2613 | 0.4479 |
| SOD1 p.Ala5Val | 50 | 0.4279 | 0.1082 | 0.0618 | 0.1575 | 0.1582 | 0.0903 | 0.2303 | 0.164 | 0.0936 | 0.2387 |
| C9orf72 expansão GGGGCC | 50 | 0.4836 | 0.0581 | 0.0355 | 0.0838 | 0.1199 | 0.0733 | 0.173 | 0.1391 | 0.0851 | 0.2007 |
| qualquer lócus | 50 |  | 0.16 | 0.111 | 0.2109 | 0.2591 | 0.1858 | 0.3337 | 0.2803 | 0.2027 | 0.3588 |
| SOD1 p.Ala5Val | 60 | 0.3585 | 0.056 | 0.0304 | 0.0864 | 0.0625 | 0.0339 | 0.0963 | 0.0626 | 0.034 | 0.0964 |
| C9orf72 expansão GGGGCC | 60 | 0.4518 | 0.0656 | 0.0392 | 0.0974 | 0.0853 | 0.0509 | 0.1265 | 0.086 | 0.0514 | 0.1276 |
| qualquer lócus | 60 |  | 0.118 | 0.0827 | 0.1578 | 0.1424 | 0.0999 | 0.1901 | 0.1432 | 0.1004 | 0.1912 |
| SOD1 p.Ala5Val | 70 | 0.3204 | 0.0068 | 0.0036 | 0.0109 | 0.0069 | 0.0037 | 0.011 | 0.0069 | 0.0037 | 0.011 |
| C9orf72 expansão GGGGCC | 70 | 0.4133 | 0.021 | 0.0122 | 0.0323 | 0.0218 | 0.0127 | 0.0335 | 0.0218 | 0.0127 | 0.0335 |
| qualquer lócus | 70 |  | 0.0277 | 0.0183 | 0.0396 | 0.0286 | 0.0189 | 0.0408 | 0.0286 | 0.0189 | 0.0408 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 10 — Sobrevivência (assintomático) estimada por Kaplan-Meier na coorte simulada, com IC 95% (Greenwood); mediana não atingida quando o risco vitalício é inferior a 50%**

| unidade | n | eventos | risco_vitalicio_km | S(40) | IC95 S(40) | S(50) | IC95 S(50) | S(60) | IC95 S(60) | S(70) | IC95 S(70) | S(80) | IC95 S(80) | mediana_sobrevivencia | idade_90pct_do_risco |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 p.Ala5Val | 10000 | 2638 | 0.2638 | 0.9528 | 0.948–0.957 | 0.8729 | 0.866–0.879 | 0.7814 | 0.773–0.789 | 0.7404 | 0.732–0.749 | 0.7363 | 0.728–0.745 | não atingida | 63.1 |
| C9orf72 expansão GGGGCC | 10000 | 1694 | 0.1694 | 0.9922 | 0.990–0.994 | 0.9674 | 0.964–0.971 | 0.913 | 0.907–0.918 | 0.8509 | 0.844–0.858 | 0.8314 | 0.824–0.839 | não atingida | 70.8 |
| qualquer lócus | 10000 | 3877 | 0.3877 | 0.945 | 0.940–0.949 | 0.8434 | 0.836–0.850 | 0.7127 | 0.704–0.721 | 0.6301 | 0.621–0.639 | 0.6128 | 0.603–0.622 | não atingida | 66.1 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 7 — Recuperação dos parâmetros de entrada (π, λ, ρ) pelo ajustador de cura mista da Lifelines na coorte simulada de portadores**

| variante | n_portadores | eventos | pi_entrada | lambda_entrada | rho_entrada | delta_sexo | pi_lifelines | lambda_lifelines | rho_lifelines | erro_rel_pi | erro_rel_lambda | erro_rel_rho | weibull_lambda_manifestantes | weibull_rho_manifestantes | mediana_weibull_manifestantes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 p.Ala5Val | 4954 | 2638 | 0.5387 | 54.3959 | 5.4648 | 0 | 0.5325 | 54.0337 | 5.4334 | 0.0116 | 0.0067 | 0.0058 | 54.0338 | 5.4333 | 50.5091 |
| C9orf72 expansão GGGGCC | 5042 | 1694 | 0.3327 | 61.5171 | 6.8334 | 1 | 0.336 | 62.7422 | 6.8934 | 0.0098 | 0.0037 | 0.0088 | 62.7419 | 6.894 | 59.4934 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 4b — Risco condicional não paramétrico (Kaplan-Meier) para um descendente assintomático aos 30 anos**

| unidade | idade_atual | risco_10_anos_km | risco_20_anos_km | risco_vitalicio_km |
|---|---|---|---|---|
| SOD1 p.Ala5Val | 30 | 0.0372 | 0.1179 | 0.2561 |
| C9orf72 expansão GGGGCC | 30 | 0.0069 | 0.0317 | 0.1687 |
| qualquer lócus | 30 | 0.0442 | 0.147 | 0.3807 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


## Figuras

![Figura 1 — Rede Bayesiana (DAG) do núcleo estocástico](figuras\figura_01_dag.png)

*Figura 1 — Rede Bayesiana (DAG) do núcleo estocástico. Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

![Figura 4 — Risco acumulado de manifestação F(t) e sobrevivência S(t) do descendente, com banda de credibilidade de 95% e Kaplan-Meier da coorte simulada](figuras\figura_04_risco_temporal.png)

*Figura 4 — Risco acumulado de manifestação F(t) e sobrevivência S(t) do descendente, com banda de credibilidade de 95% e Kaplan-Meier da coorte simulada. Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

![Figura 6 — Aderência teórica: probabilidades exatas vs Monte Carlo (PyMC e NumPy), com erro padrão](figuras\figura_06_aderencia.png)

*Figura 6 — Aderência teórica: probabilidades exatas vs Monte Carlo (PyMC e NumPy), com erro padrão. Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

![Figura 8 — Função de risco instantâneo h(t) por lócus; faixa sombreada = pico de incidência 60–75 anos (Feldman et al., 2022)](figuras\figura_08_hazard.png)

*Figura 8 — Função de risco instantâneo h(t) por lócus; faixa sombreada = pico de incidência 60–75 anos (Feldman et al., 2022). Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

![Figura 5 — Distribuição simulada da idade de início entre os descendentes que manifestam, por lócus](figuras\figura_05_idade_inicio.png)

*Figura 5 — Distribuição simulada da idade de início entre os descendentes que manifestam, por lócus. Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*
