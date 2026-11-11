"""Camada de acesso a dados de Usuarios: tabela usuarios no PostgreSQL.

So SQL e conversao de linha para dicionario. Hash de senha e regra de negocio
ficam no servico.
"""

import uuid

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from ..comum.rastreamento import rastrear_banco

COLUNAS = "id::text AS id, login, nome, papel, criado_em, telefone, endereco"
CAMPOS_EDITAVEIS = {"nome", "telefone", "endereco"}


class LoginDuplicado(Exception):
    """O login ja existe (violacao do UNIQUE da coluna login)."""


class RepositorioUsuarios:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    @rastrear_banco("usuarios.inserir")
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

    @rastrear_banco("usuarios.buscar_por_id")
    def buscar_por_id(self, usuario_id: str) -> dict | None:
        """Linha do usuario com o senha_hash, ou None se o id nao existe."""
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    f"SELECT {COLUNAS}, senha_hash FROM usuarios WHERE id = %s",
                    (usuario_id,),
                ).fetchone()

    @rastrear_banco("usuarios.atualizar")
    def atualizar(self, usuario_id: str, campos: dict) -> dict | None:
        """UPDATE so dos campos informados. None se o id nao existe."""
        desconhecidos = set(campos) - CAMPOS_EDITAVEIS
        if desconhecidos:
            raise ValueError("campos nao editaveis: %s" % sorted(desconhecidos))
        atribuicoes = sql.SQL(", ").join(
            sql.SQL("{} = {}").format(sql.Identifier(nome), sql.Placeholder(nome)) for nome in sorted(campos)
        )
        consulta = sql.SQL("UPDATE usuarios SET {} WHERE id = %(id)s RETURNING " + COLUNAS).format(atribuicoes)
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(consulta, {**campos, "id": usuario_id}).fetchone()

    @rastrear_banco("usuarios.trocar_senha")
    def trocar_senha(self, usuario_id: str, senha_hash: str) -> dict | None:
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    f"UPDATE usuarios SET senha_hash = %s WHERE id = %s RETURNING {COLUNAS}",
                    (senha_hash, usuario_id),
                ).fetchone()

    @rastrear_banco("usuarios.buscar_por_login")
    def buscar_por_login(self, login: str) -> dict | None:
        """Linha do usuario com o senha_hash, ou None se o login nao existe."""
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    f"SELECT {COLUNAS}, senha_hash FROM usuarios WHERE login = %s",
                    (login,),
                ).fetchone()
