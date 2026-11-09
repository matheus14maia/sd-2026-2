"""Log de uma linha por evento: legivel no terminal, estruturado no Cloud Logging.

Local (docker compose):  [20:43:57] [3f9a1c2e] mensagem
                         (o colchete e o inicio do id da requisicao: o mesmo id
                         aparece no Gateway e nos microsservicos que a atenderam)
Cloud Run (LOG_JSON=1):  uma linha JSON por evento. O Cloud Logging le os campos
                         `severity` e `message`, e o campo
                         `logging.googleapis.com/trace` agrupa as linhas de
                         todos os servicos que atenderam a mesma requisicao.

O trace nasce no Gateway (cabecalho que o Cloud Run injeta, ou um id sorteado)
e segue para os microsservicos no metadado gRPC `traceparent`. Assim, no Logs
Explorer, "Mostrar entradas deste trace" junta Gateway, Pedidos e Catalogo.
"""

import contextvars
import json
import os
import re
import secrets
from datetime import datetime

SERVICO = os.getenv("NOME_SERVICO", "delivery")
LOG_JSON = os.getenv("LOG_JSON", "0") == "1"
PROJETO = os.getenv("GOOGLE_CLOUD_PROJECT", "")

# Trace da requisicao em andamento. ContextVar funciona com threads do servidor
# gRPC (setado no interceptador) e com o threadpool do FastAPI (copia o contexto).
trace_atual: contextvars.ContextVar[str] = contextvars.ContextVar("trace_atual", default="")

_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")


def log(mensagem: str, severidade: str = "INFO", **campos) -> None:
    """Uma linha por evento. `severidade` segue o Cloud Logging (INFO, NOTICE, WARNING, ERROR)."""
    trace = trace_atual.get()
    if LOG_JSON:
        registro = {"severity": severidade, "message": mensagem, "servico": SERVICO, **campos}
        if trace:
            registro["trace_id"] = trace
            if PROJETO:
                registro["logging.googleapis.com/trace"] = f"projects/{PROJETO}/traces/{trace}"
        print(json.dumps(registro, ensure_ascii=False, default=str), flush=True)
        return
    requisicao = f"[{trace[:8]}] " if trace else ""
    prefixo = "" if severidade in ("INFO", "DEFAULT") else f"{severidade}: "
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {requisicao}{prefixo}{mensagem}", flush=True)


def novo_trace() -> str:
    return secrets.token_hex(16)


def trace_de_cabecalhos(obter) -> str:
    """Trace id (32 hex) de `traceparent` (W3C) ou `X-Cloud-Trace-Context`; '' se nao houver.

    `obter` e uma funcao nome -> valor (headers do HTTP ou metadados do gRPC).
    """
    traceparent = obter("traceparent") or ""
    partes = traceparent.split("-")
    if len(partes) >= 4 and _TRACE_ID.match(partes[1]):
        return partes[1]
    contexto_gcp = obter("x-cloud-trace-context") or ""
    trace = contexto_gcp.split("/")[0].lower()
    return trace if _TRACE_ID.match(trace) else ""


def metadados_trace() -> list[tuple[str, str]]:
    """Metadados gRPC que levam o trace atual para o proximo servico."""
    trace = trace_atual.get()
    if not trace:
        return []
    span = secrets.token_hex(8)
    return [
        ("traceparent", f"00-{trace}-{span}-01"),
        ("x-cloud-trace-context", f"{trace}/{int(span, 16)};o=1"),
    ]
