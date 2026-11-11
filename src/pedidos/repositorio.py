"""Camada de acesso a dados de Pedidos: tabelas pedidos, itens_pedido e etapas_pedido.

O pedido e suas linhas sao gravados na mesma transacao: ou entra tudo, ou nada.
O id do pedido vem de quem chama (chave de idempotencia): gravar de novo o mesmo
id nao duplica nada (ON CONFLICT DO NOTHING).

Cada etapa alcancada vira uma linha em etapas_pedido, com o horario. Toda
criacao e mudanca de etapa tambem dispara um NOTIFY no canal "pedidos" do
PostgreSQL, na mesma transacao (so e entregue se o COMMIT acontecer): e assim
que os streams de AcompanharPedidos ficam sabendo da mudanca na hora.
"""

import json
from dataclasses import dataclass, field

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from ..comum.rastreamento import rastrear_banco

CANAL_EVENTOS = "pedidos"

COLUNAS_PEDIDO = """
    id::text AS pedido_id, COALESCE(usuario_id::text, '') AS usuario_id, cliente, endereco, telefone,
    status, total::float8 AS total, tempo_estimado_minutos, criado_em, atualizado_em
"""
COLUNAS_ITEM = """
    codigo, nome, opcao, quantidade, preco_unitario::float8 AS preco_unitario,
    subtotal::float8 AS subtotal
"""
# Filtro opcional pelo dono: com usuario_id NULL o filtro nao restringe nada.
FILTRO_DONO = "(%(usuario_id)s::uuid IS NULL OR usuario_id = %(usuario_id)s::uuid)"
# Filtros opcionais da listagem; parametro NULL (ou lista vazia) = sem filtro.
FILTROS_LISTAGEM = """
    AND (cardinality(%(status)s::text[]) = 0 OR status = ANY(%(status)s::text[]))
    AND (%(criado_desde)s::timestamptz IS NULL OR criado_em >= %(criado_desde)s::timestamptz)
    AND (%(codigo_item)s::text IS NULL OR EXISTS (
            SELECT 1 FROM itens_pedido i WHERE i.pedido_id = pedidos.id AND i.codigo = %(codigo_item)s))
    AND (%(cliente)s::text IS NULL OR cliente ILIKE %(cliente)s ESCAPE '\\')
"""


@dataclass
class FiltrosListagem:
    usuario_id: str | None = None
    status: list[str] = field(default_factory=list)
    criado_desde: str | None = None
    codigo_item: str | None = None
    cliente: str | None = None


def _padrao_like(trecho: str) -> str:
    """Trecho de texto -> padrao do ILIKE, sem deixar % e _ virarem curinga."""
    escapado = trecho.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + escapado + "%"


def _avisar(cursor, tipo: str, pedido_id: str, usuario_id: str | None) -> None:
    cursor.execute(
        "SELECT pg_notify(%s, %s)",
        (CANAL_EVENTOS, json.dumps({"tipo": tipo, "pedido_id": str(pedido_id), "usuario_id": usuario_id or ""})),
    )


class RepositorioPedidos:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    @rastrear_banco("pedidos.inserir")
    def inserir(self, pedido_id: str, usuario_id: str, cliente: str, endereco: str, status: str,
                itens: list[dict], total: float, tempo_estimado_minutos: int, telefone: str = "") -> bool:
        """Grava pedido + itens + primeira etapa. Devolve False se ja existia pedido com este id."""
        with self.pool.connection() as conexao:  # commit ao sair do bloco sem erro
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO pedidos
                        (id, usuario_id, cliente, endereco, telefone, status, total, tempo_estimado_minutos)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (pedido_id, usuario_id, cliente, endereco, telefone, status, total, tempo_estimado_minutos),
                )
                if cursor.rowcount == 0:
                    return False
                cursor.executemany(
                    """
                    INSERT INTO itens_pedido
                        (pedido_id, linha, codigo, nome, opcao, quantidade, preco_unitario, subtotal)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (pedido_id, numero, i["codigo"], i["nome"], i.get("opcao", ""), i["quantidade"],
                         i["preco_unitario"], i["subtotal"])
                        for numero, i in enumerate(itens, start=1)
                    ],
                )
                cursor.execute(
                    "INSERT INTO etapas_pedido (pedido_id, status, registrado_em) "
                    "SELECT id, status, criado_em FROM pedidos WHERE id = %s",
                    (pedido_id,),
                )
                _avisar(cursor, "criado", pedido_id, usuario_id)
        return True

    def _completar(self, cursor, pedidos: list[dict]) -> list[dict]:
        """Preenche itens e historico de etapas dos pedidos (duas consultas para todos)."""
        if not pedidos:
            return pedidos
        ids = [p["pedido_id"] for p in pedidos]
        linhas = cursor.execute(
            f"SELECT pedido_id::text AS pedido_id, {COLUNAS_ITEM} FROM itens_pedido "
            "WHERE pedido_id = ANY(%s::uuid[]) ORDER BY pedido_id, linha",
            (ids,),
        ).fetchall()
        etapas = cursor.execute(
            "SELECT pedido_id::text AS pedido_id, status, registrado_em FROM etapas_pedido "
            "WHERE pedido_id = ANY(%s::uuid[]) ORDER BY pedido_id, registrado_em",
            (ids,),
        ).fetchall()
        por_pedido = {pid: {"itens": [], "historico": []} for pid in ids}
        for linha in linhas:
            por_pedido[linha.pop("pedido_id")]["itens"].append(linha)
        for etapa in etapas:
            por_pedido[etapa.pop("pedido_id")]["historico"].append(etapa)
        for pedido in pedidos:
            pedido.update(por_pedido[pedido["pedido_id"]])
        return pedidos

    @rastrear_banco("pedidos.buscar")
    def buscar(self, pedido_id: str, usuario_id: str | None = None) -> dict | None:
        """Pedido com itens e historico. Com usuario_id, so encontra se o pedido for dele."""
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                pedido = cursor.execute(
                    f"SELECT {COLUNAS_PEDIDO} FROM pedidos WHERE id = %(id)s AND {FILTRO_DONO}",
                    {"id": pedido_id, "usuario_id": usuario_id},
                ).fetchone()
                if pedido is None:
                    return None
                return self._completar(cursor, [pedido])[0]

    @rastrear_banco("pedidos.listar")
    def listar(self, limite: int, filtros: FiltrosListagem | None = None) -> list[dict]:
        """Pedidos mais recentes que atendem a todos os filtros preenchidos."""
        filtros = filtros or FiltrosListagem()
        parametros = {
            "usuario_id": filtros.usuario_id,
            "status": filtros.status,
            "criado_desde": filtros.criado_desde,
            "codigo_item": filtros.codigo_item,
            "cliente": _padrao_like(filtros.cliente) if filtros.cliente else None,
            "limite": limite,
        }
        with self.pool.connection() as conexao:
            with conexao.cursor(row_factory=dict_row) as cursor:
                pedidos = cursor.execute(
                    f"SELECT {COLUNAS_PEDIDO} FROM pedidos WHERE {FILTRO_DONO} {FILTROS_LISTAGEM} "
                    "ORDER BY criado_em DESC LIMIT %(limite)s",
                    parametros,
                ).fetchall()
                return self._completar(cursor, pedidos)

    @rastrear_banco("pedidos.atualizar_status")
    def atualizar_status(self, pedido_id: str, status_atual: str, novo_status: str, usuario_id: str) -> bool:
        """UPDATE condicional: so altera se o status ainda for o esperado.

        Evita que duas chamadas simultaneas avancem o mesmo pedido duas vezes.
        Na mesma transacao registra a etapa no historico e avisa os streams.
        """
        with self.pool.connection() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE pedidos
                       SET status = %s, atualizado_em = now()
                     WHERE id = %s AND status = %s
                    """,
                    (novo_status, pedido_id, status_atual),
                )
                if cursor.rowcount != 1:
                    return False
                cursor.execute(
                    "INSERT INTO etapas_pedido (pedido_id, status) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (pedido_id, novo_status),
                )
                _avisar(cursor, "status", pedido_id, usuario_id)
                return True
