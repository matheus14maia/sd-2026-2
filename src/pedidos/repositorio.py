"""Camada de acesso a dados de Pedidos: tabelas pedidos e itens_pedido.

O pedido e suas linhas sao gravados na mesma transacao: ou entra tudo, ou nada.
"""

import uuid

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

COLUNAS_PEDIDO = """
    id::text AS pedido_id, cliente, endereco, status, total::float8 AS total,
    tempo_estimado_minutos, criado_em, atualizado_em
"""
COLUNAS_ITEM = """
    codigo, nome, quantidade, preco_unitario::float8 AS preco_unitario,
    subtotal::float8 AS subtotal
"""


class RepositorioPedidos:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def inserir(self, cliente: str, endereco: str, status: str, itens: list[dict],
                total: float, tempo_estimado_minutos: int) -> dict:
        pedido_id = uuid.uuid4()
        with self.pool.connection() as conexao:  # commit ao sair do bloco sem erro
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO pedidos (id, cliente, endereco, status, total, tempo_estimado_minutos)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (pedido_id, cliente, endereco, status, total, tempo_estimado_minutos),
                )
                cursor.executemany(
                    """
                    INSERT INTO itens_pedido
                        (pedido_id, linha, codigo, nome, quantidade, preco_unitario, subtotal)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (pedido_id, numero, i["codigo"], i["nome"], i["quantidade"],
                         i["preco_unitario"], i["subtotal"])
                        for numero, i in enumerate(itens, start=1)
                    ],
                )
        return self.buscar(str(pedido_id))

    def buscar(self, pedido_id: str) -> dict | None:
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                pedido = cursor.execute(
                    f"SELECT {COLUNAS_PEDIDO} FROM pedidos WHERE id = %s", (pedido_id,)
                ).fetchone()
                if pedido is None:
                    return None
                pedido["itens"] = cursor.execute(
                    f"SELECT {COLUNAS_ITEM} FROM itens_pedido WHERE pedido_id = %s ORDER BY linha",
                    (pedido_id,),
                ).fetchall()
                return pedido

    def listar(self, limite: int) -> list[dict]:
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                pedidos = cursor.execute(
                    f"SELECT {COLUNAS_PEDIDO} FROM pedidos ORDER BY criado_em DESC LIMIT %s",
                    (limite,),
                ).fetchall()
                if not pedidos:
                    return []
                ids = [p["pedido_id"] for p in pedidos]
                linhas = cursor.execute(
                    f"SELECT pedido_id::text AS pedido_id, {COLUNAS_ITEM} FROM itens_pedido "
                    "WHERE pedido_id = ANY(%s::uuid[]) ORDER BY pedido_id, linha",
                    (ids,),
                ).fetchall()
        por_pedido: dict[str, list] = {pid: [] for pid in ids}
        for linha in linhas:
            por_pedido[linha.pop("pedido_id")].append(linha)
        for pedido in pedidos:
            pedido["itens"] = por_pedido[pedido["pedido_id"]]
        return pedidos

    def atualizar_status(self, pedido_id: str, status_atual: str, novo_status: str) -> bool:
        """UPDATE condicional: so altera se o status ainda for o esperado.

        Evita que duas chamadas simultaneas avancem o mesmo pedido duas vezes.
        """
        with self.pool.connection() as conexao:
            cursor = conexao.execute(
                """
                UPDATE pedidos
                   SET status = %s, atualizado_em = now()
                 WHERE id = %s AND status = %s
                """,
                (novo_status, pedido_id, status_atual),
            )
            return cursor.rowcount == 1
