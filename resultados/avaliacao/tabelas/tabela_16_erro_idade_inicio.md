**Tabela 16 — Erro absoluto médio da idade de início prevista (mediana condicional à idade atual) entre quem manifesta, por gene, com o piso teórico**

| verdade | gene | n_manifestam | erro_absoluto_medio_anos | erro_padrao_anos | piso_teorico_anos | razao_erro_piso | vies_medio_anos |
|---|---|---|---|---|---|---|---|
| verdade = modelo | C9orf72 | 14739 | 6.9603 | 0.0449 | 7.0587 | 0.9861 | -0.1741 |
| verdade = modelo | FUS | 3190 | 12.6144 | 0.1665 | 12.9662 | 0.9729 | 0.9283 |
| verdade = modelo | SOD1 | 30472 | 7.3897 | 0.0332 | 7.3993 | 0.9987 | -0.1768 |
| verdade = modelo | TARDBP | 8627 | 8.3926 | 0.0707 | 8.4116 | 0.9977 | -0.1931 |
| verdade = modelo | combinado (mediana do indicador) | 57028 | 7.9405 | 0.0269 | 7.9761 | 0.9955 | -0.227 |
| verdade alternativa: parâmetros do exemplo do orientador | C9orf72 | 23218 | 9.3346 | 0.0472 | 7.044 | 1.3252 | -0.4923 |
| verdade alternativa: parâmetros do exemplo do orientador | FUS | 6683 | 9.8168 | 0.0821 | 13.7875 | 0.712 | -6.4626 |
| verdade alternativa: parâmetros do exemplo do orientador | SOD1 | 43608 | 8.5684 | 0.0322 | 7.6105 | 1.1259 | -3.8381 |
| verdade alternativa: parâmetros do exemplo do orientador | TARDBP | 14015 | 10.6437 | 0.0703 | 8.6435 | 1.2314 | -4.8882 |
| verdade alternativa: parâmetros do exemplo do orientador | combinado (mediana do indicador) | 87524 | 9.704 | 0.0255 | 8.2656 | 1.174 | -3.6684 |
| verdade alternativa: penetrância log-normal truncada em 1 | C9orf72 | 14805 | 7.1175 | 0.0459 | 7.0671 | 1.0071 | -0.4821 |
| verdade alternativa: penetrância log-normal truncada em 1 | FUS | 3225 | 13.0512 | 0.1705 | 13.0023 | 1.0038 | 2.0135 |
| verdade alternativa: penetrância log-normal truncada em 1 | SOD1 | 32759 | 7.4029 | 0.0318 | 7.4027 | 1 | -0.1405 |
| verdade alternativa: penetrância log-normal truncada em 1 | TARDBP | 8939 | 8.4851 | 0.0688 | 8.4088 | 1.0091 | -0.3607 |
| verdade alternativa: penetrância log-normal truncada em 1 | combinado (mediana do indicador) | 59728 | 7.9747 | 0.0262 | 7.9798 | 0.9994 | -0.2775 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

Piso teórico: desvio absoluto médio da distribuição de início em torno da sua mediana, condicionado à idade atual. Um modelo perfeito não fica abaixo dele, porque a idade de início é aleatória; razões um pouco abaixo de 1 são flutuação amostral (compare com `erro_padrao_anos`). Nos casos com dois lóci, a distribuição de cada gene é a do início daquele gene quando ele é o primeiro.
