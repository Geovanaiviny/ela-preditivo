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
