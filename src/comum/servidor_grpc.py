"""Inicializacao comum dos servidores gRPC (Usuarios, Catalogo e Pedidos).

Os tres microsservicos sobem do mesmo jeito: ThreadPool, health check padrao do
gRPC (grpc.health.v1), reflection, porta por variavel de ambiente e
encerramento limpo no SIGINT/SIGTERM (o Cloud Run manda SIGTERM antes de
desligar uma instancia). So muda o servico registrado, entao a rotina fica aqui
e cada `servidor.py` so passa o que e seu.

O InterceptadorServidor envolve toda chamada de negocio:
  - le o trace que veio do Gateway (log correlacionado no Cloud Logging);
  - injeta falha de proposito quando FALHA_PERCENTUAL > 0 (demonstracao da
    tolerancia a falhas: o servico responde UNAVAILABLE em X% das chamadas);
  - transforma queda do banco em UNAVAILABLE (quem chama faz retry e responde
    503), em vez de um erro generico.
"""

import os
import random
import signal
import time
from concurrent import futures
from typing import Callable

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

from .registro import SERVICO, log, trace_atual, trace_de_cabecalhos

ENDERECO_ESCUTA = os.getenv("ENDERECO_ESCUTA", "0.0.0.0")
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))
ENCERRAMENTO_SEGUNDOS = 5

# Injecao de falha para a demonstracao (0 = desligada). Muda pelo painel do
# Cloud Run (variavel de ambiente -> nova revisao) ou pelo .env local.
FALHA_PERCENTUAL = float(os.getenv("FALHA_PERCENTUAL", "0") or 0)
FALHA_ATRASO_MS = int(os.getenv("FALHA_ATRASO_MS", "0") or 0)

# Metodos de infraestrutura nao passam pelo interceptador.
PREFIXOS_INFRA = ("/grpc.health.", "/grpc.reflection.")

__all__ = ["executar", "log"]


def _erros_de_banco() -> tuple[type[BaseException], ...]:
    try:
        import psycopg
        from psycopg_pool import PoolTimeout

        return (psycopg.OperationalError, PoolTimeout)
    except ImportError:  # pragma: no cover - todos os microsservicos tem psycopg
        return ()


ERROS_DE_BANCO = _erros_de_banco()


class InterceptadorServidor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, detalhes):
        handler = continuation(detalhes)
        metodo = detalhes.method or ""
        if handler is None or handler.unary_unary is None or metodo.startswith(PREFIXOS_INFRA):
            return handler

        metadados = dict(detalhes.invocation_metadata or ())
        comportamento = handler.unary_unary
        operacao = metodo.rsplit("/", 1)[-1]

        def envolvido(requisicao, contexto):
            marca = trace_atual.set(trace_de_cabecalhos(metadados.get))
            try:
                if FALHA_ATRASO_MS > 0:
                    time.sleep(FALHA_ATRASO_MS / 1000)
                if FALHA_PERCENTUAL > 0 and random.uniform(0, 100) < FALHA_PERCENTUAL:
                    log(
                        "Falha simulada em %s (FALHA_PERCENTUAL=%g)" % (operacao, FALHA_PERCENTUAL),
                        "WARNING",
                        operacao=operacao,
                        falha_simulada=True,
                    )
                    contexto.abort(
                        grpc.StatusCode.UNAVAILABLE,
                        "Falha simulada no servico %s (FALHA_PERCENTUAL=%g%%)." % (SERVICO, FALHA_PERCENTUAL),
                    )
                try:
                    return comportamento(requisicao, contexto)
                except ERROS_DE_BANCO as erro:
                    log("Banco indisponivel em %s: %s" % (operacao, str(erro).strip().splitlines()[0]), "ERROR",
                        operacao=operacao)
                    contexto.abort(grpc.StatusCode.UNAVAILABLE, "Banco de dados indisponivel no momento.")
            finally:
                trace_atual.reset(marca)

        return grpc.unary_unary_rpc_method_handler(
            envolvido,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )


def porta_de_escuta(padrao: int) -> int:
    """PORT (injetada pelo Cloud Run) tem prioridade sobre a porta padrao do servico."""
    return int(os.getenv("PORT") or padrao)


def executar(
    titulo: str,
    nome_completo_servico: str,
    porta: int,
    registrar: Callable[[grpc.Server], None],
    ao_encerrar: Callable[[], None] | None = None,
) -> int:
    porta = porta_de_escuta(porta)
    servidor = grpc.server(
        futures.ThreadPoolExecutor(max_workers=MAX_WORKERS),
        interceptors=[InterceptadorServidor()],
    )
    registrar(servidor)

    # Health check padrao do gRPC: o Cloud Run (startup/liveness probe) e o
    # Gateway (GET /saude/servicos) perguntam se o servico esta SERVING.
    saude = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(saude, servidor)
    saude.set("", health_pb2.HealthCheckResponse.SERVING)
    saude.set(nome_completo_servico, health_pb2.HealthCheckResponse.SERVING)

    # Reflection permite inspecionar o servico com o grpcurl sem o .proto local.
    reflection.enable_server_reflection(
        (nome_completo_servico, health.SERVICE_NAME, reflection.SERVICE_NAME), servidor
    )
    servidor.add_insecure_port(f"{ENDERECO_ESCUTA}:{porta}")
    servidor.start()

    print("=" * 62, flush=True)
    print(f" {titulo}", flush=True)
    print(f" Servidor gRPC ouvindo em {ENDERECO_ESCUTA}:{porta}", flush=True)
    print(f" Servico: {nome_completo_servico}", flush=True)
    if FALHA_PERCENTUAL or FALHA_ATRASO_MS:
        print(f" INJECAO DE FALHA LIGADA: {FALHA_PERCENTUAL:g}% UNAVAILABLE, atraso {FALHA_ATRASO_MS} ms", flush=True)
    print("=" * 62, flush=True)
    log("Servico %s no ar na porta %d" % (SERVICO, porta), falha_percentual=FALHA_PERCENTUAL)

    def encerrar(_sinal, _frame):
        print("\nEncerrando o servidor...", flush=True)
        saude.enter_graceful_shutdown()
        servidor.stop(ENCERRAMENTO_SEGUNDOS)

    signal.signal(signal.SIGINT, encerrar)
    signal.signal(signal.SIGTERM, encerrar)

    servidor.wait_for_termination()
    if ao_encerrar:
        ao_encerrar()
    print("Servidor encerrado.", flush=True)
    return 0
