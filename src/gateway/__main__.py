"""Sobe o Gateway com o Uvicorn.

    python -m src.gateway

A porta vem de PORT (padrao 8000; em plataformas como o Cloud Run ela e
injetada). O log de acesso do Uvicorn fica desligado porque o Gateway ja
registra uma linha por requisicao (app.registrar_requisicao).
"""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "src.gateway.app:app",
        host=os.getenv("ENDERECO_ESCUTA", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,
    )


if __name__ == "__main__":
    main()
