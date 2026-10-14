"""Rotas HTTP do cardapio, despachadas para o microsservico de Catalogo."""

from fastapi import APIRouter, Depends, Path, Query, Request

from ..autenticacao import esquema_bearer, exigir_papel
from ..esquemas import PADRAO_CODIGO, ItemAtualizacao

router = APIRouter(prefix="/cardapio", tags=["cardapio"], dependencies=[Depends(esquema_bearer)])


@router.get("", summary="Lista o cardapio (200)")
def listar(request: Request, categoria: str = Query(default="", max_length=50)):
    return request.app.state.grpc.listar_cardapio(categoria.strip())


@router.patch(
    "/{codigo}",
    summary="Altera disponibilidade/preco de um item (200; 403 se nao for cozinha)",
    dependencies=[Depends(exigir_papel("cozinha"))],
)
def atualizar(
    request: Request,
    corpo: ItemAtualizacao,
    codigo: str = Path(pattern=PADRAO_CODIGO),
):
    return request.app.state.grpc.atualizar_item(codigo.upper(), corpo.disponivel, corpo.preco)
