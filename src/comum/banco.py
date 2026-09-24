"""Conexao com o PostgreSQL compartilhada pelos microsservicos.

Toda a configuracao vem de variavel de ambiente, para o mesmo codigo rodar
contra o container local (profile banco-local) e contra o Cloud SQL no GCP:

    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_SSLMODE
"""

import os
import time

import psycopg
from psycopg_pool import ConnectionPool

TENTATIVAS_CONEXAO = int(os.getenv("DB_TENTATIVAS", "30"))
INTERVALO_TENTATIVA_SEGUNDOS = 2.0


def parametros_conexao() -> str:
    return psycopg.conninfo.make_conninfo(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "delivery"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        sslmode=os.getenv("DB_SSLMODE", "prefer"),
        connect_timeout="5",
        application_name=os.getenv("NOME_SERVICO", "delivery"),
    )


def descricao_destino() -> str:
    """Destino do banco sem a senha, para o log de inicializacao."""
    return "%s:%s/%s (sslmode=%s)" % (
        os.getenv("DB_HOST", "localhost"),
        os.getenv("DB_PORT", "5432"),
        os.getenv("DB_NAME", "delivery"),
        os.getenv("DB_SSLMODE", "prefer"),
    )


def aguardar_banco() -> None:
    """Bloqueia ate o banco aceitar conexao.

    No compose os servicos sobem juntos e o PostgreSQL leva alguns segundos
    para aceitar conexoes; no GCP a instancia do Cloud SQL pode estar ligando.
    """
    ultimo_erro = None
    for tentativa in range(1, TENTATIVAS_CONEXAO + 1):
        try:
            with psycopg.connect(parametros_conexao()) as conexao:
                conexao.execute("SELECT 1")
            return
        except psycopg.OperationalError as erro:
            ultimo_erro = erro
            print(
                "Banco indisponivel (tentativa %d/%d): %s"
                % (tentativa, TENTATIVAS_CONEXAO, str(erro).strip().splitlines()[0]),
                flush=True,
            )
            time.sleep(INTERVALO_TENTATIVA_SEGUNDOS)
    raise RuntimeError("Nao foi possivel conectar em %s" % descricao_destino()) from ultimo_erro


def criar_pool() -> ConnectionPool:
    aguardar_banco()
    pool = ConnectionPool(
        parametros_conexao(),
        min_size=1,
        max_size=int(os.getenv("DB_POOL_MAX", "5")),
        open=True,
    )
    pool.wait(timeout=30)
    return pool
