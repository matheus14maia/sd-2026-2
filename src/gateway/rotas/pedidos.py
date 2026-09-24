"""Rotas HTTP de pedidos, despachadas para o microsservico de Pedidos."""

from fastapi import APIRouter, Query, Request, status

from ..esquemas import PedidoEntrada, StatusEntrada

router = APIRouter(prefix="/pedidos", tags=["pedidos"])


@router.post("", status_code=status.HTTP_201_CREATED, summary="Cria um pedido (201)")
def criar(request: Request, corpo: PedidoEntrada):
    pedido = request.app.state.grpc.criar_pedido(
        corpo.cliente, corpo.endereco, [item.model_dump() for item in corpo.itens]
    )
    return {"mensagem": "Pedido criado com sucesso", "pedido": pedido}


@router.get("", summary="Lista os pedidos mais recentes (200)")
def listar(request: Request, limite: int = Query(default=20, gt=0, le=200)):
    return {"pedidos": request.app.state.grpc.listar_pedidos(limite)}


@router.get("/{pedido_id}", summary="Consulta um pedido (200 / 404)")
def obter(request: Request, pedido_id: str):
    return request.app.state.grpc.obter_pedido(pedido_id)


@router.patch("/{pedido_id}/status", summary="Avanca o status do pedido (200 / 409)")
def atualizar_status(request: Request, pedido_id: str, corpo: StatusEntrada):
    pedido = request.app.state.grpc.atualizar_status(pedido_id, corpo.status)
    return {"mensagem": "Status atualizado", "pedido": pedido}
