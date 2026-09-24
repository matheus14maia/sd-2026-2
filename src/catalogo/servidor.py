"""Microsservico de Catalogo (gRPC). Dono da tabela itens_cardapio.

    python -m src.catalogo.servidor
"""

import os
import sys

from ..comum.banco import criar_pool, descricao_destino
from ..comum.servidor_grpc import executar
from ..gerado import catalogo_pb2 as pb
from ..gerado import catalogo_pb2_grpc as pb_grpc
from .repositorio import RepositorioCatalogo
from .servico import NOME_RESTAURANTE, CatalogoService

PORTA = int(os.getenv("PORTA", "9091"))


def main() -> int:
    print("Conectando ao banco", descricao_destino(), flush=True)
    pool = criar_pool()
    servico = CatalogoService(RepositorioCatalogo(pool))

    return executar(
        titulo=f"{NOME_RESTAURANTE} - microsservico de Catalogo",
        nome_completo_servico=pb.DESCRIPTOR.services_by_name["CatalogoService"].full_name,
        porta=PORTA,
        registrar=lambda servidor: pb_grpc.add_CatalogoServiceServicer_to_server(servico, servidor),
        ao_encerrar=pool.close,
    )


if __name__ == "__main__":
    sys.exit(main())
