# 2. Contratos gRPC

Cada microsservico tem o proprio contrato em `proto/`. Os contratos sao a fonte
da verdade: o Gateway, o Catalogo e o Pedidos usam os stubs gerados a partir
deles, e mudar um `.proto` obriga a regerar os stubs e ajustar quem usa aquele
servico na mesma alteracao.

## `proto/catalogo.proto` - `catalogo.CatalogoService`

| RPC | Request | Response | Quem chama | O que faz no banco |
|---|---|---|---|---|
| `ListarItens` | `ListarItensRequest{categoria}` | `ListarItensResponse{restaurante, itens[]}` | Gateway (`GET /cardapio`) | `SELECT` em `itens_cardapio`, com filtro de categoria sem diferenciar maiusculas |
| `ConsultarItens` | `ConsultarItensRequest{codigos[]}` | `ConsultarItensResponse{itens[]}` | Pedidos (ao criar pedido) | `SELECT ... WHERE codigo = ANY(...)`: busca todos os itens do pedido numa consulta so |
| `AtualizarItem` | `AtualizarItemRequest{codigo, disponivel, optional preco}` | `ItemCardapio` | Gateway (`PATCH /cardapio/{codigo}`) | `UPDATE ... RETURNING`, que devolve a linha ja alterada |

`ItemCardapio`:

| Campo | Tipo | Tag | Observacao |
|---|---|---|---|
| `codigo` | string | 1 | 2 letras + 2 digitos (`PR01`) |
| `nome` | string | 2 | |
| `descricao` | string | 3 | |
| `categoria` | string | 4 | Entradas, Pratos, Bebidas, Sobremesas |
| `preco` | double | 5 | em reais; `NUMERIC(10,2)` no banco |
| `disponivel` | bool | 6 | `false` = fora do cardapio do dia |

- **`ConsultarItens` nao falha por codigo inexistente.** O codigo simplesmente
  nao aparece na resposta, e quem chama decide o que fazer: o Pedidos responde
  `INVALID_ARGUMENT`.
- **`preco` em `AtualizarItemRequest` e `optional`.** Em proto3 isso da
  *presenca* ao campo (`HasField("preco")`), o que diferencia "nao mexer no
  preco" de "preco = 0".

## `proto/pedidos.proto` - `pedidos.PedidoService`

| RPC | Request | Response | O que faz no banco | Erros |
|---|---|---|---|---|
| `CriarPedido` | `CriarPedidoRequest{cliente, endereco, itens[]}` | `Pedido` | `INSERT` em `pedidos` + `itens_pedido` numa transacao | `INVALID_ARGUMENT`, `FAILED_PRECONDITION`, `UNAVAILABLE` |
| `ObterPedido` | `ObterPedidoRequest{pedido_id}` | `Pedido` | `SELECT` do pedido e das linhas | `INVALID_ARGUMENT`, `NOT_FOUND` |
| `ListarPedidos` | `ListarPedidosRequest{limite}` | `ListarPedidosResponse{pedidos[]}` | `SELECT ... ORDER BY criado_em DESC LIMIT` | - |
| `AtualizarStatus` | `AtualizarStatusRequest{pedido_id, status}` | `Pedido` | `UPDATE ... WHERE id = ? AND status = atual` | `INVALID_ARGUMENT`, `NOT_FOUND`, `FAILED_PRECONDITION` |

`Pedido`:

| Campo | Tipo | Tag | Observacao |
|---|---|---|---|
| `pedido_id` | string | 1 | UUID4 gerado pelo servico |
| `cliente` | string | 2 | |
| `endereco` | string | 3 | |
| `status` | `StatusPedido` | 4 | enum |
| `itens` | repeated `ItemConfirmado` | 5 | `codigo, nome, quantidade, preco_unitario, subtotal` |
| `total` | double | 6 | soma dos subtotais, arredondada |
| `tempo_estimado_minutos` | int32 | 7 | `15 + 3 x unidades` |
| `criado_em` | string | 8 | ISO 8601 com fuso (`2026-09-24T20:43:57-03:00`) |
| `atualizado_em` | string | 9 | muda a cada `AtualizarStatus` |

`StatusPedido`: `STATUS_DESCONHECIDO = 0` (obrigatorio em proto3),
`RECEBIDO`, `EM_PREPARO`, `PRONTO`, `SAIU_PARA_ENTREGA`, `ENTREGUE`. O pedido so
avanca para a etapa seguinte. Pular ou voltar responde `FAILED_PRECONDITION`.

## Gerar os stubs

```bash
python scripts/gerar_stubs.py
```

- O script compila todos os `proto/*.proto` para `src/gerado/`.
- Depois reescreve `import catalogo_pb2` para `from . import catalogo_pb2` nos
  `*_pb2_grpc.py`, porque os stubs vivem dentro do pacote `src.gerado`.
- O `docker build` roda o mesmo script, entao a imagem sempre sai com os stubs
  do contrato atual.

## Inspecionar os servicos com grpcurl

Os dois servidores tem *reflection* habilitado. De dentro da rede do compose
(ou da VM, com as portas temporariamente publicadas):

```bash
grpcurl -plaintext localhost:9091 list
grpcurl -plaintext -d '{"codigos":["PR01","BE02"]}' localhost:9091 catalogo.CatalogoService/ConsultarItens
grpcurl -plaintext -d '{"limite":3}' localhost:9090 pedidos.PedidoService/ListarPedidos
```

Na configuracao padrao as portas 9090 e 9091 **nao** sao publicadas: so o
Gateway e acessivel de fora.
