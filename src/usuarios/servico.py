"""Implementacao do UsuarioService definido em proto/usuarios.proto.

A senha so existe em texto puro dentro deste servico, pelo tempo da chamada:
no banco fica o hash bcrypt, e nenhuma resposta nem linha de log leva a senha.
"""

import re
import uuid
from datetime import datetime

import bcrypt
import grpc

from ..comum.registro import log
from ..gerado import usuarios_pb2 as pb
from ..gerado import usuarios_pb2_grpc as pb_grpc
from .repositorio import LoginDuplicado, RepositorioUsuarios

TAMANHO_MINIMO_SENHA = 6
TAMANHO_MAXIMO_SENHA = 72  # limite do bcrypt
NOME_MAXIMO = 100
TELEFONE_MAXIMO = 30
ENDERECO_MAXIMO = 200
# Nome de pessoa: letras (com acento), espaco, apostrofo, ponto e hifen. Numero nao.
NOME_DE_PESSOA = re.compile(r"[^\W\d_]+(?:[ '.-]+[^\W\d_]+)*\.?")
NOME_INVALIDO = "O nome so pode ter letras, espaco, apostrofo e hifen."


def _nome_de_pessoa(texto: str) -> str | None:
    """Nome normalizado (espacos simples) ou None se tiver numero ou simbolo."""
    nome = " ".join((texto or "").split())
    if NOME_DE_PESSOA.fullmatch(nome) and sum(c.isalpha() for c in nome) >= 2:
        return nome
    return None
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
        telefone=linha.get("telefone") or "",
        endereco=linha.get("endereco") or "",
    )


def _id_valido(valor: str) -> bool:
    try:
        uuid.UUID(valor)
        return True
    except ValueError:
        return False


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
        if _nome_de_pessoa(nome) is None:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, NOME_INVALIDO)
        nome = _nome_de_pessoa(nome)
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

    def _usuario(self, usuario_id: str, context) -> dict:
        linha = self.repositorio.buscar_por_id(usuario_id) if _id_valido(usuario_id) else None
        if linha is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Usuario nao encontrado.")
        return linha

    def ObterUsuario(self, request, context):
        log("ObterUsuario: id=%s" % request.id)
        return _para_proto(self._usuario(request.id, context))

    def AtualizarUsuario(self, request, context):
        # O Gateway confere o formato (e o telefone); aqui ficam os limites, para
        # qualquer chamador gRPC (defesa em profundidade).
        campos: dict = {}
        if request.HasField("nome"):
            campos["nome"] = " ".join(request.nome.split())
            if not campos["nome"]:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Informe o nome.")
            if _nome_de_pessoa(campos["nome"]) is None:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, NOME_INVALIDO)
            if len(campos["nome"]) > NOME_MAXIMO:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "O nome passa de %d caracteres." % NOME_MAXIMO)
        if request.HasField("telefone"):
            campos["telefone"] = request.telefone.strip()
            if len(campos["telefone"]) > TELEFONE_MAXIMO:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Telefone longo demais.")
        if request.HasField("endereco"):
            campos["endereco"] = request.endereco.strip()
            if len(campos["endereco"]) > ENDERECO_MAXIMO:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                              "O endereco passa de %d caracteres." % ENDERECO_MAXIMO)
        log("AtualizarUsuario: id=%s campos=%s" % (request.id, sorted(campos) or "(nada)"))
        if not campos:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Nada para alterar: informe ao menos um campo.")
        self._usuario(request.id, context)
        return _para_proto(self.repositorio.atualizar(request.id, campos))

    def TrocarSenha(self, request, context):
        linha = self._usuario(request.id, context)
        log("TrocarSenha: id=%s" % request.id)  # a senha nunca vai para o log
        if not bcrypt.checkpw(request.senha_atual.encode(), linha["senha_hash"].encode()):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Senha atual incorreta.")
        if not TAMANHO_MINIMO_SENHA <= len(request.nova_senha) <= TAMANHO_MAXIMO_SENHA:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "A senha precisa de pelo menos %d caracteres." % TAMANHO_MINIMO_SENHA,
            )
        if request.nova_senha == request.senha_atual:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "A nova senha precisa ser diferente da atual.")
        senha_hash = bcrypt.hashpw(request.nova_senha.encode(), bcrypt.gensalt()).decode()
        return _para_proto(self.repositorio.trocar_senha(request.id, senha_hash))
