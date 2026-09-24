"""Rotas HTTP do cardapio, despachadas para o microsservico de Catalogo."""

from fastapi import APIRouter, Path, Query, Request

from ..esquemas import ItemAtualizacao

router = APIRouter(prefix="/cardapio", tags=["cardapio"])


@router.get("", summary="Lista o cardapio (200)")
def listar(request: Request, categoria: str = Query(default="", max_length=50)):
    return request.app.state.grpc.listar_cardapio(categoria.strip())


@router.patch("/{codigo}", summary="Altera disponibilidade/preco de um item (200)")
def atualizar(
    request: Request,
    corpo: ItemAtualizacao,
    codigo: str = Path(pattern=r"^[A-Za-z]{2}[0-9]{2}$"),
):
    return request.app.state.grpc.atualizar_item(codigo.upper(), corpo.disponivel, corpo.preco)
