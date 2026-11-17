# ela-preditivo

Artefato computacional do TCC **"Desenvolvimento de Sistema Preditivo de Herança e Manifestação Clínica para Esclerose Lateral Amiotrófica (ELA) Baseado em Modelagem Estocástica e Redes Bayesianas"**, de Geovana Íviny Santos Lima.

A partir do VCF da mãe e do pai (ou do genótipo de parentes, quando um genitor não pôde ser testado), o artefato estima a probabilidade de um descendente herdar uma variante de risco nos genes SOD1, C9orf72, TARDBP e FUS, a probabilidade de manifestar a doença e a idade provável de início, com Rede Bayesiana, simulação de Monte Carlo e análise de sobrevivência.

> **Aviso.** Instrumento experimental de apoio à decisão no aconselhamento genético preditivo da ELA, construído com dados sintéticos e parâmetros populacionais da literatura. Não constitui diagnóstico, não substitui o julgamento clínico e não deve ser usado isoladamente em decisões sobre pacientes.

## O que há no repositório

| Pasta ou arquivo | Conteúdo |
|---|---|
| `ela_preditivo/` | pacote Python: núcleo numérico, linha de comando, plataforma web EloSense, testes e documentação completa em [`ela_preditivo/README.md`](ela_preditivo/README.md) |
| `ela_preditivo/src/ela_preditivo/web/static/` | interface da plataforma (HTML, CSS e JavaScript, sem framework) |
| `ela_preditivo/config/` | parâmetros da literatura, com a citação de cada valor |
| `ela_preditivo/data/sinteticos/` | cenários familiares sintéticos (VCF) |
| `resultados/` | tabelas, figuras e relatórios gerados pelo artefato |
| `Dockerfile`, `docker-compose.yml`, `.env.exemplo` | subida da plataforma em um comando |
| `exemplo_maquina_tcc_ela.py` | exemplo de referência enviado pelo orientador |

## Como rodar

Com Docker, a plataforma sobe em `http://localhost:8000`:

```bash
docker compose up --build
```

Daí em diante tudo acontece no navegador. Na primeira vez a plataforma abre na tela Primeiro acesso, onde se cria o administrador e, em homologação (o padrão), os usuários e registros fictícios, com as senhas mostradas na tela. A base real do ClinVar é enviada pela tela Base de anotação. Análises, envio de VCFs e documentos, resultados, avaliação com as métricas de verificação, reprodução completa e cenários também são feitos pela interface, com permissões por papel (médico, pesquisador e administrador).

Sem Docker:

```bash
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -e "./ela_preditivo[dev,web]"
export PYTENSOR_FLAGS=cxx=            # só se a máquina não tiver g++
pytest -q ela_preditivo/tests         # testes
ela-preditivo tudo --saida resultados --seed 42   # cenários, casos, avaliação e métricas de verificação
```

Instalação detalhada, uso da linha de comando, plataforma web, saídas, verificações e limitações estão em [`ela_preditivo/README.md`](ela_preditivo/README.md).

## Licença

Apache 2.0 (arquivo `LICENSE`).
