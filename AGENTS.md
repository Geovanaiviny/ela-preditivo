# AGENTS.md — Artefato do TCC: Sistema Preditivo de Herança e Manifestação Clínica para ELA

Este arquivo é lido pelo Codex (automaticamente) e pelo Claude Code (via `CLAUDE.md`, que apenas importa este arquivo). Mantenha as instruções aqui; não duplique em `CLAUDE.md`.

## O que é este repositório

Projeto de apoio ao TCC **"Desenvolvimento de Sistema Preditivo de Herança e Manifestação Clínica para Esclerose Lateral Amiotrófica (ELA) Baseado em Modelagem Estocástica e Redes Bayesianas"** (Geovana Íviny Santos Lima; Fabricio Carneiro Costa). O objetivo é construir o protótipo Python descrito no TCC (seções 3.3 e 4.3 a 4.6) e gerar as tabelas e figuras que preencherão a **seção 5 (Resultados)**, hoje vazia.

`TCC II - Escrita.docx` é o documento original da autora. **Não o edite.** Se ele não estiver no clone, use `docs/00_tcc_texto_extraido.md`, que é a cópia integral em Markdown e a referência de requisitos.

## Contexto de trabalho: várias máquinas, dois agentes

- O repositório é versionado em git e clonado em mais de uma máquina. Numa delas o trabalho é feito com o **Codex**, noutra com o **Claude Code**. Os dois seguem este mesmo arquivo e os mesmos documentos em `docs/`.
- **Todo caminho em código, docs e comandos é relativo à raiz do repositório.** Nunca grave caminhos absolutos de uma máquina (`/home/<usuário>/...`) em código, configuração ou documentação.
- `docs/05_ambiente.md` descreve a máquina onde a análise inicial foi feita (24/10/2026). **Ao começar numa máquina nova, repita o levantamento** (versão do Python, `uv`, compiladores, internet, dados) e acrescente uma seção com a data e o nome da máquina nesse documento antes de instalar qualquer coisa.
- O estado do trabalho vive em três lugares, todos versionados: a lista de status abaixo, `docs/04_decisoes.md` e os testes. Antes de começar, faça `git pull` e leia o status; ao terminar uma fase, marque-a aqui e faça commit no mesmo passo. Assim o outro agente, na outra máquina, retoma sem perder contexto.
- Commits pequenos, mensagem em português, no imperativo, descrevendo o quê e por quê (ex.: `Adiciona calibracao Beta a partir de ponto e IC`). Não faça commit de `.venv/`, dados brutos, temporários ou segredos (ver `.gitignore`).
- Se uma decisão de `docs/04_decisoes.md` precisar mudar, registre lá o motivo e a data no mesmo commit da mudança; o outro agente só saberá por esse arquivo.
- Dúvidas que só o usuário ou a autora podem responder (parâmetros de literatura, escolhas que alteram o texto do TCC) vão para a seção "Decisões em aberto" de `docs/04_decisoes.md`, não ficam só na conversa.

## Leia primeiro, nesta ordem

1. `docs/01_analise_tcc.md` — o que o TCC exige, parâmetros da literatura, ferramentas declaradas e inconsistências encontradas.
2. `docs/02_modelo_matematico.md` — modelo probabilístico completo (DAG, CPTs, priors, calibração, sobrevivência, fórmulas exatas).
3. `docs/03_plano_implementacao.md` — layout do pacote, APIs dos módulos, cenários sintéticos, avaliação, fases com critério de pronto.
4. `docs/04_decisoes.md` — decisões já tomadas (D1 a D11) e decisões em aberto. Siga-as; se precisar mudar, registre lá o motivo.
5. `docs/05_ambiente.md` — ambiente das máquinas e comandos de setup.
6. `docs/06_base_exemplo_professor.md` — o que o exemplo do orientador (`exemplo_maquina_tcc_ela.py`, na raiz, não editar) faz e como o pacote o evolui e corrige.
7. `docs/00_tcc_texto_extraido.md` — texto integral do TCC. Fonte da verdade sobre requisitos; consulte quando houver dúvida.

## Status (atualize ao concluir cada fase e faça commit)

- [x] Fase 0 — análise do TCC, levantamento do ambiente, desenho do modelo, plano e estes documentos (24/10/2026, máquina de origem)
- [x] Fase 1 — scaffold do pacote `ela_preditivo`, `pyproject.toml`, `config/parametros_literatura.yaml`, `config/regioes_genes_grch38.yaml`, `data/variantes_curadas.csv` (coordenadas conferidas no dbSNP/Ensembl em 24/10/2026)
- [x] Fase 2 — `calibracao.py`, `exato.py` + testes (24/10/2026)
- [x] Fase 3 — `cenarios.py` (gerador de VCF), `ingestao.py`, `anotacao.py`, `genotipo.py` + testes (24/10/2026)
- [x] Fase 4 — `rede_bayesiana.py` (PyMC), `monte_carlo.py` (NumPy) + testes de aderência (24/10/2026)
- [x] Fase 5 — `sobrevivencia.py` (Lifelines) + testes (24/10/2026)
- [x] Fase 6 — `avaliacao.py`, `relatorio.py`, `pipeline.py`, `cli.py`; execução dos 5 cenários × 2 sexos e avaliação (N = 1e3/1e4/1e5 × 30 sementes) em `resultados/` (24/10/2026; regenerar com `ela-preditivo tudo --saida resultados --seed 42`)
- [x] Fase 7 — `ela_preditivo/README.md` (apresentação para o orientador) e `docs/07_resultados_secao5.md` (texto-base da seção 5 com os números da execução) (24/10/2026)
- [ ] Fase 8 — revisão pela autora/orientador: confirmar parâmetros `confirmar: true` no YAML (Richard et al., 2026; pontos de Murphy 2017), ajustar o texto do TCC (docs/01, item 9) e decidir se `resultados/` entra no repositório

## Regras do projeto

- **Nunca use dados genômicos reais.** Só VCFs sintéticos gerados por `cenarios.py` e a tabela curada de variantes públicas (ClinVar/dbSNP) em `data/variantes_curadas.csv`. Motivo: LGPD e ausência de comitê de ética (TCC, seção 3.4). Se a autora fornecer os arquivos ClinVar/dbSNP, eles ficam fora do repositório, no caminho da variável de ambiente `ELA_DADOS_BRUTOS`.
- Toda saída para o usuário final (relatório, figuras, CLI) carrega o aviso: *instrumento experimental de apoio à decisão no aconselhamento genético; não constitui diagnóstico nem substitui o julgamento clínico* (TCC, 4.6).
- **Stack fixada pelo TCC**: Python, PyVCF (fork `pyvcf3`) + Biopython, pandas/NumPy, PyMC, Lifelines, matplotlib/seaborn, pytest. Não adicione `pgmpy`, Streamlit ou outra biblioteca de modelagem sem registrar em `docs/04_decisoes.md`, pois o texto do TCC precisaria mudar.
- **Idioma**: módulos, funções, CLI, mensagens, legendas de figuras e cabeçalhos de tabelas em português; termos de bibliotecas em inglês. Figuras e tabelas saem com legenda pronta para o TCC ("Figura N — ...", "Fonte: elaborado pela autora").
- **Parâmetros da literatura só em `ela_preditivo/config/parametros_literatura.yaml`**, cada um com `valor`, `ic95`, `citacao` e `confirmar` (`true` = valor provisório que a autora precisa validar). Nunca deixe número de penetrância ou idade de início hard-coded.
- **Reprodutibilidade**: toda simulação recebe `seed`; cada resultado grava seed, N, versão do pacote, versão do YAML e data. Os VCFs sintéticos são gerados com seed fixa e versionados.
- **Testes**: pytest; todo módulo novo com teste. A aderência mendeliana é testada contra as fórmulas exatas de `docs/02_modelo_matematico.md`. Rode `pytest -q` antes de cada commit.
- **Python 3.12 via `uv`** (ver `docs/05_ambiente.md`). Nunca instale no Python do sistema. O ambiente virtual (`.venv/`) é local a cada máquina e não é versionado.
- Arquivos temporários fora do repositório (ex.: `/tmp/ela_preditivo/`), nunca em `data/`.

## Comandos (na raiz do repositório; `uv` deve estar no PATH ou use o caminho completo)

```bash
uv venv --python 3.12 .venv                      # uma vez por máquina
source .venv/bin/activate
export PYTENSOR_FLAGS=cxx=                       # só se a máquina não tiver g++
uv pip install -e "./ela_preditivo[dev]"         # após a Fase 1
pytest -q ela_preditivo/tests
ela-preditivo gerar-cenarios --saida ela_preditivo/data/sinteticos
ela-preditivo executar --vcf-mae <mae.vcf> --vcf-pai <pai.vcf> --sexo F --idade-atual 30 --n 10000 --seed 42 --saida resultados/cenario_1
ela-preditivo avaliar --n 1000 10000 100000 --repeticoes 30 --saida resultados/avaliacao
ela-preditivo tudo --saida resultados --seed 42
```

## Estrutura alvo

```
<raiz do repositório>/
  AGENTS.md                      # este arquivo (Codex)
  CLAUDE.md                      # só importa o AGENTS.md (Claude Code)
  .gitignore
  TCC II - Escrita.docx          # original da autora (não editar; pode não estar no clone)
  exemplo_maquina_tcc_ela.py     # exemplo do orientador (não editar; ver docs/06)
  docs/                          # análise, modelo, plano, decisões, ambiente, texto do TCC
  ela_preditivo/                 # pacote Python (README.md = apresentação para o orientador)
    pyproject.toml  README.md
    config/parametros_literatura.yaml  config/regioes_genes_grch38.yaml
    data/variantes_curadas.csv  data/sinteticos/
    src/ela_preditivo/{ingestao,anotacao,genotipo,calibracao,exato,rede_bayesiana,monte_carlo,sobrevivencia,cenarios,avaliacao,relatorio,pipeline,cli}.py
    tests/
  resultados/                    # saídas da execução definitiva (índice em resultados/README.md); regeneráveis com `ela-preditivo tudo`
```
