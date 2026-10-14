"""Microsservico de Usuarios (gRPC). Dono da tabela usuarios.

    python -m src.usuarios.servidor
"""

import os
import sys

from ..comum.banco import criar_pool, descricao_destino
from ..comum.servidor_grpc import executar
from ..gerado import usuarios_pb2 as pb
from ..gerado import usuarios_pb2_grpc as pb_grpc
from .repositorio import RepositorioUsuarios
from .servico import UsuarioService

PORTA = int(os.getenv("PORTA", "9092"))


def main() -> int:
    print("Conectando ao banco", descricao_destino(), flush=True)
    pool = criar_pool()
    servico = UsuarioService(RepositorioUsuarios(pool))

    return executar(
        titulo="Microsservico de Usuarios",
        nome_completo_servico=pb.DESCRIPTOR.services_by_name["UsuarioService"].full_name,
        porta=PORTA,
        registrar=lambda servidor: pb_grpc.add_UsuarioServiceServicer_to_server(servico, servidor),
        ao_encerrar=pool.close,
    )


if __name__ == "__main__":
    sys.exit(main())
