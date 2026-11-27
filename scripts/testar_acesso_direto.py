#!/usr/bin/env python3
"""Chama os microsservicos direto, sem o Gateway, e confere o que cada um aceita.

Os tres microsservicos tem endpoint HTTPS publico no Cloud Run. Este roteiro
prova as duas metades disso:

  1. o endpoint esta no ar para qualquer um: o health check gRPC responde SERVING;
  2. o negocio nao: uma chamada sem a chave interna (ex.: ListarItens no
     Catalogo, ListarPedidos no Pedidos) responde UNAUTHENTICATED.

No Cloud Run (TLS na porta 443, endereco sem https://):

    python scripts/testar_acesso_direto.py \\
        --catalogo delivery-catalogo-xxxx-uc.a.run.app:443 \\
        --usuarios delivery-usuarios-xxxx-uc.a.run.app:443 \\
        --pedidos  delivery-pedidos-xxxx-uc.a.run.app:443

No computador (docker compose com CHAVE_INTERNA no .env), os padroes ja servem:
127.0.0.1:9091, :9092 e :9090. Sem CHAVE_INTERNA o negocio responde normalmente
e o roteiro avisa que a chave nao esta sendo exigida.
"""

import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import grpc  # noqa: E402
from grpc_health.v1 import health_pb2, health_pb2_grpc  # noqa: E402

from src.gerado import (  # noqa: E402
    catalogo_pb2,
    catalogo_pb2_grpc,
    pedidos_pb2,
    pedidos_pb2_grpc,
    usuarios_pb2,
    usuarios_pb2_grpc,
)

TIMEOUT = 30  # o Cloud Run pode estar com 0 instancias (partida a frio)


def canal(destino: str) -> grpc.Channel:
    if destino.endswith(":443"):
        return grpc.secure_channel(destino, grpc.ssl_channel_credentials())
    return grpc.insecure_channel(destino)


def negocio(nome: str, ch: grpc.Channel):
    """Uma chamada de leitura de cada servico, sem chave nenhuma."""
    if nome == "catalogo":
        return lambda: catalogo_pb2_grpc.CatalogoServiceStub(ch).ListarItens(
            catalogo_pb2.ListarItensRequest(), timeout=TIMEOUT), "ListarItens"
    if nome == "pedidos":
        return lambda: pedidos_pb2_grpc.PedidoServiceStub(ch).ListarPedidos(
            pedidos_pb2.ListarPedidosRequest(), timeout=TIMEOUT), "ListarPedidos"
    return lambda: usuarios_pb2_grpc.UsuarioServiceStub(ch).VerificarCredenciais(
        usuarios_pb2.VerificarCredenciaisRequest(login="ninguem", senha="x"), timeout=TIMEOUT), \
        "VerificarCredenciais"


def conferir_recusa(chamar, metodo: str) -> int:
    """0 se a chamada sem chave foi recusada com UNAUTHENTICATED, 1 se nao."""
    try:
        chamar()
    except grpc.RpcError as erro:
        codigo = erro.code()
        if codigo == grpc.StatusCode.UNAUTHENTICATED:
            print(f"OK   {metodo} sem chave recusado: UNAUTHENTICATED ({erro.details()})")
            return 0
        if codigo == grpc.StatusCode.DEADLINE_EXCEEDED and "stream" in metodo:
            print(f"AVISO {metodo} sem chave ficou aberto: a chave interna nao esta sendo exigida")
            return 1
        print(f"ERRO {metodo} sem chave: esperado UNAUTHENTICATED, veio {codigo.name} ({erro.details()})")
        return 1
    print(f"AVISO {metodo} sem chave respondeu OK: a chave interna nao esta sendo exigida")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--usuarios", default="127.0.0.1:9092")
    parser.add_argument("--catalogo", default="127.0.0.1:9091")
    parser.add_argument("--pedidos", default="127.0.0.1:9090")
    args = parser.parse_args()

    erros = 0
    for nome in ("usuarios", "catalogo", "pedidos"):
        destino = getattr(args, nome)
        print(f"\n== {nome} ({destino})")
        ch = canal(destino)

        try:
            resposta = health_pb2_grpc.HealthStub(ch).Check(health_pb2.HealthCheckRequest(), timeout=TIMEOUT)
            situacao = health_pb2.HealthCheckResponse.ServingStatus.Name(resposta.status)
            ok = situacao == "SERVING"
            print(f"{'OK  ' if ok else 'ERRO'} health check sem chave: {situacao}")
            erros += not ok
        except grpc.RpcError as erro:
            print(f"ERRO health check sem chave: {erro.code().name} {erro.details()}")
            erros += 1

        chamadas = [negocio(nome, ch)]
        if nome == "pedidos":
            # O stream de tempo real tambem e negocio: tem que ser recusado.
            stub = pedidos_pb2_grpc.PedidoServiceStub(ch)
            chamadas.append((lambda: next(stub.AcompanharPedidos(
                pedidos_pb2.AcompanharPedidosRequest(), timeout=TIMEOUT)), "AcompanharPedidos (stream)"))
        for chamar, metodo in chamadas:
            erros += conferir_recusa(chamar, metodo)
        ch.close()

    print("\nAcesso direto OK: endpoint publico, negocio so com a chave interna." if not erros
          else f"\n{erros} verificacao(oes) falharam.")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
