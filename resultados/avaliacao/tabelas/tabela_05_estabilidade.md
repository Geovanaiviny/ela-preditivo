**Tabela 5 — Estabilidade numérica: média e desvio padrão de P(manifestação) e da idade mediana entre 30 execuções com sementes distintas, por N, vs erro padrão teórico √(p(1−p)/N)**

| cenario | motor | n | repeticoes | p_manifesta_qualquer_exato | p_manifesta_qualquer_media | p_manifesta_qualquer_dp | ep_teorico | razao_dp_ep | idade_mediana_media | idade_mediana_dp | tempo_medio_s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cenário 1 | numpy | 1000 | 30 | 0.2694 | 0.2688 | 0.0132 | 0.014 | 0.9394 | 50.7188 | 0.7763 | 0.0001 |
| cenário 1 | numpy | 10000 | 30 | 0.2694 | 0.2688 | 0.0043 | 0.0044 | 0.9759 | 50.8855 | 0.2773 | 0.0006 |
| cenário 1 | numpy | 100000 | 30 | 0.2694 | 0.2694 | 0.0016 | 0.0014 | 1.1382 | 50.8751 | 0.0768 | 0.0049 |
| cenário 2 | numpy | 1000 | 30 | 0.1664 | 0.1663 | 0.0115 | 0.0118 | 0.9738 | 59.3742 | 0.8932 | 0.0001 |
| cenário 2 | numpy | 10000 | 30 | 0.1664 | 0.1651 | 0.0047 | 0.0037 | 1.2662 | 59.3289 | 0.3366 | 0.0005 |
| cenário 2 | numpy | 100000 | 30 | 0.1664 | 0.1663 | 0.0013 | 0.0012 | 1.071 | 59.3147 | 0.1092 | 0.0046 |
| cenário 3 | numpy | 1000 | 30 | 0.3909 | 0.3887 | 0.0172 | 0.0154 | 1.1134 | 53.1774 | 0.6983 | 0.0002 |
| cenário 3 | numpy | 10000 | 30 | 0.3909 | 0.3912 | 0.0046 | 0.0049 | 0.9357 | 53.1212 | 0.2959 | 0.0012 |
| cenário 3 | numpy | 100000 | 30 | 0.3909 | 0.3909 | 0.0015 | 0.0015 | 0.9757 | 53.063 | 0.0652 | 0.0108 |
| cenário 4 | numpy | 1000 | 30 | 0.1347 | 0.1367 | 0.0101 | 0.0108 | 0.9368 | 50.9359 | 1.1433 | 0.0001 |
| cenário 4 | numpy | 10000 | 30 | 0.1347 | 0.1338 | 0.0036 | 0.0034 | 1.052 | 50.8724 | 0.417 | 0.0005 |
| cenário 4 | numpy | 100000 | 30 | 0.1347 | 0.1346 | 0.0012 | 0.0011 | 1.0941 | 50.8827 | 0.142 | 0.0045 |
| cenário 5 | numpy | 1000 | 30 | 0.2657 | 0.2649 | 0.0127 | 0.014 | 0.9077 | 55.2399 | 1.2058 | 0.0003 |
| cenário 5 | numpy | 10000 | 30 | 0.2657 | 0.265 | 0.005 | 0.0044 | 1.129 | 55.3616 | 0.4593 | 0.0011 |
| cenário 5 | numpy | 100000 | 30 | 0.2657 | 0.266 | 0.0014 | 0.0014 | 1.0265 | 55.3762 | 0.1284 | 0.0105 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

DP/EP próximo de 1 indica que a variabilidade entre execuções é a esperada para o Monte Carlo; o DP cai por ≈√10 a cada década de N.
