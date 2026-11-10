"""Implementacao do CatalogoService definido em proto/catalogo.proto.

Toda leitura e alteracao passa pelo PostgreSQL (RepositorioCatalogo). Erros
viram status code do gRPC via context.abort, e quem chama (Gateway ou Pedidos)
decide como apresentar. As regras do cardapio (categorias, limites de texto,
opcoes, foto) ficam aqui: o Gateway so confere o formato do JSON.
"""

import os
import uuid

import grpc

from ..comum.imagens import FOTO_MAXIMO_BYTES, tipo_da_imagem, versao_da_foto
from ..comum.registro import log
from ..gerado import catalogo_pb2 as pb
from ..gerado import catalogo_pb2_grpc as pb_grpc
from .repositorio import RepositorioCatalogo

NOME_RESTAURANTE = os.getenv("NOME_RESTAURANTE", "Hell's Kitchen")

# Categoria -> prefixo do codigo dos itens dela (Pratos -> PR01, PR02...).
CATEGORIAS = {"Entradas": "EN", "Pratos": "PR", "Bebidas": "BE", "Sobremesas": "SO"}
NOME_MAXIMO = 60
DESCRICAO_MAXIMA = 300
OPCAO_MAXIMA = 40
OPCOES_MAXIMO = 12
PRECO_MAXIMO = 10000


def _normalizar(codigo: str) -> str:
    return (codigo or "").strip().upper()


def _para_proto(linha: dict) -> pb.ItemCardapio:
    return pb.ItemCardapio(**linha)


def _categoria(texto: str, context) -> tuple[str, str]:
    """(nome oficial, prefixo do codigo). Aceita qualquer caixa: 'pratos' -> 'Pratos'."""
    for nome, prefixo in CATEGORIAS.items():
        if nome.casefold() == (texto or "").strip().casefold():
            return nome, prefixo
    context.abort(
        grpc.StatusCode.INVALID_ARGUMENT,
        "Categoria '%s' nao existe. Use uma de: %s." % ((texto or "").strip(), ", ".join(CATEGORIAS)),
    )


def _nome(texto: str, context) -> str:
    nome = " ".join((texto or "").split())
    if not nome:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Informe o nome do item.")
    if len(nome) > NOME_MAXIMO:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "O nome do item passa de %d caracteres." % NOME_MAXIMO)
    return nome


def _descricao(texto: str, context) -> str:
    descricao = (texto or "").strip()
    if len(descricao) > DESCRICAO_MAXIMA:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "A descricao passa de %d caracteres." % DESCRICAO_MAXIMA)
    return descricao


def _preco(valor: float, context) -> float:
    if valor <= 0:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "O preco deve ser maior que zero.")
    if valor > PRECO_MAXIMO:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "O preco deve ser no maximo %d." % PRECO_MAXIMO)
    return round(valor, 2)


def _opcoes(valores, context) -> list[str]:
    """Limpa a lista (espacos, linhas vazias) e recusa repeticao e excesso."""
    opcoes: list[str] = []
    vistas: set[str] = set()
    for valor in valores:
        opcao = " ".join(valor.split())
        if not opcao:
            continue
        if len(opcao) > OPCAO_MAXIMA:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          "A opcao '%s' passa de %d caracteres." % (opcao, OPCAO_MAXIMA))
        if opcao.casefold() in vistas:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "A opcao '%s' aparece duas vezes." % opcao)
        vistas.add(opcao.casefold())
        opcoes.append(opcao)
    if len(opcoes) > OPCOES_MAXIMO:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No maximo %d opcoes por item." % OPCOES_MAXIMO)
    return opcoes


def _resumo(campos: dict) -> str:
    """Campos alterados para o log (texto longo aparece so pelo nome)."""
    partes = []
    for nome, valor in sorted(campos.items()):
        if nome == "descricao":
            partes.append("descricao")
        elif nome == "opcoes":
            partes.append("opcoes=%d" % len(valor))
        else:
            partes.append("%s=%r" % (nome, valor))
    return " ".join(partes)


class CatalogoService(pb_grpc.CatalogoServiceServicer):
    def __init__(self, repositorio: RepositorioCatalogo) -> None:
        self.repositorio = repositorio

    def ListarItens(self, request, context):
        itens = self.repositorio.listar(request.categoria)
        log("ListarItens: categoria=%r -> %d itens" % (request.categoria or "todas", len(itens)))
        if request.categoria and not itens:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                "Categoria '%s' nao existe no cardapio." % request.categoria,
            )
        return pb.ListarItensResponse(
            restaurante=NOME_RESTAURANTE,
            itens=[_para_proto(linha) for linha in itens],
        )

    def ConsultarItens(self, request, context):
        codigos = sorted({_normalizar(c) for c in request.codigos if c.strip()})
        itens = self.repositorio.buscar_varios(codigos)
        log("ConsultarItens: %s -> %d encontrados" % (codigos, len(itens)))
        return pb.ConsultarItensResponse(itens=[_para_proto(linha) for linha in itens])

    def AtualizarItem(self, request, context):
        codigo = _normalizar(request.codigo)
        campos: dict = {}
        if request.HasField("disponivel"):
            campos["disponivel"] = request.disponivel
        if request.HasField("preco"):
            campos["preco"] = _preco(request.preco, context)
        if request.HasField("nome"):
            campos["nome"] = _nome(request.nome, context)
        if request.HasField("descricao"):
            campos["descricao"] = _descricao(request.descricao, context)
        if request.HasField("categoria"):
            campos["categoria"] = _categoria(request.categoria, context)[0]
        if request.HasField("opcoes"):
            campos["opcoes"] = _opcoes(request.opcoes.valores, context)
        log("AtualizarItem: codigo=%s %s" % (codigo, _resumo(campos) or "(nada)"))

        if not campos:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Nada para alterar: informe ao menos um campo.")
        linha = self.repositorio.atualizar(codigo, campos)
        if linha is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item '%s' nao existe no cardapio." % codigo)
        return _para_proto(linha)

    def CriarItem(self, request, context):
        chave = request.chave.strip() or str(uuid.uuid4())
        try:
            chave = str(uuid.UUID(chave))
        except ValueError:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Chave de criacao invalida (use um uuid).")
        categoria, prefixo = _categoria(request.categoria, context)
        item = {
            "nome": _nome(request.nome, context),
            "descricao": _descricao(request.descricao, context),
            "categoria": categoria,
            "preco": _preco(request.preco, context),
            "disponivel": request.disponivel,
            "opcoes": _opcoes(request.opcoes, context),
        }
        linha, novo = self.repositorio.criar(chave, prefixo, item)
        log("CriarItem: %s %r em %s%s" % (linha["codigo"], linha["nome"], categoria,
                                          "" if novo else " (repeticao da mesma chave: nada gravado)"))
        return _para_proto(linha)

    def ExcluirItem(self, request, context):
        codigo = _normalizar(request.codigo)
        existe = self.repositorio.excluir(codigo)
        log("ExcluirItem: %s%s" % (codigo, "" if existe else " (nao existe)"))
        if not existe:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item '%s' nao existe no cardapio." % codigo)
        return pb.ExcluirItemResponse(codigo=codigo)

    def SalvarFoto(self, request, context):
        codigo = _normalizar(request.codigo)
        conteudo = request.conteudo
        tipo = tipo_da_imagem(conteudo)
        log("SalvarFoto: %s %s %d KB" % (codigo, tipo or request.tipo or "?", len(conteudo) // 1024))
        if not conteudo:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Envie a foto no corpo da requisicao.")
        if len(conteudo) > FOTO_MAXIMO_BYTES:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          "A foto passa de %d KB." % (FOTO_MAXIMO_BYTES // 1024))
        if not tipo:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "O arquivo nao e uma foto JPEG, PNG ou WebP.")
        linha = self.repositorio.salvar_foto(codigo, tipo, conteudo, versao_da_foto(conteudo))
        if linha is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item '%s' nao existe no cardapio." % codigo)
        return _para_proto(linha)

    def RemoverFoto(self, request, context):
        codigo = _normalizar(request.codigo)
        log("RemoverFoto: %s" % codigo)
        linha = self.repositorio.remover_foto(codigo)
        if linha is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item '%s' nao existe no cardapio." % codigo)
        return _para_proto(linha)

    def ObterFoto(self, request, context):
        codigo = _normalizar(request.codigo)
        foto = self.repositorio.obter_foto(codigo)
        if foto is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "O item '%s' nao tem foto." % codigo)
        return pb.Foto(codigo=foto["codigo"], tipo=foto["tipo"], conteudo=bytes(foto["conteudo"]),
                       versao=foto["versao"])
