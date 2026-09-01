# Imagem unica usada pelos dois microsservicos. O papel (servidor ou cliente)
# e escolhido pelo comando passado no docker compose.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY proto/ ./proto/
COPY scripts/ ./scripts/
COPY src/ ./src/

# Os stubs sao gerados no build a partir do contrato .proto, nunca versionados.
RUN python scripts/gerar_stubs.py

EXPOSE 50051

CMD ["python", "-m", "src.servidor.servidor"]
