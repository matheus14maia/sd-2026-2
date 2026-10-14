# 5. API Gateway

O Gateway (`src/gateway/`) e o ponto unico de entrada do backend. Ele recebe
HTTP/JSON, autentica o token JWT, confere o papel do usuario, valida o payload,
traduz para Protobuf, chama o microsservico certo por gRPC e traduz a resposta,
ou o erro, de volta para HTTP/JSON.

Camadas de uma requisicao, de fora para dentro:

```text
CORSMiddleware -> log -> MiddlewareJWT (401) -> exigir_papel (403) -> Pydantic (400) -> rota -> gRPC
```

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | cria o FastAPI, registra os middlewares (CORS, log, JWT), os handlers de erro e as rotas |
| `autenticacao.py` | emite o JWT, `MiddlewareJWT` (401 na borda) e `exigir_papel` (403) |
| `esquemas.py` | modelos Pydantic de entrada: os campos obrigatorios de negocio |
| `rotas/auth.py`, `rotas/cardapio.py`, `rotas/pedidos.py` | endpoints HTTP, cada um delegando a uma chamada gRPC |
| `clientes_grpc.py` | canais e stubs gRPC (abertos uma vez) e conversao Protobuf <-> dict |
| `erros.py` | payload invalido -> 400; papel sem permissao -> 403; status gRPC -> status HTTP |

## Rotas

| Metodo e rota | Acesso | Corpo | Sucesso | RPC |
|---|---|---|---|---|
| `GET /saude` | publica | - | 200 `{"status":"ok"}` | - |
| `POST /auth/cadastro` | publica | `{"login", "nome", "senha"}` | **201** `{"mensagem", "usuario"}` | `UsuarioService.CadastrarUsuario` |
| `POST /auth/login` | publica | `{"login", "senha"}` | 200 `{"access_token", "token_type", "expira_em_segundos", "usuario"}` | `UsuarioService.VerificarCredenciais` |
| `GET /auth/eu` | token | - | 200 dados do token | - |
| `GET /cardapio?categoria=Bebidas` | token | - | 200 `{restaurante, itens[]}` | `CatalogoService.ListarItens` |
| `PATCH /cardapio/{codigo}` | token + papel `cozinha` | `{"disponivel": true, "preco": 82.5}` (`preco` opcional) | 200 item alterado | `CatalogoService.AtualizarItem` |
| `POST /pedidos` | token | `{"cliente", "endereco", "itens": [{"codigo", "quantidade"}]}` | **201** `{"mensagem", "pedido"}` | `PedidoService.CriarPedido` |
| `GET /pedidos?limite=20` | token | - | 200 `{"pedidos": [...]}` | `PedidoService.ListarPedidos` |
| `GET /pedidos/{id}` | token | - | 200 pedido | `PedidoService.ObterPedido` |
| `PATCH /pedidos/{id}/status` | token + papel `cozinha` | `{"status": "EM_PREPARO"}` | 200 `{"mensagem", "pedido"}` | `PedidoService.AtualizarStatus` |

`/docs` e `/openapi.json` (Swagger) tambem sao publicos. No Swagger, faca o
`POST /auth/login`, copie o `access_token` e cole no botao **Authorize**.

## Autenticacao JWT (401)

- **Emissao.** `POST /auth/login` chama `VerificarCredenciais` no Usuarios. Se a
  senha confere, o Gateway assina um JWT **HS256** com `JWT_SEGREDO` e as
  claims `sub` (id), `login`, `nome`, `papel`, `iat` e `exp`
  (`JWT_EXPIRACAO_MINUTOS`, padrao 60).
- **Conferencia.** O `MiddlewareJWT` roda antes de qualquer rota. Fora de
  `ROTAS_PUBLICAS` (`/saude`, `/auth/login`, `/auth/cadastro`, `/docs`,
  `/openapi.json`), a requisicao precisa de `Authorization: Bearer <token>`
  com assinatura valida e dentro da validade. Senao, **401** com o cabecalho
  `WWW-Authenticate: Bearer`, sem nenhuma chamada gRPC.
- **Preflight do CORS.** Requisicoes `OPTIONS` passam sem token: o navegador nao
  manda o `Authorization` no preflight.
- **Segredo.** `JWT_SEGREDO` fica so no `.env` da VM do Gateway. Sem a
  variavel, o Gateway sorteia um segredo a cada subida (e avisa no log): nao
  existe segredo fixo no codigo, que e publico.

| Situacao | Resposta 401 |
|---|---|
| sem `Authorization` | `{"mensagem": "Token ausente. Envie o cabecalho Authorization: Bearer <token>."}` |
| esquema diferente de `Bearer` | `{"mensagem": "Cabecalho Authorization invalido. Use: Bearer <token>."}` |
| assinatura errada, token editado ou malformado | `{"mensagem": "Token invalido."}` |
| token vencido | `{"mensagem": "Token expirado. Faca login novamente."}` |
| login ou senha errados no `POST /auth/login` | `{"mensagem": "Login ou senha invalidos.", "codigo_grpc": "UNAUTHENTICATED"}` |

## Papeis (403)

Quem se cadastra por `POST /auth/cadastro` entra com papel `cliente`. O usuario
de demonstracao `professor` tem papel `cozinha`. As rotas que alteram dados da
operacao (`PATCH /cardapio/{codigo}` e `PATCH /pedidos/{id}/status`) usam a
dependencia `exigir_papel("cozinha")`. Token valido de outro papel responde
**403**:

```json
{"mensagem": "Operacao permitida so para o papel 'cozinha'."}
```

O token ja foi conferido pelo middleware: o 403 e decisao de autorizacao, nao de
autenticacao.

## Validacao do payload

As regras ficam declaradas nos modelos de `esquemas.py`, e todos recusam campo
desconhecido (`extra="forbid"`).

| Campo | Regra |
|---|---|
| `login` (cadastro) | 3 a 30 letras, numeros, ponto ou sublinhado; normalizado para minusculo |
| `nome` (cadastro) | obrigatorio, nao vazio, ate 200 caracteres |
| `senha` | cadastro: 6 a 72 caracteres (72 e o limite do bcrypt); login: obrigatoria |
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
traduz as mensagens para portugues. Campos com formato fixo (codigo do item,
login) explicam o formato esperado pela tabela `FORMATOS`.

## Erros vindos dos microsservicos

| Status gRPC | HTTP | Exemplo |
|---|---|---|
| `INVALID_ARGUMENT` | 400 | item `XX99` nao existe no cardapio |
| `UNAUTHENTICATED` | 401 | login ou senha errados |
| `NOT_FOUND` | 404 | pedido ou categoria inexistente |
| `FAILED_PRECONDITION` | 409 | item indisponivel; transicao de status invalida |
| `ALREADY_EXISTS` | 409 | login ja cadastrado |
| `UNAVAILABLE`, `DEADLINE_EXCEEDED` | 503 | microsservico fora do ar |
| qualquer outro | 500 | "Erro interno ao processar a requisicao." |

Corpo: `{"mensagem": "<detalhe do microsservico>", "codigo_grpc": "NOT_FOUND"}`.

## CORS

O frontend roda em outra origem (outra porta, e no GCP outra VM). O
`CORSMiddleware` libera as origens de `CORS_ORIGENS` (separadas por virgula;
padrao `*`), os metodos `GET`, `POST`, `PATCH`, `OPTIONS` e os cabecalhos
`Authorization` e `Content-Type`. Ele e o middleware mais externo: assim ate as
respostas 401 e 400 saem com os cabecalhos de CORS, e o navegador consegue
mostrar o erro em vez de esconde-lo como falha de rede.

## Variaveis de ambiente

| Variavel | Padrao | Uso |
|---|---|---|
| `USUARIOS_HOST` / `USUARIOS_PORTA` | `localhost` / `9092` | endereco do microsservico de Usuarios |
| `CATALOGO_HOST` / `CATALOGO_PORTA` | `localhost` / `9091` | endereco do Catalogo |
| `PEDIDOS_HOST` / `PEDIDOS_PORTA` | `localhost` / `9090` | endereco do Pedidos |
| `GRPC_TIMEOUT` | `5` | prazo de cada chamada gRPC, em segundos |
| `JWT_SEGREDO` | sorteado na subida | chave HMAC do token |
| `JWT_EXPIRACAO_MINUTOS` | `60` | validade do token |
| `CORS_ORIGENS` | `*` | origens liberadas para o navegador |

## Exemplos

Bash (curl + jq):

```bash
URL=http://localhost:8000

# 401: sem token
curl -i "$URL/cardapio"

# login e token
TOKEN=$(curl -s -X POST "$URL/auth/login" -H "Content-Type: application/json" \
  -d '{"login":"professor","senha":"delivery2026"}' | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"

curl -i "$URL/cardapio?categoria=Pratos" -H "$AUTH"

# 201
curl -i -X POST "$URL/pedidos" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"cliente":"Maria","endereco":"Rua 10, 123","itens":[{"codigo":"PR01","quantidade":2},{"codigo":"BE02","quantidade":1}]}'

# 400
curl -i -X POST "$URL/pedidos" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"endereco":"Rua 10","itens":[{"codigo":"PR01","quantidade":0}]}'

# 200 (troque COLE_O_ID pelo pedido_id devolvido no 201)
curl -i -X PATCH "$URL/pedidos/COLE_O_ID/status" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"status":"EM_PREPARO"}'
```

PowerShell (`Invoke-WebRequest` lanca excecao em 4xx; no 5.1 use `curl.exe`
para ver o status):

```powershell
$URL = "http://localhost:8000"
$sessao = Invoke-RestMethod "$URL/auth/login" -Method Post -ContentType "application/json" `
  -Body '{"login":"professor","senha":"delivery2026"}'
$AUTH = "Authorization: Bearer $($sessao.access_token)"
curl.exe -i "$URL/cardapio?categoria=Pratos" -H $AUTH
```

O teste `python scripts/testar_gateway.py --url $URL` roda todos os cenarios em
sequencia, inclusive os de 401 e 403.
