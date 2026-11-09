"""Rotas HTTP de pedidos, despachadas para o microsservico de Pedidos.

O dono do pedido vem sempre do token JWT, nunca do corpo da requisicao:
  - POST /pedidos grava o pedido com o id e o nome do usuario do token;
  - papel cliente so lista e consulta os proprios pedidos (pedido de outro
    usuario responde 404, sem revelar que o id existe);
  - papel cozinha ve todos os pedidos e avanca as etapas.

GET /pedidos aceita filtros opcionais (etapa, periodo, item, cliente), aplicados
no banco pelo Pedidos. GET /pedidos/eventos e um fluxo Server-Sent Events: a
tela recebe cada pedido criado ou com etapa alterada sem precisar de F5.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse

from ..autenticacao import esquema_bearer, exigir_papel
from ..esquemas import ETAPAS, PADRAO_CODIGO, PedidoEntrada, StatusEntrada
from ..eventos import mensagem_sse

router = APIRouter(prefix="/pedidos", tags=["pedidos"], dependencies=[Depends(esquema_bearer)])

FiltroEtapa = Literal["EM_ANDAMENTO", "RECEBIDO", "EM_PREPARO", "PRONTO", "SAIU_PARA_ENTREGA", "ENTREGUE"]
FiltroPeriodo = Literal["hoje", "7d", "30d"]
# Sem evento por este tempo, o fluxo manda um comentario (": ping") para a
# conexao nao ser fechada por proxy ou navegador ociosos.
PING_SSE_SEGUNDOS = 15


def _filtro_dono(request: Request) -> str:
    """usuario_id para filtrar os pedidos: '' (todos) para a cozinha, o proprio id para cliente."""
    usuario = request.state.usuario
    return "" if usuario.get("papel") == "cozinha" else usuario["sub"]


def _etapas(etapa: str | None) -> list[str]:
    if not etapa:
        return []
    if etapa == "EM_ANDAMENTO":
        return [e for e in ETAPAS if e != "ENTREGUE"]
    return [etapa]


def _criado_desde(periodo: str | None) -> str:
    """Inicio do periodo no fuso do servidor (TZ=America/Sao_Paulo), em ISO 8601."""
    if not periodo:
        return ""
    agora = datetime.now().astimezone()
    if periodo == "hoje":
        inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        inicio = agora - timedelta(days=int(periodo.rstrip("d")))
    return inicio.isoformat(timespec="seconds")


@router.post("", status_code=status.HTTP_201_CREATED, summary="Cria um pedido em nome do dono do token (201)")
def criar(request: Request, corpo: PedidoEntrada):
    usuario = request.state.usuario
    pedido = request.app.state.grpc.criar_pedido(
        usuario["sub"], usuario["nome"], corpo.endereco, [item.model_dump() for item in corpo.itens]
    )
    return {"mensagem": "Pedido criado com sucesso", "pedido": pedido}


@router.get("", summary="Lista os pedidos: os seus (cliente) ou todos (cozinha), com filtros opcionais (200)")
def listar(
    request: Request,
    limite: int = Query(default=20, gt=0, le=200),
    etapa: FiltroEtapa | None = Query(default=None, description="etapa do pedido; EM_ANDAMENTO = ainda nao entregue"),
    periodo: FiltroPeriodo | None = Query(default=None, description="hoje, 7d (ultimos 7 dias) ou 30d"),
    item: str | None = Query(default=None, pattern=PADRAO_CODIGO, description="pedidos com este item (ex.: PR01)"),
    cliente: str | None = Query(default=None, max_length=100, description="trecho do nome do cliente"),
):
    dono = _filtro_dono(request)
    pedidos = request.app.state.grpc.listar_pedidos(
        limite,
        dono,
        status=_etapas(etapa),
        criado_desde=_criado_desde(periodo),
        codigo_item=(item or "").upper(),
        cliente=(cliente or "").strip(),
    )
    return {
        "escopo": "todos" if not dono else "meus",
        "filtros": {"etapa": etapa, "periodo": periodo, "item": (item or "").upper() or None,
                    "cliente": (cliente or "").strip() or None},
        "pedidos": pedidos,
    }


# Declarada antes de /{pedido_id}: senao "eventos" seria lido como um id de pedido.
@router.get(
    "/eventos",
    summary="Atualizacoes dos pedidos em tempo real (Server-Sent Events)",
    response_class=StreamingResponse,
)
async def eventos(request: Request):
    retransmissor = request.app.state.eventos
    fila: asyncio.Queue = asyncio.Queue(maxsize=200)
    ident = retransmissor.assinar(asyncio.get_running_loop(), fila, _filtro_dono(request) or None)

    async def gerar():
        try:
            yield "retry: 3000\n\n"
            yield mensagem_sse("estado", {"conectado": retransmissor.conectado})
            while True:
                try:
                    yield await asyncio.wait_for(fila.get(), timeout=PING_SSE_SEGUNDOS)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            retransmissor.cancelar(ident)

    return StreamingResponse(
        gerar(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{pedido_id}", summary="Consulta um pedido seu (cliente) ou qualquer um (cozinha) (200 / 404)")
def obter(request: Request, pedido_id: str):
    return request.app.state.grpc.obter_pedido(pedido_id, _filtro_dono(request))


@router.patch(
    "/{pedido_id}/status",
    summary="Avanca o status do pedido (200 / 409; 403 se nao for cozinha)",
    dependencies=[Depends(exigir_papel("cozinha"))],
)
def atualizar_status(request: Request, pedido_id: str, corpo: StatusEntrada):
    pedido = request.app.state.grpc.atualizar_status(pedido_id, corpo.status)
    return {"mensagem": "Status atualizado", "pedido": pedido}
