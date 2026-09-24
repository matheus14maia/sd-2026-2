"""Cliente gRPC que o microsservico de Pedidos usa para falar com o Catalogo.

Comunicacao entre microsservicos: Pedidos nao le a tabela itens_cardapio, ele
pergunta ao Catalogo, que e o dono desses dados.
"""

import os

import grpc

from ..gerado import catalogo_pb2 as catalogo_pb
from ..gerado import catalogo_pb2_grpc as catalogo_grpc

CATALOGO_HOST = os.getenv("CATALOGO_HOST", "localhost")
CATALOGO_PORTA = int(os.getenv("CATALOGO_PORTA", "9091"))
# Menor que o prazo do Gateway (5 s): assim a falha do Catalogo volta como
# "Catalogo indisponivel" antes de o Gateway desistir por timeout.
TIMEOUT_SEGUNDOS = float(os.getenv("CATALOGO_TIMEOUT", "3"))


class ClienteCatalogo:
    def __init__(self) -> None:
        self.endereco = f"{CATALOGO_HOST}:{CATALOGO_PORTA}"
        self.canal = grpc.insecure_channel(self.endereco)
        self.stub = catalogo_grpc.CatalogoServiceStub(self.canal)

    def consultar(self, codigos: list[str]) -> dict[str, catalogo_pb.ItemCardapio]:
        """Itens encontrados, indexados pelo codigo. Pode lancar grpc.RpcError."""
        resposta = self.stub.ConsultarItens(
            catalogo_pb.ConsultarItensRequest(codigos=codigos),
            timeout=TIMEOUT_SEGUNDOS,
        )
        return {item.codigo: item for item in resposta.itens}

    def fechar(self) -> None:
        self.canal.close()
