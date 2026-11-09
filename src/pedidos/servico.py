"""Implementacao do PedidoService definido em proto/pedidos.proto.

CriarPedido orquestra os dois microsservicos: valida a requisicao, pergunta ao
Catalogo (gRPC) se os itens existem, estao disponiveis e quanto custam, calcula
o total e grava pedido + itens no PostgreSQL numa transacao.

Todo pedido tem dono (usuario_id). Quem preenche o dono e o nome do cliente e o
Gateway, a partir do token JWT; ObterPedido e ListarPedidos recebem o usuario_id
para filtrar (papel cliente) ou vazio para ver tudo (papel cozinha).
"""

import uuid
from datetime import datetime

import grpc

from ..comum.registro import log
from ..comum.resiliencia import METADADO_FALHA_DEPENDENCIA, CircuitoAberto
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
        usuario_id=pedido["usuario_id"],
        cliente=pedido["cliente"],
        endereco=pedido["endereco"],
        status=pb.StatusPedido.Value(pedido["status"]),
        itens=[pb.ItemConfirmado(**linha) for linha in pedido["itens"]],
        total=pedido["total"],
        tempo_estimado_minutos=pedido["tempo_estimado_minutos"],
        criado_em=_iso(pedido["criado_em"]),
        atualizado_em=_iso(pedido["atualizado_em"]),
    )


def _uuid_valido(valor: str) -> bool:
    try:
        uuid.UUID(valor)
        return True
    except ValueError:
        return False


def _filtro_dono(request, context) -> str | None:
    """usuario_id do filtro (None = sem filtro). Recusa id malformado."""
    usuario_id = request.usuario_id.strip()
    if not usuario_id:
        return None
    if not _uuid_valido(usuario_id):
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "usuario_id invalido: '%s'." % usuario_id)
    return usuario_id


class PedidoService(pb_grpc.PedidoServiceServicer):
    def __init__(self, repositorio: RepositorioPedidos, catalogo: ClienteCatalogo) -> None:
        self.repositorio = repositorio
        self.catalogo = catalogo

    # ------------------------------------------------------------ CriarPedido
    def CriarPedido(self, request, context):
        linhas = [(i.codigo.strip().upper(), i.quantidade) for i in request.itens]
        usuario_id = request.usuario_id.strip()
        pedido_id = request.pedido_id.strip() or str(uuid.uuid4())
        log("CriarPedido: pedido=%s usuario=%s cliente=%r itens=%s"
            % (pedido_id, usuario_id, request.cliente, linhas))

        # O Gateway ja valida o payload e preenche o dono a partir do token; a
        # checagem aqui protege o servico de qualquer outro chamador gRPC.
        if not _uuid_valido(usuario_id):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Informe o usuario_id (UUID) do dono do pedido.")
        if not _uuid_valido(pedido_id):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "pedido_id invalido: '%s'." % pedido_id)
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

        # Idempotencia: o Gateway repete a chamada com o mesmo pedido_id quando
        # a primeira tentativa estoura o prazo. Se ela chegou a gravar, devolve
        # o pedido gravado em vez de criar outro.
        existente = self.repositorio.buscar(pedido_id)
        if existente is not None:
            return self._repeticao(existente, usuario_id, context)

        try:
            catalogo = self.catalogo.consultar(
                sorted({codigo for codigo, _ in linhas}), prazo=context.time_remaining()
            )
        except (grpc.RpcError, CircuitoAberto) as erro:
            motivo = erro.code().name if isinstance(erro, grpc.RpcError) else "circuito aberto"
            log("Catalogo indisponivel para o pedido %s: %s" % (pedido_id, motivo), "ERROR",
                dependencia="catalogo")
            # Avisa quem chamou que a falha e do Catalogo: o Gateway nao repete o
            # CriarPedido (o retry no Catalogo ja foi feito aqui) e nao conta a
            # falha contra o Pedidos.
            context.set_trailing_metadata(((METADADO_FALHA_DEPENDENCIA, "catalogo"),))
            context.abort(
                grpc.StatusCode.UNAVAILABLE,
                "Catalogo indisponivel no momento (%s): nao foi possivel confirmar os itens. "
                "Tente novamente em instantes." % motivo,
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

        gravado = self.repositorio.inserir(
            pedido_id=pedido_id,
            usuario_id=usuario_id,
            cliente=request.cliente.strip(),
            endereco=request.endereco.strip(),
            status=ETAPAS[0],
            itens=confirmados,
            total=round(total, 2),
            tempo_estimado_minutos=TEMPO_BASE_MINUTOS + TEMPO_POR_UNIDADE_MINUTOS * unidades,
        )
        pedido = self.repositorio.buscar(pedido_id)
        if not gravado:  # outra tentativa com o mesmo id gravou primeiro
            return self._repeticao(pedido, usuario_id, context)
        log(
            "Pedido %s gravado: %d itens, %d unidades, total R$ %.2f"
            % (pedido_id, len(confirmados), unidades, pedido["total"])
        )
        return _para_proto(pedido)

    def _repeticao(self, pedido: dict, usuario_id: str, context):
        if pedido["usuario_id"] != usuario_id:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, "Id de pedido ja usado.")
        log("CriarPedido repetido (idempotente): pedido %s ja estava gravado" % pedido["pedido_id"], "NOTICE")
        return _para_proto(pedido)

    # ------------------------------------------------------------ ObterPedido
    def ObterPedido(self, request, context):
        pedido_id = request.pedido_id.strip()
        dono = _filtro_dono(request, context)
        log("ObterPedido: pedido_id=%r dono=%s" % (pedido_id, dono or "qualquer"))
        if not _uuid_valido(pedido_id):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Id de pedido invalido: '%s'." % pedido_id)
        pedido = self.repositorio.buscar(pedido_id, dono)
        if pedido is None:
            # Pedido de outro usuario responde igual a inexistente: nao revela o id.
            context.abort(grpc.StatusCode.NOT_FOUND, "Pedido '%s' nao encontrado." % pedido_id)
        return _para_proto(pedido)

    # ---------------------------------------------------------- ListarPedidos
    def ListarPedidos(self, request, context):
        limite = request.limite if request.limite > 0 else LIMITE_PADRAO
        limite = min(limite, LIMITE_MAXIMO)
        dono = _filtro_dono(request, context)
        pedidos = self.repositorio.listar(limite, dono)
        log("ListarPedidos: limite=%d dono=%s -> %d pedidos" % (limite, dono or "todos", len(pedidos)))
        return pb.ListarPedidosResponse(pedidos=[_para_proto(p) for p in pedidos])

    # -------------------------------------------------------- AtualizarStatus
    def AtualizarStatus(self, request, context):
        pedido_id = request.pedido_id.strip()
        novo = pb.StatusPedido.Name(request.status)
        log("AtualizarStatus: pedido_id=%r -> %s" % (pedido_id, novo))

        if novo not in ETAPAS:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Status '%s' invalido." % novo)
        if not _uuid_valido(pedido_id):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Id de pedido invalido: '%s'." % pedido_id)

        pedido = self.repositorio.buscar(pedido_id)
        if pedido is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Pedido '%s' nao encontrado." % pedido_id)

        atual = pedido["status"]
        if novo == atual:
            # Idempotente: repetir a mesma mudanca (ex.: retry depois de um
            # timeout) devolve o pedido como esta, sem erro e sem nova escrita.
            log("Pedido %s ja estava em %s (sem alteracao)" % (pedido_id, atual))
            return _para_proto(pedido)

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
