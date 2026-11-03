"""ela_preditivo — protótipo de apoio ao aconselhamento genético preditivo da ELA.

Camadas (TCC, seções 4.3 a 4.6): ingestão e anotação de VCFs parentais; núcleo estocástico
(Rede Bayesiana + Monte Carlo); análise de sobrevivência; relatório.
"""
from __future__ import annotations

import os
from pathlib import Path

__version__ = "0.1.0"

GENES = ("SOD1", "C9orf72", "TARDBP", "FUS")

# Raiz do projeto (diretório que contém config/ e data/). Pode ser sobrescrita por ELA_PREDITIVO_RAIZ.
RAIZ_PROJETO = Path(os.environ.get("ELA_PREDITIVO_RAIZ", Path(__file__).resolve().parents[2]))
DIR_CONFIG = RAIZ_PROJETO / "config"
DIR_DADOS = RAIZ_PROJETO / "data"
# Dados reais (subconjunto do ClinVar/dbSNP dos quatro genes, TCC 4.2.2): fora do pacote e fora do versionamento.
# Caminho em ELA_DADOS_BRUTOS; padrão: pasta `dados_reais/` na raiz do repositório (ignorada pelo git).
DIR_DADOS_BRUTOS = Path(os.environ.get("ELA_DADOS_BRUTOS", RAIZ_PROJETO.parent / "dados_reais"))

AVISO_LEGAL = (
    "AVISO: instrumento experimental de apoio à decisão no aconselhamento genético preditivo da ELA, "
    "construído com dados sintéticos e parâmetros populacionais da literatura. Não constitui diagnóstico, "
    "não substitui o julgamento clínico e não deve ser usado isoladamente em decisões sobre pacientes."
)
