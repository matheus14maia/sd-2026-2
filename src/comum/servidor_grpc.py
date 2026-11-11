"""Inicializacao comum dos servidores gRPC (Usuarios, Catalogo e Pedidos).

Os tres microsservicos sobem do mesmo jeito: ThreadPool, health check padrao do
gRPC (grpc.health.v1), reflection, porta por variavel de ambiente e
encerramento limpo no SIGINT/SIGTERM (o Cloud Run manda SIGTERM antes de
desligar uma instancia). So muda o servico registrado, entao a rotina fica aqui
e cada `servidor.py` so passa o que e seu.

O InterceptadorServidor envolve toda chamada de negocio:
  - abre um span SERVER filho do span de quem chamou (o contexto vem nos
    metadados gRPC), entao o Cloud Trace mostra o caminho inteiro e os logs
    saem com o mesmo trace id;
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

from .rastreamento import SpanKind, Status, StatusCode, configurar, extrair, tracer
from .rastreamento import encerrar as encerrar_rastreamento
from .registro import SERVICO, log

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

# Codigos que indicam problema no proprio servico (span marcado como erro). Erro
# de negocio (INVALID_ARGUMENT, NOT_FOUND...) fica so como atributo do span.
CODIGOS_DE_FALHA = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
    grpc.StatusCode.INTERNAL,
    grpc.StatusCode.UNKNOWN,
    grpc.StatusCode.DATA_LOSS,
}


def _anotar_status(span, contexto) -> None:
    codigo = contexto.code() if hasattr(contexto, "code") else None
    if codigo is None or codigo == grpc.StatusCode.OK:
        return
    span.set_attribute("rpc.grpc.status_code", codigo.value[0])
    if codigo in CODIGOS_DE_FALHA:
        span.set_status(Status(StatusCode.ERROR, codigo.name))


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
            with tracer.start_as_current_span(
                "%s.%s" % (SERVICO, operacao),
                context=extrair(metadados),
                kind=SpanKind.SERVER,
                attributes={"rpc.system": "grpc", "rpc.service": metodo.strip("/").split("/")[0],
                            "rpc.method": operacao},
                # context.abort() levanta uma excecao generica: o status do span
                # sai do codigo gRPC (_anotar_status), nao da excecao.
                record_exception=False,
                set_status_on_exception=False,
            ) as span:
                try:
                    if FALHA_ATRASO_MS > 0:
                        span.add_event("atraso simulado", {"atraso_ms": FALHA_ATRASO_MS})
                        time.sleep(FALHA_ATRASO_MS / 1000)
                    if FALHA_PERCENTUAL > 0 and random.uniform(0, 100) < FALHA_PERCENTUAL:
                        span.add_event("falha simulada", {"falha_percentual": FALHA_PERCENTUAL})
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
                        log("Banco indisponivel em %s: %s" % (operacao, str(erro).strip().splitlines()[0]),
                            "ERROR", operacao=operacao)
                        span.add_event("banco indisponivel")
                        contexto.abort(grpc.StatusCode.UNAVAILABLE, "Banco de dados indisponivel no momento.")
                finally:
                    _anotar_status(span, contexto)

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
    destino_rastreamento = configurar(SERVICO)
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
    log("Servico %s no ar na porta %d (rastreamento: %s)" % (SERVICO, porta, destino_rastreamento),
        falha_percentual=FALHA_PERCENTUAL)

    def ao_receber_sinal(_sinal, _frame):
        print("\nEncerrando o servidor...", flush=True)
        saude.enter_graceful_shutdown()
        servidor.stop(ENCERRAMENTO_SEGUNDOS)

    signal.signal(signal.SIGINT, ao_receber_sinal)
    signal.signal(signal.SIGTERM, ao_receber_sinal)

    servidor.wait_for_termination()
    encerrar_rastreamento()  # envia os spans que ainda estao na fila
    if ao_encerrar:
        ao_encerrar()
    print("Servidor encerrado.", flush=True)
    return 0
