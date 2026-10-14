"""Autenticacao JWT do Gateway: emissao do token e filtro de borda.

O Gateway e o unico ponto que emite e confere token. O microsservico de
Usuarios so confirma login e senha; daqui para dentro (gRPC) ninguem ve token.

    JWT_SEGREDO             chave HMAC do HS256. Sem ela, o Gateway sorteia uma
                            chave a cada subida (os tokens antigos deixam de valer)
    JWT_EXPIRACAO_MINUTOS   validade do token (padrao 60)

O MiddlewareJWT barra na borda, com 401, toda requisicao sem
"Authorization: Bearer <token>" valido, antes de qualquer chamada gRPC. So as
rotas de ROTAS_PUBLICAS passam sem token.
"""

import os
import secrets
import time

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

# Nunca ha segredo fixo no codigo: o repositorio e publico e qualquer um
# poderia assinar tokens com ele.
SEGREDO_DEFINIDO = bool(os.getenv("JWT_SEGREDO"))
SEGREDO = os.getenv("JWT_SEGREDO") or secrets.token_hex(32)
ALGORITMO = "HS256"
EXPIRACAO_MINUTOS = int(os.getenv("JWT_EXPIRACAO_MINUTOS", "60"))

ROTAS_PUBLICAS = {
    "/saude",
    "/auth/login",
    "/auth/cadastro",
    "/docs",
    "/docs/oauth2-redirect",
    "/openapi.json",
}

# So para o Swagger mostrar o botao "Authorize"; quem barra e o middleware.
esquema_bearer = HTTPBearer(auto_error=False, description="Token devolvido por POST /auth/login")


def emitir_token(usuario: dict) -> dict:
    agora = int(time.time())
    claims = {
        "sub": usuario["id"],
        "login": usuario["login"],
        "nome": usuario["nome"],
        "papel": usuario["papel"],
        "iat": agora,
        "exp": agora + EXPIRACAO_MINUTOS * 60,
    }
    return {
        "access_token": jwt.encode(claims, SEGREDO, algorithm=ALGORITMO),
        "token_type": "Bearer",
        "expira_em_segundos": EXPIRACAO_MINUTOS * 60,
    }


def validar_token(token: str) -> dict:
    """Claims do token. Lanca jwt.InvalidTokenError se assinatura/prazo nao conferem."""
    return jwt.decode(
        token,
        SEGREDO,
        algorithms=[ALGORITMO],
        options={"require": ["sub", "exp", "iat"]},
    )


class AcessoNegado(Exception):
    """Token valido, mas o papel do usuario nao permite a operacao (403)."""


def exigir_papel(papel: str):
    """Dependencia de rota: so deixa passar quem tem o papel no token.

    O MiddlewareJWT ja garantiu que o token e valido; aqui so se confere a
    autorizacao. Quem se cadastra pela API e sempre "cliente".
    """

    def conferir(request: Request) -> None:
        if request.state.usuario.get("papel") != papel:
            raise AcessoNegado("Operacao permitida so para o papel '%s'." % papel)

    return conferir


def _nao_autorizado(mensagem: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"mensagem": mensagem},
        headers={"WWW-Authenticate": "Bearer"},
    )


class MiddlewareJWT(BaseHTTPMiddleware):
    async def dispatch(self, request, chamar_proxima):
        # OPTIONS e o preflight do CORS: o navegador nao manda o token nele.
        if request.method == "OPTIONS" or request.url.path in ROTAS_PUBLICAS:
            return await chamar_proxima(request)

        cabecalho = request.headers.get("authorization", "")
        esquema, _, token = cabecalho.partition(" ")
        if not cabecalho:
            return _nao_autorizado("Token ausente. Envie o cabecalho Authorization: Bearer <token>.")
        if esquema.lower() != "bearer" or not token.strip():
            return _nao_autorizado("Cabecalho Authorization invalido. Use: Bearer <token>.")

        try:
            claims = validar_token(token.strip())
        except jwt.ExpiredSignatureError:
            return _nao_autorizado("Token expirado. Faca login novamente.")
        except jwt.InvalidTokenError:
            return _nao_autorizado("Token invalido.")

        request.state.usuario = claims
        return await chamar_proxima(request)
