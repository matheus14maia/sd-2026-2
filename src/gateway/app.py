"""API Gateway (FastAPI): ponto unico de entrada HTTP/JSON do delivery.

Recebe JSON, valida o payload (400 se invalido), traduz para Protobuf e
despacha por gRPC para os microsservicos de Catalogo e Pedidos. Os
microsservicos nao sao expostos para fora: so o Gateway publica porta.

    uvicorn src.gateway.app:app --host 0.0.0.0 --port 8000
"""

import time
from contextlib import asynccontextmanager
from datetime import datetime

import grpc
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from . import erros
from .clientes_grpc import CATALOGO_ENDERECO, PEDIDOS_ENDERECO, ClientesGrpc
from .rotas import cardapio, pedidos


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    app.state.grpc = ClientesGrpc()
    print(f"Gateway -> Catalogo em {CATALOGO_ENDERECO}, Pedidos em {PEDIDOS_ENDERECO}", flush=True)
    yield
    app.state.grpc.fechar()


app = FastAPI(
    title="Hell's Kitchen - API Gateway",
    description="Entrada HTTP/JSON do delivery. Despacha para os microsservicos gRPC de Catalogo e Pedidos.",
    version="2.0.0",
    lifespan=ciclo_de_vida,
)

app.add_exception_handler(RequestValidationError, erros.validacao_invalida)
app.add_exception_handler(grpc.RpcError, erros.erro_grpc)

app.include_router(cardapio.router)
app.include_router(pedidos.router)


@app.middleware("http")
async def registrar_requisicao(request: Request, chamar_proxima):
    """Uma linha de log por requisicao: metodo, caminho, status e duracao."""
    inicio = time.perf_counter()
    resposta = await chamar_proxima(request)
    duracao_ms = (time.perf_counter() - inicio) * 1000
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] {request.method} {request.url.path} "
        f"-> {resposta.status_code} ({duracao_ms:.0f} ms)",
        flush=True,
    )
    return resposta


@app.get("/saude", tags=["infra"], summary="Verifica se o Gateway esta no ar (200)")
def saude():
    return {"status": "ok"}
