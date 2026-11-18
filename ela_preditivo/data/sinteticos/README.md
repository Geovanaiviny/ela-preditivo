# VCFs sintéticos

Gerados por `ela-preditivo gerar-cenarios --saida ela_preditivo/data/sinteticos` (semente 2026). Nenhum arquivo
vem de uma pessoa: as coordenadas e os alelos das variantes de risco e da variante benigna são os da base pública do
ClinVar/dbSNP, e os genótipos, a profundidade e a qualidade são gerados pela semente. A expansão do C9orf72 não vai no
VCF; entra pelo laudo (número de repetições) informado na análise.

Cada pasta reúne os arquivos usados num caso de atendimento. O par de VCFs em si serve a qualquer caso.

| Pasta | Arquivos | O que representa | Laudo do C9orf72 |
| --- | --- | --- | --- |
| `caso_1_pessoa_com_historico/` | `cenario_1_*` | pai heterozigoto SOD1 p.Ala5Val | normal nos dois |
| | `cenario_2_*` | mãe com expansão do C9orf72 | mãe 45, pai normal |
| | `cenario_3_*` | pai SOD1 p.Ala5Val e mãe com expansão do C9orf72 | mãe 45, pai normal |
| | `cenario_5_*` | pai TARDBP p.Met337Val e mãe FUS p.Arg521Cys | normal nos dois |
| | `parentes_1_mae`, `parentes_1_avo_paterna` | pai sem exame, falecido sem ELA aos 60 anos; avó paterna heterozigota SOD1 p.Ala5Val | normal na mãe e na avó |
| `caso_2_casal_ou_futuro_filho/` | `casal_1_mae` | parceira com expansão do C9orf72; parceiro sem exame | parceira 45 |
| | `casal_2_*` | os dois parceiros heterozigotos SOD1 p.Asp91Ala (herança recessiva) | normal nos dois |
| `caso_3_familia_com_variante/` | `cenario_4_*` | os dois genitores heterozigotos SOD1 p.Asp91Ala (herança recessiva), filhos adultos | normal nos dois |
| | `parentes_2_mae`, `parentes_2_avo_paterna`, `parentes_2_filho_testado` | pai sem exame, vivo sem sintomas aos 62 anos; avó paterna portadora; um filho já testado, sem a variante | normal |

"Normal" é o laudo com 23 repetições (`cenarios.LAUDO_NORMAL`, um abaixo da faixa intermediária do YAML).
`cenarios.csv` indexa os cinco cenários com o laudo de cada genitor.
