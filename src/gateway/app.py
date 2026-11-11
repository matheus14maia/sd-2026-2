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
from contextlib import asynccontextmanager, nullcontext

import grpc
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from ..comum.rastreamento import SpanKind, Status, StatusCode, configurar, encerrar, extrair, tracer
from ..comum.registro import ids_atuais, log
from ..comum.resiliencia import CircuitoAberto
from . import erros
from .autenticacao import SEGREDO_DEFINIDO, AcessoNegado, MiddlewareJWT
from .clientes_grpc import ClientesGrpc
from .eventos import RetransmissorEventos
from .rotas import auth, cardapio, conta, pedidos, saude

# Origens do frontend que o navegador pode usar para chamar o Gateway, separadas
# por virgula. "*" basta porque o token vai no cabecalho Authorization, nao em cookie.
CORS_ORIGENS = [o.strip() for o in os.getenv("CORS_ORIGENS", "*").split(",") if o.strip()]
# Sondas de saude (HEALTHCHECK a cada 15 s, tela Saude a cada 3 s) nao viram
# trace: seriam milhares de traces iguais escondendo as requisicoes de verdade.
SEM_RASTREAMENTO = ("/saude",)

DESTINO_RASTREAMENTO = configurar(os.getenv("NOME_SERVICO", "gateway"))


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    app.state.grpc = ClientesGrpc()
    app.state.eventos = RetransmissorEventos(app.state.grpc)
    log("Gateway -> " + ClientesGrpc.destinos())
    log("CORS liberado para: " + ", ".join(CORS_ORIGENS))
    log("Rastreamento: " + DESTINO_RASTREAMENTO)
    if not SEGREDO_DEFINIDO:
        log("JWT_SEGREDO nao definido; segredo sorteado nesta subida.", "WARNING")
    yield
    app.state.eventos.encerrar()
    app.state.grpc.fechar()
    encerrar()


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
app.add_exception_handler(erros.RequisicaoInvalida, erros.requisicao_invalida)

app.include_router(auth.router)
app.include_router(conta.router)
app.include_router(cardapio.router)
app.include_router(cardapio.publico)
app.include_router(pedidos.router)
app.include_router(saude.router)

# No Starlette o ultimo middleware adicionado e o mais externo. Ordem final:
# CORS (fora) -> log -> JWT (dentro). Assim o log registra os 401 e ate a
# resposta 401 sai com os cabecalhos de CORS (senao o navegador a esconderia).
app.add_middleware(MiddlewareJWT)


@app.middleware("http")
async def registrar_requisicao(request: Request, chamar_proxima):
    """Span da requisicao + uma linha de log: metodo, caminho, status, duracao e usuario.

    O span (SERVER) continua o trace que o Cloud Run informa nos cabecalhos (ou
    comeca um novo) e e o pai de tudo o que esta requisicao fizer: as chamadas
    gRPC levam o contexto nos metadados. O trace id volta para o navegador no
    cabecalho X-Requisicao-Id: com ele se acha a requisicao nos logs de todos
    os servicos e no Cloud Trace.
    """
    caminho = request.url.path
    if caminho.startswith(SEM_RASTREAMENTO):
        contexto_span = nullcontext(None)
    else:
        contexto_span = tracer.start_as_current_span(
            f"{request.method} {caminho}",
            context=extrair(request.headers),
            kind=SpanKind.SERVER,
            attributes={"http.request.method": request.method, "url.path": caminho},
        )
    with contexto_span as span:
        inicio = time.perf_counter()
        resposta = await chamar_proxima(request)
        duracao_ms = (time.perf_counter() - inicio) * 1000
        usuario = getattr(request.state, "usuario", None)
        if span is not None:
            # Nome pela rota (/pedidos/{pedido_id}), nao pelo caminho com o id.
            rota = getattr(request.scope.get("route"), "path", None)
            if rota:
                span.update_name(f"{request.method} {rota}")
                span.set_attribute("http.route", rota)
            span.set_attribute("http.response.status_code", resposta.status_code)
            if usuario:
                span.set_attribute("enduser.id", usuario["login"])
            if resposta.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR, "HTTP %d" % resposta.status_code))
        quem = f" [{usuario['login']}]" if usuario else ""
        log(
            f"{request.method} {caminho} -> {resposta.status_code} ({duracao_ms:.0f} ms){quem}",
            "ERROR" if resposta.status_code >= 500 else "INFO",
            metodo=request.method,
            caminho=caminho,
            status=resposta.status_code,
            duracao_ms=round(duracao_ms),
            usuario=usuario["login"] if usuario else "",
        )
        trace_id = ids_atuais()[0]
        if trace_id:
            resposta.headers["X-Requisicao-Id"] = trace_id
        return resposta


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGENS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    # Sem isso o JavaScript do frontend nao enxerga estes cabecalhos.
    expose_headers=["X-Requisicao-Id", "Retry-After"],
)
