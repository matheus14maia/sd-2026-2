"""Inicializacao comum dos servidores gRPC (Catalogo e Pedidos).

Os dois microsservicos sobem do mesmo jeito: ThreadPool, reflection, porta por
variavel de ambiente e encerramento limpo no SIGINT/SIGTERM. So muda o servico
registrado, entao a rotina fica aqui e cada `servidor.py` so passa o que e seu.
"""

import os
import signal
from concurrent import futures
from datetime import datetime
from typing import Callable

import grpc
from grpc_reflection.v1alpha import reflection

ENDERECO_ESCUTA = os.getenv("ENDERECO_ESCUTA", "0.0.0.0")
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))
ENCERRAMENTO_SEGUNDOS = 5


def log(mensagem: str) -> None:
    """Uma linha por chamada, com horario: o log e parte da demonstracao."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {mensagem}", flush=True)


def executar(
    titulo: str,
    nome_completo_servico: str,
    porta: int,
    registrar: Callable[[grpc.Server], None],
    ao_encerrar: Callable[[], None] | None = None,
) -> int:
    servidor = grpc.server(futures.ThreadPoolExecutor(max_workers=MAX_WORKERS))
    registrar(servidor)

    # Reflection permite inspecionar o servico com o grpcurl sem o .proto local.
    reflection.enable_server_reflection(
        (nome_completo_servico, reflection.SERVICE_NAME), servidor
    )
    servidor.add_insecure_port(f"{ENDERECO_ESCUTA}:{porta}")
    servidor.start()

    print("=" * 62, flush=True)
    print(f" {titulo}", flush=True)
    print(f" Servidor gRPC ouvindo em {ENDERECO_ESCUTA}:{porta}", flush=True)
    print(f" Servico: {nome_completo_servico}", flush=True)
    print("=" * 62, flush=True)

    def encerrar(_sinal, _frame):
        print("\nEncerrando o servidor...", flush=True)
        servidor.stop(ENCERRAMENTO_SEGUNDOS)

    signal.signal(signal.SIGINT, encerrar)
    signal.signal(signal.SIGTERM, encerrar)

    servidor.wait_for_termination()
    if ao_encerrar:
        ao_encerrar()
    print("Servidor encerrado.", flush=True)
    return 0
