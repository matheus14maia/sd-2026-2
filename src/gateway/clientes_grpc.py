"""Clientes gRPC que o Gateway usa para despachar as requisicoes HTTP.

E aqui que acontece a traducao de protocolo: dict (JSON) -> mensagem Protobuf
na ida, mensagem Protobuf -> dict na volta. Os canais sao abertos uma vez, na
subida do Gateway, e reaproveitados por todas as requisicoes.
"""

import os

import grpc
from google.protobuf.json_format import MessageToDict

from ..gerado import catalogo_pb2, catalogo_pb2_grpc, pedidos_pb2, pedidos_pb2_grpc

CATALOGO_ENDERECO = "%s:%s" % (os.getenv("CATALOGO_HOST", "localhost"), os.getenv("CATALOGO_PORTA", "9091"))
PEDIDOS_ENDERECO = "%s:%s" % (os.getenv("PEDIDOS_HOST", "localhost"), os.getenv("PEDIDOS_PORTA", "9090"))
TIMEOUT_SEGUNDOS = float(os.getenv("GRPC_TIMEOUT", "5"))


def para_dict(mensagem) -> dict:
    """Protobuf -> dict com os nomes de campo do .proto e os valores padrao."""
    return MessageToDict(
        mensagem,
        preserving_proto_field_name=True,
        always_print_fields_with_no_presence=True,
    )


class ClientesGrpc:
    def __init__(self) -> None:
        self._canal_catalogo = grpc.insecure_channel(CATALOGO_ENDERECO)
        self._canal_pedidos = grpc.insecure_channel(PEDIDOS_ENDERECO)
        self.catalogo = catalogo_pb2_grpc.CatalogoServiceStub(self._canal_catalogo)
        self.pedidos = pedidos_pb2_grpc.PedidoServiceStub(self._canal_pedidos)

    def fechar(self) -> None:
        self._canal_catalogo.close()
        self._canal_pedidos.close()

    # Catalogo ---------------------------------------------------------------
    def listar_cardapio(self, categoria: str) -> dict:
        resposta = self.catalogo.ListarItens(
            catalogo_pb2.ListarItensRequest(categoria=categoria), timeout=TIMEOUT_SEGUNDOS
        )
        return para_dict(resposta)

    def atualizar_item(self, codigo: str, disponivel: bool, preco: float | None) -> dict:
        requisicao = catalogo_pb2.AtualizarItemRequest(codigo=codigo, disponivel=disponivel)
        if preco is not None:
            requisicao.preco = preco
        return para_dict(self.catalogo.AtualizarItem(requisicao, timeout=TIMEOUT_SEGUNDOS))

    # Pedidos ----------------------------------------------------------------
    def criar_pedido(self, cliente: str, endereco: str, itens: list[dict]) -> dict:
        requisicao = pedidos_pb2.CriarPedidoRequest(
            cliente=cliente,
            endereco=endereco,
            itens=[pedidos_pb2.ItemPedido(codigo=i["codigo"], quantidade=i["quantidade"]) for i in itens],
        )
        return para_dict(self.pedidos.CriarPedido(requisicao, timeout=TIMEOUT_SEGUNDOS))

    def obter_pedido(self, pedido_id: str) -> dict:
        resposta = self.pedidos.ObterPedido(
            pedidos_pb2.ObterPedidoRequest(pedido_id=pedido_id), timeout=TIMEOUT_SEGUNDOS
        )
        return para_dict(resposta)

    def listar_pedidos(self, limite: int) -> list[dict]:
        resposta = self.pedidos.ListarPedidos(
            pedidos_pb2.ListarPedidosRequest(limite=limite), timeout=TIMEOUT_SEGUNDOS
        )
        return para_dict(resposta).get("pedidos", [])

    def atualizar_status(self, pedido_id: str, status: str) -> dict:
        requisicao = pedidos_pb2.AtualizarStatusRequest(
            pedido_id=pedido_id, status=pedidos_pb2.StatusPedido.Value(status)
        )
        return para_dict(self.pedidos.AtualizarStatus(requisicao, timeout=TIMEOUT_SEGUNDOS))
