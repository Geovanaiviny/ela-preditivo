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
