"""Central de eventos do Pedidos: LISTEN no PostgreSQL e distribuicao aos streams.

Toda criacao ou mudanca de etapa grava um NOTIFY no canal "pedidos" (ver
repositorio.py), na mesma transacao. Esta central mantem UMA conexao dedicada
com LISTEN nesse canal e entrega cada aviso para todos os streams de
AcompanharPedidos abertos nesta instancia.

Como o aviso sai do banco, funciona com varias instancias do Pedidos: a
instancia que gravou nao precisa ser a mesma que mantem o stream do Gateway.
Se a conexao do LISTEN cair (banco reiniciando), a central reconecta sozinha.
"""

import json
import queue
import threading
import time

import psycopg

from ..comum.banco import parametros_conexao
from ..comum.registro import log
from .repositorio import CANAL_EVENTOS

ESPERA_RECONEXAO_SEGUNDOS = 2
TAMANHO_FILA = 200


class CentralEventos:
    def __init__(self) -> None:
        self._assinantes: set[queue.Queue] = set()
        self._trava = threading.Lock()
        self._thread = threading.Thread(target=self._escutar, name="listen-pedidos", daemon=True)
        self._thread.start()

    def assinar(self) -> queue.Queue:
        fila: queue.Queue = queue.Queue(maxsize=TAMANHO_FILA)
        with self._trava:
            self._assinantes.add(fila)
        return fila

    def cancelar(self, fila: queue.Queue) -> None:
        with self._trava:
            self._assinantes.discard(fila)

    def _distribuir(self, aviso: dict) -> None:
        with self._trava:
            filas = list(self._assinantes)
        for fila in filas:
            try:
                fila.put_nowait(aviso)
            except queue.Full:
                # Stream que nao consome: perde o aviso, mas nao trava os outros.
                log("Stream de pedidos atrasado: aviso descartado", "WARNING")

    def _escutar(self) -> None:
        while True:
            try:
                with psycopg.connect(parametros_conexao(), autocommit=True) as conexao:
                    conexao.execute(f"LISTEN {CANAL_EVENTOS}")
                    log("Escutando o canal '%s' do PostgreSQL" % CANAL_EVENTOS)
                    while True:
                        # timeout: de tempos em tempos o laco volta aqui, e uma
                        # conexao morta aparece como OperationalError.
                        for notificacao in conexao.notifies(timeout=30):
                            try:
                                self._distribuir(json.loads(notificacao.payload))
                            except ValueError:
                                log("Aviso invalido no canal: %r" % notificacao.payload, "WARNING")
                        conexao.execute("SELECT 1")
            except psycopg.Error as erro:
                log(
                    "LISTEN no PostgreSQL caiu (%s); reconectando em %d s"
                    % (str(erro).strip().splitlines()[0] if str(erro).strip() else type(erro).__name__,
                       ESPERA_RECONEXAO_SEGUNDOS),
                    "WARNING",
                )
                time.sleep(ESPERA_RECONEXAO_SEGUNDOS)
