"""Camada de acesso a dados de Pedidos: tabelas pedidos e itens_pedido.

O pedido e suas linhas sao gravados na mesma transacao: ou entra tudo, ou nada.
O id do pedido vem de quem chama (chave de idempotencia): gravar de novo o mesmo
id nao duplica nada (ON CONFLICT DO NOTHING).
"""

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

COLUNAS_PEDIDO = """
    id::text AS pedido_id, COALESCE(usuario_id::text, '') AS usuario_id, cliente, endereco,
    status, total::float8 AS total, tempo_estimado_minutos, criado_em, atualizado_em
"""
COLUNAS_ITEM = """
    codigo, nome, quantidade, preco_unitario::float8 AS preco_unitario,
    subtotal::float8 AS subtotal
"""
# Filtro opcional pelo dono: com usuario_id NULL o filtro nao restringe nada.
FILTRO_DONO = "(%(usuario_id)s::uuid IS NULL OR usuario_id = %(usuario_id)s::uuid)"


class RepositorioPedidos:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def inserir(self, pedido_id: str, usuario_id: str, cliente: str, endereco: str, status: str,
                itens: list[dict], total: float, tempo_estimado_minutos: int) -> bool:
        """Grava pedido + itens. Devolve False se ja existia pedido com este id."""
        with self.pool.connection() as conexao:  # commit ao sair do bloco sem erro
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO pedidos
                        (id, usuario_id, cliente, endereco, status, total, tempo_estimado_minutos)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (pedido_id, usuario_id, cliente, endereco, status, total, tempo_estimado_minutos),
                )
                if cursor.rowcount == 0:
                    return False
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
        return True

    def buscar(self, pedido_id: str, usuario_id: str | None = None) -> dict | None:
        """Pedido com os itens. Com usuario_id, so encontra se o pedido for dele."""
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                pedido = cursor.execute(
                    f"SELECT {COLUNAS_PEDIDO} FROM pedidos WHERE id = %(id)s AND {FILTRO_DONO}",
                    {"id": pedido_id, "usuario_id": usuario_id},
                ).fetchone()
                if pedido is None:
                    return None
                pedido["itens"] = cursor.execute(
                    f"SELECT {COLUNAS_ITEM} FROM itens_pedido WHERE pedido_id = %s ORDER BY linha",
                    (pedido_id,),
                ).fetchall()
                return pedido

    def listar(self, limite: int, usuario_id: str | None = None) -> list[dict]:
        """Pedidos mais recentes. Com usuario_id, so os pedidos desse usuario."""
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                pedidos = cursor.execute(
                    f"SELECT {COLUNAS_PEDIDO} FROM pedidos WHERE {FILTRO_DONO} "
                    "ORDER BY criado_em DESC LIMIT %(limite)s",
                    {"usuario_id": usuario_id, "limite": limite},
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
