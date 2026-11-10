# Imagem do migrador: aplica db/schema.sql e db/seed.sql e garante o usuario da
# cozinha. Roda uma vez e termina (servico one-shot no compose).
#
#   docker build -f docker/migrador.Dockerfile -t delivery-migrador .
#
# Nao usa gRPC: so o driver do PostgreSQL e o bcrypt.

ARG PYTHON=3.12
# Imagem base: Docker Hub por padrao; o Cloud Build usa o espelho do Google
# (mirror.gcr.io/library/python) para nao esbarrar no limite do Docker Hub.
ARG IMAGEM_PYTHON=python

FROM ${IMAGEM_PYTHON}:${PYTHON}-slim AS deps
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements/banco.txt requirements/migrador.txt /tmp/requirements/
# O pip so serve para instalar: sai do venv antes de ele ir para a imagem final.
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/requirements/migrador.txt \
    && pip uninstall -y pip

FROM ${IMAGEM_PYTHON}:${PYTHON}-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH \
    NOME_SERVICO=migrador

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app

COPY --from=deps /opt/venv /opt/venv
COPY src/__init__.py src/__init__.py
COPY src/comum/__init__.py src/comum/banco.py src/comum/imagens.py src/comum/registro.py src/comum/
COPY db/ db/
COPY scripts/migrar_banco.py scripts/migrar_banco.py

USER app
CMD ["python", "scripts/migrar_banco.py"]
