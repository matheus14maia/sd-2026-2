# Imagem do API Gateway (FastAPI + cliente gRPC).
#
#   docker build -f docker/gateway.Dockerfile -t delivery-gateway .
#
# Multi-stage: stubs (protoc) e deps (pip) ficam fora da imagem final, que leva
# so o venv e o codigo do Gateway. Nao tem driver de banco: o Gateway nao
# acessa o PostgreSQL.

ARG PYTHON=3.12

# --------------------------------------------------------------------- stubs
FROM python:${PYTHON}-slim AS stubs
WORKDIR /build
COPY requirements/build.txt requirements/build.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements/build.txt
COPY proto/ proto/
COPY scripts/gerar_stubs.py scripts/gerar_stubs.py
RUN python scripts/gerar_stubs.py

# ---------------------------------------------------------------------- deps
FROM python:${PYTHON}-slim AS deps
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements/comum.txt requirements/gateway.txt /tmp/requirements/
# O pip so serve para instalar: sai do venv antes de ele ir para a imagem final.
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/requirements/gateway.txt \
    && pip uninstall -y pip

# --------------------------------------------------------------------- final
FROM python:${PYTHON}-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH \
    NOME_SERVICO=gateway

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app

COPY --from=deps /opt/venv /opt/venv
COPY src/__init__.py src/__init__.py
COPY src/comum/__init__.py src/comum/canal.py src/comum/registro.py src/comum/resiliencia.py src/comum/
COPY --from=stubs /build/src/gerado/ src/gerado/
COPY src/gateway/ src/gateway/
RUN python -m compileall -q src

USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/saude' % os.getenv('PORT', '8000'), timeout=3)"]
# Porta em PORT (padrao 8000). python -m src.gateway chama o Uvicorn.
CMD ["python", "-m", "src.gateway"]
