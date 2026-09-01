"""Servidor gRPC do restaurante.

Este e o Microsservico B do trabalho: fica na VM do GCP, escuta na porta
configurada e responde as chamadas do cliente. Executar com:

    python -m src.servidor.servidor
"""

import os
import signal
import sys
from concurrent import futures

import grpc
from grpc_reflection.v1alpha import reflection

from ..gerado import restaurante_pb2 as pb
from ..gerado import restaurante_pb2_grpc as pb_grpc
from .cardapio import NOME_RESTAURANTE
from .servico import RestauranteService

PORTA = int(os.getenv("PORTA", "50051"))
ENDERECO_ESCUTA = os.getenv("ENDERECO_ESCUTA", "0.0.0.0")
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))
ENCERRAMENTO_SEGUNDOS = 5


def criar_servidor() -> grpc.Server:
    servidor = grpc.server(futures.ThreadPoolExecutor(max_workers=MAX_WORKERS))
    pb_grpc.add_RestauranteServiceServicer_to_server(RestauranteService(), servidor)

    # Reflection permite inspecionar o servico em execucao com ferramentas como
    # o grpcurl, sem precisar do arquivo .proto na maquina que consulta.
    reflection.enable_server_reflection(
        (
            pb.DESCRIPTOR.services_by_name["RestauranteService"].full_name,
            reflection.SERVICE_NAME,
        ),
        servidor,
    )

    servidor.add_insecure_port(f"{ENDERECO_ESCUTA}:{PORTA}")
    return servidor


def main() -> int:
    servidor = criar_servidor()
    servidor.start()

    print("=" * 62, flush=True)
    print(f" {NOME_RESTAURANTE} - servidor gRPC", flush=True)
    print(f" Servidor gRPC ouvindo em {ENDERECO_ESCUTA}:{PORTA}", flush=True)
    print(f" Servico: restaurante.RestauranteService", flush=True)
    print(" Aguardando pedidos... (Ctrl+C encerra)", flush=True)
    print("=" * 62, flush=True)

    def encerrar(_sinal, _frame):
        print("\nEncerrando o servidor...", flush=True)
        servidor.stop(ENCERRAMENTO_SEGUNDOS)

    signal.signal(signal.SIGINT, encerrar)
    signal.signal(signal.SIGTERM, encerrar)

    servidor.wait_for_termination()
    print("Servidor encerrado.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
