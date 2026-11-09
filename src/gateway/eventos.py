"""Atualizacao em tempo real: do stream gRPC do Pedidos para os navegadores (SSE).

UMA chamada AcompanharPedidos (server streaming) por instancia do Gateway, aberta
quando o primeiro navegador se conecta em GET /pedidos/eventos e fechada quando
o ultimo sai. Cada evento recebido e repassado aos navegadores conectados,
filtrado pelo dono: cliente so recebe os proprios pedidos, a cozinha recebe
todos. Assim o numero de streams no Pedidos nao cresce com o numero de abas
abertas.

Se o Pedidos cair, a thread tenta de novo com backoff exponencial (1 s, 2 s,
4 s... ate 15 s) e avisa os navegadores com o evento "estado", para a tela
mostrar que a atualizacao automatica esta pausada.

Formato (text/event-stream):
    event: pedido
    data: {"tipo": "criado" | "status", "pedido": {...}}

    event: estado
    data: {"conectado": true}
"""

import asyncio
import itertools
import json
import threading
import time
from dataclasses import dataclass

import grpc

from ..comum.registro import log
from ..gerado import pedidos_pb2
from .clientes_grpc import ClientesGrpc, para_dict

ESPERA_MAXIMA_SEGUNDOS = 15.0
TIPOS = {pedidos_pb2.PEDIDO_CRIADO: "criado", pedidos_pb2.STATUS_ATUALIZADO: "status"}


def mensagem_sse(evento: str, dados: dict) -> str:
    return "event: %s\ndata: %s\n\n" % (evento, json.dumps(dados, ensure_ascii=False))


@dataclass
class Assinante:
    laco: asyncio.AbstractEventLoop
    fila: asyncio.Queue
    usuario_id: str | None  # None = recebe todos os pedidos (cozinha)


class RetransmissorEventos:
    def __init__(self, clientes: ClientesGrpc) -> None:
        self._clientes = clientes
        self._assinantes: dict[int, Assinante] = {}
        self._contador = itertools.count(1)
        self._trava = threading.Lock()
        self._thread: threading.Thread | None = None
        self._chamada = None
        self.conectado = False

    # ------------------------------------------------------------ assinantes
    def resumo(self) -> dict:
        with self._trava:
            return {"conectado": self.conectado, "navegadores": len(self._assinantes)}

    def assinar(self, laco: asyncio.AbstractEventLoop, fila: asyncio.Queue, usuario_id: str | None) -> int:
        with self._trava:
            ident = next(self._contador)
            self._assinantes[ident] = Assinante(laco, fila, usuario_id)
            if self._thread is None:
                self._thread = threading.Thread(target=self._executar, name="stream-pedidos", daemon=True)
                self._thread.start()
        return ident

    def cancelar(self, ident: int) -> None:
        with self._trava:
            self._assinantes.pop(ident, None)
            chamada = self._chamada if not self._assinantes else None
        if chamada is not None:
            chamada.cancel()  # ninguem mais ouvindo: fecha o stream com o Pedidos

    def encerrar(self) -> None:
        with self._trava:
            self._assinantes.clear()
            chamada = self._chamada
        if chamada is not None:
            chamada.cancel()

    # ------------------------------------------------------------ entrega
    @staticmethod
    def _enviar(assinante: Assinante, texto: str) -> None:
        def colocar() -> None:
            try:
                assinante.fila.put_nowait(texto)
            except asyncio.QueueFull:
                pass  # navegador que nao le: perde o evento, os outros seguem

        try:
            assinante.laco.call_soon_threadsafe(colocar)
        except RuntimeError:
            pass  # laco ja encerrado (Gateway desligando)

    def _para_todos(self, texto: str, dono: str | None = None) -> None:
        with self._trava:
            assinantes = list(self._assinantes.values())
        for assinante in assinantes:
            if dono is None or assinante.usuario_id is None or assinante.usuario_id == dono:
                self._enviar(assinante, texto)

    def _mudar_estado(self, conectado: bool) -> None:
        if conectado == self.conectado:
            return
        self.conectado = conectado
        log(
            "Tempo real: stream com o Pedidos %s" % ("conectado" if conectado else "interrompido"),
            "NOTICE" if conectado else "WARNING",
        )
        self._para_todos(mensagem_sse("estado", {"conectado": conectado}))

    def _distribuir(self, evento) -> None:
        pedido = para_dict(evento.pedido)
        texto = mensagem_sse("pedido", {"tipo": TIPOS.get(evento.tipo, "desconhecido"), "pedido": pedido})
        self._para_todos(texto, dono=pedido.get("usuario_id", ""))

    # ------------------------------------------------------------ stream
    def _executar(self) -> None:
        espera = 1.0
        while True:
            with self._trava:
                if not self._assinantes:
                    self._thread = None
                    self._chamada = None
                    break
                chamada = self._clientes.acompanhar_pedidos()
                self._chamada = chamada
            try:
                for evento in chamada:
                    self._mudar_estado(True)
                    espera = 1.0
                    if evento.tipo != pedidos_pb2.BATIMENTO:
                        self._distribuir(evento)
            except grpc.RpcError as erro:
                with self._trava:
                    alguem_ouvindo = bool(self._assinantes)
                if alguem_ouvindo:
                    log(
                        "Tempo real: stream com o Pedidos caiu (%s); nova tentativa em %.0f s"
                        % (erro.code().name, espera),
                        "WARNING",
                    )
            with self._trava:
                alguem_ouvindo = bool(self._assinantes)
                if not alguem_ouvindo:
                    # Fechamento normal: o ultimo navegador saiu.
                    self._thread = None
                    self._chamada = None
                    self.conectado = False
            if not alguem_ouvindo:
                break
            self._mudar_estado(False)
            time.sleep(espera)
            espera = min(espera * 2, ESPERA_MAXIMA_SEGUNDOS)
        log("Tempo real: nenhum navegador conectado, stream com o Pedidos fechado")
