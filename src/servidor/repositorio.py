"""Armazenamento em memoria dos pedidos.

O servidor gRPC atende varias chamadas em paralelo (ThreadPoolExecutor), entao
todo acesso ao dicionario passa por um lock.
"""

import threading
import uuid
from dataclasses import dataclass, field


@dataclass
class Pedido:
    pedido_id: str
    cliente: str
    endereco: str
    itens: list = field(default_factory=list)  # lista de dicts ja precificados
    total: float = 0.0
    tempo_estimado_minutos: int = 0


class RepositorioPedidos:
    def __init__(self) -> None:
        self._pedidos: dict[str, Pedido] = {}
        self._lock = threading.Lock()

    def salvar(self, cliente: str, endereco: str, itens: list, total: float,
               tempo_estimado_minutos: int) -> Pedido:
        pedido = Pedido(
            pedido_id=str(uuid.uuid4()),
            cliente=cliente,
            endereco=endereco,
            itens=itens,
            total=total,
            tempo_estimado_minutos=tempo_estimado_minutos,
        )
        with self._lock:
            self._pedidos[pedido.pedido_id] = pedido
        return pedido

    def buscar(self, pedido_id: str) -> Pedido | None:
        with self._lock:
            return self._pedidos.get((pedido_id or "").strip())

    def quantidade(self) -> int:
        with self._lock:
            return len(self._pedidos)
