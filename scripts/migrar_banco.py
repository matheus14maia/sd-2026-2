#!/usr/bin/env python3
"""Cria as tabelas e carrega o cardapio inicial no PostgreSQL.

Aplica db/schema.sql e db/seed.sql, nessa ordem, numa unica transacao. Os dois
arquivos sao idempotentes, entao o script pode rodar a cada deploy: no compose
ele e o servico one-shot `migrador`, que termina antes dos microsservicos subirem.

    python scripts/migrar_banco.py
"""

import pathlib
import sys

import psycopg

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.comum.banco import aguardar_banco, descricao_destino, parametros_conexao  # noqa: E402

ARQUIVOS = (RAIZ / "db" / "schema.sql", RAIZ / "db" / "seed.sql")


def main() -> int:
    print("Migrando banco em", descricao_destino(), flush=True)
    aguardar_banco()

    with psycopg.connect(parametros_conexao()) as conexao:
        for arquivo in ARQUIVOS:
            print("  aplicando", arquivo.relative_to(RAIZ).as_posix(), flush=True)
            conexao.execute(arquivo.read_text(encoding="utf-8"))
        conexao.commit()

        itens = conexao.execute("SELECT count(*) FROM itens_cardapio").fetchone()[0]
        pedidos = conexao.execute("SELECT count(*) FROM pedidos").fetchone()[0]

    print("Banco pronto: %d itens no cardapio, %d pedidos." % (itens, pedidos), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
