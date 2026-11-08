# 05 — Ambiente da máquina e setup

Este documento é **específico de cada máquina**. Ao clonar o repositório noutra máquina, acrescente uma seção "Máquina: <nome> (<data>)" com o mesmo levantamento antes de instalar.

## Máquina de origem: levantamento de 24/10/2026 (Linux Rocky/RHEL 9, kernel 5.14)

### Fatos

| Item | Situação |
|---|---|
| Python | `/usr/bin/python3` = 3.9.25 (sistema; **não usar**); `/usr/bin/python3.11` = 3.11.13; CPython 3.12.13 gerenciado pelo `uv` em `~/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/` |
| uv | `~/.local/bin/uv` 0.12.5 (não está no PATH por padrão em shells não interativos; use o caminho completo) |
| pip | 21.3.1 no Python 3.9 (irrelevante) |
| Compiladores | `gcc` presente; **`g++` ausente** (PyTensor usa modo Python; aviso "g++ not detected" é esperado) |
| Hardware | 12 núcleos, 15 GB RAM (~4 GB livres no momento do levantamento), 104 GB livres em disco |
| Internet | PyPI acessível (HTTP 200); NCBI/Ensembl devem estar acessíveis para conferir coordenadas |
| Dados genômicos | **nenhum** arquivo ClinVar/dbSNP/VCF no home |
| Pacotes-alvo instalados | nenhum (só PyYAML 5.4.1 no Python 3.9) |
| Git | o diretório **não** é um repositório; iniciar `git init` na fase 1 se desejado |

## Versões verificadas no PyPI em 24/10/2026 (pinar no `pyproject.toml`)

```
pymc==5.28.5          # requer pytensor 2.38.x, arviz<1.0
lifelines==0.30.3     # mesma versão citada no TCC (Davidson-Pilon, 2026); exige pandas<3
numpy>=2,<2.5
pandas>=2.1,<3
scipy>=1.11
matplotlib>=3.8
seaborn>=0.13
pyvcf3==1.0.4         # fork do PyVCF; `import vcf`
biopython>=1.83
pyyaml>=6
pytest>=8             # extra [dev]
```

Caminho alternativo com Python 3.9 (não recomendado): `pymc==5.12.0`, `pytensor>=2.19,<2.20`, `numpy<2`, `arviz==0.17.1`, `lifelines==0.30.1`.

## Setup

```bash
cd <raiz do repositório>
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e "./ela_preditivo[dev]"      # após existir o pyproject (fase 1)
export PYTENSOR_FLAGS=cxx=                                   # silencia o aviso de g++ ausente
python -c "import pymc, pytensor, lifelines, vcf, Bio; print(pymc.__version__, pytensor.__version__, lifelines.__version__)"
```

Esperado: `5.28.5 2.38.x 0.30.3`.

## Convenções de diretório

- Código: `ela_preditivo/` (relativo à raiz do repositório)
- Saídas: `resultados/` (pode ser apagado e regenerado com `ela-preditivo tudo`)
- Temporários: fora do repositório (`/tmp/ela_preditivo/`)
- Dados brutos reais (se a autora fornecer): fora do repositório, caminho em `ELA_DADOS_BRUTOS`; nunca commitar

## Conferência de coordenadas (fase 1)

```bash
curl -s "https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/121912442" | python -c "import sys,json; d=json.load(sys.stdin); print(d['primary_snapshot_data']['placements_with_allele'][0]['alleles'])"
curl -s "https://rest.ensembl.org/lookup/symbol/homo_sapiens/SOD1?content-type=application/json"
```
Registrar `conferido_em` na tabela curada e `regioes_genes_grch38.yaml`.

## Dados reais (03/11/2026, máquina de origem)

Levantamento repetido em 03/11/2026 na mesma máquina (NOTEBOOK-8VRSKY3, Rocky 9.8, uv 0.12.5, CPython 3.12.13 gerenciado pelo uv, g++ ausente): sem mudanças em relação a 24/10/2026. `.venv` recriado com `uv venv --python 3.12 .venv` + `uv pip install -e "./ela_preditivo[dev]"` (pymc 5.28.5, pytensor 2.38.3, lifelines 0.30.3).

O usuário colocou o subconjunto real do ClinVar dos quatro genes em `dados_reais/` (raiz do repositório, **ignorada pelo git**; caminho alternativo em `ELA_DADOS_BRUTOS`):

| Arquivo | Conteúdo | Como o pacote usa |
|---|---|---|
| `base_consolidada_ela.csv` (1,2 MB, 1.463 linhas × 66 colunas) | `variant_summary` filtrado (43 colunas do ClinVar) + consequência molecular, classificação conflitante, AF_ESP/EXAC/TGP, `VCF_POS/REF/ALT`, casamento com o dbSNP (`dbsnp_rsid_casado`, método, validação, classe funcional, nº de estudos) e frequências ALFA/TOPMED/gnomAD/1000G | **fonte preferida** de `anotacao.tabela_anotacao()` (1.458 variantes com posição em VCF; 5 microssatélites/inserção do C9orf72 sem posição ficam de fora e são cobertas pela tabela curada) |
| `clinvar_ela_4genes.csv` (724 kB, 1.463 × 43) | `variant_summary.txt` filtrado por gene e GRCh38, em CSV | mesma leitura (`carregar_variant_summary`), sem as colunas do dbSNP |
| `clinvar_ela_4genes.vcf` (753 kB, VCF 4.1, 1.541 registros) | projeção do ClinVar (release 2026-09-28, GRCh38) sobre o VCF: sem amostras, QUAL/FILTER nulos, classificação em INFO (CLNSIG, CLNREVSTAT, GENEINFO, RS, AF_TGP, CLNSIGCONF) | `carregar_clinvar_vcf` (1.540 registros úteis; 1 sem ALT); alternativa quando as tabelas não estiverem presentes |

Contagens conferidas em 03/11/2026: 394 registros no cromossomo 1 (TARDBP), 698 no 16 (FUS), 331 no 21 (SOD1), 118 no 9 (C9orf72); CLNSIG: 616 incertas, 375 provavelmente benignas, 111 benignas, 90 patogênicas, 80 provavelmente patogênicas, 76 conflitantes, 53 B/LB, 47 P/LP. Na base consolidada: 1.082 rs casados por rsID, 203 por coordenada, 99 recusados por alelo divergente, 77 sem candidato. Observações que mudaram o código: SOD1 p.Asp91Ala é *conflitante* (D18); FUS c.1561C>G/T/A compartilham o rs121909668 (chave por coordenadas, D17); `GeneSymbol` pode vir como `MASP2;TARDBP`.

**Ainda não há VCF parental real.** Quando chegar: conferir `##reference`, prefixo `chr`, mono/multiamostra (`--amostra-mae/--amostra-pai`), campos FORMAT (`GT:DP:GQ` esperados) e se o laudo do C9orf72 vem à parte (`--c9orf72-mae/--c9orf72-pai`).

## Levantamento de 08/11/2026 (mesma máquina NOTEBOOK-8VRSKY3, clone novo)

- Clone novo em outro diretório, sem `.venv`; recriado com `uv venv --python 3.12 .venv` + `uv pip install -e "./ela_preditivo[dev]"`: pymc 5.28.5, pytensor 2.38.3, lifelines 0.30.3, pandas 2.3.3, numpy 2.4.6; uv 0.12.5; CPython 3.12.13 do uv; g++ ausente (`PYTENSOR_FLAGS=cxx=`); Rocky 9.8. Suíte: 106 testes em ~14 s.
- **`dados_reais/` não está neste clone**: os 5 testes com dados reais são pulados e `resultados/` não pode ser regenerado aqui com a base consolidada. Para repor, copiar os três arquivos da tabela acima; `ela-preditivo atualizar-base --baixar --release 2026-09-28` baixa só o VCF dessa release (não reconstrói a base consolidada com o dbSNP).
- FTP do ClinVar acessível (`https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/`): release corrente 2026-11-01; arquivo mensal em `archive_2.0/2026/` (2026-10-11, 10-19, 10-25). Teste de `atualizacao.baixar_clinvar` gravado fora do repositório, em `/tmp/ela_preditivo/clinvar_real/`: 55 s e 36 s por release (≈ 110 MB comprimidos cada; só os registros dos quatro genes são gravados: 1.561 e 1.565).
- Registro de versões (D29): `dados_reais/versoes/` com `versoes.json`, instantâneos `clinvar_<release>_<sha8>.csv` e relatórios `atualizacao_<anterior>_<atual>.md`; ignorado pelo git junto com o resto de `dados_reais/`. Os downloads chamam-se `clinvar_ela_4genes_<release>.vcf` e já são cobertos pelo padrão `clinvar*.vcf` do `.gitignore`.
