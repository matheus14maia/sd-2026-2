"""Implementacao do CatalogoService definido em proto/catalogo.proto.

Toda leitura e alteracao passa pelo PostgreSQL (RepositorioCatalogo). Erros
viram status code do gRPC via context.abort, e quem chama (Gateway ou Pedidos)
decide como apresentar.
"""

import os

import grpc

from ..comum.servidor_grpc import log
from ..gerado import catalogo_pb2 as pb
from ..gerado import catalogo_pb2_grpc as pb_grpc
from .repositorio import RepositorioCatalogo

NOME_RESTAURANTE = os.getenv("NOME_RESTAURANTE", "Hell's Kitchen")


def _normalizar(codigo: str) -> str:
    return (codigo or "").strip().upper()


def _para_proto(linha: dict) -> pb.ItemCardapio:
    return pb.ItemCardapio(**linha)


class CatalogoService(pb_grpc.CatalogoServiceServicer):
    def __init__(self, repositorio: RepositorioCatalogo) -> None:
        self.repositorio = repositorio

    def ListarItens(self, request, context):
        itens = self.repositorio.listar(request.categoria)
        log("ListarItens: categoria=%r -> %d itens" % (request.categoria or "todas", len(itens)))
        if request.categoria and not itens:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                "Categoria '%s' nao existe no cardapio." % request.categoria,
            )
        return pb.ListarItensResponse(
            restaurante=NOME_RESTAURANTE,
            itens=[_para_proto(linha) for linha in itens],
        )

    def ConsultarItens(self, request, context):
        codigos = sorted({_normalizar(c) for c in request.codigos if c.strip()})
        itens = self.repositorio.buscar_varios(codigos)
        log("ConsultarItens: %s -> %d encontrados" % (codigos, len(itens)))
        return pb.ConsultarItensResponse(itens=[_para_proto(linha) for linha in itens])

    def AtualizarItem(self, request, context):
        codigo = _normalizar(request.codigo)
        preco = request.preco if request.HasField("preco") else None
        log("AtualizarItem: codigo=%s disponivel=%s preco=%s" % (codigo, request.disponivel, preco))

        if preco is not None and preco <= 0:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "O preco deve ser maior que zero.")

        linha = self.repositorio.atualizar(codigo, request.disponivel, preco)
        if linha is None:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                "Item '%s' nao existe no cardapio." % codigo,
            )
        return _para_proto(linha)
