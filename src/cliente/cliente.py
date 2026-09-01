"""Cliente gRPC do delivery.

Este e o Microsservico A do trabalho: roda na maquina local, consulta o cardapio
do restaurante, monta o pedido (quais itens e quantas unidades de cada um),
envia o pedido e acompanha o status ate a entrega.

    python -m src.cliente.cliente --host 34.123.45.67
    python -m src.cliente.cliente --itens PR01:2,BE02:3 --cliente "Matheus"
"""

import argparse
import os
import sys

import grpc

from ..gerado import restaurante_pb2 as pb
from ..gerado import restaurante_pb2_grpc as pb_grpc

HOST_PADRAO = os.getenv("SERVIDOR_HOST", "localhost")
PORTA_PADRAO = os.getenv("SERVIDOR_PORTA", "50051")
TIMEOUT_SEGUNDOS = 10


# --------------------------------------------------------------------- saida
def titulo(texto: str) -> None:
    print()
    print("=" * 62)
    print(texto)
    print("=" * 62)


def moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def mostrar_cardapio(resposta) -> None:
    titulo(f"CARDAPIO - {resposta.restaurante}")
    categoria_atual = ""
    for item in resposta.itens:
        if item.categoria != categoria_atual:
            categoria_atual = item.categoria
            print(f"\n{categoria_atual.upper()}")
            print("-" * 62)
        marca = "" if item.disponivel else "   [INDISPONIVEL HOJE]"
        print(f"  {item.codigo}  {item.nome:<28} {moeda(item.preco):>12}{marca}")
        print(f"        {item.descricao}")
    print()


def mostrar_confirmacao(resposta) -> None:
    titulo("PEDIDO CONFIRMADO")
    print(f"ID do pedido : {resposta.pedido_id}")
    print(f"Status       : {pb.StatusPedidoEnum.Name(resposta.status)}")
    print()
    print(f"{'Item':<32}{'Qtd':>5}{'Unit.':>12}{'Subtotal':>13}")
    print("-" * 62)
    for item in resposta.itens:
        print(
            f"{item.nome[:30]:<32}{item.quantidade:>5}"
            f"{moeda(item.preco_unitario):>12}{moeda(item.subtotal):>13}"
        )
    print("-" * 62)
    print(f"{'TOTAL':<49}{moeda(resposta.total):>13}")
    print(f"\nTempo estimado: {resposta.tempo_estimado_minutos} minutos")
    print(resposta.mensagem)


# ------------------------------------------------------------------ interacao
def montar_pedido_interativo(resposta_cardapio) -> list:
    disponiveis = {
        item.codigo: item for item in resposta_cardapio.itens if item.disponivel
    }
    carrinho: dict[str, int] = {}

    titulo("MONTE O SEU PEDIDO")
    print("Digite o codigo do item (ex: PR01) e a quantidade.")
    print("Deixe o codigo em branco para finalizar.\n")

    while True:
        codigo = input("Codigo do item (ENTER para finalizar): ").strip().upper()
        if not codigo:
            if carrinho:
                break
            print("  > O pedido esta vazio. Escolha pelo menos um item.")
            continue

        item = disponiveis.get(codigo)
        if item is None:
            print(f"  > Codigo '{codigo}' invalido ou indisponivel. Tente de novo.")
            continue

        bruto = input(f"  Quantidade de '{item.nome}': ").strip()
        try:
            quantidade = int(bruto)
        except ValueError:
            print("  > Quantidade precisa ser um numero inteiro.")
            continue
        if quantidade <= 0:
            print("  > Quantidade precisa ser maior que zero.")
            continue

        carrinho[codigo] = carrinho.get(codigo, 0) + quantidade
        print(f"  > Adicionado: {quantidade}x {item.nome}")
        parcial = sum(disponiveis[c].preco * q for c, q in carrinho.items())
        print(
            f"  > Carrinho: {sum(carrinho.values())} unidade(s), parcial {moeda(parcial)}\n"
        )

    return [pb.ItemPedido(codigo=c, quantidade=q) for c, q in carrinho.items()]


def parsear_itens(texto: str) -> list:
    """Converte 'PR01:2,BE02:3' na lista de ItemPedido."""
    itens = []
    for parte in texto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if ":" not in parte:
            raise ValueError(f"Formato invalido em '{parte}'. Use CODIGO:QUANTIDADE.")
        codigo, quantidade = parte.split(":", 1)
        itens.append(
            pb.ItemPedido(codigo=codigo.strip().upper(), quantidade=int(quantidade))
        )
    return itens


# ---------------------------------------------------------------------- fluxo
def executar(args) -> int:
    alvo = f"{args.host}:{args.porta}"
    print(f"Conectando ao restaurante em {alvo} ...")

    with grpc.insecure_channel(alvo) as canal:
        stub = pb_grpc.RestauranteServiceStub(canal)

        cardapio = stub.ObterCardapio(
            pb.ObterCardapioRequest(categoria=args.categoria),
            timeout=TIMEOUT_SEGUNDOS,
        )
        mostrar_cardapio(cardapio)

        if args.itens:
            itens = parsear_itens(args.itens)
            nome = args.cliente
            endereco = args.endereco
            print(
                "Pedido automatico: "
                + ", ".join(f"{i.quantidade}x {i.codigo}" for i in itens)
            )
        else:
            nome = args.cliente or input("Seu nome: ").strip()
            endereco = args.endereco or input("Endereco de entrega: ").strip()
            itens = montar_pedido_interativo(cardapio)

        confirmacao = stub.CriarPedido(
            pb.CriarPedidoRequest(cliente=nome, endereco=endereco, itens=itens),
            timeout=TIMEOUT_SEGUNDOS,
        )
        mostrar_confirmacao(confirmacao)

        if args.sem_acompanhar:
            return 0

        titulo("ACOMPANHAMENTO EM TEMPO REAL (streaming gRPC)")
        for atualizacao in stub.AcompanharPedido(
            pb.AcompanharPedidoRequest(pedido_id=confirmacao.pedido_id)
        ):
            print(
                f"[{atualizacao.horario}] "
                f"{pb.StatusPedidoEnum.Name(atualizacao.status):<18} "
                f"{atualizacao.descricao}"
            )
        print("\nAcompanhamento encerrado pelo servidor.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Cliente de delivery via gRPC.")
    parser.add_argument("--host", default=HOST_PADRAO, help="IP ou host do servidor")
    parser.add_argument("--porta", default=PORTA_PADRAO, help="porta do servidor")
    parser.add_argument("--cliente", default="", help="nome do cliente")
    parser.add_argument("--endereco", default="", help="endereco de entrega")
    parser.add_argument(
        "--categoria", default="", help="filtra o cardapio por categoria"
    )
    parser.add_argument(
        "--itens",
        default="",
        help="pedido nao interativo no formato CODIGO:QTD,CODIGO:QTD",
    )
    parser.add_argument(
        "--sem-acompanhar",
        action="store_true",
        help="nao abre o stream de acompanhamento",
    )
    args = parser.parse_args()

    try:
        return executar(args)
    except grpc.RpcError as erro:
        codigo = erro.code()
        print(f"\nERRO gRPC: {codigo.name}", file=sys.stderr)
        print(f"Detalhe: {erro.details()}", file=sys.stderr)
        if codigo == grpc.StatusCode.UNAVAILABLE:
            print(
                "\nO cliente nao conseguiu falar com o servidor. Verifique:\n"
                f"  1. o servidor esta rodando em {args.host}:{args.porta}?\n"
                "  2. o IP externo da VM esta correto (ele muda se a VM reiniciar)?\n"
                f"  3. existe regra de firewall VPC liberando tcp:{args.porta}?\n"
                "  4. o container esta com a porta publicada (docker compose ps)?",
                file=sys.stderr,
            )
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado pelo usuario.")
        return 130
    except ValueError as erro:
        print(f"\nEntrada invalida: {erro}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
