# Relatório do artefato — Cenário 1 (F): Pai heterozigoto SOD1 p.Ala5Val (alta penetrância) × mãe selvagem

> AVISO: instrumento experimental de apoio à decisão no aconselhamento genético preditivo da ELA, construído com dados sintéticos e parâmetros populacionais da literatura. Não constitui diagnóstico, não substitui o julgamento clínico e não deve ser usado isoladamente em decisões sobre pacientes.

## Entrada

VCF materno: `cenario_1_mae.vcf`; VCF paterno: `cenario_1_pai.vcf`; sexo do descendente: F; idade atual sem sintomas: 30.0; motor: pymc; N = 10.000; seed = 42; horizonte = 90 anos.

## Resultado

- **SOD1 A4V (p.A5V)** (dominante; dosagens mãe/pai 0/1): P(portador) = 50.0% (MC 49.5%); penetrância média 53.9% [32.7%–74.4%]; risco vitalício 26.9% [16.3%–37.2%]; idade mediana de início 50.3 anos (p10–p90 MC: 34–65).
- **Combinado (qualquer lócus, independência)**: P(portador de ≥ 1) = 50.0%; risco vitalício 26.9% [16.3%–37.2%]; idade mediana do primeiro início 50.6 anos. Condicionando ao descendente assintomático aos 30 anos (rejeição de 154 sorteios), P(portador de ≥ 1 lócus) passa de 49.5% para 48.8% e o risco vitalício residual é 25.3%.

## Verificações

Aderência: maior desvio entre Monte Carlo e valor exato = 1.19 erros padrão (limite usual: 4). Coerência: risco vitalício por Kaplan-Meier = SOD1 A4V (p.A5V): 26.4%, qualquer lócus: 26.4%. Recuperação Lifelines: erro relativo máximo em π = 1.0%. Tempo: 2.7 s no total (pymc: 1.32 s; motor cruzado: 0.00 s).

## Limitações desta execução

Parâmetros provisórios (confirmar: true) em: SOD1, C9orf72, TARDBP, FUS. Independência entre lóci; sem fatores modificadores; penetrância populacional de coortes europeias/norte-americanas; dados sintéticos.

## Tabelas

**Tabela 1 — Variantes aprovadas no filtro de qualidade e sua anotação, por genitor**

| amostra | gene | cromossomo | posicao | ref | alt | id | tipo | dosagem | repeticoes | classe | clnsig | estrelas | nome_curto | heranca | fonte_anotacao |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MAE | TARDBP | 1 | 11020000 | G | A |  | snv | 0 |  | nao_anotada |  |  |  |  |  |
| MAE | TARDBP | 1 | 11020000 | G | T |  | snv | 1 |  | nao_anotada |  |  |  |  |  |
| MAE | FUS | 16 | 31185000 | A | G |  | snv | 1 |  | nao_anotada |  |  |  |  |  |
| MAE | SOD1 | 21 | 31659509 | G | T | rs17883296 | snv | 1 |  | benigna | Likely_benign | 1 | rs17883296 |  | tabela_curada:posicao_alelos |
| MAE | SOD1 | 21 | 31659783 | C | T | rs121912442 | snv | 0 |  | risco | Pathogenic | 2 | A4V (p.A5V) | dominante | tabela_curada:posicao_alelos |
| PAI | TARDBP | 1 | 11020000 | G | A |  | snv | 0 |  | nao_anotada |  |  |  |  |  |
| PAI | TARDBP | 1 | 11020000 | G | T |  | snv | 1 |  | nao_anotada |  |  |  |  |  |
| PAI | FUS | 16 | 31185000 | A | G |  | snv | 1 |  | nao_anotada |  |  |  |  |  |
| PAI | SOD1 | 21 | 31659509 | G | T | rs17883296 | snv | 1 |  | benigna | Likely_benign | 1 | rs17883296 |  | tabela_curada:posicao_alelos |
| PAI | SOD1 | 21 | 31659783 | C | T | rs121912442 | snv | 1 |  | risco | Pathogenic | 2 | A4V (p.A5V) | dominante | tabela_curada:posicao_alelos |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

Registros lidos/aprovados: mãe 7/5, pai 7/5. Reprovações: mãe {'fora_das_regioes': 1, 'filtro_nao_pass': 1, 'dp_baixo': 1, 'gq_baixo': 1}, pai {'fora_das_regioes': 1, 'filtro_nao_pass': 1, 'dp_baixo': 1, 'gq_baixo': 1}.


**Tabela 1b — Vetor genotípico parental: dosagem alélica (0/1/2) por lócus de risco e P(portador) exata**

| gene | variante | rs | tipo | heranca | dosagem_mae | dosagem_pai | repeticoes_mae | repeticoes_pai | clnsig | estrelas | p_portador_exato | observacao |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 | A4V (p.A5V) | rs121912442 | snv | dominante | 0 | 1 |  |  | Pathogenic | 2 | 0.5 |  |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 2 — Aderência teórica: probabilidades exatas vs Monte Carlo (PyMC e NumPy), erro padrão e qui-quadrado do genótipo do descendente**

| variante | n | p_portador_exato | p_portador_pymc | p_portador_numpy | ep_portador | desvio_portador_pymc_em_ep | desvio_portador_numpy_em_ep | p_manifesta_exato | p_manifesta_pymc | p_manifesta_numpy | ep_manifesta | desvio_manifesta_pymc_em_ep | desvio_manifesta_numpy_em_ep | qui2_genotipo_pymc | valor_p_genotipo_pymc | qui2_genotipo_numpy | valor_p_genotipo_numpy | idade_mediana_exata | idade_mediana_pymc | idade_mediana_numpy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 A4V (p.A5V) | 10000 | 0.5 | 0.4954 | 0.4923 | 0.005 | 0.92 | 1.5402 | 0.2694 | 0.2641 | 0.2669 | 0.0044 | 1.1939 | 0.5568 | 0.8464 | 0.3576 | 2.3716 | 0.1236 | 50.2576 | 50.5814 | 50.5744 |
| qualquer lócus | 10000 | 0.5 | 0.4954 | 0.4923 |  |  |  | 0.2694 | 0.2641 | 0.2669 | 0.0044 | 1.1939 | 0.5568 |  |  |  |  |  | 50.5814 | 50.5744 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 3 — Probabilidade de transmissão (portador), penetrância e risco vitalício de manifestação por lócus e combinado, com intervalo de credibilidade de 95% (incerteza da penetrância) e idade de início**

| gene | variante | heranca | dosagem_mae | dosagem_pai | p_portador_exato | p_portador_mc | penetrancia_media | penetrancia_q025 | penetrancia_q975 | p_manifesta_exato | p_manifesta_mc | p_manifesta_q025 | p_manifesta_q975 | idade_mediana_exata | idade_mediana_mc | idade_p10_mc | idade_p90_mc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 | SOD1 A4V (p.A5V) | dominante | 0 | 1 | 0.5 | 0.4954 | 0.5387 | 0.3267 | 0.7436 | 0.2694 | 0.2641 | 0.1633 | 0.3718 | 50.2576 | 50.5814 | 33.8583 | 65.1364 |
| — | qualquer lócus | independência |  |  | 0.5 | 0.4954 |  |  |  | 0.2694 | 0.2641 | 0.1633 | 0.3718 |  | 50.5814 |  |  |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 4 — Risco condicional à idade atual sem sintomas: P(portador | assintomático), risco nos próximos 10 e 20 anos e risco vitalício residual, com banda de 95%**

| unidade | idade_atual | p_portador_condicional | risco_10_anos | risco_10_anos_q025 | risco_10_anos_q975 | risco_20_anos | risco_20_anos_q025 | risco_20_anos_q975 | risco_vitalicio | risco_vitalicio_q025 | risco_vitalicio_q975 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 A4V (p.A5V) | 0 | 0.5 | 9.17e-05 | 5.62e-05 | 0.0001 | 0.0024 | 0.0015 | 0.0033 | 0.2694 | 0.1649 | 0.3727 |
| SOD1 A4V (p.A5V) | 20 | 0.4988 | 0.0135 | 0.0083 | 0.0187 | 0.0544 | 0.0333 | 0.0753 | 0.2676 | 0.1637 | 0.3706 |
| SOD1 A4V (p.A5V) | 30 | 0.4919 | 0.0414 | 0.0252 | 0.0577 | 0.1184 | 0.0721 | 0.1649 | 0.2576 | 0.1567 | 0.3586 |
| SOD1 A4V (p.A5V) | 40 | 0.47 | 0.0803 | 0.0481 | 0.1138 | 0.1678 | 0.1004 | 0.2376 | 0.2255 | 0.1349 | 0.3193 |
| SOD1 A4V (p.A5V) | 50 | 0.4237 | 0.0951 | 0.055 | 0.1398 | 0.1465 | 0.0847 | 0.2153 | 0.1578 | 0.0912 | 0.2319 |
| SOD1 A4V (p.A5V) | 60 | 0.3631 | 0.0568 | 0.0314 | 0.0878 | 0.0686 | 0.038 | 0.1061 | 0.0693 | 0.0384 | 0.1072 |
| SOD1 A4V (p.A5V) | 70 | 0.3248 | 0.0126 | 0.0068 | 0.0201 | 0.0133 | 0.0072 | 0.0212 | 0.0133 | 0.0072 | 0.0212 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 10 — Sobrevivência (assintomático) estimada por Kaplan-Meier na coorte simulada, com IC 95% (Greenwood); mediana não atingida quando o risco vitalício é inferior a 50%**

| unidade | n | eventos | risco_vitalicio_km | S(40) | IC95 S(40) | S(50) | IC95 S(50) | S(60) | IC95 S(60) | S(70) | IC95 S(70) | S(80) | IC95 S(80) | mediana_sobrevivencia | idade_90pct_do_risco |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 A4V (p.A5V) | 10000 | 2641 | 0.2641 | 0.9465 | 0.942–0.951 | 0.8718 | 0.865–0.878 | 0.7915 | 0.783–0.799 | 0.7469 | 0.738–0.755 | 0.7362 | 0.727–0.745 | não atingida | 65.1 |
| qualquer lócus | 10000 | 2641 | 0.2641 | 0.9465 | 0.942–0.951 | 0.8718 | 0.865–0.878 | 0.7915 | 0.783–0.799 | 0.7469 | 0.738–0.755 | 0.7362 | 0.727–0.745 | não atingida | 65.1 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 7 — Recuperação dos parâmetros de entrada (π, λ, ρ) pelo ajustador de cura mista da Lifelines na coorte simulada de portadores**

| variante | n_portadores | eventos | pi_entrada | lambda_entrada | rho_entrada | delta_sexo | pi_lifelines | lambda_lifelines | rho_lifelines | erro_rel_pi | erro_rel_lambda | erro_rel_rho | weibull_lambda_manifestantes | weibull_rho_manifestantes | mediana_weibull_manifestantes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 A4V (p.A5V) | 4954 | 2641 | 0.5387 | 54.3171 | 4.7185 | 0 | 0.5331 | 54.6245 | 4.7693 | 0.0104 | 0.0057 | 0.0108 | 54.6233 | 4.7705 | 50.5838 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 4b — Risco condicional não paramétrico (Kaplan-Meier) para um descendente assintomático aos 30 anos**

| unidade | idade_atual | risco_10_anos_km | risco_20_anos_km | risco_vitalicio_km |
|---|---|---|---|---|
| SOD1 A4V (p.A5V) | 30 | 0.0387 | 0.1146 | 0.2526 |
| qualquer lócus | 30 | 0.0387 | 0.1146 | 0.2526 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


## Figuras

![Figura 1 — Rede Bayesiana (DAG) do núcleo estocástico](figuras/figura_01_dag.png)

*Figura 1 — Rede Bayesiana (DAG) do núcleo estocástico. Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

![Figura 4 — Risco acumulado de manifestação F(t) e sobrevivência S(t) do descendente, com banda de credibilidade de 95% e Kaplan-Meier da coorte simulada](figuras/figura_04_risco_temporal.png)

*Figura 4 — Risco acumulado de manifestação F(t) e sobrevivência S(t) do descendente, com banda de credibilidade de 95% e Kaplan-Meier da coorte simulada. Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

![Figura 6 — Aderência teórica: probabilidades exatas vs Monte Carlo (PyMC e NumPy), com erro padrão](figuras/figura_06_aderencia.png)

*Figura 6 — Aderência teórica: probabilidades exatas vs Monte Carlo (PyMC e NumPy), com erro padrão. Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

![Figura 8 — Função de risco instantâneo h(t) por lócus; faixa sombreada = pico de incidência 60–75 anos (Feldman et al., 2022)](figuras/figura_08_hazard.png)

*Figura 8 — Função de risco instantâneo h(t) por lócus; faixa sombreada = pico de incidência 60–75 anos (Feldman et al., 2022). Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

![Figura 5 — Distribuição simulada da idade de início entre os descendentes que manifestam, por lócus](figuras/figura_05_idade_inicio.png)

*Figura 5 — Distribuição simulada da idade de início entre os descendentes que manifestam, por lócus. Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*
