**Tabela 13 — Brier score das previsões a 10 e 20 anos a partir da idade atual e até o horizonte, com verdade = modelo e com verdades alternativas**

| verdade | previsao | n | prevalencia_observada | risco_previsto_medio | brier | brier_referencia | habilidade |
|---|---|---|---|---|---|---|---|
| verdade = modelo | 10 anos | 326006 | 0.0313 | 0.0315 | 0.029 | 0.0303 | 0.0428 |
| verdade = modelo | 20 anos | 326006 | 0.0632 | 0.0633 | 0.0551 | 0.0592 | 0.0691 |
| verdade = modelo | até o horizonte | 326006 | 0.1749 | 0.1746 | 0.1327 | 0.1443 | 0.0805 |
| verdade alternativa: parâmetros do exemplo do orientador | 10 anos | 293050 | 0.0586 | 0.0296 | 0.0531 | 0.0552 | 0.0368 |
| verdade alternativa: parâmetros do exemplo do orientador | 20 anos | 293050 | 0.1174 | 0.0613 | 0.0979 | 0.1036 | 0.0551 |
| verdade alternativa: parâmetros do exemplo do orientador | até o horizonte | 293050 | 0.2987 | 0.1813 | 0.1948 | 0.2095 | 0.0699 |
| verdade alternativa: penetrância log-normal truncada em 1 | 10 anos | 323830 | 0.0332 | 0.0315 | 0.0306 | 0.0321 | 0.0462 |
| verdade alternativa: penetrância log-normal truncada em 1 | 20 anos | 323830 | 0.0667 | 0.0634 | 0.0576 | 0.0622 | 0.0739 |
| verdade alternativa: penetrância log-normal truncada em 1 | até o horizonte | 323830 | 0.1844 | 0.1752 | 0.1375 | 0.1504 | 0.0858 |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

brier_referencia = p̄(1 − p̄), de quem prevê a prevalência para todos; habilidade = 1 − Brier/referência.
