#!/usr/bin/env python3
"""Cria as tabelas, carrega o cardapio e garante o usuario da cozinha no PostgreSQL.

Aplica db/schema.sql e db/seed.sql, nessa ordem, numa unica transacao. Os dois
arquivos sao idempotentes, entao o script pode rodar a cada deploy: no compose
ele e o servico one-shot `migrador`, que termina antes dos microsservicos subirem.

O usuario com papel cozinha vem do ambiente, nunca do repositorio:

    DEMO_LOGIN   login (padrao "professor")
    DEMO_SENHA   senha; sem ela, nenhum usuario da cozinha e criado

    python scripts/migrar_banco.py
"""

import os
import pathlib
import sys
import uuid

import bcrypt
import psycopg

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.comum.banco import aguardar_banco, descricao_destino, parametros_conexao  # noqa: E402

ARQUIVOS = (RAIZ / "db" / "schema.sql", RAIZ / "db" / "seed.sql")


def garantir_usuario_cozinha(conexao: psycopg.Connection) -> None:
    login = os.getenv("DEMO_LOGIN", "professor").strip().lower()
    senha = os.getenv("DEMO_SENHA", "")
    if len(senha) < 6:
        print("  DEMO_SENHA ausente ou curta: usuario da cozinha nao criado.", flush=True)
        return

    linha = conexao.execute("SELECT senha_hash FROM usuarios WHERE login = %s", (login,)).fetchone()
    if linha and bcrypt.checkpw(senha.encode(), linha[0].encode()):
        conexao.execute("UPDATE usuarios SET papel = 'cozinha' WHERE login = %s", (login,))
    else:
        conexao.execute(
            """
            INSERT INTO usuarios (id, login, nome, senha_hash, papel)
            VALUES (%s, %s, %s, %s, 'cozinha')
            ON CONFLICT (login) DO UPDATE
               SET senha_hash = EXCLUDED.senha_hash, papel = 'cozinha'
            """,
            (uuid.uuid4(), login, login.capitalize(), bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()),
        )
    print("  usuario da cozinha: %s" % login, flush=True)


def main() -> int:
    print("Migrando banco em", descricao_destino(), flush=True)
    aguardar_banco()

    with psycopg.connect(parametros_conexao()) as conexao:
        for arquivo in ARQUIVOS:
            print("  aplicando", arquivo.relative_to(RAIZ).as_posix(), flush=True)
            conexao.execute(arquivo.read_text(encoding="utf-8"))
        garantir_usuario_cozinha(conexao)
        conexao.commit()

        itens = conexao.execute("SELECT count(*) FROM itens_cardapio").fetchone()[0]
        pedidos = conexao.execute("SELECT count(*) FROM pedidos").fetchone()[0]
        usuarios = conexao.execute("SELECT count(*) FROM usuarios").fetchone()[0]

    print(
        "Banco pronto: %d itens no cardapio, %d pedidos, %d usuarios." % (itens, pedidos, usuarios),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
