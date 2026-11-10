"""Camada de acesso a dados do Catalogo: tabelas itens_cardapio e fotos_itens.

So SQL e conversao de linha para dicionario. Regra de negocio fica no servico.
Item excluido continua na tabela (excluido_em preenchido): some de todas as
consultas, mas o codigo fica reservado e a carga inicial (db/seed.sql) nao o
recria.
"""

from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from ..comum.rastreamento import rastrear_banco

COLUNAS = (
    "codigo, nome, descricao, categoria, preco::float8 AS preco, disponivel, opcoes, foto_versao, opcoes_indisponiveis"
)
# Ordem do cardapio: prefixo da categoria e depois o numero (PR09 < PR10 < PR100).
ORDEM = "left(codigo, 2), length(codigo), codigo"
# Mudar um destes campos conta como edicao: a carga inicial deixa o item em paz.
CAMPOS_CONTEUDO = {"nome", "descricao", "categoria", "opcoes"}
# Disponibilidade (do item e de cada opcao) e preco nao contam como edicao.
CAMPOS_EDITAVEIS = CAMPOS_CONTEUDO | {"preco", "disponivel", "opcoes_indisponiveis"}
# Trava transacional (pg_advisory_xact_lock) que serializa a escolha do proximo
# codigo: dois cadastros ao mesmo tempo nao pegam o mesmo PR06.
TRAVA_CODIGO = 7310001


class RepositorioCatalogo:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    @rastrear_banco("itens_cardapio.listar")
    def listar(self, categoria: str = "") -> list[dict]:
        consulta = f"SELECT {COLUNAS} FROM itens_cardapio WHERE excluido_em IS NULL"
        parametros: tuple = ()
        if categoria:
            consulta += " AND lower(categoria) = lower(%s)"
            parametros = (categoria.strip(),)
        consulta += f" ORDER BY {ORDEM}"
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(consulta, parametros).fetchall()

    @rastrear_banco("itens_cardapio.buscar_varios")
    def buscar_varios(self, codigos: list[str]) -> list[dict]:
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    f"SELECT {COLUNAS} FROM itens_cardapio"
                    f" WHERE codigo = ANY(%s) AND excluido_em IS NULL ORDER BY {ORDEM}",
                    (codigos,),
                ).fetchall()

    @rastrear_banco("itens_cardapio.atualizar")
    def atualizar(self, codigo: str, campos: dict) -> dict | None:
        """UPDATE so dos campos informados. Devolve a linha alterada, ou None se o item nao existe."""
        desconhecidos = set(campos) - CAMPOS_EDITAVEIS
        if desconhecidos:
            raise ValueError("campos nao editaveis: %s" % sorted(desconhecidos))
        atribuicoes = [
            sql.SQL("{} = {}").format(sql.Identifier(nome), sql.Placeholder(nome)) for nome in sorted(campos)
        ]
        if CAMPOS_CONTEUDO & campos.keys():
            atribuicoes.append(sql.SQL("editado_em = now()"))
        if "opcoes" in campos and "opcoes_indisponiveis" not in campos:
            # Lista de opcoes nova: so continua fora do dia o que ainda existe.
            atribuicoes.append(sql.SQL(
                "opcoes_indisponiveis = ARRAY(SELECT o FROM unnest(itens_cardapio.opcoes_indisponiveis) AS o"
                " WHERE o = ANY(%(opcoes)s::text[]))"
            ))
        atribuicoes.append(sql.SQL("atualizado_em = now()"))
        consulta = sql.SQL(
            "UPDATE itens_cardapio SET {} WHERE codigo = %(codigo)s AND excluido_em IS NULL RETURNING " + COLUNAS
        ).format(sql.SQL(", ").join(atribuicoes))
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(consulta, {**campos, "codigo": codigo}).fetchone()

    @rastrear_banco("itens_cardapio.criar")
    def criar(self, chave: str, prefixo: str, item: dict) -> tuple[dict, bool]:
        """INSERT com o proximo codigo do prefixo. Devolve (linha, criado agora?).

        A mesma chave devolve o item ja criado (retry do Gateway), mesmo que ele
        tenha sido excluido depois.
        """
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (TRAVA_CODIGO,))
                existente = cursor.execute(
                    f"SELECT {COLUNAS} FROM itens_cardapio WHERE chave_criacao = %s", (chave,)
                ).fetchone()
                if existente:
                    return existente, False
                # Conta tambem os excluidos: codigo de item excluido nunca volta.
                numero = cursor.execute(
                    "SELECT coalesce(max(substring(codigo FROM 3)::int), 0) + 1 AS proximo"
                    "  FROM itens_cardapio WHERE codigo ~ %s",
                    ("^%s[0-9]+$" % prefixo,),
                ).fetchone()["proximo"]
                linha = cursor.execute(
                    f"""
                    INSERT INTO itens_cardapio
                        (codigo, nome, descricao, categoria, preco, disponivel, opcoes, chave_criacao, editado_em)
                    VALUES (%(codigo)s, %(nome)s, %(descricao)s, %(categoria)s, %(preco)s, %(disponivel)s,
                            %(opcoes)s, %(chave)s, now())
                    RETURNING {COLUNAS}
                    """,
                    {**item, "codigo": "%s%02d" % (prefixo, numero), "chave": chave},
                ).fetchone()
                return linha, True

    @rastrear_banco("itens_cardapio.excluir")
    def excluir(self, codigo: str) -> bool:
        """Exclusao logica. True se o item existe (excluido agora ou antes); False se nunca existiu."""
        with self.pool.connection() as conexao:
            with conexao.cursor() as cursor:
                linha = cursor.execute(
                    """
                    UPDATE itens_cardapio
                       SET excluido_em = coalesce(excluido_em, now()), editado_em = now(),
                           atualizado_em = now(), disponivel = FALSE, foto_versao = ''
                     WHERE codigo = %s
                 RETURNING codigo
                    """,
                    (codigo,),
                ).fetchone()
                if linha:
                    cursor.execute("DELETE FROM fotos_itens WHERE codigo = %s", (codigo,))
                return linha is not None

    @rastrear_banco("fotos_itens.salvar")
    def salvar_foto(self, codigo: str, tipo: str, conteudo: bytes, versao: str) -> dict | None:
        """Grava a foto e a versao no item. None se o item nao existe."""
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                linha = cursor.execute(
                    f"""
                    UPDATE itens_cardapio
                       SET foto_versao = %s, editado_em = now(), atualizado_em = now()
                     WHERE codigo = %s AND excluido_em IS NULL
                 RETURNING {COLUNAS}
                    """,
                    (versao, codigo),
                ).fetchone()
                if linha is None:
                    return None
                cursor.execute(
                    """
                    INSERT INTO fotos_itens (codigo, tipo, conteudo) VALUES (%s, %s, %s)
                    ON CONFLICT (codigo) DO UPDATE
                       SET tipo = EXCLUDED.tipo, conteudo = EXCLUDED.conteudo, atualizado_em = now()
                    """,
                    (codigo, tipo, conteudo),
                )
                return linha

    @rastrear_banco("fotos_itens.remover")
    def remover_foto(self, codigo: str) -> dict | None:
        """Tira a foto do item (sem foto, o card mostra as iniciais). None se o item nao existe."""
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                linha = cursor.execute(
                    f"""
                    UPDATE itens_cardapio
                       SET foto_versao = '', editado_em = now(), atualizado_em = now()
                     WHERE codigo = %s AND excluido_em IS NULL
                 RETURNING {COLUNAS}
                    """,
                    (codigo,),
                ).fetchone()
                if linha is not None:
                    cursor.execute("DELETE FROM fotos_itens WHERE codigo = %s", (codigo,))
                return linha

    @rastrear_banco("fotos_itens.obter")
    def obter_foto(self, codigo: str) -> dict | None:
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    """
                    SELECT f.codigo, f.tipo, f.conteudo, i.foto_versao AS versao
                      FROM fotos_itens f
                      JOIN itens_cardapio i ON i.codigo = f.codigo
                     WHERE f.codigo = %s AND i.excluido_em IS NULL
                    """,
                    (codigo,),
                ).fetchone()
