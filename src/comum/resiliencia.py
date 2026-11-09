"""Tolerancia a falhas nas chamadas gRPC entre servicos.

Usado pelo Gateway (para Usuarios, Catalogo e Pedidos) e pelo Pedidos (para o
Catalogo). Quatro mecanismos:

1. Timeout por tentativa e prazo total: nenhuma chamada espera para sempre. O
   prazo total limita a soma das tentativas; no Pedidos ele vem do prazo que o
   Gateway mandou (propagacao de deadline), entao o Pedidos desiste antes de o
   Gateway desistir dele.
2. Retry com backoff exponencial e jitter: falha transitoria e repetida ate
   RETRY_TENTATIVAS vezes, esperando ~0,2 s, ~0,4 s, ~0,8 s (com sorteio de
   50% a 100% do valor, para varios clientes nao repetirem no mesmo instante).
     - UNAVAILABLE e RESOURCE_EXHAUSTED: sempre repete. Neste sistema esses
       codigos so saem antes de qualquer gravacao (servico fora, falha simulada,
       banco fora com rollback), entao repetir e seguro.
     - DEADLINE_EXCEEDED e CANCELLED: so repete operacao idempotente (o
       servidor pode ter terminado depois que o cliente desistiu, ou estava
       desligando no meio da chamada - um container parando responde CANCELLED).
       CriarPedido e idempotente pelo pedido_id gerado no Gateway.
3. Circuit breaker (disjuntor) por servico: depois de DISJUNTOR_FALHAS chamadas
   seguidas que falharam mesmo com retry, o circuito ABRE e as chamadas
   seguintes falham na hora (503 sem esperar timeout) por DISJUNTOR_ABERTO_SEGUNDOS.
   Depois fica MEIO_ABERTO: uma chamada de teste passa; deu certo, FECHA; falhou,
   ABRE de novo. Erro de negocio (400, 404, 409) nao conta como falha: o servico
   respondeu, so recusou o pedido.
4. Sem tempestade de retries: quando o servico chamado avisa que quem falhou foi
   uma dependencia dele (metadado `x-falha-dependencia`), quem chama nao repete
   e nao conta a falha contra ele. Ex.: Catalogo fora -> o Pedidos ja fez os
   retries no Catalogo; o Gateway nao repete o CriarPedido e nao abre o
   circuito do Pedidos (GET /pedidos continua funcionando).
"""

import os
import random
import threading
import time
from typing import Callable, TypeVar

import grpc

from .registro import log

T = TypeVar("T")

SEMPRE_REPETIR = {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.RESOURCE_EXHAUSTED}
# CANCELLED so chega aqui vindo do servidor (este codigo nunca cancela chamada).
REPETIR_SE_IDEMPOTENTE = {grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.CANCELLED}
FALHAS_DO_SERVICO = SEMPRE_REPETIR | REPETIR_SE_IDEMPOTENTE

METADADO_FALHA_DEPENDENCIA = "x-falha-dependencia"

FECHADO = "FECHADO"
ABERTO = "ABERTO"
MEIO_ABERTO = "MEIO_ABERTO"


def _env_float(nome: str, padrao: float) -> float:
    return float(os.getenv(nome, str(padrao)))


class CircuitoAberto(Exception):
    """O disjuntor do servico esta aberto: a chamada nem foi feita."""

    def __init__(self, servico: str, segundos: float) -> None:
        self.servico = servico
        self.segundos = max(1, round(segundos))
        super().__init__(
            "Servico de %s temporariamente indisponivel (circuito aberto). "
            "Tente novamente em %d s." % (servico, self.segundos)
        )


def falha_de_dependencia(erro: grpc.RpcError) -> str:
    """Nome da dependencia que falhou, se o servico chamado avisou; '' senao."""
    try:
        for chave, valor in erro.trailing_metadata() or ():
            if chave == METADADO_FALHA_DEPENDENCIA:
                return valor
    except Exception:
        pass
    return ""


class Disjuntor:
    """Circuit breaker de um servico. Seguro para varias threads."""

    def __init__(self, servico: str, limite_falhas: int | None = None, tempo_aberto: float | None = None) -> None:
        self.servico = servico
        self.limite_falhas = limite_falhas or int(os.getenv("DISJUNTOR_FALHAS", "3"))
        self.tempo_aberto = tempo_aberto or _env_float("DISJUNTOR_ABERTO_SEGUNDOS", 15)
        self._estado = FECHADO
        self._falhas_seguidas = 0
        self._aberto_em = 0.0
        self._teste_em_andamento = False
        self._trava = threading.Lock()

    def antes_da_chamada(self) -> bool:
        """Libera ou recusa a chamada. Devolve True se ela e a chamada de teste (MEIO_ABERTO)."""
        with self._trava:
            if self._estado == FECHADO:
                return False
            restante = self.tempo_aberto - (time.monotonic() - self._aberto_em)
            if self._estado == ABERTO and restante <= 0:
                self._estado = MEIO_ABERTO
                self._teste_em_andamento = False
                log("Circuito de %s MEIO_ABERTO: liberando uma chamada de teste" % self.servico, "NOTICE",
                    circuito=MEIO_ABERTO, alvo=self.servico)
            if self._estado == MEIO_ABERTO and not self._teste_em_andamento:
                self._teste_em_andamento = True
                return True
            raise CircuitoAberto(self.servico, max(restante, 1))

    def sucesso(self) -> None:
        with self._trava:
            if self._estado != FECHADO:
                log("Circuito de %s FECHADO: servico respondeu de novo" % self.servico, "NOTICE",
                    circuito=FECHADO, alvo=self.servico)
            self._estado = FECHADO
            self._falhas_seguidas = 0
            self._teste_em_andamento = False

    def falha(self) -> None:
        with self._trava:
            self._falhas_seguidas += 1
            self._teste_em_andamento = False
            if self._estado == MEIO_ABERTO or (
                self._estado == FECHADO and self._falhas_seguidas >= self.limite_falhas
            ):
                self._estado = ABERTO
                self._aberto_em = time.monotonic()
                log(
                    "Circuito de %s ABERTO apos %d falhas seguidas: chamadas recusadas na hora por %.0f s"
                    % (self.servico, self._falhas_seguidas, self.tempo_aberto),
                    "ERROR",
                    circuito=ABERTO,
                    alvo=self.servico,
                )

    def resumo(self) -> dict:
        with self._trava:
            restante = 0.0
            if self._estado == ABERTO:
                restante = max(0.0, self.tempo_aberto - (time.monotonic() - self._aberto_em))
            return {
                "circuito": self._estado,
                "falhas_seguidas": self._falhas_seguidas,
                "reabre_em_segundos": round(restante),
            }


class ClienteResiliente:
    """Executa as chamadas a um servico com prazo, retry e disjuntor."""

    def __init__(self, servico: str) -> None:
        self.servico = servico
        self.disjuntor = Disjuntor(servico)
        self.tentativas = int(os.getenv("RETRY_TENTATIVAS", "3"))
        self.espera_inicial = _env_float("RETRY_ESPERA_INICIAL", 0.2)
        self.espera_maxima = _env_float("RETRY_ESPERA_MAXIMA", 2.0)
        self.timeout = _env_float("GRPC_TIMEOUT", 5)
        self.prazo_total = _env_float("GRPC_PRAZO_TOTAL", 12)

    def _espera(self, tentativa: int) -> float:
        base = min(self.espera_maxima, self.espera_inicial * (2 ** (tentativa - 1)))
        return base * random.uniform(0.5, 1.0)

    def chamar(
        self,
        operacao: str,
        funcao: Callable[..., T],
        idempotente: bool = True,
        prazo: float | None = None,
    ) -> T:
        """Chama `funcao(timeout=..., wait_for_ready=...)` com retry.

        `prazo` (s) limita o total das tentativas; padrao GRPC_PRAZO_TOTAL.
        Na chamada de teste do circuito (MEIO_ABERTO) usa wait_for_ready: se o
        canal ainda estiver reconectando, a chamada espera a conexao (ate o
        timeout) em vez de falhar na hora e reabrir o circuito a toa.
        """
        chamada_de_teste = self.disjuntor.antes_da_chamada()
        limite = time.monotonic() + (prazo if prazo is not None else self.prazo_total)
        nome = "%s.%s" % (self.servico, operacao)

        tentativa = 0
        while True:
            tentativa += 1
            restante = limite - time.monotonic()
            timeout = min(self.timeout, restante)
            try:
                if timeout <= 0.05:
                    raise _SemTempo()
                resultado = funcao(timeout=timeout, wait_for_ready=chamada_de_teste)
            except _SemTempo:
                log("%s: prazo total esgotado antes da tentativa %d" % (nome, tentativa), "ERROR", operacao=nome)
                self.disjuntor.falha()
                raise grpc_erro_prazo(nome)
            except grpc.RpcError as erro:
                codigo = erro.code()
                dependencia = falha_de_dependencia(erro)
                if dependencia or codigo not in FALHAS_DO_SERVICO:
                    # O servico respondeu: erro de negocio ou falha de uma dependencia dele.
                    self.disjuntor.sucesso()
                    raise
                repetivel = codigo in SEMPRE_REPETIR or (idempotente and codigo in REPETIR_SE_IDEMPOTENTE)
                espera = self._espera(tentativa)
                tem_tempo = limite - time.monotonic() - espera > 0.05
                if repetivel and tentativa < self.tentativas and tem_tempo:
                    log(
                        "%s falhou com %s (tentativa %d/%d); repetindo em %d ms"
                        % (nome, codigo.name, tentativa, self.tentativas, espera * 1000),
                        "WARNING",
                        operacao=nome,
                        codigo_grpc=codigo.name,
                        tentativa=tentativa,
                    )
                    time.sleep(espera)
                    continue
                log(
                    "%s falhou com %s apos %d tentativa(s): %s"
                    % (nome, codigo.name, tentativa, (erro.details() or "")[:200]),
                    "ERROR",
                    operacao=nome,
                    codigo_grpc=codigo.name,
                    tentativa=tentativa,
                )
                self.disjuntor.falha()
                raise
            else:
                if tentativa > 1:
                    log("%s respondeu na tentativa %d" % (nome, tentativa), "NOTICE", operacao=nome,
                        tentativa=tentativa)
                self.disjuntor.sucesso()
                return resultado


class _SemTempo(Exception):
    pass


class _ErroPrazo(grpc.RpcError):
    """RpcError sintetico para quando o prazo total acaba entre tentativas."""

    def __init__(self, nome: str) -> None:
        super().__init__()
        self._detalhes = "Prazo esgotado chamando %s." % nome

    def code(self):
        return grpc.StatusCode.DEADLINE_EXCEEDED

    def details(self):
        return self._detalhes

    def trailing_metadata(self):
        return ()


def grpc_erro_prazo(nome: str) -> grpc.RpcError:
    return _ErroPrazo(nome)
