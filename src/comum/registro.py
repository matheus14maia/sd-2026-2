"""Log de uma linha por evento: legivel no terminal, estruturado no Cloud Logging.

Local (docker compose):  [20:43:57] [3f9a1c2e] mensagem
                         (o colchete e o inicio do id da requisicao: o mesmo id
                         aparece no Gateway e nos microsservicos que a atenderam)
Cloud Run (LOG_JSON=1):  uma linha JSON por evento. O Cloud Logging le os campos
                         `severity` e `message`; `logging.googleapis.com/trace`
                         e `.../spanId` ligam a linha ao trace e ao span no
                         Cloud Trace, e "Mostrar entradas deste trace" junta as
                         linhas de todos os servicos daquela requisicao.

O id da requisicao e o trace id do OpenTelemetry (src/comum/rastreamento.py),
que segue de um servico para o outro nos metadados gRPC.
"""

import json
import os
from datetime import datetime

try:
    from opentelemetry import trace as _otel_trace
except ImportError:  # o migrador nao instala o OpenTelemetry: log sem trace
    _otel_trace = None

SERVICO = os.getenv("NOME_SERVICO", "delivery")
LOG_JSON = os.getenv("LOG_JSON", "0") == "1"
PROJETO = os.getenv("GOOGLE_CLOUD_PROJECT", "")


def ids_atuais() -> tuple[str, str, bool]:
    """(trace id, span id, amostrado) do span em andamento; ('', '', False) se nao houver."""
    if _otel_trace is None:
        return "", "", False
    contexto = _otel_trace.get_current_span().get_span_context()
    if not contexto.is_valid:
        return "", "", False
    return format(contexto.trace_id, "032x"), format(contexto.span_id, "016x"), contexto.trace_flags.sampled


def log(mensagem: str, severidade: str = "INFO", **campos) -> None:
    """Uma linha por evento. `severidade` segue o Cloud Logging (INFO, NOTICE, WARNING, ERROR)."""
    trace_id, span_id, amostrado = ids_atuais()
    if LOG_JSON:
        registro = {"severity": severidade, "message": mensagem, "servico": SERVICO, **campos}
        if trace_id:
            registro["trace_id"] = trace_id
            if PROJETO:
                registro["logging.googleapis.com/trace"] = f"projects/{PROJETO}/traces/{trace_id}"
                registro["logging.googleapis.com/spanId"] = span_id
                registro["logging.googleapis.com/trace_sampled"] = amostrado
        print(json.dumps(registro, ensure_ascii=False, default=str), flush=True)
        return
    requisicao = f"[{trace_id[:8]}] " if trace_id else ""
    prefixo = "" if severidade in ("INFO", "DEFAULT") else f"{severidade}: "
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {requisicao}{prefixo}{mensagem}", flush=True)
