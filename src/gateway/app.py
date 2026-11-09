"""API Gateway (FastAPI): ponto unico de entrada HTTP/JSON do delivery.

Recebe JSON, autentica o token JWT (401 se ausente/invalido), valida o payload
(400 se invalido), traduz para Protobuf e despacha por gRPC para os
microsservicos de Usuarios, Catalogo e Pedidos. Os microsservicos nao sao
expostos para fora: so o Gateway publica porta.

Ordem das camadas de uma requisicao (de fora para dentro):

    CORS -> log + trace -> MiddlewareJWT (401) -> papel (403) -> validacao Pydantic (400) -> rota
         -> ClienteResiliente (prazo, retry, circuit breaker) -> gRPC

    python -m src.gateway          (porta em PORT, padrao 8000)
"""

import os
import time
from contextlib import asynccontextmanager

import grpc
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from ..comum.registro import log, novo_trace, trace_atual, trace_de_cabecalhos
from ..comum.resiliencia import CircuitoAberto
from . import erros
from .autenticacao import SEGREDO_DEFINIDO, AcessoNegado, MiddlewareJWT
from .clientes_grpc import ClientesGrpc
from .eventos import RetransmissorEventos
from .rotas import auth, cardapio, pedidos, saude

# Origens do frontend que o navegador pode usar para chamar o Gateway, separadas
# por virgula. "*" basta porque o token vai no cabecalho Authorization, nao em cookie.
CORS_ORIGENS = [o.strip() for o in os.getenv("CORS_ORIGENS", "*").split(",") if o.strip()]


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    app.state.grpc = ClientesGrpc()
    app.state.eventos = RetransmissorEventos(app.state.grpc)
    log("Gateway -> " + ClientesGrpc.destinos())
    log("CORS liberado para: " + ", ".join(CORS_ORIGENS))
    if not SEGREDO_DEFINIDO:
        log("JWT_SEGREDO nao definido; segredo sorteado nesta subida.", "WARNING")
    yield
    app.state.eventos.encerrar()
    app.state.grpc.fechar()


app = FastAPI(
    title="Hell's Kitchen - API Gateway",
    description=(
        "Entrada HTTP/JSON do delivery. Autentica com JWT e despacha para os "
        "microsservicos gRPC de Usuarios, Catalogo e Pedidos, com retry, circuit "
        "breaker e fallback. Faca POST /auth/login e use o token no botao Authorize."
    ),
    version="4.0.0",
    lifespan=ciclo_de_vida,
)

app.add_exception_handler(RequestValidationError, erros.validacao_invalida)
app.add_exception_handler(grpc.RpcError, erros.erro_grpc)
app.add_exception_handler(AcessoNegado, erros.acesso_negado)
app.add_exception_handler(CircuitoAberto, erros.circuito_aberto)

app.include_router(auth.router)
app.include_router(cardapio.router)
app.include_router(pedidos.router)
app.include_router(saude.router)

# No Starlette o ultimo middleware adicionado e o mais externo. Ordem final:
# CORS (fora) -> log -> JWT (dentro). Assim o log registra os 401 e ate a
# resposta 401 sai com os cabecalhos de CORS (senao o navegador a esconderia).
app.add_middleware(MiddlewareJWT)


@app.middleware("http")
async def registrar_requisicao(request: Request, chamar_proxima):
    """Trace da requisicao + uma linha de log: metodo, caminho, status, duracao e usuario.

    O trace vem do cabecalho que o Cloud Run injeta (ou e sorteado aqui), segue
    para os microsservicos nos metadados gRPC e volta para o navegador no
    cabecalho X-Requisicao-Id: com ele se acha a requisicao nos logs de todos
    os servicos.
    """
    trace = trace_de_cabecalhos(request.headers.get) or novo_trace()
    marca = trace_atual.set(trace)
    inicio = time.perf_counter()
    try:
        resposta = await chamar_proxima(request)
        duracao_ms = (time.perf_counter() - inicio) * 1000
        usuario = getattr(request.state, "usuario", None)
        quem = f" [{usuario['login']}]" if usuario else ""
        log(
            f"{request.method} {request.url.path} -> {resposta.status_code} ({duracao_ms:.0f} ms){quem}",
            "ERROR" if resposta.status_code >= 500 else "INFO",
            metodo=request.method,
            caminho=request.url.path,
            status=resposta.status_code,
            duracao_ms=round(duracao_ms),
            usuario=usuario["login"] if usuario else "",
        )
        resposta.headers["X-Requisicao-Id"] = trace
        return resposta
    finally:
        trace_atual.reset(marca)


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGENS,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    # Sem isso o JavaScript do frontend nao enxerga estes cabecalhos.
    expose_headers=["X-Requisicao-Id", "Retry-After"],
)
