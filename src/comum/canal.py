"""Canal gRPC de um servico para outro (Gateway -> microsservicos, Pedidos -> Catalogo).

Dois modos, escolhidos pela porta de destino:

- Porta comum (9090-9092): canal sem TLS. E o caso do docker compose, onde os
  containers conversam pela rede interna do compose.
- Porta 443 (Cloud Run): TLS + token de identidade (ID token) do Google no
  metadado `authorization`. Os microsservicos no Cloud Run sao privados
  (--no-allow-unauthenticated): o proprio Cloud Run recusa quem nao tem o papel
  roles/run.invoker no servico, entao so o Gateway (e o Pedidos, no Catalogo)
  conseguem chamar, mesmo o servico tendo URL HTTPS publica.

O ID token vem do metadata server do Cloud Run (conta de servico da revisao),
com a URL do servico chamado como audiencia, e fica em cache ate perto de vencer.
"""

import base64
import json
import os
import threading
import time
import urllib.parse
import urllib.request

import grpc

URL_METADATA = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
)

OPCOES_CANAL = [
    # Keepalive: detecta conexao morta (ex.: container reiniciado) sem esperar a
    # proxima chamada falhar por timeout.
    ("grpc.keepalive_time_ms", 60_000),
    ("grpc.keepalive_timeout_ms", 20_000),
    ("grpc.http2.max_pings_without_data", 0),
    # Reconexao rapida depois de uma queda. No padrao do gRPC o intervalo entre
    # tentativas cresce ate 120 s e cada tentativa pode esperar 20 s: o servico
    # volta e o canal continua falhando por minutos.
    ("grpc.initial_reconnect_backoff_ms", 500),
    ("grpc.max_reconnect_backoff_ms", 5_000),
    ("grpc.min_reconnect_backoff_ms", 2_000),
    # Container religado pode voltar com outro IP: re-resolve o nome logo.
    ("grpc.dns_min_time_between_resolutions_ms", 1_000),
]


class TokenDeIdentidade(grpc.AuthMetadataPlugin):
    """Poe `authorization: Bearer <ID token>` em toda chamada do canal."""

    def __init__(self, audiencia: str) -> None:
        self.audiencia = audiencia
        self._token = ""
        self._vence_em = 0.0
        self._trava = threading.Lock()
        # Sem proxy: o metadata server so existe dentro do Google Cloud.
        self._abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _buscar(self) -> str:
        with self._trava:
            if self._token and time.time() < self._vence_em - 300:
                return self._token
            url = URL_METADATA + "?audience=" + urllib.parse.quote(self.audiencia, safe="")
            requisicao = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
            with self._abridor.open(requisicao, timeout=3) as resposta:
                token = resposta.read().decode().strip()
            carga = token.split(".")[1]
            carga += "=" * (-len(carga) % 4)
            self._vence_em = float(json.loads(base64.urlsafe_b64decode(carga))["exp"])
            self._token = token
            return token

    def __call__(self, contexto, callback) -> None:
        try:
            callback((("authorization", "Bearer " + self._buscar()),), None)
        except Exception as erro:  # o gRPC transforma em UNAVAILABLE para quem chamou
            callback((), erro)


def usa_tls(porta: int | str) -> bool:
    return int(porta) == 443


def criar_canal(host: str, porta: int | str) -> grpc.Channel:
    destino = f"{host}:{porta}"
    if not usa_tls(porta):
        return grpc.insecure_channel(destino, options=OPCOES_CANAL)

    credenciais = grpc.ssl_channel_credentials()
    # GRPC_ID_TOKEN=0 desliga o token (ex.: servico publico ou teste fora do GCP).
    if os.getenv("GRPC_ID_TOKEN", "1") != "0":
        credenciais = grpc.composite_channel_credentials(
            credenciais,
            grpc.metadata_call_credentials(TokenDeIdentidade(f"https://{host}"), name="id-token"),
        )
    return grpc.secure_channel(destino, credenciais, options=OPCOES_CANAL)
