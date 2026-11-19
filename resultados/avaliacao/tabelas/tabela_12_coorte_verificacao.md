**Tabela 12 — Coorte sintética de verificação: 200 mundos, 10 pessoas sorteadas por estrato e mundo (cenário × sexo × idade atual de 0 a 70 anos) e desfecho verdadeiro conhecido, por verdade e cenário**

| verdade | cenario | estratos | pessoas_sorteadas | pessoas | mundos | eventos_ate_o_horizonte | fracao_que_manifesta | risco_previsto_min | risco_previsto_max |
|---|---|---|---|---|---|---|---|---|---|
| verdade = modelo | cenário 1 | 30 | 60000 | 55342 | 200 | 11349 | 0.2051 | 0.0069 | 0.2694 |
| verdade = modelo | cenário 2 | 30 | 60000 | 57867 | 200 | 8163 | 0.1411 | 0.0137 | 0.1664 |
| verdade = modelo | cenário 3 | 30 | 60000 | 53654 | 200 | 16966 | 0.3162 | 0.0205 | 0.3909 |
| verdade = modelo | cenário 4 | 30 | 60000 | 57671 | 200 | 5645 | 0.0979 | 0.0029 | 0.1347 |
| verdade = modelo | cenário 5 | 30 | 60000 | 55782 | 200 | 11817 | 0.2118 | 0.0464 | 0.2657 |
| verdade = modelo | cenário de parentes 1 | 30 | 60000 | 45690 | 200 | 3088 | 0.0676 | 0.0019 | 0.0935 |
| verdade alternativa: parâmetros do exemplo do orientador | cenário 1 | 30 | 60000 | 50433 | 200 | 17354 | 0.3441 | 0.0069 | 0.2694 |
| verdade alternativa: parâmetros do exemplo do orientador | cenário 2 | 30 | 60000 | 56110 | 200 | 14127 | 0.2518 | 0.0137 | 0.1664 |
| verdade alternativa: parâmetros do exemplo do orientador | cenário 3 | 30 | 60000 | 47858 | 200 | 24883 | 0.5199 | 0.0205 | 0.3909 |
| verdade alternativa: parâmetros do exemplo do orientador | cenário 4 | 30 | 60000 | 55274 | 200 | 8835 | 0.1598 | 0.0029 | 0.1347 |
| verdade alternativa: parâmetros do exemplo do orientador | cenário 5 | 30 | 60000 | 48734 | 200 | 20698 | 0.4247 | 0.0464 | 0.2657 |
| verdade alternativa: parâmetros do exemplo do orientador | cenário de parentes 1 | 30 | 60000 | 34641 | 200 | 1627 | 0.047 | 0.0019 | 0.0935 |
| verdade alternativa: penetrância log-normal truncada em 1 | cenário 1 | 30 | 60000 | 54974 | 200 | 12171 | 0.2214 | 0.0069 | 0.2694 |
| verdade alternativa: penetrância log-normal truncada em 1 | cenário 2 | 30 | 60000 | 57940 | 200 | 8271 | 0.1428 | 0.0137 | 0.1664 |
| verdade alternativa: penetrância log-normal truncada em 1 | cenário 3 | 30 | 60000 | 53231 | 200 | 17877 | 0.3358 | 0.0205 | 0.3909 |
| verdade alternativa: penetrância log-normal truncada em 1 | cenário 4 | 30 | 60000 | 57427 | 200 | 6128 | 0.1067 | 0.0029 | 0.1347 |
| verdade alternativa: penetrância log-normal truncada em 1 | cenário 5 | 30 | 60000 | 55769 | 200 | 12164 | 0.2181 | 0.0464 | 0.2657 |
| verdade alternativa: penetrância log-normal truncada em 1 | cenário de parentes 1 | 30 | 60000 | 44489 | 200 | 3117 | 0.0701 | 0.0019 | 0.0935 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

Verificação, não validação: Com dados sintéticos gerados pelo próprio modelo, estas métricas medem verificação (a implementação reproduz o modelo especificado), não validação contra pacientes reais. Para não ficar só circular, cada métrica é calculada em dois mundos: verdade = modelo, em que o desfecho é sorteado com os mesmos parâmetros da previsão, e verdade alternativa, em que o desfecho é sorteado com parâmetros diferentes e as métricas mostram como degradam quando o modelo está errado. Entram na coorte as pessoas que chegam sem sintomas à idade atual (e, com genitor inferido, as de famílias compatíveis com a evidência), de modo que cada mundo pesa pelo quanto é compatível com o que se observa. Semente própria da coorte: 105729 (independente da semente das previsões, 1000).
