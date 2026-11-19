**Tabela 15 — Discriminação: C-index de Harrell e AUC dependente do tempo a 10 e 20 anos**

| verdade | metrica | valor | dp_entre_mundos | mundos | casos | controles |
|---|---|---|---|---|---|---|
| verdade = modelo | C-index de Harrell (risco residual até o horizonte) | 0.6296 | 0.0152 | 200 | 57028 | 268978 |
| verdade = modelo | AUC dependente do tempo, 10 anos (Mann-Whitney) | 0.8056 | 0.0252 | 200 | 10198 | 315808 |
| verdade = modelo | AUC dependente do tempo, 20 anos (Mann-Whitney) | 0.7865 | 0.0213 | 200 | 20599 | 305407 |
| verdade alternativa: parâmetros do exemplo do orientador | C-index de Harrell (risco residual até o horizonte) | 0.6548 | 0.0125 | 200 | 87524 | 205526 |
| verdade alternativa: parâmetros do exemplo do orientador | AUC dependente do tempo, 10 anos (Mann-Whitney) | 0.7865 | 0.0187 | 200 | 17170 | 275880 |
| verdade alternativa: parâmetros do exemplo do orientador | AUC dependente do tempo, 20 anos (Mann-Whitney) | 0.7709 | 0.0176 | 200 | 34404 | 258646 |
| verdade alternativa: penetrância log-normal truncada em 1 | C-index de Harrell (risco residual até o horizonte) | 0.6309 | 0.0154 | 200 | 59728 | 264102 |
| verdade alternativa: penetrância log-normal truncada em 1 | AUC dependente do tempo, 10 anos (Mann-Whitney) | 0.8074 | 0.0254 | 200 | 10751 | 313079 |
| verdade alternativa: penetrância log-normal truncada em 1 | AUC dependente do tempo, 20 anos (Mann-Whitney) | 0.7886 | 0.0202 | 200 | 21591 | 302239 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

Tempo contado a partir da idade atual, com censura no horizonte. A verdade sintética não tem censura além do horizonte e as idades atuais vão até 70 anos, por isso a AUC não precisa de ponderação pela censura.
