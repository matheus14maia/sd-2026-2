# 2. O contrato gRPC explicado

O arquivo `proto/restaurante.proto` e a **fonte da verdade** do sistema. Ele
define o que pode ser chamado, o que trafega na rede e como os bytes sao
serializados. Servidor e cliente sao gerados a partir dele: se o contrato muda,
os dois lados precisam ser regerados.

## 2.1 Cabecalho

```proto
syntax = "proto3";
package restaurante;
```

- `proto3` e a versao da linguagem Protocol Buffers.
- `package restaurante` e o namespace: o nome totalmente qualificado do servico
  fica `restaurante.RestauranteService` (e assim que o `grpcurl` o enxerga).

## 2.2 O servico

```proto
service RestauranteService {
  rpc ObterCardapio(ObterCardapioRequest) returns (ObterCardapioResponse);
  rpc CriarPedido(CriarPedidoRequest) returns (CriarPedidoResponse);
  rpc AcompanharPedido(AcompanharPedidoRequest) returns (stream StatusPedido);
}
```

| RPC | Tipo | Para que serve |
|---|---|---|
| `ObterCardapio` | unario (1 request, 1 response) | listar os itens a venda |
| `CriarPedido` | unario | registrar o pedido e devolver a confirmacao precificada |
| `AcompanharPedido` | **server streaming** (1 request, N responses) | enviar cada mudanca de status pela mesma conexao |

A palavra `stream` antes do tipo de retorno e o unico ponto que transforma um
RPC unario em streaming. Do lado Python isso vira um metodo com `yield` no
servidor e um `for` no cliente.

## 2.3 As mensagens, campo a campo

### Cardapio

```proto
message ObterCardapioRequest { string categoria = 1; }
```

`categoria` vazia significa "cardapio completo". Os numeros (`= 1`, `= 2`, ...)
nao sao valores: sao as **tags de campo**, o identificador que vai no binario no
lugar do nome do campo. Por isso o Protobuf e menor que JSON. Uma tag nunca deve
ser reaproveitada para outro campo depois que o contrato foi publicado.

```proto
message ItemCardapio {
  string codigo = 1;      // codigo digitado pelo cliente, ex: "PR01"
  string nome = 2;
  string descricao = 3;
  string categoria = 4;   // Entradas, Pratos, Bebidas, Sobremesas
  double preco = 5;       // em reais
  bool disponivel = 6;    // false = existe no cardapio, mas esgotou hoje
}

message ObterCardapioResponse {
  string restaurante = 1;
  repeated ItemCardapio itens = 2;
}
```

`repeated` e uma lista: cada elemento e serializado repetindo a mesma tag de
campo. Em Python vira uma lista comum.

### Pedido

```proto
message ItemPedido {
  string codigo = 1;
  int32 quantidade = 2;
}

message CriarPedidoRequest {
  string cliente = 1;
  string endereco = 2;
  repeated ItemPedido itens = 3;      // <- varios itens, cada um com quantidade
}
```

`repeated ItemPedido itens` e exatamente o requisito do trabalho: o cliente
escolhe **quais itens** e **quantas unidades de cada um** em um unico pedido.

```proto
message ItemConfirmado {
  string codigo = 1;
  string nome = 2;              // o servidor devolve o nome, o cliente so mandou o codigo
  int32 quantidade = 3;
  double preco_unitario = 4;    // preco vigente no servidor
  double subtotal = 5;          // preco_unitario x quantidade
}

message CriarPedidoResponse {
  string pedido_id = 1;                // UUID gerado pelo servidor
  StatusPedidoEnum status = 2;
  repeated ItemConfirmado itens = 3;
  double total = 4;
  int32 tempo_estimado_minutos = 5;
  string mensagem = 6;
}
```

A resposta e mais rica que a requisicao de proposito: o cliente envia o minimo
(codigo + quantidade) e recebe do servidor tudo o que foi resolvido do lado do
restaurante.

### Acompanhamento

```proto
enum StatusPedidoEnum {
  STATUS_DESCONHECIDO = 0;
  RECEBIDO = 1;
  EM_PREPARO = 2;
  PRONTO = 3;
  SAIU_PARA_ENTREGA = 4;
  ENTREGUE = 5;
}

message AcompanharPedidoRequest { string pedido_id = 1; }

message StatusPedido {
  string pedido_id = 1;
  StatusPedidoEnum status = 2;
  string descricao = 3;
  string horario = 4;
}
```

Em proto3 todo `enum` **precisa** ter o valor `0`, que representa "nao
informado". Por isso existe `STATUS_DESCONHECIDO = 0`.

## 2.4 Como os stubs sao gerados

```bash
python scripts/gerar_stubs.py
```

O script chama o compilador do Protobuf:

```bash
python -m grpc_tools.protoc \
  --proto_path=proto \
  --python_out=src/gerado \
  --pyi_out=src/gerado \
  --grpc_python_out=src/gerado \
  proto/restaurante.proto
```

e produz tres arquivos em `src/gerado/`:

| Arquivo | Conteudo |
|---|---|
| `restaurante_pb2.py` | as classes de mensagem (serializacao/desserializacao) |
| `restaurante_pb2.pyi` | tipagem, ajuda o editor a completar os campos |
| `restaurante_pb2_grpc.py` | `RestauranteServiceStub` (cliente) e `RestauranteServiceServicer` (servidor) |

Depois de gerar, o script corrige o import de `restaurante_pb2` para import
relativo, porque os stubs vivem dentro do pacote `src.gerado` (o `protoc` gera
import absoluto por padrao).

**Os arquivos gerados nao sao versionados e nunca devem ser editados a mao.**
Eles sao regerados no `docker build` e por quem clona o projeto.

## 2.5 Conferindo o contrato com o servico no ar

O servidor habilita *server reflection*, entao da para inspecionar o contrato do
processo em execucao sem ter o `.proto` na maquina:

```bash
grpcurl -plaintext localhost:9090 list
grpcurl -plaintext localhost:9090 describe restaurante.RestauranteService
grpcurl -plaintext -d '{}' localhost:9090 restaurante.RestauranteService/ObterCardapio
```
