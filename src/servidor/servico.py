"""Implementacao do RestauranteService definido em proto/restaurante.proto.

Cada metodo aqui e um RPC. As regras de validacao devolvem status codes do gRPC
(context.abort), que e como o servidor "reage" a uma requisicao invalida: o
cliente recebe o codigo e a mensagem, e nao uma resposta pela metade.
"""

import time
from datetime import datetime

import grpc

from ..gerado import restaurante_pb2 as pb
from ..gerado import restaurante_pb2_grpc as pb_grpc
from . import cardapio
from .repositorio import RepositorioPedidos

# Tempo base de preparo + acrescimo por unidade pedida.
TEMPO_BASE_MINUTOS = 15
TEMPO_POR_UNIDADE_MINUTOS = 3

# Sequencia de status emitida pelo acompanhamento e a pausa entre cada etapa.
ETAPAS = (
    (pb.EM_PREPARO, "A cozinha comecou a preparar o seu pedido."),
    (pb.PRONTO, "Pedido pronto, aguardando o entregador."),
    (pb.SAIU_PARA_ENTREGA, "Entregador a caminho do endereco informado."),
    (pb.ENTREGUE, "Pedido entregue. Bom apetite!"),
)
INTERVALO_ETAPA_SEGUNDOS = 2.0


def _agora() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _log(mensagem: str) -> None:
    print(f"[{_agora()}] {mensagem}", flush=True)


class RestauranteService(pb_grpc.RestauranteServiceServicer):
    def __init__(self) -> None:
        self.repositorio = RepositorioPedidos()

    # ------------------------------------------------------------------ RPC 1
    def ObterCardapio(self, request, context):
        itens = cardapio.listar(request.categoria)
        _log(
            "ObterCardapio: categoria=%r -> %d itens"
            % (request.categoria or "todas", len(itens))
        )
        if request.categoria and not itens:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                "Categoria '%s' nao existe no cardapio." % request.categoria,
            )
        return pb.ObterCardapioResponse(
            restaurante=cardapio.NOME_RESTAURANTE,
            itens=[
                pb.ItemCardapio(
                    codigo=item.codigo,
                    nome=item.nome,
                    descricao=item.descricao,
                    categoria=item.categoria,
                    preco=item.preco,
                    disponivel=item.disponivel,
                )
                for item in itens
            ],
        )

    # ------------------------------------------------------------------ RPC 2
    def CriarPedido(self, request, context):
        _log(
            "CriarPedido: cliente=%r itens=%s"
            % (
                request.cliente,
                [(i.codigo, i.quantidade) for i in request.itens],
            )
        )

        if not request.cliente.strip():
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "Informe o nome do cliente.",
            )
        if not request.itens:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "O pedido precisa de pelo menos um item.",
            )

        confirmados = []
        total = 0.0
        unidades = 0

        for linha in request.itens:
            if linha.quantidade <= 0:
                context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    "Quantidade invalida (%d) para o item %s. Use um numero maior que zero."
                    % (linha.quantidade, linha.codigo),
                )

            item = cardapio.buscar(linha.codigo)
            if item is None:
                context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    "Item '%s' nao existe no cardapio. Codigos validos: %s."
                    % (linha.codigo, cardapio.codigos_validos()),
                )
            if not item.disponivel:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION,
                    "Item '%s' (%s) esta indisponivel hoje." % (item.codigo, item.nome),
                )

            subtotal = round(item.preco * linha.quantidade, 2)
            total += subtotal
            unidades += linha.quantidade
            confirmados.append(
                {
                    "codigo": item.codigo,
                    "nome": item.nome,
                    "quantidade": linha.quantidade,
                    "preco_unitario": item.preco,
                    "subtotal": subtotal,
                }
            )

        total = round(total, 2)
        tempo = TEMPO_BASE_MINUTOS + TEMPO_POR_UNIDADE_MINUTOS * unidades

        pedido = self.repositorio.salvar(
            cliente=request.cliente.strip(),
            endereco=request.endereco.strip(),
            itens=confirmados,
            total=total,
            tempo_estimado_minutos=tempo,
        )

        _log(
            "Pedido %s aceito: %d itens, %d unidades, total R$ %.2f"
            % (pedido.pedido_id, len(confirmados), unidades, total)
        )

        return pb.CriarPedidoResponse(
            pedido_id=pedido.pedido_id,
            status=pb.RECEBIDO,
            itens=[pb.ItemConfirmado(**linha) for linha in confirmados],
            total=total,
            tempo_estimado_minutos=tempo,
            mensagem="Pedido recebido pelo %s. Entrega estimada em %d minutos."
            % (cardapio.NOME_RESTAURANTE, tempo),
        )

    # ------------------------------------------------------------------ RPC 3
    def AcompanharPedido(self, request, context):
        _log("AcompanharPedido: pedido_id=%r" % request.pedido_id)

        pedido = self.repositorio.buscar(request.pedido_id)
        if pedido is None:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                "Pedido '%s' nao encontrado." % request.pedido_id,
            )

        yield pb.StatusPedido(
            pedido_id=pedido.pedido_id,
            status=pb.RECEBIDO,
            descricao="Pedido confirmado pela cozinha.",
            horario=_agora(),
        )

        for status, descricao in ETAPAS:
            # Se o cliente desligar (Ctrl+C), o stream e encerrado sem erro.
            if not context.is_active():
                _log("Cliente desconectou do acompanhamento de %s" % pedido.pedido_id)
                return
            time.sleep(INTERVALO_ETAPA_SEGUNDOS)
            _log(
                "Pedido %s -> %s"
                % (pedido.pedido_id, pb.StatusPedidoEnum.Name(status))
            )
            yield pb.StatusPedido(
                pedido_id=pedido.pedido_id,
                status=status,
                descricao=descricao,
                horario=_agora(),
            )
