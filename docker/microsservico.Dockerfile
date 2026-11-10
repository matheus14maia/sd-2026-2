# Imagem de um microsservico gRPC (Usuarios, Catalogo ou Pedidos). O mesmo
# arquivo gera as tres imagens; o servico e escolhido pelo argumento SERVICO:
#
#   docker build -f docker/microsservico.Dockerfile --build-arg SERVICO=catalogo -t delivery-catalogo .
#
# Multi-stage: so o ultimo estagio vira a imagem final.
#   stubs  compila os .proto (grpcio-tools e o protoc ficam so aqui)
#   deps   instala as dependencias num venv (cache do pip e ferramentas ficam aqui)
#   final  python slim + venv + codigo do servico, rodando sem root

ARG PYTHON=3.12
# Imagem base: Docker Hub por padrao; o Cloud Build usa o espelho do Google
# (mirror.gcr.io/library/python) para nao esbarrar no limite do Docker Hub.
ARG IMAGEM_PYTHON=python

# --------------------------------------------------------------------- stubs
FROM ${IMAGEM_PYTHON}:${PYTHON}-slim AS stubs
WORKDIR /build
COPY requirements/build.txt requirements/build.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements/build.txt
COPY proto/ proto/
COPY scripts/gerar_stubs.py scripts/gerar_stubs.py
RUN python scripts/gerar_stubs.py

# ---------------------------------------------------------------------- deps
FROM ${IMAGEM_PYTHON}:${PYTHON}-slim AS deps
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
# So os arquivos de dependencia: a camada fica em cache enquanto eles nao mudam,
# e mudar o codigo nao reinstala nada.
COPY requirements/comum.txt requirements/banco.txt requirements/rastreamento.txt requirements/servicos.txt /tmp/requirements/
# O pip so serve para instalar: sai do venv antes de ele ir para a imagem final.
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/requirements/servicos.txt \
    && pip uninstall -y pip

# --------------------------------------------------------------------- final
FROM ${IMAGEM_PYTHON}:${PYTHON}-slim
ARG SERVICO
RUN test -n "$SERVICO" || (echo "Informe --build-arg SERVICO=usuarios|catalogo|pedidos" >&2 && exit 1)

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH \
    SERVICO=${SERVICO} \
    NOME_SERVICO=${SERVICO}

# Usuario sem privilegio: o processo nao roda como root dentro do container.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app

COPY --from=deps /opt/venv /opt/venv
COPY src/__init__.py src/__init__.py
COPY src/comum/ src/comum/
COPY --from=stubs /build/src/gerado/ src/gerado/
COPY src/${SERVICO}/ src/${SERVICO}/
# Bytecode pronto na imagem: o servico sobe mais rapido.
RUN python -m compileall -q src

USER app
# Porta do servico: usuarios 9092, catalogo 9091, pedidos 9090 (ou a de PORT).
EXPOSE 9090 9091 9092
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-m", "src.comum.sonda_saude"]
# exec: o Python vira o PID 1 e recebe o SIGTERM do `docker stop` (encerramento limpo).
CMD ["sh", "-c", "exec python -m src.${SERVICO}.servidor"]
