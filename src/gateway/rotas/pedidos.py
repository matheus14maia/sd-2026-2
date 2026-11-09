"""Rotas HTTP de pedidos, despachadas para o microsservico de Pedidos.

O dono do pedido vem sempre do token JWT, nunca do corpo da requisicao:
  - POST /pedidos grava o pedido com o id e o nome do usuario do token;
  - papel cliente so lista e consulta os proprios pedidos (pedido de outro
    usuario responde 404, sem revelar que o id existe);
  - papel cozinha ve todos os pedidos e avanca as etapas.
"""

from fastapi import APIRouter, Depends, Query, Request, status

from ..autenticacao import esquema_bearer, exigir_papel
from ..esquemas import PedidoEntrada, StatusEntrada

router = APIRouter(prefix="/pedidos", tags=["pedidos"], dependencies=[Depends(esquema_bearer)])


def _filtro_dono(request: Request) -> str:
    """usuario_id para filtrar os pedidos: '' (todos) para a cozinha, o proprio id para cliente."""
    usuario = request.state.usuario
    return "" if usuario.get("papel") == "cozinha" else usuario["sub"]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Cria um pedido em nome do dono do token (201)")
def criar(request: Request, corpo: PedidoEntrada):
    usuario = request.state.usuario
    pedido = request.app.state.grpc.criar_pedido(
        usuario["sub"], usuario["nome"], corpo.endereco, [item.model_dump() for item in corpo.itens]
    )
    return {"mensagem": "Pedido criado com sucesso", "pedido": pedido}


@router.get("", summary="Lista os pedidos: os seus (cliente) ou todos (cozinha) (200)")
def listar(request: Request, limite: int = Query(default=20, gt=0, le=200)):
    dono = _filtro_dono(request)
    return {
        "escopo": "todos" if not dono else "meus",
        "pedidos": request.app.state.grpc.listar_pedidos(limite, dono),
    }


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
