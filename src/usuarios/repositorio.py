"""Camada de acesso a dados de Usuarios: tabela usuarios no PostgreSQL.

So SQL e conversao de linha para dicionario. Hash de senha e regra de negocio
ficam no servico.
"""

import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

COLUNAS = "id::text AS id, login, nome, papel, criado_em"


class LoginDuplicado(Exception):
    """O login ja existe (violacao do UNIQUE da coluna login)."""


class RepositorioUsuarios:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def inserir(self, login: str, nome: str, senha_hash: str) -> dict:
        try:
            with self.pool.connection() as conexao:
                with conexao.cursor(row_factory=dict_row) as cursor:
                    return cursor.execute(
                        f"""
                        INSERT INTO usuarios (id, login, nome, senha_hash)
                        VALUES (%s, %s, %s, %s)
                        RETURNING {COLUNAS}
                        """,
                        (uuid.uuid4(), login, nome, senha_hash),
                    ).fetchone()
        except psycopg.errors.UniqueViolation as erro:
            raise LoginDuplicado(login) from erro

    def buscar_por_login(self, login: str) -> dict | None:
        """Linha do usuario com o senha_hash, ou None se o login nao existe."""
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    f"SELECT {COLUNAS}, senha_hash FROM usuarios WHERE login = %s",
                    (login,),
                ).fetchone()
