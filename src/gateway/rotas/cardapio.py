"""Rotas HTTP do cardapio, despachadas para o microsservico de Catalogo.

Ler o cardapio: qualquer usuario logado. Cadastrar, editar, excluir e trocar
foto: so a cozinha (403 para cliente). A foto em si (GET /cardapio/{codigo}/foto)
e publica, porque a tag <img> do navegador nao manda o cabecalho Authorization.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from ...comum.imagens import FOTO_MAXIMO_BYTES, TIPOS_ACEITOS, tipo_da_imagem
from ..autenticacao import esquema_bearer, exigir_papel
from ..erros import RequisicaoInvalida
from ..esquemas import PADRAO_CODIGO, ItemAtualizacao, ItemNovo

router = APIRouter(prefix="/cardapio", tags=["cardapio"], dependencies=[Depends(esquema_bearer)])
publico = APIRouter(prefix="/cardapio", tags=["cardapio"])

SO_COZINHA = [Depends(exigir_papel("cozinha"))]
Codigo = Annotated[str, Path(pattern=PADRAO_CODIGO)]

# Para o Swagger mostrar um campo de arquivo no PUT da foto.
CORPO_FOTO = {
    "requestBody": {
        "required": True,
        "description": "Bytes da foto, ate %d KB. O Content-Type tem que ser o do arquivo." % (FOTO_MAXIMO_BYTES // 1024),
        "content": {tipo: {"schema": {"type": "string", "format": "binary"}} for tipo in TIPOS_ACEITOS},
    }
}


@router.get("", summary="Lista o cardapio (200)")
def listar(request: Request, categoria: str = Query(default="", max_length=50)):
    return request.app.state.grpc.listar_cardapio(categoria.strip())


@router.post("", status_code=201, summary="Cadastra um prato; o codigo sai da categoria (201)",
             dependencies=SO_COZINHA)
def criar(request: Request, corpo: ItemNovo):
    return request.app.state.grpc.criar_item(corpo.model_dump())


@router.patch("/{codigo}", summary="Edita um prato: so os campos enviados mudam (200)", dependencies=SO_COZINHA)
def atualizar(request: Request, corpo: ItemAtualizacao, codigo: Codigo):
    return request.app.state.grpc.atualizar_item(codigo.upper(), corpo.model_dump(exclude_none=True))


@router.delete("/{codigo}", summary="Tira o prato do cardapio (200; repetir nao e erro)", dependencies=SO_COZINHA)
def excluir(request: Request, codigo: Codigo):
    return request.app.state.grpc.excluir_item(codigo.upper())


async def ler_foto(request: Request) -> tuple[str, bytes]:
    """Le o corpo binario e confere tamanho e tipo antes de chamar o Catalogo.

    O tipo vem dos bytes do arquivo e tem que bater com o Content-Type: um PDF
    renomeado para .jpg (ou enviado como image/jpeg) volta 415.
    """
    tamanho = request.headers.get("content-length", "")
    if tamanho.isdigit() and int(tamanho) > FOTO_MAXIMO_BYTES:
        raise RequisicaoInvalida("A foto passa de %d KB." % (FOTO_MAXIMO_BYTES // 1024), 413)
    conteudo = await request.body()
    if not conteudo:
        raise RequisicaoInvalida("Envie a foto no corpo da requisicao.")
    if len(conteudo) > FOTO_MAXIMO_BYTES:
        raise RequisicaoInvalida("A foto passa de %d KB." % (FOTO_MAXIMO_BYTES // 1024), 413)
    declarado = request.headers.get("content-type", "").split(";")[0].strip().lower()
    tipo = tipo_da_imagem(conteudo)
    if not tipo or tipo != declarado:
        raise RequisicaoInvalida("Envie uma foto JPEG, PNG ou WebP (Content-Type image/jpeg, image/png "
                                 "ou image/webp, igual ao do arquivo).", 415)
    return tipo, conteudo


@router.put("/{codigo}/foto", summary="Envia ou troca a foto do prato (200; 413 grande demais; 415 nao e foto)",
            dependencies=SO_COZINHA, openapi_extra=CORPO_FOTO)
def salvar_foto(request: Request, codigo: Codigo, foto: Annotated[tuple[str, bytes], Depends(ler_foto)]):
    tipo, conteudo = foto
    return request.app.state.grpc.salvar_foto(codigo.upper(), tipo, conteudo)


@router.delete("/{codigo}/foto", summary="Tira a foto do prato (200)", dependencies=SO_COZINHA)
def remover_foto(request: Request, codigo: Codigo):
    return request.app.state.grpc.remover_foto(codigo.upper())


@publico.get(
    "/{codigo}/foto",
    summary="Foto do prato (publica, sem token; 404 se o prato nao tem foto)",
    response_class=Response,
    responses={200: {"description": "Bytes da foto", "content": {tipo: {} for tipo in TIPOS_ACEITOS}}},
)
def foto(
    request: Request,
    codigo: Codigo,
    v: str = Query(default="", max_length=64, description="Versao da foto (vem pronta no campo foto do item)"),
):
    foto = request.app.state.grpc.obter_foto(codigo.upper())
    etag = '"%s"' % foto["versao"]
    cabecalhos = {
        "ETag": etag,
        # URL com a versao atual nunca muda de conteudo: o navegador guarda de vez.
        # Sem versao (ou com uma antiga), o navegador confere a cada uso (304).
        "Cache-Control": "public, max-age=31536000, immutable" if v == foto["versao"] else "no-cache",
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=cabecalhos)
    return Response(content=foto["conteudo"], media_type=foto["tipo"], headers=cabecalhos)
