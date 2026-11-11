"""Conexao com o PostgreSQL compartilhada pelos microsservicos.

Toda a configuracao vem de variavel de ambiente, para o mesmo codigo rodar
contra o container local (profile banco-local) e contra o Cloud SQL no GCP:

    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_SSLMODE, DB_POOL_MAX

No Cloud Run, DB_HOST e o diretorio do socket do conector do Cloud SQL
(/cloudsql/PROJETO:REGIAO:INSTANCIA): a conexao passa pelo conector gerenciado,
criptografada e autorizada pela conta de servico (papel Cloud SQL Client), sem
IP liberado no banco. Por isso DB_SSLMODE=disable nesse caso.
"""

import os
import time

import psycopg
from psycopg_pool import ConnectionPool

from .registro import log

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
            log(
                "Banco indisponivel (tentativa %d/%d): %s"
                % (tentativa, TENTATIVAS_CONEXAO, str(erro).strip().splitlines()[0]),
                "WARNING",
            )
            time.sleep(INTERVALO_TENTATIVA_SEGUNDOS)
    raise RuntimeError("Nao foi possivel conectar em %s" % descricao_destino()) from ultimo_erro


def criar_pool() -> ConnectionPool:
    """Pool de conexoes. `check` testa a conexao antes de emprestar: se o banco
    reiniciou ou derrubou uma conexao ociosa, o pool descarta e abre outra, em
    vez de entregar uma conexao morta para a chamada."""
    aguardar_banco()
    pool = ConnectionPool(
        parametros_conexao(),
        min_size=1,
        max_size=int(os.getenv("DB_POOL_MAX", "5")),
        timeout=float(os.getenv("DB_POOL_TIMEOUT", "5")),
        max_idle=300,
        check=ConnectionPool.check_connection,
        open=True,
    )
    pool.wait(timeout=30)
    return pool
