# Relatório do artefato — Cenário 4 (M): Ambos os pais heterozigotos para SOD1 p.Asp91Ala (herança recessiva)

> AVISO: instrumento experimental de apoio à decisão no aconselhamento genético preditivo da ELA, construído com dados sintéticos e parâmetros populacionais da literatura. Não constitui diagnóstico, não substitui o julgamento clínico e não deve ser usado isoladamente em decisões sobre pacientes.

## Entrada

VCF materno: `cenario_4_mae.vcf` (amostra MAE); VCF paterno: `cenario_4_pai.vcf` (amostra PAI); laudo do C9orf72: não informado; sexo do descendente: M; idade atual sem sintomas: 30.0; motor: pymc; N = 10.000; seed = 42; horizonte = 90 anos.

## Qualidade dos dados (TCC 4.2.3)

- Mãe: montagem GRCh38 (coerente); 5/7 registros aprovados (71%); 2 aprovados encontrados na base de anotação (40%; estado de revisão 1★: 1, 2★: 1); classes {'nao_anotada': 3, 'benigna': 1, 'vus': 1}; significado incerto/conflitante: 1 (50% das anotadas); risco com frequência > 1%: 0.
- Pai: montagem GRCh38 (coerente); 5/7 registros aprovados (71%); 2 aprovados encontrados na base de anotação (40%; estado de revisão 1★: 1, 2★: 1); classes {'nao_anotada': 3, 'benigna': 1, 'vus': 1}; significado incerto/conflitante: 1 (50% das anotadas); risco com frequência > 1%: 0.
- Base de anotação: clinvar_base_consolidada; regra de classe: só Pathogenic/Likely pathogenic sustentam risco; significado incerto e classificações conflitantes não (TCC 4.2.2).

## Resultado

Nenhum lócus de risco (classe patogênica/provavelmente patogênica) foi encontrado nos genes-alvo dos dois genitores. O risco de transmissão de variantes conhecidas é nulo neste recorte; o risco populacional de base não é modelado. Foram encontradas variantes que não sustentam atribuição de risco pela regra do TCC 4.2.2 (significado incerto, classificação conflitante ou faixa intermediária): MAE: SOD1 p.Asp91Ala (Conflicting classifications of pathogenicity); PAI: SOD1 p.Asp91Ala (Conflicting classifications of pathogenicity).

## Tabelas

**Tabela 1 — Variantes aprovadas no filtro de qualidade e sua anotação, por genitor**

| amostra | gene | cromossomo | posicao | ref | alt | id | tipo | dosagem | repeticoes | classe | clnsig | estrelas | nome_curto | heranca | fonte_anotacao |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MAE | TARDBP | 1 | 11020000 | G | A |  | snv | 0 |  | nao_anotada |  |  |  |  |  |
| MAE | TARDBP | 1 | 11020000 | G | T |  | snv | 1 |  | nao_anotada |  |  |  |  |  |
| MAE | FUS | 16 | 31185000 | A | G |  | snv | 1 |  | nao_anotada |  |  |  |  |  |
| MAE | SOD1 | 21 | 31659509 | G | T | rs17883296 | snv | 1 |  | benigna | Likely benign | 2 | rs17883296 |  | clinvar_base_consolidada:posicao_alelos |
| MAE | SOD1 | 21 | 31667290 | A | C | rs80265967 | snv | 1 |  | vus | Conflicting classifications of pathogenicity | 1 | p.Asp91Ala | recessiva | clinvar_base_consolidada:posicao_alelos |
| PAI | TARDBP | 1 | 11020000 | G | A |  | snv | 0 |  | nao_anotada |  |  |  |  |  |
| PAI | TARDBP | 1 | 11020000 | G | T |  | snv | 1 |  | nao_anotada |  |  |  |  |  |
| PAI | FUS | 16 | 31185000 | A | G |  | snv | 1 |  | nao_anotada |  |  |  |  |  |
| PAI | SOD1 | 21 | 31659509 | G | T | rs17883296 | snv | 1 |  | benigna | Likely benign | 2 | rs17883296 |  | clinvar_base_consolidada:posicao_alelos |
| PAI | SOD1 | 21 | 31667290 | A | C | rs80265967 | snv | 1 |  | vus | Conflicting classifications of pathogenicity | 1 | p.Asp91Ala | recessiva | clinvar_base_consolidada:posicao_alelos |

*Fonte: elaborado pela autora (2026), a partir do artefato ela_preditivo.*

Registros lidos/aprovados: mãe 7/5, pai 7/5. Reprovações: mãe {'fora_das_regioes': 1, 'filtro_nao_pass': 1, 'dp_baixo': 1, 'gq_baixo': 1}, pai {'fora_das_regioes': 1, 'filtro_nao_pass': 1, 'dp_baixo': 1, 'gq_baixo': 1}. Base de anotação: clinvar_base_consolidada (1458 variantes do ClinVar + 1 da tabela curada).

