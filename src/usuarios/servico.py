"""Implementacao do UsuarioService definido em proto/usuarios.proto.

A senha so existe em texto puro dentro deste servico, pelo tempo da chamada:
no banco fica o hash bcrypt, e nenhuma resposta nem linha de log leva a senha.
"""

from datetime import datetime

import bcrypt
import grpc

from ..comum.servidor_grpc import log
from ..gerado import usuarios_pb2 as pb
from ..gerado import usuarios_pb2_grpc as pb_grpc
from .repositorio import LoginDuplicado, RepositorioUsuarios

TAMANHO_MINIMO_SENHA = 6
# Mesma mensagem para login inexistente e senha errada: a resposta nao revela
# quais logins existem.
CREDENCIAIS_INVALIDAS = "Login ou senha invalidos."


def _normalizar_login(login: str) -> str:
    return (login or "").strip().lower()


def _para_proto(linha: dict) -> pb.Usuario:
    criado_em: datetime = linha["criado_em"]
    return pb.Usuario(
        id=linha["id"],
        login=linha["login"],
        nome=linha["nome"],
        papel=linha["papel"],
        criado_em=criado_em.astimezone().isoformat(timespec="seconds"),
    )


class UsuarioService(pb_grpc.UsuarioServiceServicer):
    def __init__(self, repositorio: RepositorioUsuarios) -> None:
        self.repositorio = repositorio

    def CadastrarUsuario(self, request, context):
        login = _normalizar_login(request.login)
        nome = request.nome.strip()
        log("CadastrarUsuario: login=%r nome=%r" % (login, nome))

        # O Gateway ja valida o payload; a checagem aqui protege o servico de
        # qualquer outro chamador gRPC (defesa em profundidade).
        if not login or not nome:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Informe login e nome.")
        if len(request.senha) < TAMANHO_MINIMO_SENHA:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "A senha precisa de pelo menos %d caracteres." % TAMANHO_MINIMO_SENHA,
            )

        senha_hash = bcrypt.hashpw(request.senha.encode(), bcrypt.gensalt()).decode()
        try:
            linha = self.repositorio.inserir(login, nome, senha_hash)
        except LoginDuplicado:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, "O login '%s' ja esta em uso." % login)
        log("Usuario %s gravado (id %s)" % (login, linha["id"]))
        return _para_proto(linha)

    def VerificarCredenciais(self, request, context):
        login = _normalizar_login(request.login)
        linha = self.repositorio.buscar_por_login(login) if login else None
        valido = linha is not None and bcrypt.checkpw(
            request.senha.encode(), linha["senha_hash"].encode()
        )
        log("VerificarCredenciais: login=%r -> %s" % (login, "ok" if valido else "recusado"))
        if not valido:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, CREDENCIAIS_INVALIDAS)
        return _para_proto(linha)
