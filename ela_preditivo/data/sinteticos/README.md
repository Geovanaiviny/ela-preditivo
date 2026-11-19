# VCFs sintéticos e documentos fictícios

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

## Fichas de teste: prontuário e laudo do C9orf72

A plataforma guarda dois tipos de documento: o documento do prontuário, obrigatório no cadastro, e o laudo do C9orf72 de
cada genitor. Para o roteiro de testes há sete registros fictícios, com um PDF de cada documento na pasta do caso. O
mesmo comando que gera os VCFs grava esses PDFs (`documentos_ficticios.py`); todos trazem a marca "FICTÍCIO" e o aviso de
que não são documento clínico. Os nomes não repetem os da demonstração.

| Ficha | Pasta | Registro | Prontuário | Mãe ou parceira | Pai ou parceiro |
| --- | --- | --- | --- | --- | --- |
| 1A | `caso_1_pessoa_com_historico/` | Beatriz Fictícia Andrade | `caso_1A_prontuario_HML-1001.pdf` | `cenario_3_mae.vcf`, laudo 45 (`caso_1A_laudo_c9orf72_mae.pdf`) | `cenario_3_pai.vcf`, laudo 23 (`caso_1A_laudo_c9orf72_pai.pdf`) |
| 1B | | Caio Fictício Menezes | `caso_1B_prontuario_HML-1002.pdf` | `parentes_1_mae.vcf`, laudo 23 (`caso_1B_laudo_c9orf72_mae.pdf`) | sem exame e sem laudo; avó paterna `parentes_1_avo_paterna.vcf`, laudo 23 |
| 1C | | Mateus Fictício Rocha | `caso_1C_prontuario_HML-1003.pdf` | `cenario_5_mae.vcf`, laudo 23 (`caso_1C_laudo_c9orf72_mae.pdf`) | `cenario_5_pai.vcf`, laudo 23 (`caso_1C_laudo_c9orf72_pai.pdf`) |
| 2A | `caso_2_casal_ou_futuro_filho/` | Juliana Fictícia Prates e Eduardo Fictício Prates | `caso_2A_prontuario_HML-2001.pdf` | `casal_1_mae.vcf`, laudo 45 (`caso_2A_laudo_c9orf72_mae.pdf`) | sem exame e sem laudo |
| 2B | | Patrícia Fictícia Lins e Fábio Fictício Lins | `caso_2B_prontuario_HML-2002.pdf` | `casal_2_mae.vcf`, laudo 23 (`caso_2B_laudo_c9orf72_mae.pdf`) | `casal_2_pai.vcf`, laudo 23 (`caso_2B_laudo_c9orf72_pai.pdf`) |
| 3A | `caso_3_familia_com_variante/` | Família Fictícia Bastos | `caso_3A_prontuario_HML-3001.pdf` | `cenario_4_mae.vcf`, laudo 23 (`caso_3A_laudo_c9orf72_mae.pdf`) | `cenario_4_pai.vcf`, laudo 23 (`caso_3A_laudo_c9orf72_pai.pdf`) |
| 3B | | Família Fictícia Cardoso | `caso_3B_prontuario_HML-3002.pdf` | `parentes_2_mae.vcf`, laudo 23 (`caso_3B_laudo_c9orf72_mae.pdf`) | sem exame e sem laudo; avó paterna `parentes_2_avo_paterna.vcf`, laudo 23; filho testado `parentes_2_filho_testado.vcf` |

O prontuário de cada ficha traz os dados do cadastro: pessoa atendida ou filhos, nascimentos, momento do aconselhamento e
observações. O laudo traz o número de repetições a digitar no campo do genitor: a plataforma não lê o arquivo e, sem
o número digitado, o C9orf72 fica indeterminado mesmo com o PDF anexado. Genitor sem exame não tem laudo; o laudo do
parente dele entra só como número, no cadastro do parente, porque a plataforma não guarda documento de parente.
