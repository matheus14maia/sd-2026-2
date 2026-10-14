"""Rotas HTTP de autenticacao.

Cadastro e login sao despachados para o microsservico de Usuarios; o token JWT
e emitido aqui no Gateway, depois que o Usuarios confirma as credenciais.
"""

from fastapi import APIRouter, Depends, Request, status

from ..autenticacao import emitir_token, esquema_bearer
from ..esquemas import CadastroEntrada, LoginEntrada

router = APIRouter(prefix="/auth", tags=["autenticacao"])


@router.post("/cadastro", status_code=status.HTTP_201_CREATED, summary="Cria um usuario (201)")
def cadastrar(request: Request, corpo: CadastroEntrada):
    usuario = request.app.state.grpc.cadastrar_usuario(corpo.login, corpo.nome, corpo.senha)
    return {"mensagem": "Usuario criado com sucesso", "usuario": usuario}


@router.post("/login", summary="Confere login e senha e devolve o token JWT (200 / 401)")
def login(request: Request, corpo: LoginEntrada):
    usuario = request.app.state.grpc.verificar_credenciais(corpo.login, corpo.senha)
    return {**emitir_token(usuario), "usuario": usuario}


@router.get(
    "/eu",
    summary="Dados do usuario dono do token (200 / 401)",
    dependencies=[Depends(esquema_bearer)],
)
def eu(request: Request):
    claims = request.state.usuario
    return {"id": claims["sub"], "login": claims["login"], "nome": claims["nome"], "expira_em": claims["exp"]}
