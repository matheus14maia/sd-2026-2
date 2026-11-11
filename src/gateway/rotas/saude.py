"""Rotas de saude: o Gateway esta no ar e como estao os microsservicos.

GET /saude           publica: o Gateway responde e o estado dos circuitos.
GET /saude/servicos  papel cozinha: health check gRPC (grpc.health.v1) de cada
                     microsservico, com latencia, o estado do circuit breaker e
                     o stream de tempo real. A tela "Saude" do frontend consulta
                     esta rota. Cliente recebe 403: e informacao de operacao.
"""

from fastapi import APIRouter, Depends, Request

from ..autenticacao import esquema_bearer, exigir_papel

router = APIRouter(prefix="/saude", tags=["infra"])


@router.get("", summary="Gateway no ar e estado dos circuitos (200)")
def saude(request: Request):
    return {"status": "ok", "circuitos": request.app.state.grpc.circuitos()}


@router.get(
    "/servicos",
    summary="Health check gRPC e circuito de cada microsservico (200; 403 se nao for cozinha)",
    dependencies=[Depends(esquema_bearer), Depends(exigir_papel("cozinha"))],
)
def servicos(request: Request):
    return {
        "servicos": request.app.state.grpc.verificar_servicos(),
        "tempo_real": request.app.state.eventos.resumo(),
    }
