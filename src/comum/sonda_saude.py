"""Health check do container de um microsservico (HEALTHCHECK do Dockerfile).

Pergunta ao proprio servico, pelo protocolo padrao grpc.health.v1, se ele esta
SERVING. Sai com 0 (saudavel) ou 1. A porta segue a mesma regra do servidor:
PORT > PORTA > porta padrao do servico.

    python -m src.comum.sonda_saude
"""

import os
import sys

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

PORTAS_PADRAO = {"usuarios": 9092, "catalogo": 9091, "pedidos": 9090}


def main() -> int:
    servico = os.getenv("SERVICO", "")
    porta = os.getenv("PORT") or os.getenv("PORTA") or PORTAS_PADRAO.get(servico, 9090)
    try:
        with grpc.insecure_channel(f"127.0.0.1:{porta}") as canal:
            resposta = health_pb2_grpc.HealthStub(canal).Check(health_pb2.HealthCheckRequest(), timeout=2)
    except grpc.RpcError as erro:
        print("fora do ar:", erro.code().name)
        return 1
    return 0 if resposta.status == health_pb2.HealthCheckResponse.SERVING else 1


if __name__ == "__main__":
    sys.exit(main())
