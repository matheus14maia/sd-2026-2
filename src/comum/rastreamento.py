"""Rastreamento distribuido (OpenTelemetry): o caminho de cada requisicao entre os servicos.

Cada requisicao vira um trace: uma arvore de spans (trechos com inicio, fim e
atributos) que atravessa os servicos. Um POST /pedidos, por exemplo:

    gateway  POST /pedidos                       SERVER    requisicao HTTP inteira
      gateway  pedidos.CriarPedido               INTERNAL  chamada com retry e circuit breaker
        gateway  pedidos.CriarPedido tentativa 1 CLIENT    cada tentativa gRPC
          pedidos  pedidos.CriarPedido           SERVER    atendimento no microsservico
            pedidos  catalogo.ConsultarItens ... (mesma estrutura, ate o Catalogo)
            pedidos  banco pedidos.inserir       CLIENT    gravacao no PostgreSQL

O contexto (trace id + span pai) vai nos metadados gRPC em dois formatos: W3C
(traceparent) e o do Google (x-cloud-trace-context). O mesmo trace id aparece
nas linhas de log (src/comum/registro.py) e no cabecalho X-Requisicao-Id.

Para onde os spans vao (variavel RASTREAMENTO):
  gcp      Cloud Trace. No Cloud Run a conta de servico precisa do papel
           roles/cloudtrace.agent; o projeto vem do proprio ambiente.
  otlp     OTLP/HTTP em OTEL_EXPORTER_OTLP_ENDPOINT. No computador: o Jaeger do
           profile "rastreamento" do compose (http://127.0.0.1:16686).
  console  imprime cada span no log (para depurar).
  vazio    nenhum lugar: os spans so fazem o trace id seguir entre os servicos.
"""

import atexit
import functools
import os

from opentelemetry import propagate, trace
from opentelemetry.propagators.cloud_trace_propagator import CloudTraceFormatPropagator
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

__all__ = [
    "SpanKind",
    "Status",
    "StatusCode",
    "configurar",
    "encerrar",
    "extrair",
    "metadados",
    "rastrear_banco",
    "tracer",
]

tracer = trace.get_tracer("delivery")
_provedor: TracerProvider | None = None


def _exportador(destino: str):
    if destino == "gcp":
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

        return CloudTraceSpanExporter()
    if destino == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter()  # endereco em OTEL_EXPORTER_OTLP_ENDPOINT
    if destino == "console":
        return ConsoleSpanExporter()
    return None


def configurar(servico: str) -> str:
    """Liga o rastreamento deste processo e devolve o destino dos spans."""
    global _provedor
    destino = os.getenv("RASTREAMENTO", "").strip().lower()
    if _provedor is not None:
        return destino or "nenhum"
    # Amostra: fracao dos traces gravados (1.0 = todos). Quem ja vem com um trace
    # amostrado (ParentBased) segue a decisao de quem chamou.
    amostra = float(os.getenv("RASTREAMENTO_AMOSTRA", "1.0"))
    _provedor = TracerProvider(
        resource=Resource.create({"service.name": servico, "service.namespace": "delivery"}),
        sampler=ParentBased(TraceIdRatioBased(amostra)),
    )
    exportador = _exportador(destino)
    if exportador is not None:
        _provedor.add_span_processor(BatchSpanProcessor(exportador))
    trace.set_tracer_provider(_provedor)
    propagate.set_global_textmap(
        CompositePropagator([TraceContextTextMapPropagator(), CloudTraceFormatPropagator()])
    )
    atexit.register(encerrar)
    return destino or "nenhum"


def encerrar() -> None:
    """Envia os spans que ainda estao na fila (desligamento do processo)."""
    global _provedor
    if _provedor is not None:
        provedor, _provedor = _provedor, None
        provedor.shutdown()


def extrair(portador):
    """Contexto do trace de quem chamou (cabecalhos HTTP ou metadados gRPC)."""
    return propagate.extract(portador)


def metadados() -> list[tuple[str, str]]:
    """Metadados gRPC que levam o trace atual (e o span pai) para o proximo servico."""
    portador: dict[str, str] = {}
    propagate.inject(portador)
    return list(portador.items())


def rastrear_banco(operacao: str):
    """Decorador: a funcao do repositorio vira um span "banco <operacao>".

    So cria o span dentro de uma requisicao rastreada; chamada solta (ex.: o
    stream de eventos buscando um pedido) nao abre um trace sozinha.
    """

    def decorador(funcao):
        @functools.wraps(funcao)
        def envolvida(*args, **kwargs):
            if not trace.get_current_span().is_recording():
                return funcao(*args, **kwargs)
            with tracer.start_as_current_span(
                "banco " + operacao,
                kind=SpanKind.CLIENT,
                attributes={"db.system": "postgresql", "db.operation.name": operacao},
            ):
                return funcao(*args, **kwargs)

        return envolvida

    return decorador
