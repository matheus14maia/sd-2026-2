# 5. API Gateway

O Gateway (`src/gateway/`) e o unico componente acessivel de fora. Ele recebe
HTTP/JSON, valida o payload, traduz para Protobuf, chama o microsservico certo
por gRPC e traduz a resposta, ou o erro, de volta para HTTP/JSON.

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | cria o FastAPI, registra os handlers de erro, as rotas e o log de cada requisicao |
| `esquemas.py` | modelos Pydantic de entrada: os campos obrigatorios de negocio |
| `rotas/cardapio.py`, `rotas/pedidos.py` | endpoints HTTP, cada um delegando a uma chamada gRPC |
| `clientes_grpc.py` | canais e stubs gRPC (abertos uma vez) e conversao Protobuf <-> dict |
| `erros.py` | payload invalido -> 400; status gRPC -> status HTTP |

## Rotas

| Metodo e rota | Corpo | Sucesso | RPC |
|---|---|---|---|
| `GET /saude` | - | 200 `{"status":"ok"}` | - |
| `GET /cardapio?categoria=Bebidas` | - | 200 `{restaurante, itens[]}` | `CatalogoService.ListarItens` |
| `PATCH /cardapio/{codigo}` | `{"disponivel": true, "preco": 82.5}` (`preco` opcional) | 200 item alterado | `CatalogoService.AtualizarItem` |
| `POST /pedidos` | `{"cliente", "endereco", "itens": [{"codigo", "quantidade"}]}` | **201** `{"mensagem", "pedido"}` | `PedidoService.CriarPedido` |
| `GET /pedidos?limite=20` | - | 200 `{"pedidos": [...]}` | `PedidoService.ListarPedidos` |
| `GET /pedidos/{id}` | - | 200 pedido | `PedidoService.ObterPedido` |
| `PATCH /pedidos/{id}/status` | `{"status": "EM_PREPARO"}` | 200 `{"mensagem", "pedido"}` | `PedidoService.AtualizarStatus` |

## Validacao do payload

As regras ficam declaradas nos modelos de `esquemas.py`, e todos recusam campo
desconhecido (`extra="forbid"`).

| Campo | Regra |
|---|---|
| `cliente`, `endereco` | obrigatorios, texto; espacos nas pontas sao removidos; nao podem ficar vazios; ate 200 caracteres |
| `itens` | obrigatorio, lista com 1 a 30 itens |
| `itens[].codigo` | 2 letras + 2 digitos; aceita minusculo e normaliza para maiusculo |
| `itens[].quantidade` | inteiro estrito (`"2"` e `1.5` sao recusados), de 1 a 99 |
| `status` | um de `RECEBIDO`, `EM_PREPARO`, `PRONTO`, `SAIU_PARA_ENTREGA`, `ENTREGUE` |
| `disponivel` | booleano estrito |
| `preco` | opcional, maior que zero |

Resposta de payload invalido, sempre **400**, com todos os campos com problema
de uma vez:

```json
{
  "mensagem": "Dados da requisicao invalidos",
  "erros": {
    "cliente": "nao deve estar vazio",
    "endereco": "campo obrigatorio",
    "itens.0.codigo": "codigo invalido: use 2 letras e 2 digitos (ex.: PR01)",
    "itens.0.quantidade": "deve ser um numero inteiro",
    "preco": "campo nao permitido"
  }
}
```

O FastAPI responderia **422** por padrao. O handler de `RequestValidationError`
em `erros.py` troca para 400, que e o status pedido para dado invalido, e
traduz as mensagens para portugues.

## Erros vindos dos microsservicos

| Status gRPC | HTTP | Exemplo |
|---|---|---|
| `INVALID_ARGUMENT` | 400 | item `XX99` nao existe no cardapio |
| `NOT_FOUND` | 404 | pedido ou categoria inexistente |
| `FAILED_PRECONDITION` | 409 | item indisponivel; transicao de status invalida |
| `UNAVAILABLE`, `DEADLINE_EXCEEDED` | 503 | microsservico fora do ar |
| qualquer outro | 500 | "Erro interno ao processar a requisicao." |

Corpo: `{"mensagem": "<detalhe do microsservico>", "codigo_grpc": "NOT_FOUND"}`.

## Exemplos

Bash (curl):

```bash
URL=http://localhost:8000

curl -i "$URL/cardapio?categoria=Pratos"

curl -i -X POST "$URL/pedidos" -H "Content-Type: application/json" \
  -d '{"cliente":"Maria","endereco":"Rua 10, 123","itens":[{"codigo":"PR01","quantidade":2},{"codigo":"BE02","quantidade":1}]}'

curl -i -X POST "$URL/pedidos" -H "Content-Type: application/json" \
  -d '{"endereco":"Rua 10","itens":[{"codigo":"PR01","quantidade":0}]}'

curl -i -X PATCH "$URL/pedidos/COLE_O_ID/status" -H "Content-Type: application/json" \
  -d '{"status":"EM_PREPARO"}'
```

PowerShell (`Invoke-WebRequest` lanca excecao em 4xx; o `-SkipHttpErrorCheck`
do PowerShell 7 evita isso, e no 5.1 use `curl.exe`):

```powershell
$URL = "http://localhost:8000"
curl.exe -i "$URL/cardapio?categoria=Pratos"
curl.exe -i -X POST "$URL/pedidos" -H "Content-Type: application/json" --data-raw '{\"cliente\":\"Maria\",\"endereco\":\"Rua 10\",\"itens\":[{\"codigo\":\"PR01\",\"quantidade\":2}]}'
```

O smoke test `python scripts/testar_gateway.py --url $URL` roda todos os
cenarios em sequencia.

## O que vem depois

A autenticacao JWT (401 sem token valido) entra como dependencia do FastAPI
aplicada aos routers, sem mudar os microsservicos: o Gateway continua sendo o
unico ponto que precisa conhecer o token.
