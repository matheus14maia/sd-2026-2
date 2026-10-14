"""API Gateway (FastAPI): ponto unico de entrada HTTP/JSON do delivery.

Recebe JSON, autentica o token JWT (401 se ausente/invalido), valida o payload
(400 se invalido), traduz para Protobuf e despacha por gRPC para os
microsservicos de Usuarios, Catalogo e Pedidos. Os microsservicos nao sao
expostos para fora: so o Gateway publica porta.

Ordem das camadas de uma requisicao (de fora para dentro):

    CORS -> log -> MiddlewareJWT -> validacao Pydantic -> rota -> gRPC

    uvicorn src.gateway.app:app --host 0.0.0.0 --port 8000
"""

import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

import grpc
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from . import erros
from .autenticacao import SEGREDO, SEGREDO_PADRAO, MiddlewareJWT
from .clientes_grpc import CATALOGO_ENDERECO, PEDIDOS_ENDERECO, USUARIOS_ENDERECO, ClientesGrpc
from .rotas import auth, cardapio, pedidos

# Origens do frontend que o navegador pode usar para chamar o Gateway, separadas
# por virgula. "*" basta porque o token vai no cabecalho Authorization, nao em cookie.
CORS_ORIGENS = [o.strip() for o in os.getenv("CORS_ORIGENS", "*").split(",") if o.strip()]


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    app.state.grpc = ClientesGrpc()
    print(
        f"Gateway -> Usuarios em {USUARIOS_ENDERECO}, Catalogo em {CATALOGO_ENDERECO}, "
        f"Pedidos em {PEDIDOS_ENDERECO}",
        flush=True,
    )
    print(f"CORS liberado para: {', '.join(CORS_ORIGENS)}", flush=True)
    if SEGREDO == SEGREDO_PADRAO:
        print("AVISO: JWT_SEGREDO nao definido, usando o segredo local de desenvolvimento.", flush=True)
    yield
    app.state.grpc.fechar()


app = FastAPI(
    title="Hell's Kitchen - API Gateway",
    description=(
        "Entrada HTTP/JSON do delivery. Autentica com JWT e despacha para os "
        "microsservicos gRPC de Usuarios, Catalogo e Pedidos. Faca POST /auth/login "
        "e use o token no botao Authorize."
    ),
    version="3.0.0",
    lifespan=ciclo_de_vida,
)

app.add_exception_handler(RequestValidationError, erros.validacao_invalida)
app.add_exception_handler(grpc.RpcError, erros.erro_grpc)

app.include_router(auth.router)
app.include_router(cardapio.router)
app.include_router(pedidos.router)

# No Starlette o ultimo middleware adicionado e o mais externo. Ordem final:
# CORS (fora) -> log -> JWT (dentro). Assim o log registra os 401 e ate a
# resposta 401 sai com os cabecalhos de CORS (senao o navegador a esconderia).
app.add_middleware(MiddlewareJWT)


@app.middleware("http")
async def registrar_requisicao(request: Request, chamar_proxima):
    """Uma linha de log por requisicao: metodo, caminho, status, duracao e usuario."""
    inicio = time.perf_counter()
    resposta = await chamar_proxima(request)
    duracao_ms = (time.perf_counter() - inicio) * 1000
    usuario = getattr(request.state, "usuario", None)
    quem = f" [{usuario['login']}]" if usuario else ""
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] {request.method} {request.url.path} "
        f"-> {resposta.status_code} ({duracao_ms:.0f} ms){quem}",
        flush=True,
    )
    return resposta


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGENS,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/saude", tags=["infra"], summary="Verifica se o Gateway esta no ar (200)")
def saude():
    return {"status": "ok"}
