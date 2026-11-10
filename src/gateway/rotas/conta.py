"""Rotas da conta de quem esta logado ("Meus dados" no frontend).

O usuario e sempre o dono do token: nao ha id na URL, entao ninguem le nem
altera a conta de outra pessoa. Os dados ficam no microsservico de Usuarios.
"""

from fastapi import APIRouter, Depends, Request

from ..autenticacao import emitir_token, esquema_bearer
from ..esquemas import ContaAtualizacao, TrocaSenha

router = APIRouter(prefix="/conta", tags=["conta"], dependencies=[Depends(esquema_bearer)])


@router.get("", summary="Dados de quem esta logado: nome, telefone e endereco (200)")
def obter(request: Request):
    return request.app.state.grpc.obter_usuario(request.state.usuario["sub"])


@router.patch("", summary="Altera nome, telefone e endereco; devolve um token novo (200)")
def atualizar(request: Request, corpo: ContaAtualizacao):
    usuario = request.app.state.grpc.atualizar_usuario(
        request.state.usuario["sub"], corpo.model_dump(exclude_none=True)
    )
    # O nome vai no token, e dele sai o nome dos pedidos novos: o token novo ja
    # leva o nome atualizado (o antigo continua valido ate expirar).
    return {**emitir_token(usuario), "usuario": usuario}


@router.put("/senha", summary="Troca a senha conferindo a atual (200; 400 se a atual estiver errada)")
def trocar_senha(request: Request, corpo: TrocaSenha):
    request.app.state.grpc.trocar_senha(request.state.usuario["sub"], corpo.senha_atual, corpo.nova_senha)
    return {"mensagem": "Senha alterada."}
