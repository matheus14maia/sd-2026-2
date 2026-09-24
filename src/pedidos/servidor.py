"""Microsservico de Pedidos (gRPC). Dono das tabelas pedidos e itens_pedido.

    python -m src.pedidos.servidor
"""

import os
import sys

from ..comum.banco import criar_pool, descricao_destino
from ..comum.servidor_grpc import executar
from ..gerado import pedidos_pb2 as pb
from ..gerado import pedidos_pb2_grpc as pb_grpc
from .cliente_catalogo import ClienteCatalogo
from .repositorio import RepositorioPedidos
from .servico import PedidoService

PORTA = int(os.getenv("PORTA", "9090"))


def main() -> int:
    print("Conectando ao banco", descricao_destino(), flush=True)
    pool = criar_pool()
    catalogo = ClienteCatalogo()
    print("Catalogo em", catalogo.endereco, flush=True)
    servico = PedidoService(RepositorioPedidos(pool), catalogo)

    def encerrar() -> None:
        catalogo.fechar()
        pool.close()

    return executar(
        titulo="Microsservico de Pedidos",
        nome_completo_servico=pb.DESCRIPTOR.services_by_name["PedidoService"].full_name,
        porta=PORTA,
        registrar=lambda servidor: pb_grpc.add_PedidoServiceServicer_to_server(servico, servidor),
        ao_encerrar=encerrar,
    )


if __name__ == "__main__":
    sys.exit(main())
