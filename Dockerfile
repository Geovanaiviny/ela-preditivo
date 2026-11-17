# Imagem da plataforma EloSense: o pacote ela_preditivo com a camada web.
# Uso: docker compose up --build   (ver docker-compose.yml)
FROM python:3.12-slim

# PyTensor em modo Python (a imagem não traz compilador; os números são os mesmos), figuras sem tela,
# dados fora do código: banco e arquivos cifrados em /app/dados_web, base do ClinVar em /app/dados_reais
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTENSOR_FLAGS=cxx= \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    ELA_DADOS_BRUTOS=/app/dados_reais \
    ELA_WEB_BD=/app/dados_web/ela_web.sqlite3 \
    ELA_WEB_VCFS=/app/dados_web/vcfs \
    ELA_WEB_HOST=0.0.0.0 \
    ELA_WEB_PORTA=8000

WORKDIR /app

# As dependências vêm antes do código: mexer no código não reinstala tudo
COPY ela_preditivo/pyproject.toml ela_preditivo/README.md ela_preditivo/
RUN mkdir -p ela_preditivo/src/ela_preditivo \
    && touch ela_preditivo/src/ela_preditivo/__init__.py \
    && pip install -e "./ela_preditivo[web]"

COPY ela_preditivo/src ela_preditivo/src
COPY ela_preditivo/config ela_preditivo/config
COPY ela_preditivo/data ela_preditivo/data
RUN mkdir -p /app/dados_web /app/dados_reais

VOLUME ["/app/dados_web"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/sistema', timeout=4).status == 200 else 1)"

# Sem argumentos: prepara a chave e o banco e sobe o servidor. Com argumentos: roda esse comando de ela-preditivo.
ENTRYPOINT ["python", "-m", "ela_preditivo.web.arranque"]
