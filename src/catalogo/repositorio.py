"""Camada de acesso a dados do Catalogo: tabela itens_cardapio no PostgreSQL.

So SQL e conversao de linha para dicionario. Regra de negocio fica no servico.
"""

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

COLUNAS = "codigo, nome, descricao, categoria, preco::float8 AS preco, disponivel"


class RepositorioCatalogo:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def listar(self, categoria: str = "") -> list[dict]:
        sql = f"SELECT {COLUNAS} FROM itens_cardapio"
        parametros: tuple = ()
        if categoria:
            sql += " WHERE lower(categoria) = lower(%s)"
            parametros = (categoria.strip(),)
        sql += " ORDER BY codigo"
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(sql, parametros).fetchall()

    def buscar_varios(self, codigos: list[str]) -> list[dict]:
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    f"SELECT {COLUNAS} FROM itens_cardapio WHERE codigo = ANY(%s) ORDER BY codigo",
                    (codigos,),
                ).fetchall()

    def atualizar(self, codigo: str, disponivel: bool, preco: float | None) -> dict | None:
        """UPDATE do item. Devolve a linha ja alterada, ou None se nao existe."""
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    f"""
                    UPDATE itens_cardapio
                       SET disponivel = %s,
                           preco = COALESCE(%s, preco),
                           atualizado_em = now()
                     WHERE codigo = %s
                 RETURNING {COLUNAS}
                    """,
                    (disponivel, preco, codigo),
                ).fetchone()
