"""Traducao de erros para respostas HTTP semanticas.

Dois tipos de erro chegam aqui:

1. Payload invalido (RequestValidationError do FastAPI/Pydantic) -> 400, com o
   motivo de cada campo. O FastAPI responderia 422 por padrao; o trabalho pede
   400 Bad Request, por isso o handler e sobrescrito.
2. Erro devolvido por um microsservico (grpc.RpcError) -> o status HTTP
   equivalente ao status code do gRPC.
"""

import grpc
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

GRPC_PARA_HTTP = {
    grpc.StatusCode.INVALID_ARGUMENT: 400,
    grpc.StatusCode.NOT_FOUND: 404,
    grpc.StatusCode.FAILED_PRECONDITION: 409,
    grpc.StatusCode.ALREADY_EXISTS: 409,
    grpc.StatusCode.UNAVAILABLE: 503,
    grpc.StatusCode.DEADLINE_EXCEEDED: 503,
}

# Mensagens em portugues por tipo de erro do Pydantic.
MENSAGENS = {
    "missing": "campo obrigatorio",
    "string_too_short": "nao deve estar vazio",
    "string_too_long": "texto muito longo",
    "string_type": "deve ser um texto",
    "string_pattern_mismatch": "codigo invalido: use 2 letras e 2 digitos (ex.: PR01)",
    "int_type": "deve ser um numero inteiro",
    "int_parsing": "deve ser um numero inteiro",
    "float_type": "deve ser um numero",
    "float_parsing": "deve ser um numero",
    "bool_type": "deve ser true ou false",
    "greater_than": "deve ser maior que zero",
    "less_than_equal": "valor acima do permitido",
    "too_short": "deve ter pelo menos um item",
    "too_long": "itens demais",
    "list_type": "deve ser uma lista",
    "model_type": "deve ser um objeto JSON",
    "model_attributes_type": "deve ser um objeto JSON",
    "dict_type": "deve ser um objeto JSON",
    "literal_error": "valor nao permitido",
    "extra_forbidden": "campo nao permitido",
    "json_invalid": "JSON malformado",
}


def _campo(loc: tuple) -> str:
    # loc vem como ("body", "itens", 0, "quantidade"); o "body" nao interessa.
    partes = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(partes) or "corpo"


def _mensagem(erro: dict) -> str:
    tipo = erro.get("type", "")
    if tipo == "literal_error":
        esperado = (erro.get("ctx") or {}).get("expected", "")
        return "valor nao permitido; use um de: %s" % esperado.replace("'", "")
    if tipo == "less_than_equal":
        return "deve ser no maximo %s" % (erro.get("ctx") or {}).get("le")
    return MENSAGENS.get(tipo, erro.get("msg", "valor invalido"))


async def validacao_invalida(request: Request, exc: RequestValidationError) -> JSONResponse:
    erros: dict[str, str] = {}
    for erro in exc.errors():
        erros.setdefault(_campo(tuple(erro.get("loc", ()))), _mensagem(erro))
    return JSONResponse(
        status_code=400,
        content={"mensagem": "Dados da requisicao invalidos", "erros": erros},
    )


async def erro_grpc(request: Request, exc: grpc.RpcError) -> JSONResponse:
    status = GRPC_PARA_HTTP.get(exc.code(), 500)
    mensagem = exc.details() or exc.code().name
    if status >= 500 and exc.code() not in GRPC_PARA_HTTP:
        mensagem = "Erro interno ao processar a requisicao."
    return JSONResponse(
        status_code=status,
        content={"mensagem": mensagem, "codigo_grpc": exc.code().name},
    )
