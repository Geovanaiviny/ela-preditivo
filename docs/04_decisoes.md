# 04 — Registro de decisões

Formato: decisão, escolha, motivo, alternativa e como trocar. Decisões tomadas em 24/10/2026 na análise inicial; podem ser revistas pelo usuário ou pela autora. Ao mudar uma decisão, atualizar aqui, no AGENTS.md e no texto do TCC afetado.

| # | Decisão | Escolha | Motivo | Alternativa / como trocar |
|---|---|---|---|---|
| D1 | Motor da Rede Bayesiana e do Monte Carlo | **PyMC** (`sample_prior_predictive`) como motor declarado + amostrador NumPy equivalente para N = 1e5 × 30 repetições + fórmulas exatas em `exato.py` | PyMC é o que o TCC cita (3.3, 4.4.D); prior Beta carrega a incerteza do IC; NumPy evita o custo do PyTensor nas repetições | `pgmpy` seria a biblioteca clássica de RB discreta, mas exige mudar o TCC. Para trocar: implementar `rede_pgmpy.py` com a mesma interface de `rede_bayesiana.simular(...)` |
| D2 | Parser de VCF | **`pyvcf3`** (fork mantido do PyVCF, `import vcf`) + Biopython só para o motivo de repetição | mantém verdadeira a citação "PyVCF"; Biopython não tem parser de VCF | parser próprio em pandas (VCF é TSV) se `pyvcf3` falhar no 3.12; `cyvcf2`/`pysam` exigem compilar htslib |
| D3 | Dados ClinVar/dbSNP | tabela curada embutida (6 variantes) + carregador opcional do subconjunto real descrito na seção 4.2 | arquivos não estão nesta máquina; o protótipo precisa rodar sem eles | baixar `clinvar_20260928.vcf.gz` (~2 GB) do FTP do NCBI e reconstruir o recorte dos 4 genes; ou a autora fornece os arquivos |
| D4 | Forma de entrega | pacote Python + CLI + figuras PNG e tabelas CSV/Markdown (matplotlib/seaborn) | é o que o TCC declara em 4.4.D e 4.6 | notebook Jupyter de demonstração (fase 7, opcional); Streamlit não está no TCC |
| D5 | Idioma do código | módulos, funções, CLI, mensagens e legendas em português; termos de biblioteca em inglês | banca e autora leem em português; legendas saem prontas para o texto | tudo em inglês (renomear módulos antes da fase 3) |
| D6 | Versão do Python | **3.12** via `uv venv --python 3.12` (já baixado em `~/.local/share/uv`) | PyMC 5.x exige ≥ 3.10; 3.12 é estável e gerenciado pelo uv | `/usr/bin/python3.11 -m venv` funciona também; 3.9 do sistema exigiria `pymc==5.12`, `numpy<2`, `lifelines==0.30.1` |
| D7 | Compilador C++ ausente | rodar PyTensor em modo Python (`PYTENSOR_FLAGS=cxx=` para silenciar o aviso) | modelo pequeno; `sample_prior_predictive` não precisa do backend C | pedir ao administrador `sudo dnf install gcc-c++` para acelerar |
| D8 | Penetrância do C9orf72 | nível π de Douglas & Baralle (0,33); forma G(t) de Murphy 2017 normalizada pelo platô; sensibilidade com π = 0,9 | reconcilia população vs coortes familiares sem descartar nenhuma fonte | usar Murphy integral (π ≈ 1) como cenário principal; registrar no texto |
| D9 | Combinação de genes | independência: `1 − ∏(1 − P_g)` | genes em cromossomos distintos; sem evidência quantitativa de oligogenia | modelo de interação (fora do escopo; listar em trabalhos futuros) |
| D10 | Limiar da expansão C9orf72 | ≥ 30 repetições patogênico; 24–29 intermediário (configurável) | prática clínica corrente; ClinVar registra GGGGCC[>24] | ajustar em `limiar_repeticoes_c9orf72` no YAML |
| D11 | Horizonte temporal e censura | 90 anos; coorte sintética censurada no horizonte ou na idade atual | cobre o pico 60–75 e a cauda; mediana infinita sob cura mista é esperada | 100 anos |
| D12 | Critério da prior Beta (24/10/2026) | `calibracao_beta.peso_ponto: 1.0`: o valor publicado é a mediana da Beta; limite inferior do IC reproduzido; limite superior aproximado (erro reportado na Tabela 6) | os IC de Douglas & Baralle são simétricos em escala log (estimativas de razão) e a Beta não reproduz ponto e IC ao mesmo tempo; o ponto é o que a banca confere à mão | `peso_ponto: 0.0` reproduz o IC exatamente e desloca a mediana (SOD1 0,54 → 0,64) |
| D13 | Exemplo do orientador como base (24/10/2026) | manter a estrutura em três camadas e a lógica de transmissão de `exemplo_maquina_tcc_ela.py`; evoluir e corrigir conforme `docs/06_base_exemplo_professor.md`; parâmetros dele como `sensibilidade.exemplo_professor` | dá continuidade ao que o orientador propôs e permite comparar na seção 5 | reescrever do zero sem referência ao exemplo |

## Decisões em aberto (confirmar com o usuário/autora antes da fase 1)

1. Confirmar D1, D2, D4 e D5 (afetam o texto do TCC e a leitura pela banca).
2. A autora fornecerá os arquivos ClinVar/dbSNP da seção 4.2? Se sim, onde colocá-los (fora do repositório, caminho em variável de ambiente `ELA_DADOS_BRUTOS`).
3. Valores de Richard et al. 2026 para as faixas etárias de SOD1, TARDBP e FUS (até lá, placeholders com `confirmar: true`).
4. Pontos adicionais da curva de Murphy 2017 (digitalizar a figura do artigo para melhorar o ajuste de G(t)).
