"""Implementacao do PedidoService definido em proto/pedidos.proto.

CriarPedido orquestra os dois microsservicos: valida a requisicao, pergunta ao
Catalogo (gRPC) se os itens existem, estao disponiveis e quanto custam, calcula
o total e grava pedido + itens no PostgreSQL numa transacao.
"""

import uuid
from datetime import datetime

import grpc

from ..comum.servidor_grpc import log
from ..gerado import pedidos_pb2 as pb
from ..gerado import pedidos_pb2_grpc as pb_grpc
from .cliente_catalogo import ClienteCatalogo
from .repositorio import RepositorioPedidos

# Tempo base de preparo + acrescimo por unidade pedida.
TEMPO_BASE_MINUTOS = 15
TEMPO_POR_UNIDADE_MINUTOS = 3

# Ordem das etapas. Um pedido so avanca para a etapa seguinte.
ETAPAS = ("RECEBIDO", "EM_PREPARO", "PRONTO", "SAIU_PARA_ENTREGA", "ENTREGUE")

LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200


def _iso(momento: datetime) -> str:
    return momento.astimezone().isoformat(timespec="seconds")


def _para_proto(pedido: dict) -> pb.Pedido:
    return pb.Pedido(
        pedido_id=pedido["pedido_id"],
        cliente=pedido["cliente"],
        endereco=pedido["endereco"],
        status=pb.StatusPedido.Value(pedido["status"]),
        itens=[pb.ItemConfirmado(**linha) for linha in pedido["itens"]],
        total=pedido["total"],
        tempo_estimado_minutos=pedido["tempo_estimado_minutos"],
        criado_em=_iso(pedido["criado_em"]),
        atualizado_em=_iso(pedido["atualizado_em"]),
    )


def _id_valido(pedido_id: str) -> bool:
    try:
        uuid.UUID(pedido_id)
        return True
    except ValueError:
        return False


class PedidoService(pb_grpc.PedidoServiceServicer):
    def __init__(self, repositorio: RepositorioPedidos, catalogo: ClienteCatalogo) -> None:
        self.repositorio = repositorio
        self.catalogo = catalogo

    # ------------------------------------------------------------ CriarPedido
    def CriarPedido(self, request, context):
        linhas = [(i.codigo.strip().upper(), i.quantidade) for i in request.itens]
        log("CriarPedido: cliente=%r itens=%s" % (request.cliente, linhas))

        # O Gateway ja valida o payload; a checagem aqui protege o servico de
        # qualquer outro chamador gRPC (defesa em profundidade).
        if not request.cliente.strip():
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Informe o nome do cliente.")
        if not request.endereco.strip():
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Informe o endereco de entrega.")
        if not linhas:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "O pedido precisa de pelo menos um item.")
        for codigo, quantidade in linhas:
            if quantidade <= 0:
                context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    "Quantidade invalida (%d) para o item %s. Use um numero maior que zero."
                    % (quantidade, codigo),
                )

        try:
            catalogo = self.catalogo.consultar(sorted({codigo for codigo, _ in linhas}))
        except grpc.RpcError as erro:
            log("Catalogo falhou: %s %s" % (erro.code().name, erro.details()))
            context.abort(
                grpc.StatusCode.UNAVAILABLE,
                "Catalogo indisponivel no momento (%s). Tente novamente." % erro.code().name,
            )

        confirmados = []
        total = 0.0
        unidades = 0
        for codigo, quantidade in linhas:
            item = catalogo.get(codigo)
            if item is None:
                context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    "Item '%s' nao existe no cardapio." % codigo,
                )
            if not item.disponivel:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION,
                    "Item '%s' (%s) esta indisponivel hoje." % (item.codigo, item.nome),
                )
            subtotal = round(item.preco * quantidade, 2)
            total += subtotal
            unidades += quantidade
            confirmados.append(
                {
                    "codigo": item.codigo,
                    "nome": item.nome,
                    "quantidade": quantidade,
                    "preco_unitario": item.preco,
                    "subtotal": subtotal,
                }
            )

        pedido = self.repositorio.inserir(
            cliente=request.cliente.strip(),
            endereco=request.endereco.strip(),
            status=ETAPAS[0],
            itens=confirmados,
            total=round(total, 2),
            tempo_estimado_minutos=TEMPO_BASE_MINUTOS + TEMPO_POR_UNIDADE_MINUTOS * unidades,
        )
        log(
            "Pedido %s gravado: %d itens, %d unidades, total R$ %.2f"
            % (pedido["pedido_id"], len(confirmados), unidades, pedido["total"])
        )
        return _para_proto(pedido)

    # ------------------------------------------------------------ ObterPedido
    def ObterPedido(self, request, context):
        pedido_id = request.pedido_id.strip()
        log("ObterPedido: pedido_id=%r" % pedido_id)
        if not _id_valido(pedido_id):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Id de pedido invalido: '%s'." % pedido_id)
        pedido = self.repositorio.buscar(pedido_id)
        if pedido is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Pedido '%s' nao encontrado." % pedido_id)
        return _para_proto(pedido)

    # ---------------------------------------------------------- ListarPedidos
    def ListarPedidos(self, request, context):
        limite = request.limite if request.limite > 0 else LIMITE_PADRAO
        limite = min(limite, LIMITE_MAXIMO)
        pedidos = self.repositorio.listar(limite)
        log("ListarPedidos: limite=%d -> %d pedidos" % (limite, len(pedidos)))
        return pb.ListarPedidosResponse(pedidos=[_para_proto(p) for p in pedidos])

    # -------------------------------------------------------- AtualizarStatus
    def AtualizarStatus(self, request, context):
        pedido_id = request.pedido_id.strip()
        novo = pb.StatusPedido.Name(request.status)
        log("AtualizarStatus: pedido_id=%r -> %s" % (pedido_id, novo))

        if novo not in ETAPAS:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Status '%s' invalido." % novo)
        if not _id_valido(pedido_id):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Id de pedido invalido: '%s'." % pedido_id)

        pedido = self.repositorio.buscar(pedido_id)
        if pedido is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Pedido '%s' nao encontrado." % pedido_id)

        atual = pedido["status"]
        indice = ETAPAS.index(atual)
        esperado = ETAPAS[indice + 1] if indice + 1 < len(ETAPAS) else None
        if novo != esperado:
            if esperado is None:
                motivo = "o pedido ja foi entregue"
            else:
                motivo = "a proxima etapa e %s" % esperado
            context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                "Nao e possivel mudar de %s para %s: %s." % (atual, novo, motivo),
            )

        if not self.repositorio.atualizar_status(pedido_id, atual, novo):
            context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                "O pedido mudou de status durante a operacao. Consulte e tente de novo.",
            )
        log("Pedido %s: %s -> %s" % (pedido_id, atual, novo))
        return _para_proto(self.repositorio.buscar(pedido_id))
