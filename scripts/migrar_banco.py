#!/usr/bin/env python3
"""Cria as tabelas, carrega o cardapio e garante o usuario da cozinha no PostgreSQL.

Aplica db/schema.sql e db/seed.sql, nessa ordem, numa unica transacao, e carrega
as fotos iniciais de db/fotos/ (<CODIGO>.jpg, .png ou .webp). Tudo e idempotente,
entao o script pode rodar a cada deploy: no compose ele e o servico one-shot
`migrador`, que termina antes dos microsservicos subirem.

Foto inicial so entra em item que a cozinha nunca editou: depois que alguem
troca ou remove a foto pela tela, o migrador deixa o item como esta.

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
from src.comum.imagens import FOTO_MAXIMO_BYTES, tipo_da_imagem, versao_da_foto  # noqa: E402

ARQUIVOS = (RAIZ / "db" / "schema.sql", RAIZ / "db" / "seed.sql")
PASTA_FOTOS = RAIZ / "db" / "fotos"
EXTENSOES_FOTO = {".jpg", ".jpeg", ".png", ".webp"}

# Valores que ja apareceram no repositorio publico: nunca viram senha da cozinha.
SENHAS_PUBLICAS = {"troque-esta-senha", "delivery2026", "senha-local-teste"}


def garantir_usuario_cozinha(conexao: psycopg.Connection) -> None:
    login = os.getenv("DEMO_LOGIN", "professor").strip().lower()
    senha = os.getenv("DEMO_SENHA", "")
    if len(senha) < 6:
        print("  DEMO_SENHA ausente ou curta: usuario da cozinha nao criado.", flush=True)
        return
    if senha in SENHAS_PUBLICAS:
        print("  DEMO_SENHA e um valor de exemplo publico: usuario da cozinha nao criado.", flush=True)
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


def carregar_fotos(conexao: psycopg.Connection) -> None:
    """Fotos de db/fotos/ nos itens que nunca foram editados pela cozinha."""
    if not PASTA_FOTOS.is_dir():
        return
    carregadas = 0
    for arquivo in sorted(PASTA_FOTOS.iterdir()):
        if arquivo.suffix.lower() not in EXTENSOES_FOTO:
            continue
        codigo = arquivo.stem.upper()
        conteudo = arquivo.read_bytes()
        tipo = tipo_da_imagem(conteudo)
        if not tipo or len(conteudo) > FOTO_MAXIMO_BYTES:
            print("  foto %s ignorada: nao e JPEG/PNG/WebP ou passa de %d KB"
                  % (arquivo.name, FOTO_MAXIMO_BYTES // 1024), flush=True)
            continue
        versao = versao_da_foto(conteudo)
        alterado = conexao.execute(
            """
            UPDATE itens_cardapio SET foto_versao = %s
             WHERE codigo = %s AND editado_em IS NULL AND excluido_em IS NULL
               AND foto_versao IS DISTINCT FROM %s
         RETURNING codigo
            """,
            (versao, codigo, versao),
        ).fetchone()
        if alterado:
            conexao.execute(
                """
                INSERT INTO fotos_itens (codigo, tipo, conteudo) VALUES (%s, %s, %s)
                ON CONFLICT (codigo) DO UPDATE
                   SET tipo = EXCLUDED.tipo, conteudo = EXCLUDED.conteudo, atualizado_em = now()
                """,
                (codigo, tipo, conteudo),
            )
            carregadas += 1
    print("  fotos iniciais carregadas agora: %d" % carregadas, flush=True)


def main() -> int:
    print("Migrando banco em", descricao_destino(), flush=True)
    aguardar_banco()

    with psycopg.connect(parametros_conexao()) as conexao:
        for arquivo in ARQUIVOS:
            print("  aplicando", arquivo.relative_to(RAIZ).as_posix(), flush=True)
            conexao.execute(arquivo.read_text(encoding="utf-8"))
        carregar_fotos(conexao)
        garantir_usuario_cozinha(conexao)
        conexao.commit()

        itens = conexao.execute("SELECT count(*) FROM itens_cardapio WHERE excluido_em IS NULL").fetchone()[0]
        pedidos = conexao.execute("SELECT count(*) FROM pedidos").fetchone()[0]
        usuarios = conexao.execute("SELECT count(*) FROM usuarios").fetchone()[0]

    print(
        "Banco pronto: %d itens no cardapio, %d pedidos, %d usuarios." % (itens, pedidos, usuarios),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
