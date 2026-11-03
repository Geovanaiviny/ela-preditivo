# Avaliação do artefato (TCC 4.5)

> AVISO: instrumento experimental de apoio à decisão no aconselhamento genético preditivo da ELA, construído com dados sintéticos e parâmetros populacionais da literatura. Não constitui diagnóstico, não substitui o julgamento clínico e não deve ser usado isoladamente em decisões sobre pacientes.

## Configuração

Cenários [1, 2, 3, 5]; N ∈ [1000, 10000, 100000]; 30 repetições por N; seed inicial 1000; sexo do descendente F; coerência e sensibilidade com N = 10.000. Base de anotação: clinvar_base_consolidada. Cenários sem lócus de risco nesta base (pulados): [4].

## Leitura

Razão DP/EP média = 1.03. Picos de risco entre 60 e 75 anos: 2 de 6 lóci. Tempo médio PyMC para N = 100.000: 19.68 s; NumPy: 0.009 s.

## Tabelas

**Tabela 5 — Estabilidade numérica: média e desvio padrão de P(manifestação) e da idade mediana entre 30 execuções com sementes distintas, por N, vs erro padrão teórico √(p(1−p)/N)**

| cenario | motor | n | repeticoes | p_manifesta_qualquer_exato | p_manifesta_qualquer_media | p_manifesta_qualquer_dp | ep_teorico | razao_dp_ep | idade_mediana_media | idade_mediana_dp | tempo_medio_s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cenário 1 | numpy | 1000 | 30 | 0.2694 | 0.2688 | 0.0132 | 0.014 | 0.9394 | 50.0888 | 0.8875 | 0.0001 |
| cenário 1 | numpy | 10000 | 30 | 0.2694 | 0.2688 | 0.0043 | 0.0044 | 0.9759 | 50.2786 | 0.3173 | 0.0006 |
| cenário 1 | numpy | 100000 | 30 | 0.2694 | 0.2694 | 0.0016 | 0.0014 | 1.1382 | 50.2666 | 0.0879 | 0.0054 |
| cenário 2 | numpy | 1000 | 30 | 0.1664 | 0.1663 | 0.0115 | 0.0118 | 0.9738 | 59.3742 | 0.8932 | 0.0001 |
| cenário 2 | numpy | 10000 | 30 | 0.1664 | 0.1651 | 0.0047 | 0.0037 | 1.2662 | 59.3289 | 0.3366 | 0.0005 |
| cenário 2 | numpy | 100000 | 30 | 0.1664 | 0.1663 | 0.0013 | 0.0012 | 1.0714 | 59.3147 | 0.1092 | 0.0049 |
| cenário 3 | numpy | 1000 | 30 | 0.3909 | 0.3887 | 0.0172 | 0.0154 | 1.1134 | 53.0049 | 0.7669 | 0.0002 |
| cenário 3 | numpy | 10000 | 30 | 0.3909 | 0.3912 | 0.0046 | 0.0049 | 0.9357 | 52.931 | 0.3188 | 0.0013 |
| cenário 3 | numpy | 100000 | 30 | 0.3909 | 0.3909 | 0.0015 | 0.0015 | 0.9757 | 52.8722 | 0.0734 | 0.0119 |
| cenário 5 | numpy | 1000 | 30 | 0.2691 | 0.2676 | 0.0125 | 0.014 | 0.892 | 50.0144 | 1.1614 | 0.0002 |
| cenário 5 | numpy | 10000 | 30 | 0.2691 | 0.2684 | 0.0049 | 0.0044 | 1.1001 | 50.1338 | 0.4375 | 0.0012 |
| cenário 5 | numpy | 100000 | 30 | 0.2691 | 0.2694 | 0.0014 | 0.0014 | 1.0328 | 50.1485 | 0.1245 | 0.0123 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

DP/EP próximo de 1 indica que a variabilidade entre execuções é a esperada para o Monte Carlo; o DP cai por ≈√10 a cada década de N.


**Tabela 6 — Calibração das priors Beta de penetrância e das distribuições de idade de início a partir da literatura (docs/02, §2)**

| gene | heranca | penetrancia_publicada | ic95_publicado | alpha | beta | media_beta | mediana_beta | ic95_beta | distribuicao_inicio | parametros_inicio | mediana_inicio_anos | rss_escolhida | rss_alternativa | delta_sexo | erro_ic_beta | valor_provisorio | citacao_penetrancia | citacao_inicio |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 | dominante | 0.54 | 0.327–0.886 | 11.026 | 9.441 | 0.539 | 0.54 | 0.327–0.744 | weibull | k=4.72, lam=54.32 | 50.3 | 0.0004 | 0.001 | M +0.0 / F +0.0 | 0.142 | sim | DOUGLAS; BARALLE, 2024, p. 294 | PLACEHOLDER: substituir pelas faixas etárias de RICHARD et al., 2026; mediana ~50 anos coerente com FELDMAN et al., 2022 |
| C9orf72 | dominante | 0.33 | 0.209–0.532 | 15.086 | 30.257 | 0.333 | 0.33 | 0.205–0.475 | weibull | k=6.83, lam=61.52 | 58.3 | 0.0011 | 0.0016 | M -1.0 / F +1.0 | 0.057 | sim | DOUGLAS; BARALLE, 2024, p. 294 | MURPHY et al., 2017: 35, 58 e 80 anos vêm do resumo (0%, 50%, quase completa); 45 e 70 anos são leituras aproximadas da curva, a digitalizar da figura |
| TARDBP | dominante | 0.38 | 0.211–0.698 | 9.896 | 15.933 | 0.383 | 0.38 | 0.210–0.574 | weibull | k=4.63, lam=58.64 | 54.2 | 0.0001 | 0.0023 | M +0.0 / F +0.0 | 0.124 | sim | DOUGLAS; BARALLE, 2024, p. 294 | PLACEHOLDER: substituir pelas faixas etárias de RICHARD et al., 2026 |
| FUS | dominante | 0.19 | 0.130–0.284 | 23.078 | 97.174 | 0.192 | 0.19 | 0.127–0.267 | weibull | k=3.23, lam=47.97 | 42.8 | 0.0027 | 0.0125 | M +0.0 / F +0.0 | 0.017 | sim | DOUGLAS; BARALLE, 2024, p. 294 | PLACEHOLDER: substituir pelas faixas etárias de RICHARD et al., 2026; início mais precoce (FELDMAN et al., 2022) |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

valor_provisorio = sim: parâmetro marcado com confirmar: true no YAML, a validar pela autora.


**Tabela 7 — Coerência das curvas: F(∞) exato vs Kaplan-Meier, medianas de início (exata vs Weibull da Lifelines), parâmetros recuperados pelo modelo de cura mista e idade do pico de risco**

| cenario | variante | F_inf_exato | risco_vitalicio_km | idade_mediana_exata | idade_mediana_weibull_lifelines | pi_recuperado | lambda_recuperado | rho_recuperado | idade_pico_hazard | pico_em_60_75 | idade_90pct_do_risco | mediana_sobrevivencia |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cenário 1 | SOD1 p.Ala5Val | 0.2694 | 0.263 | 50.2576 | 50.0128 | 0.5262 | 53.9663 | 4.8174 | 53 | não | 64.3 | não atingida |
| cenário 2 | C9orf72 expansão GGGGCC | 0.1664 | 0.1676 | 59.3045 | 59.173 | 0.3376 | 62.2726 | 7.1786 | 62 | sim | 70.6 | não atingida |
| cenário 3 | SOD1 p.Ala5Val | 0.2694 | 0.2696 | 50.2576 | 50.3851 | 0.5394 | 54.4548 | 4.7188 | 53 | não | 65.2 | não atingida |
| cenário 3 | C9orf72 expansão GGGGCC | 0.1664 | 0.1662 | 59.3045 | 58.8705 | 0.3347 | 62.1069 | 6.8485 | 62 | sim | 70.1 | não atingida |
| cenário 5 | TARDBP p.Met337Val | 0.1916 | 0.1954 | 54.1776 | 53.745 | 0.3913 | 58.3715 | 4.4606 | 57 | não | 70.8 | não atingida |
| cenário 5 | FUS p.Arg521Cys | 0.096 | 0.0965 | 42.8269 | 41.6528 | 0.1944 | 46.8436 | 3.1271 | 43.5 | não | 60.7 | não atingida |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 8 — Tempo de processamento por motor (PyMC e NumPy) e por N, em segundos (média de execuções sucessivas)**

| cenario | motor | n | repeticoes | tempo_medio_s | tempo_max_s | sorteios_por_segundo |
|---|---|---|---|---|---|---|
| cenário 1 | numpy | 1000 | 5 | 0.0001 | 0.0003 | 6.725.538 |
| cenário 1 | pymc | 1000 | 3 | 0.1867 | 0.1929 | 5.356 |
| cenário 1 | numpy | 10000 | 5 | 0.0006 | 0.0007 | 16.611.969 |
| cenário 1 | pymc | 10000 | 3 | 1.5645 | 1.6172 | 6.392 |
| cenário 1 | numpy | 100000 | 5 | 0.0055 | 0.0058 | 18.057.698 |
| cenário 1 | pymc | 100000 | 3 | 15.0773 | 15.3761 | 6.632 |
| cenário 2 | numpy | 1000 | 5 | 0.0001 | 0.0002 | 7.438.782 |
| cenário 2 | pymc | 1000 | 3 | 0.2067 | 0.2226 | 4.837 |
| cenário 2 | numpy | 10000 | 5 | 0.0006 | 0.0007 | 18.138.556 |
| cenário 2 | pymc | 10000 | 3 | 1.7329 | 1.7869 | 5.771 |
| cenário 2 | numpy | 100000 | 5 | 0.0052 | 0.0056 | 19.235.344 |
| cenário 2 | pymc | 100000 | 3 | 16.7275 | 16.9564 | 5.978 |
| cenário 3 | numpy | 1000 | 5 | 0.0002 | 0.0003 | 4.364.674 |
| cenário 3 | pymc | 1000 | 3 | 0.2596 | 0.2787 | 3.852 |
| cenário 3 | numpy | 10000 | 5 | 0.0012 | 0.0014 | 8.054.676 |
| cenário 3 | pymc | 10000 | 3 | 2.3387 | 2.4184 | 4.276 |
| cenário 3 | numpy | 100000 | 5 | 0.0136 | 0.0147 | 7.347.855 |
| cenário 3 | pymc | 100000 | 3 | 23.4219 | 23.4806 | 4.270 |
| cenário 5 | numpy | 1000 | 5 | 0.0003 | 0.0003 | 3.934.019 |
| cenário 5 | pymc | 1000 | 3 | 0.254 | 0.26 | 3.937 |
| cenário 5 | numpy | 10000 | 5 | 0.0012 | 0.0013 | 8.480.536 |
| cenário 5 | pymc | 10000 | 3 | 2.2524 | 2.3563 | 4.440 |
| cenário 5 | numpy | 100000 | 5 | 0.012 | 0.0127 | 8.339.949 |
| cenário 5 | pymc | 100000 | 3 | 23.504 | 27.7915 | 4.255 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 9 — Análise de sensibilidade: risco vitalício e idade mediana sob a calibração pela literatura, sob os parâmetros do exemplo do orientador e sob penetrância de coorte familiar para o C9orf72**

| cenario | conjunto_de_parametros | variante | penetrancia_media | p_manifesta_exato | p_manifesta_mc | idade_mediana_exata | idade_mediana_mc |
|---|---|---|---|---|---|---|---|
| cenário 1 | literatura (Douglas & Baralle 2024; Murphy 2017) | SOD1 p.Ala5Val | 0.5387 | 0.2694 | 0.2724 | 50.2576 | 50.1095 |
| cenário 1 | literatura (Douglas & Baralle 2024; Murphy 2017) | qualquer lócus |  | 0.2694 | 0.2724 |  | 50.1095 |
| cenário 1 | exemplo do orientador (penetrance_max e Weibull fixos) | SOD1 p.Ala5Val | 0.9 | 0.45 | 0.4474 | 46.0891 | 46.2669 |
| cenário 1 | exemplo do orientador (penetrance_max e Weibull fixos) | qualquer lócus |  | 0.45 | 0.4474 |  | 46.2669 |
| cenário 2 | literatura (Douglas & Baralle 2024; Murphy 2017) | C9orf72 expansão GGGGCC | 0.3327 | 0.1664 | 0.1749 | 59.3045 | 58.808 |
| cenário 2 | literatura (Douglas & Baralle 2024; Murphy 2017) | qualquer lócus |  | 0.1664 | 0.1749 |  | 58.808 |
| cenário 2 | exemplo do orientador (penetrance_max e Weibull fixos) | C9orf72 expansão GGGGCC | 0.6 | 0.3 | 0.3002 | 58.6178 | 58.6868 |
| cenário 2 | exemplo do orientador (penetrance_max e Weibull fixos) | qualquer lócus |  | 0.3 | 0.3002 |  | 58.6868 |
| cenário 2 | C9orf72 com penetrância de coorte familiar (Murphy 2017) | C9orf72 expansão GGGGCC | 0.9 | 0.45 | 0.4457 | 59.3045 | 59.4291 |
| cenário 2 | C9orf72 com penetrância de coorte familiar (Murphy 2017) | qualquer lócus |  | 0.45 | 0.4457 |  | 59.4291 |
| cenário 3 | literatura (Douglas & Baralle 2024; Murphy 2017) | SOD1 p.Ala5Val | 0.5387 | 0.2694 | 0.2739 | 50.2576 | 50.2598 |
| cenário 3 | literatura (Douglas & Baralle 2024; Murphy 2017) | C9orf72 expansão GGGGCC | 0.3327 | 0.1664 | 0.1717 | 59.3045 | 58.889 |
| cenário 3 | literatura (Douglas & Baralle 2024; Murphy 2017) | qualquer lócus |  | 0.3909 | 0.3983 |  | 52.754 |
| cenário 3 | exemplo do orientador (penetrance_max e Weibull fixos) | SOD1 p.Ala5Val | 0.9 | 0.45 | 0.4526 | 46.0891 | 45.9328 |
| cenário 3 | exemplo do orientador (penetrance_max e Weibull fixos) | C9orf72 expansão GGGGCC | 0.6 | 0.3 | 0.2994 | 58.6178 | 57.9244 |
| cenário 3 | exemplo do orientador (penetrance_max e Weibull fixos) | qualquer lócus |  | 0.615 | 0.6131 |  | 47.8712 |
| cenário 3 | C9orf72 com penetrância de coorte familiar (Murphy 2017) | SOD1 p.Ala5Val | 0.5387 | 0.2694 | 0.2719 | 50.2576 | 50.5003 |
| cenário 3 | C9orf72 com penetrância de coorte familiar (Murphy 2017) | C9orf72 expansão GGGGCC | 0.9 | 0.45 | 0.4528 | 59.3045 | 59.152 |
| cenário 3 | C9orf72 com penetrância de coorte familiar (Murphy 2017) | qualquer lócus |  | 0.5981 | 0.6021 |  | 54.9007 |
| cenário 5 | literatura (Douglas & Baralle 2024; Murphy 2017) | TARDBP p.Met337Val | 0.3831 | 0.1916 | 0.1997 | 54.1776 | 54.1882 |
| cenário 5 | literatura (Douglas & Baralle 2024; Murphy 2017) | FUS p.Arg521Cys | 0.1919 | 0.096 | 0.0951 | 42.8269 | 43.0086 |
| cenário 5 | literatura (Douglas & Baralle 2024; Murphy 2017) | qualquer lócus |  | 0.2691 | 0.2775 |  | 50.011 |
| cenário 5 | exemplo do orientador (penetrance_max e Weibull fixos) | TARDBP p.Met337Val | 0.8 | 0.4 | 0.4058 | 52.2368 | 52.1617 |
| cenário 5 | exemplo do orientador (penetrance_max e Weibull fixos) | FUS p.Arg521Cys | 0.45 | 0.225 | 0.2257 | 39.9544 | 39.5133 |
| cenário 5 | exemplo do orientador (penetrance_max e Weibull fixos) | qualquer lócus |  | 0.535 | 0.5355 |  | 45.5094 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


## Figuras

![Figura 2 — Priors Beta de penetrância vitalícia por gene, calibradas ao ponto e ao IC 95% de Douglas & Baralle (2024)](figuras/figura_02_priors.png)

*Figura 2 — Priors Beta de penetrância vitalícia por gene, calibradas ao ponto e ao IC 95% de Douglas & Baralle (2024). Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

![Figura 3 — Distribuição acumulada da idade de início G(t) ajustada aos pontos da literatura, por gene](figuras/figura_03_curvas_inicio.png)

*Figura 3 — Distribuição acumulada da idade de início G(t) ajustada aos pontos da literatura, por gene. Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

![Figura 7 — Estabilidade numérica: desvio padrão entre execuções vs N (escala log-log) e erro padrão teórico √(p(1−p)/N)](figuras/figura_07_estabilidade.png)

*Figura 7 — Estabilidade numérica: desvio padrão entre execuções vs N (escala log-log) e erro padrão teórico √(p(1−p)/N). Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*
