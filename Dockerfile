# Imagem unica para os tres papeis (gateway, pedidos, catalogo) e o migrador:
# o docker-compose.yml escolhe o papel pelo `command`.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY proto/ ./proto/
COPY scripts/ ./scripts/
COPY db/ ./db/
COPY src/ ./src/
RUN python scripts/gerar_stubs.py

EXPOSE 8000 9090 9091
CMD ["uvicorn", "src.gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
