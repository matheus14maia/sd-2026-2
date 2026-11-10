"""Clientes gRPC que o Gateway usa para despachar as requisicoes HTTP.

E aqui que acontece a traducao de protocolo: dict (JSON) -> mensagem Protobuf
na ida, mensagem Protobuf -> dict na volta. Os canais sao abertos uma vez, na
subida do Gateway, e reaproveitados por todas as requisicoes.

Toda chamada passa pelo ClienteResiliente do servico de destino (prazo, retry
com backoff exponencial e circuit breaker, ver src/comum/resiliencia.py) e leva
o trace da requisicao nos metadados.

Degradacao graciosa no cardapio: a ultima lista boa de cada categoria fica em
memoria. Se o Catalogo cair (ou o circuito dele estiver aberto), GET /cardapio
responde 200 com a lista salva e "origem": "cache", em vez de 503.
"""

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import grpc
from google.protobuf.json_format import MessageToDict
from grpc_health.v1 import health_pb2, health_pb2_grpc

from ..comum.canal import criar_canal
from ..comum.rastreamento import metadados
from ..comum.registro import log
from ..comum.resiliencia import FALHAS_DO_SERVICO, CircuitoAberto, ClienteResiliente
from ..gerado import (
    catalogo_pb2,
    catalogo_pb2_grpc,
    pedidos_pb2,
    pedidos_pb2_grpc,
    usuarios_pb2,
    usuarios_pb2_grpc,
)

# Local: nomes dos containers e portas 9090-9092 (sem TLS).
# Cloud Run: host <servico>.run.app e porta 443 (TLS + ID token, ver comum/canal.py).
DESTINOS = {
    "usuarios": (os.getenv("USUARIOS_HOST", "localhost"), int(os.getenv("USUARIOS_PORTA", "9092"))),
    "catalogo": (os.getenv("CATALOGO_HOST", "localhost"), int(os.getenv("CATALOGO_PORTA", "9091"))),
    "pedidos": (os.getenv("PEDIDOS_HOST", "localhost"), int(os.getenv("PEDIDOS_PORTA", "9090"))),
}
# Por quanto tempo a lista salva do cardapio ainda serve de fallback.
CACHE_CARDAPIO_SEGUNDOS = float(os.getenv("CACHE_CARDAPIO_SEGUNDOS", "1800"))
TIMEOUT_SAUDE_SEGUNDOS = 2.0


def para_dict(mensagem) -> dict:
    """Protobuf -> dict com os nomes de campo do .proto e os valores padrao."""
    return MessageToDict(
        mensagem,
        preserving_proto_field_name=True,
        always_print_fields_with_no_presence=True,
    )


def com_foto(item: dict) -> dict:
    """Acrescenta ao item a URL da foto (relativa ao Gateway) ou None se nao tem foto.

    A versao vai na URL: foto nova = URL nova, entao o navegador pode guardar a
    foto em cache para sempre sem nunca mostrar uma foto velha.
    """
    versao = item.get("foto_versao") or ""
    item["foto"] = "/cardapio/%s/foto?v=%s" % (item["codigo"], versao) if versao else None
    return item


def _ordem_do_cardapio(item: dict) -> tuple:
    codigo = item.get("codigo", "")
    return codigo[:2], len(codigo), codigo


class ClientesGrpc:
    def __init__(self) -> None:
        self._canais = {nome: criar_canal(host, porta) for nome, (host, porta) in DESTINOS.items()}
        self.usuarios = usuarios_pb2_grpc.UsuarioServiceStub(self._canais["usuarios"])
        self.catalogo = catalogo_pb2_grpc.CatalogoServiceStub(self._canais["catalogo"])
        self.pedidos = pedidos_pb2_grpc.PedidoServiceStub(self._canais["pedidos"])
        self._saude = {nome: health_pb2_grpc.HealthStub(canal) for nome, canal in self._canais.items()}
        self.resiliencia = {nome: ClienteResiliente(nome) for nome in DESTINOS}
        self._cache_cardapio: dict[str, tuple[float, dict]] = {}
        self._trava_cache = threading.Lock()

    def fechar(self) -> None:
        for canal in self._canais.values():
            canal.close()

    @staticmethod
    def destinos() -> str:
        return ", ".join("%s em %s:%s" % (nome, host, porta) for nome, (host, porta) in DESTINOS.items())

    def _chamar(self, servico: str, operacao: str, metodo, requisicao, idempotente: bool = True):
        # timeout, wait_for_ready e metadata (com o trace) vem do ClienteResiliente.
        return self.resiliencia[servico].chamar(
            operacao,
            lambda **opcoes: metodo(requisicao, **opcoes),
            idempotente=idempotente,
        )

    # Usuarios ---------------------------------------------------------------
    def cadastrar_usuario(self, login: str, nome: str, senha: str) -> dict:
        requisicao = usuarios_pb2.CadastrarUsuarioRequest(login=login, nome=nome, senha=senha)
        # Nao idempotente: um retry depois de timeout poderia responder 409 para
        # um cadastro que deu certo. UNAVAILABLE ainda e repetido (nada foi gravado).
        resposta = self._chamar("usuarios", "CadastrarUsuario", self.usuarios.CadastrarUsuario, requisicao,
                                idempotente=False)
        return para_dict(resposta)

    def verificar_credenciais(self, login: str, senha: str) -> dict:
        requisicao = usuarios_pb2.VerificarCredenciaisRequest(login=login, senha=senha)
        return para_dict(
            self._chamar("usuarios", "VerificarCredenciais", self.usuarios.VerificarCredenciais, requisicao)
        )

    def obter_usuario(self, usuario_id: str) -> dict:
        requisicao = usuarios_pb2.ObterUsuarioRequest(id=usuario_id)
        return para_dict(self._chamar("usuarios", "ObterUsuario", self.usuarios.ObterUsuario, requisicao))

    def atualizar_usuario(self, usuario_id: str, campos: dict) -> dict:
        """So os campos presentes em `campos` mudam (None = nao mexe; "" apaga)."""
        requisicao = usuarios_pb2.AtualizarUsuarioRequest(id=usuario_id)
        for nome in ("nome", "telefone", "endereco"):
            if campos.get(nome) is not None:
                setattr(requisicao, nome, campos[nome])
        return para_dict(self._chamar("usuarios", "AtualizarUsuario", self.usuarios.AtualizarUsuario, requisicao))

    def trocar_senha(self, usuario_id: str, senha_atual: str, nova_senha: str) -> dict:
        requisicao = usuarios_pb2.TrocarSenhaRequest(id=usuario_id, senha_atual=senha_atual, nova_senha=nova_senha)
        # Nao idempotente: repetir depois de dar certo responderia "senha atual
        # incorreta". UNAVAILABLE ainda e repetido (nada foi gravado).
        return para_dict(
            self._chamar("usuarios", "TrocarSenha", self.usuarios.TrocarSenha, requisicao, idempotente=False)
        )

    # Catalogo ---------------------------------------------------------------
    def listar_cardapio(self, categoria: str) -> dict:
        chave = categoria.lower()
        requisicao = catalogo_pb2.ListarItensRequest(categoria=categoria)
        try:
            resposta = para_dict(self._chamar("catalogo", "ListarItens", self.catalogo.ListarItens, requisicao))
            for item in resposta.get("itens", []):
                com_foto(item)
        except CircuitoAberto as erro:
            return self._cardapio_salvo(chave, erro, str(erro))
        except grpc.RpcError as erro:
            if erro.code() not in FALHAS_DO_SERVICO:
                raise  # ex.: categoria inexistente (404) nao e falha do Catalogo
            return self._cardapio_salvo(chave, erro, "Catalogo nao respondeu (%s)." % erro.code().name)

        with self._trava_cache:
            self._cache_cardapio[chave] = (time.time(), resposta)
        return {**resposta, "origem": "catalogo"}

    def _cardapio_salvo(self, chave: str, erro: Exception, motivo: str) -> dict:
        with self._trava_cache:
            salvo = self._cache_cardapio.get(chave)
        if salvo is None or time.time() - salvo[0] > CACHE_CARDAPIO_SEGUNDOS:
            raise erro
        momento, dados = salvo
        hora = datetime.fromtimestamp(momento).astimezone().strftime("%H:%M:%S")
        log("Catalogo fora: GET /cardapio respondido com a lista salva as %s" % hora, "WARNING",
            fallback="cache_cardapio")
        return {
            **dados,
            "origem": "cache",
            "salvo_em": datetime.fromtimestamp(momento).astimezone().isoformat(timespec="seconds"),
            "aviso": "%s Exibindo o cardapio salvo as %s; precos e disponibilidade podem estar "
                     "desatualizados." % (motivo, hora),
        }

    def _atualizar_cache(self, item: dict | None = None, excluido: str = "") -> None:
        """Mantem o cardapio salvo (fallback) coerente com a alteracao que acabou de dar certo."""
        sai = {excluido, (item or {}).get("codigo", "")} - {""}
        with self._trava_cache:
            for chave, (_, dados) in self._cache_cardapio.items():
                itens = [i for i in dados.get("itens", []) if i.get("codigo") not in sai]
                # Entra de novo so na lista completa ("") e na da categoria dele.
                if item is not None and chave in ("", item.get("categoria", "").lower()):
                    itens = sorted(itens + [item], key=_ordem_do_cardapio)
                dados["itens"] = itens

    def _item(self, operacao: str, requisicao) -> dict:
        """Chama uma operacao do Catalogo que devolve ItemCardapio e atualiza o fallback."""
        item = com_foto(para_dict(self._chamar("catalogo", operacao, getattr(self.catalogo, operacao), requisicao)))
        self._atualizar_cache(item)
        return item

    def atualizar_item(self, codigo: str, campos: dict) -> dict:
        """So os campos presentes em `campos` mudam (None = nao mexe)."""
        requisicao = catalogo_pb2.AtualizarItemRequest(codigo=codigo)
        for nome in ("disponivel", "preco", "nome", "descricao", "categoria"):
            if campos.get(nome) is not None:
                setattr(requisicao, nome, campos[nome])
        if campos.get("opcoes") is not None:
            requisicao.opcoes.valores.extend(campos["opcoes"])
            requisicao.opcoes.SetInParent()  # lista vazia tambem e "presente": tira as opcoes
        return self._item("AtualizarItem", requisicao)

    def criar_item(self, dados: dict) -> dict:
        requisicao = catalogo_pb2.CriarItemRequest(
            # Chave de idempotencia: todas as tentativas desta requisicao HTTP
            # levam a mesma chave, entao um retry nunca cadastra o prato duas vezes.
            chave=str(uuid.uuid4()),
            nome=dados["nome"],
            descricao=dados.get("descricao") or "",
            categoria=dados["categoria"],
            preco=dados["preco"],
            disponivel=dados.get("disponivel", True),
            opcoes=dados.get("opcoes") or [],
        )
        return self._item("CriarItem", requisicao)

    def excluir_item(self, codigo: str) -> dict:
        resposta = self._chamar(
            "catalogo", "ExcluirItem", self.catalogo.ExcluirItem, catalogo_pb2.ExcluirItemRequest(codigo=codigo)
        )
        self._atualizar_cache(excluido=resposta.codigo)
        return {"mensagem": "Item %s excluido do cardapio." % resposta.codigo, "codigo": resposta.codigo}

    def salvar_foto(self, codigo: str, tipo: str, conteudo: bytes) -> dict:
        return self._item("SalvarFoto", catalogo_pb2.SalvarFotoRequest(codigo=codigo, tipo=tipo, conteudo=conteudo))

    def remover_foto(self, codigo: str) -> dict:
        return self._item("RemoverFoto", catalogo_pb2.RemoverFotoRequest(codigo=codigo))

    def obter_foto(self, codigo: str) -> dict:
        foto = self._chamar("catalogo", "ObterFoto", self.catalogo.ObterFoto, catalogo_pb2.ObterFotoRequest(codigo=codigo))
        return {"tipo": foto.tipo, "conteudo": foto.conteudo, "versao": foto.versao}

    # Pedidos ----------------------------------------------------------------
    def criar_pedido(self, usuario_id: str, cliente: str, endereco: str, itens: list[dict], telefone: str = "") -> dict:
        requisicao = pedidos_pb2.CriarPedidoRequest(
            # Chave de idempotencia: todas as tentativas desta requisicao HTTP
            # levam o mesmo id, entao um retry nunca grava o pedido duas vezes.
            pedido_id=str(uuid.uuid4()),
            usuario_id=usuario_id,
            cliente=cliente,
            endereco=endereco,
            telefone=telefone,
            itens=[
                pedidos_pb2.ItemPedido(codigo=i["codigo"], quantidade=i["quantidade"], opcao=i.get("opcao") or "")
                for i in itens
            ],
        )
        return para_dict(self._chamar("pedidos", "CriarPedido", self.pedidos.CriarPedido, requisicao))

    def obter_pedido(self, pedido_id: str, usuario_id: str) -> dict:
        requisicao = pedidos_pb2.ObterPedidoRequest(pedido_id=pedido_id, usuario_id=usuario_id)
        return para_dict(self._chamar("pedidos", "ObterPedido", self.pedidos.ObterPedido, requisicao))

    def listar_pedidos(self, limite: int, usuario_id: str, status: list[str] | None = None,
                       criado_desde: str = "", codigo_item: str = "", cliente: str = "") -> list[dict]:
        requisicao = pedidos_pb2.ListarPedidosRequest(
            limite=limite,
            usuario_id=usuario_id,
            status=[pedidos_pb2.StatusPedido.Value(s) for s in (status or [])],
            criado_desde=criado_desde,
            codigo_item=codigo_item,
            cliente=cliente,
        )
        resposta = self._chamar("pedidos", "ListarPedidos", self.pedidos.ListarPedidos, requisicao)
        return para_dict(resposta).get("pedidos", [])

    def acompanhar_pedidos(self):
        """Abre o stream AcompanharPedidos (todos os pedidos). Sem prazo: fica aberto
        enquanto houver navegador ouvindo; quem chama itera e pode cancelar."""
        return self.pedidos.AcompanharPedidos(
            pedidos_pb2.AcompanharPedidosRequest(), metadata=metadados()
        )

    def atualizar_status(self, pedido_id: str, status: str) -> dict:
        requisicao = pedidos_pb2.AtualizarStatusRequest(
            pedido_id=pedido_id, status=pedidos_pb2.StatusPedido.Value(status)
        )
        return para_dict(self._chamar("pedidos", "AtualizarStatus", self.pedidos.AtualizarStatus, requisicao))

    # Saude ------------------------------------------------------------------
    def circuitos(self) -> dict:
        return {nome: cliente.disjuntor.resumo() for nome, cliente in self.resiliencia.items()}

    def verificar_servicos(self) -> dict:
        """Health check gRPC (grpc.health.v1) dos tres servicos, em paralelo."""
        cabecalhos = metadados()

        def verificar(nome: str) -> tuple[str, dict]:
            host, porta = DESTINOS[nome]
            inicio = time.perf_counter()
            try:
                resposta = self._saude[nome].Check(
                    health_pb2.HealthCheckRequest(service=""), timeout=TIMEOUT_SAUDE_SEGUNDOS, metadata=cabecalhos
                )
                status = health_pb2.HealthCheckResponse.ServingStatus.Name(resposta.status)
                detalhe = ""
            except grpc.RpcError as erro:
                status = "INDISPONIVEL"
                detalhe = erro.code().name
            return nome, {
                "health_check": status,
                "detalhe": detalhe,
                "latencia_ms": round((time.perf_counter() - inicio) * 1000),
                "destino": "%s:%s" % (host, porta),
                **self.resiliencia[nome].disjuntor.resumo(),
            }

        with ThreadPoolExecutor(max_workers=len(DESTINOS)) as executor:
            return dict(executor.map(verificar, DESTINOS))
