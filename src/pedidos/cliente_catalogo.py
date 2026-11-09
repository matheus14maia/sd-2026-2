"""Cliente gRPC que o microsservico de Pedidos usa para falar com o Catalogo.

Comunicacao entre microsservicos: Pedidos nao le a tabela itens_cardapio, ele
pergunta ao Catalogo, que e o dono desses dados.

A chamada passa pelo ClienteResiliente (retry com backoff + circuit breaker) e
respeita o prazo que o Gateway deu para o CriarPedido (propagacao de deadline):
o Pedidos desiste do Catalogo antes de o Gateway desistir do Pedidos.

Local: CATALOGO_HOST=catalogo, CATALOGO_PORTA=9091 (rede do compose).
Cloud Run: CATALOGO_HOST=<servico>.run.app, CATALOGO_PORTA=443 (TLS + ID token).
"""

import os

from ..comum.canal import criar_canal
from ..comum.registro import metadados_trace
from ..comum.resiliencia import ClienteResiliente
from ..gerado import catalogo_pb2 as catalogo_pb
from ..gerado import catalogo_pb2_grpc as catalogo_grpc

CATALOGO_HOST = os.getenv("CATALOGO_HOST", "localhost")
CATALOGO_PORTA = int(os.getenv("CATALOGO_PORTA", "9091"))
# Folga entre o prazo do Gateway e o do Pedidos: sobra tempo para o Pedidos
# responder "Catalogo indisponivel" antes de o Gateway desistir por timeout.
FOLGA_SEGUNDOS = 0.5


class ClienteCatalogo:
    def __init__(self) -> None:
        self.endereco = f"{CATALOGO_HOST}:{CATALOGO_PORTA}"
        self.canal = criar_canal(CATALOGO_HOST, CATALOGO_PORTA)
        self.stub = catalogo_grpc.CatalogoServiceStub(self.canal)
        self.resiliencia = ClienteResiliente("catalogo")

    def consultar(self, codigos: list[str], prazo: float | None = None) -> dict[str, catalogo_pb.ItemCardapio]:
        """Itens encontrados, indexados pelo codigo.

        `prazo`: segundos que restam para quem chamou o Pedidos (None = padrao).
        Pode lancar grpc.RpcError ou CircuitoAberto.
        """
        requisicao = catalogo_pb.ConsultarItensRequest(codigos=codigos)
        metadados = metadados_trace()
        if prazo is not None:
            prazo = max(0.1, prazo - FOLGA_SEGUNDOS)
        resposta = self.resiliencia.chamar(
            "ConsultarItens",
            lambda **opcoes: self.stub.ConsultarItens(requisicao, metadata=metadados, **opcoes),
            prazo=prazo,
        )
        return {item.codigo: item for item in resposta.itens}

    def fechar(self) -> None:
        self.canal.close()
