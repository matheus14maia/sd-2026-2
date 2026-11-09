"""Rotas de saude: o Gateway esta no ar e como estao os microsservicos.

GET /saude           publica: o Gateway responde e o estado dos circuitos.
GET /saude/servicos  com token: health check gRPC (grpc.health.v1) de cada
                     microsservico, com latencia e o estado do circuit breaker.
                     A tela "Saude" do frontend consulta esta rota.
"""

from fastapi import APIRouter, Depends, Request

from ..autenticacao import esquema_bearer

router = APIRouter(prefix="/saude", tags=["infra"])


@router.get("", summary="Gateway no ar e estado dos circuitos (200)")
def saude(request: Request):
    return {"status": "ok", "circuitos": request.app.state.grpc.circuitos()}


@router.get(
    "/servicos",
    summary="Health check gRPC e circuito de cada microsservico (200)",
    dependencies=[Depends(esquema_bearer)],
)
def servicos(request: Request):
    return {"servicos": request.app.state.grpc.verificar_servicos()}
