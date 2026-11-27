"""Chave interna entre os servicos (Gateway -> microsservicos, Pedidos -> Catalogo).

No Cloud Run os tres microsservicos tem endpoint HTTPS publico (qualquer um
alcanca a URL e o health check responde). O que impede alguem de fora de chamar
o negocio direto, pulando o Gateway (que confere o JWT e o papel), e esta chave:
quem chama manda o metadado `x-chave-interna`; o microsservico confere e, sem
ela, responde UNAUTHENTICATED.

A chave vem da variavel CHAVE_INTERNA (no Cloud Run, do Secret Manager). Vazia,
nada e exigido nem enviado: e o caso do docker compose, em que as portas gRPC so
escutam na propria maquina.

Falha fechada no Cloud Run: la o endpoint e publico, entao subir sem a chave
(segredo esquecido, nome errado) abriria o negocio para qualquer um. Por isso,
com K_SERVICE definida (o Cloud Run sempre define) e sem CHAVE_INTERNA, o
processo se recusa a iniciar: a revisao nova nao recebe trafego e a anterior
continua atendendo.
"""

import hmac
import os

CABECALHO = "x-chave-interna"
CHAVE_INTERNA = os.getenv("CHAVE_INTERNA", "").strip()

if os.getenv("K_SERVICE") and not CHAVE_INTERNA:
    raise RuntimeError(
        "CHAVE_INTERNA obrigatoria no Cloud Run (servico %s): sem ela o endpoint publico "
        "ficaria aberto. Configure --set-secrets CHAVE_INTERNA=delivery-chave-interna:latest."
        % os.getenv("K_SERVICE")
    )


def exigida() -> bool:
    return bool(CHAVE_INTERNA)


def metadados() -> list[tuple[str, str]]:
    """Metadado que leva a chave para o proximo servico (vazio sem chave)."""
    return [(CABECALHO, CHAVE_INTERNA)] if CHAVE_INTERNA else []


def confere(recebidos: dict[str, str]) -> bool:
    """True se a chamada pode passar: sem chave configurada ou chave igual."""
    if not CHAVE_INTERNA:
        return True
    return hmac.compare_digest(recebidos.get(CABECALHO, ""), CHAVE_INTERNA)
