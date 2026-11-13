# Avaliação do artefato (TCC 4.5)

> AVISO: instrumento experimental de apoio à decisão no aconselhamento genético preditivo da ELA, construído com dados sintéticos e parâmetros populacionais da literatura. Não constitui diagnóstico, não substitui o julgamento clínico e não deve ser usado isoladamente em decisões sobre pacientes.

## Configuração

Cenários [1, 2, 3, 5]; N ∈ [1000, 10000, 100000]; 30 repetições por N; seed inicial 1000; sexo do descendente F; coerência e sensibilidade com N = 10.000. Base de anotação: clinvar_base_consolidada. Cenários sem lócus de risco nesta base (pulados): [4].

## Leitura

Razão DP/EP média = 1.03. Idade do pico de h(t) do risco combinado por cenário: cenário 1: 53.5 anos; cenário 2: 62.0 anos; cenário 3: 56.5 anos; cenário 5: 60.5 anos; 2 de 4 dentro da faixa de incidência populacional 60–75 anos (FELDMAN et al., 2022), que é referência e não critério de aprovação: variantes de início precoce (SOD1 p.Ala5Val, FUS) têm pico antes dela. Tempo médio PyMC para N = 100.000: 56.03 s; NumPy: 0.022 s.

## Tabelas

**Tabela 5 — Estabilidade numérica: média e desvio padrão de P(manifestação) e da idade mediana entre 30 execuções com sementes distintas, por N, vs erro padrão teórico √(p(1−p)/N)**

| cenario | motor | n | repeticoes | p_manifesta_qualquer_exato | p_manifesta_qualquer_media | p_manifesta_qualquer_dp | ep_teorico | razao_dp_ep | idade_mediana_media | idade_mediana_dp | tempo_medio_s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cenário 1 | numpy | 1000 | 30 | 0.2694 | 0.2688 | 0.0132 | 0.014 | 0.9394 | 50.7188 | 0.7763 | 0.0002 |
| cenário 1 | numpy | 10000 | 30 | 0.2694 | 0.2688 | 0.0043 | 0.0044 | 0.9759 | 50.8855 | 0.2773 | 0.0007 |
| cenário 1 | numpy | 100000 | 30 | 0.2694 | 0.2694 | 0.0016 | 0.0014 | 1.1382 | 50.8751 | 0.0768 | 0.0069 |
| cenário 2 | numpy | 1000 | 30 | 0.1664 | 0.1663 | 0.0115 | 0.0118 | 0.9738 | 59.3742 | 0.8932 | 0.0003 |
| cenário 2 | numpy | 10000 | 30 | 0.1664 | 0.1651 | 0.0047 | 0.0037 | 1.2662 | 59.3289 | 0.3366 | 0.0021 |
| cenário 2 | numpy | 100000 | 30 | 0.1664 | 0.1663 | 0.0013 | 0.0012 | 1.0714 | 59.3147 | 0.1092 | 0.0116 |
| cenário 3 | numpy | 1000 | 30 | 0.3909 | 0.3887 | 0.0172 | 0.0154 | 1.1134 | 53.1774 | 0.6983 | 0.0009 |
| cenário 3 | numpy | 10000 | 30 | 0.3909 | 0.3912 | 0.0046 | 0.0049 | 0.9357 | 53.1212 | 0.2959 | 0.0038 |
| cenário 3 | numpy | 100000 | 30 | 0.3909 | 0.3909 | 0.0015 | 0.0015 | 0.9757 | 53.063 | 0.0652 | 0.0383 |
| cenário 5 | numpy | 1000 | 30 | 0.2691 | 0.2676 | 0.0125 | 0.014 | 0.892 | 55.2399 | 1.2058 | 0.0005 |
| cenário 5 | numpy | 10000 | 30 | 0.2691 | 0.2684 | 0.0049 | 0.0044 | 1.1001 | 55.3616 | 0.4593 | 0.0019 |
| cenário 5 | numpy | 100000 | 30 | 0.2691 | 0.2694 | 0.0014 | 0.0014 | 1.0328 | 55.3762 | 0.1284 | 0.0339 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

DP/EP próximo de 1 indica que a variabilidade entre execuções é a esperada para o Monte Carlo; o DP cai por ≈√10 a cada década de N.


**Tabela 6 — Calibração das priors Beta de penetrância e das distribuições de idade de início a partir da literatura (docs/02, §2)**

| gene | heranca | penetrancia_publicada | ic95_publicado | alpha | beta | media_beta | mediana_beta | ic95_beta | distribuicao_inicio | metodo_inicio | parametros_inicio | mediana_inicio_anos | rss_escolhida | rss_alternativa | delta_sexo | erro_ic_beta | valor_provisorio | citacao_penetrancia | citacao_inicio |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOD1 | dominante | 0.54 | 0.327–0.886 | 11.026 | 9.441 | 0.539 | 0.54 | 0.327–0.744 | weibull | momentos | k=5.46, lam=54.40 | 50.9 |  |  | M +0.0 / F +0.0 | 0.142 | não | DOUGLAS; BARALLE, 2024, p. 295, Tabela 1 | BERDYŃSKI et al., 2022, Tabela 1: idade de início dos 64 portadores de mutação no SOD1 (média 50,2 ± 10,6 anos; faixa 21–75). Weibull resolvida pelos momentos; a mediana implicada (50,9) reproduz a mediana publicada (51,0), que não entrou no ajuste. Corroboram McFARLANE et al., 2025 (mediana 54,19; n = 149) e OPIE-MARTIN et al., 2022 (média 48,9 ± 12,8; n = 1.383). Curva por gene, não por variante: a p.Ala5Val tem início mais precoce (RICHARD et al., 2026) |
| C9orf72 | dominante | 0.33 | 0.209–0.532 | 15.086 | 30.257 | 0.333 | 0.33 | 0.205–0.475 | weibull | pontos | k=6.83, lam=61.52 | 58.3 | 0.0011 | 0.0016 | M -1.0 / F +1.0 | 0.057 | sim | DOUGLAS; BARALLE, 2024, p. 295, Tabela 1 | MURPHY et al., 2017: 35, 58 e 80 anos vêm do resumo (0%, 50%, quase completa); 45 e 70 anos são leituras aproximadas da curva, a digitalizar da figura. A mediana ajustada (58,3) é compatível com McFARLANE et al., 2025 (59,58), GRASSANO et al., 2022, Figura 1 (62,9) e YAMASHITA; ANDO, 2015, Tabela 1 (média 57) |
| TARDBP | dominante | 0.38 | 0.211–0.698 | 9.896 | 15.933 | 0.383 | 0.38 | 0.210–0.574 | weibull | quantis | k=5.57, lam=62.26 | 58.3 |  |  | M +0.0 / F +0.0 | 0.124 | sim | DOUGLAS; BARALLE, 2024, p. 295, Tabela 1 | McFARLANE et al., 2025 (PRECISION-ALS): mediana da idade de início de 58,30 anos e IQR de 16,23 entre 64 portadores de variante no TARDBP. Weibull resolvida pelo casamento de quantis. Corroboram YAMASHITA; ANDO, 2015, Tabela 1 (média 54; faixa 20–77) e GRASSANO et al., 2022, Figura 1 (mediana 66,6, em coorte de perfil etário mais alto). A CONFERIR: mediana e IQR na Figura 2 do artigo antes da versão final |
| FUS | dominante | 0.19 | 0.130–0.284 | 23.078 | 97.174 | 0.192 | 0.19 | 0.127–0.267 | weibull | pontos | k=2.31, lam=54.75 | 46.7 | 0.0009 | 0.0027 | M +0.0 / F +0.0 | 0.017 | não | DOUGLAS; BARALLE, 2024, p. 295, Tabela 1 | GRASSANO et al., 2022, Figura 1 (distribuição acumulada da idade de início): mediana 48,00 anos, primeiro quartil 31,0 e terceiro quartil 62,0 entre os portadores de variante no FUS. Quartis publicados, usados sem derivação. Limitação: a distribuição é bimodal, com picos entre 30–40 e entre 60–70 anos (McFARLANE et al., 2025), e uma Weibull única a descreve de forma aproximada |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

valor_provisorio = sim: parâmetro marcado com confirmar: true no YAML, a validar pela autora.


**Tabela 7 — Coerência das curvas: F(∞) exato vs Kaplan-Meier, medianas de início (exata vs Weibull da Lifelines), parâmetros recuperados pelo modelo de cura mista e idade do pico de h(t) por lócus e para o risco combinado**

| cenario | variante | F_inf_exato | risco_vitalicio_km | idade_mediana_exata | idade_mediana_weibull_lifelines | pi_recuperado | lambda_recuperado | rho_recuperado | idade_pico_hazard | pico_combinado_na_faixa_60_75 | idade_90pct_do_risco | mediana_sobrevivencia |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cenário 1 | SOD1 p.Ala5Val | 0.2694 | 0.263 | 50.8673 | 50.6533 | 0.5262 | 54.092 | 5.58 | 53.5 |  | 62.9 | não atingida |
| cenário 1 | qualquer lócus | 0.2694 | 0.263 |  |  |  |  |  | 53.5 | não | 62.9 | não atingida |
| cenário 2 | C9orf72 expansão GGGGCC | 0.1664 | 0.1676 | 59.3045 | 59.173 | 0.3376 | 62.2726 | 7.1786 | 62 |  | 70.6 | não atingida |
| cenário 2 | qualquer lócus | 0.1664 | 0.1676 |  |  |  |  |  | 62 | sim | 70.6 | não atingida |
| cenário 3 | SOD1 p.Ala5Val | 0.2694 | 0.2696 | 50.8673 | 50.9787 | 0.5394 | 54.5138 | 5.4667 | 53.5 |  | 63.7 | não atingida |
| cenário 3 | C9orf72 expansão GGGGCC | 0.1664 | 0.1662 | 59.3045 | 58.8705 | 0.3347 | 62.1069 | 6.8485 | 62 |  | 70.1 | não atingida |
| cenário 3 | qualquer lócus | 0.3909 | 0.3903 |  |  |  |  |  | 56.5 | não | 66.2 | não atingida |
| cenário 5 | TARDBP p.Met337Val | 0.1916 | 0.1954 | 58.3 | 57.9132 | 0.3912 | 62.0048 | 5.3835 | 61 |  | 72.8 | não atingida |
| cenário 5 | FUS p.Arg521Cys | 0.096 | 0.0925 | 46.7083 | 43.2531 | 0.1926 | 52.3505 | 2.2684 | 44 |  | 72 | não atingida |
| cenário 5 | qualquer lócus | 0.2691 | 0.2696 |  |  |  |  |  | 60.5 | sim | 72.5 | não atingida |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

A faixa de incidência populacional 60–75 anos (FELDMAN et al., 2022) é comparada só com o pico do risco combinado (linha 'qualquer lócus'); o pico de cada variante é propriedade da sua distribuição de início e não é critério de aprovação.


**Tabela 8 — Tempo de processamento por motor (PyMC e NumPy) e por N, em segundos (média de execuções sucessivas)**

| cenario | motor | n | repeticoes | tempo_medio_s | tempo_max_s | sorteios_por_segundo |
|---|---|---|---|---|---|---|
| cenário 1 | numpy | 1000 | 5 | 0.0002 | 0.0003 | 5.303.352 |
| cenário 1 | pymc | 1000 | 3 | 0.3039 | 0.3261 | 3.291 |
| cenário 1 | numpy | 10000 | 5 | 0.0011 | 0.0013 | 8.747.835 |
| cenário 1 | pymc | 10000 | 3 | 2.2621 | 2.3438 | 4.421 |
| cenário 1 | numpy | 100000 | 5 | 0.0068 | 0.0072 | 14.753.441 |
| cenário 1 | pymc | 100000 | 3 | 25.5465 | 32.7184 | 3.914 |
| cenário 2 | numpy | 1000 | 5 | 0.0007 | 0.0009 | 1.427.307 |
| cenário 2 | pymc | 1000 | 3 | 0.6122 | 0.687 | 1.633 |
| cenário 2 | numpy | 10000 | 5 | 0.0022 | 0.0034 | 4.522.636 |
| cenário 2 | pymc | 10000 | 3 | 4.9528 | 5.1357 | 2.019 |
| cenário 2 | numpy | 100000 | 5 | 0.0115 | 0.0125 | 8.684.551 |
| cenário 2 | pymc | 100000 | 3 | 55.53 | 57.8691 | 1.801 |
| cenário 3 | numpy | 1000 | 5 | 0.0005 | 0.0006 | 1.931.845 |
| cenário 3 | pymc | 1000 | 3 | 0.932 | 0.9742 | 1.073 |
| cenário 3 | numpy | 10000 | 5 | 0.0031 | 0.0043 | 3.257.775 |
| cenário 3 | pymc | 10000 | 3 | 8.1619 | 8.6284 | 1.225 |
| cenário 3 | numpy | 100000 | 5 | 0.0338 | 0.0411 | 2.955.418 |
| cenário 3 | pymc | 100000 | 3 | 75.3936 | 83.2216 | 1.326 |
| cenário 5 | numpy | 1000 | 5 | 0.0006 | 0.0008 | 1.704.565 |
| cenário 5 | pymc | 1000 | 3 | 0.8037 | 0.8214 | 1.244 |
| cenário 5 | numpy | 10000 | 5 | 0.0029 | 0.0037 | 3.417.845 |
| cenário 5 | pymc | 10000 | 3 | 8.4612 | 10.5301 | 1.182 |
| cenário 5 | numpy | 100000 | 5 | 0.035 | 0.0402 | 2.855.213 |
| cenário 5 | pymc | 100000 | 3 | 67.662 | 71.1916 | 1.478 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


**Tabela 9 — Análise de sensibilidade: risco vitalício e idade mediana sob a calibração pela literatura, sob os parâmetros do exemplo do orientador e sob penetrância de coorte familiar para o C9orf72**

| cenario | conjunto_de_parametros | variante | penetrancia_media | p_manifesta_exato | p_manifesta_mc | idade_mediana_exata | idade_mediana_mc |
|---|---|---|---|---|---|---|---|
| cenário 1 | literatura (Douglas & Baralle 2024; Murphy 2017) | SOD1 p.Ala5Val | 0.5387 | 0.2694 | 0.2724 | 50.8673 | 50.7378 |
| cenário 1 | literatura (Douglas & Baralle 2024; Murphy 2017) | qualquer lócus |  | 0.2694 | 0.2724 |  | 50.7378 |
| cenário 1 | exemplo do orientador (penetrance_max e Weibull fixos) | SOD1 p.Ala5Val | 0.9 | 0.45 | 0.4474 | 46.0891 | 46.2669 |
| cenário 1 | exemplo do orientador (penetrance_max e Weibull fixos) | qualquer lócus |  | 0.45 | 0.4474 |  | 46.2669 |
| cenário 2 | literatura (Douglas & Baralle 2024; Murphy 2017) | C9orf72 expansão GGGGCC | 0.3327 | 0.1664 | 0.1749 | 59.3045 | 58.808 |
| cenário 2 | literatura (Douglas & Baralle 2024; Murphy 2017) | qualquer lócus |  | 0.1664 | 0.1749 |  | 58.808 |
| cenário 2 | exemplo do orientador (penetrance_max e Weibull fixos) | C9orf72 expansão GGGGCC | 0.6 | 0.3 | 0.3002 | 58.6178 | 58.6868 |
| cenário 2 | exemplo do orientador (penetrance_max e Weibull fixos) | qualquer lócus |  | 0.3 | 0.3002 |  | 58.6868 |
| cenário 2 | C9orf72 com penetrância de coorte familiar (Murphy 2017) | C9orf72 expansão GGGGCC | 0.9 | 0.45 | 0.4457 | 59.3045 | 59.4291 |
| cenário 2 | C9orf72 com penetrância de coorte familiar (Murphy 2017) | qualquer lócus |  | 0.45 | 0.4457 |  | 59.4291 |
| cenário 3 | literatura (Douglas & Baralle 2024; Murphy 2017) | SOD1 p.Ala5Val | 0.5387 | 0.2694 | 0.2739 | 50.8673 | 50.8692 |
| cenário 3 | literatura (Douglas & Baralle 2024; Murphy 2017) | C9orf72 expansão GGGGCC | 0.3327 | 0.1664 | 0.1717 | 59.3045 | 58.889 |
| cenário 3 | literatura (Douglas & Baralle 2024; Murphy 2017) | qualquer lócus |  | 0.3909 | 0.3983 |  | 52.9355 |
| cenário 3 | exemplo do orientador (penetrance_max e Weibull fixos) | SOD1 p.Ala5Val | 0.9 | 0.45 | 0.4526 | 46.0891 | 45.9328 |
| cenário 3 | exemplo do orientador (penetrance_max e Weibull fixos) | C9orf72 expansão GGGGCC | 0.6 | 0.3 | 0.2994 | 58.6178 | 57.9244 |
| cenário 3 | exemplo do orientador (penetrance_max e Weibull fixos) | qualquer lócus |  | 0.615 | 0.6131 |  | 47.8712 |
| cenário 3 | C9orf72 com penetrância de coorte familiar (Murphy 2017) | SOD1 p.Ala5Val | 0.5387 | 0.2694 | 0.2719 | 50.8673 | 51.0792 |
| cenário 3 | C9orf72 com penetrância de coorte familiar (Murphy 2017) | C9orf72 expansão GGGGCC | 0.9 | 0.45 | 0.4528 | 59.3045 | 59.152 |
| cenário 3 | C9orf72 com penetrância de coorte familiar (Murphy 2017) | qualquer lócus |  | 0.5981 | 0.6021 |  | 54.9001 |
| cenário 5 | literatura (Douglas & Baralle 2024; Murphy 2017) | TARDBP p.Met337Val | 0.3831 | 0.1916 | 0.1997 | 58.3 | 58.3094 |
| cenário 5 | literatura (Douglas & Baralle 2024; Murphy 2017) | FUS p.Arg521Cys | 0.1919 | 0.096 | 0.0951 | 46.7083 | 46.9865 |
| cenário 5 | literatura (Douglas & Baralle 2024; Murphy 2017) | qualquer lócus |  | 0.2691 | 0.2775 |  | 55.3146 |
| cenário 5 | exemplo do orientador (penetrance_max e Weibull fixos) | TARDBP p.Met337Val | 0.8 | 0.4 | 0.4058 | 52.2368 | 52.1617 |
| cenário 5 | exemplo do orientador (penetrance_max e Weibull fixos) | FUS p.Arg521Cys | 0.45 | 0.225 | 0.2257 | 39.9544 | 39.5133 |
| cenário 5 | exemplo do orientador (penetrance_max e Weibull fixos) | qualquer lócus |  | 0.535 | 0.5355 |  | 45.5094 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*


## Figuras

![Figura 2 — Priors Beta de penetrância vitalícia por gene, calibradas ao ponto e ao IC 95% de Douglas & Baralle (2024)](figuras\figura_02_priors.png)

*Figura 2 — Priors Beta de penetrância vitalícia por gene, calibradas ao ponto e ao IC 95% de Douglas & Baralle (2024). Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

![Figura 3 — Distribuição acumulada da idade de início G(t) ajustada aos pontos da literatura, por gene](figuras\figura_03_curvas_inicio.png)

*Figura 3 — Distribuição acumulada da idade de início G(t) ajustada aos pontos da literatura, por gene. Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

![Figura 7 — Estabilidade numérica: desvio padrão entre execuções vs N (escala log-log) e erro padrão teórico √(p(1−p)/N)](figuras\figura_07_estabilidade.png)

*Figura 7 — Estabilidade numérica: desvio padrão entre execuções vs N (escala log-log) e erro padrão teórico √(p(1−p)/N). Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*
