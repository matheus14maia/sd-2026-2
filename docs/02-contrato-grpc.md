# 2. Contratos gRPC

Cada microsservico tem o proprio contrato em `proto/`. Os contratos sao a fonte
da verdade: o Gateway, o Usuarios, o Catalogo e o Pedidos usam os stubs gerados
a partir deles, e mudar um `.proto` obriga a regerar os stubs e ajustar quem usa
aquele servico na mesma alteracao.

| Contrato | Servico | Porta | Quem chama |
|---|---|---|---|
| `proto/usuarios.proto` | `usuarios.UsuarioService` | 9092 | Gateway |
| `proto/catalogo.proto` | `catalogo.CatalogoService` | 9091 | Gateway e Pedidos |
| `proto/pedidos.proto` | `pedidos.PedidoService` | 9090 | Gateway |

## `proto/usuarios.proto` - `usuarios.UsuarioService`

| RPC | Request | Response | Quem chama | O que faz no banco | Erros |
|---|---|---|---|---|---|
| `CadastrarUsuario` | `CadastrarUsuarioRequest{login, nome, senha}` | `Usuario` | Gateway (`POST /auth/cadastro`) | `INSERT` em `usuarios` com o hash bcrypt da senha | `INVALID_ARGUMENT`, `ALREADY_EXISTS` |
| `VerificarCredenciais` | `VerificarCredenciaisRequest{login, senha}` | `Usuario` | Gateway (`POST /auth/login`) | `SELECT` pelo login e `bcrypt.checkpw` | `UNAUTHENTICATED` |
| `ObterUsuario` | `ObterUsuarioRequest{id}` | `Usuario` | Gateway (`GET /conta`, id do token) | `SELECT` pelo id | `NOT_FOUND` |
| `AtualizarUsuario` | `AtualizarUsuarioRequest{id, optional nome, optional telefone, optional endereco}` | `Usuario` | Gateway (`PATCH /conta`) | `UPDATE` so dos campos presentes | `INVALID_ARGUMENT`, `NOT_FOUND` |
| `TrocarSenha` | `TrocarSenhaRequest{id, senha_atual, nova_senha}` | `Usuario` | Gateway (`PUT /conta/senha`) | `bcrypt.checkpw` da atual e `UPDATE` do hash novo | `INVALID_ARGUMENT` (senha atual errada, nova curta ou igual) |

`Usuario`:

| Campo | Tipo | Tag | Observacao |
|---|---|---|---|
| `id` | string | 1 | UUID4 gerado pelo servico |
| `login` | string | 2 | normalizado para minusculo |
| `nome` | string | 3 | |
| `criado_em` | string | 4 | ISO 8601 com fuso |
| `papel` | string | 5 | `cliente` (cadastro pela API) ou `cozinha` |

- **A senha nunca volta.** Nenhuma mensagem de resposta tem senha nem hash, e o
  log do servico nao imprime a senha.
- **Mesma mensagem para login inexistente e senha errada** (`Login ou senha
  invalidos.`): a resposta nao revela quais logins existem.
- **Quem emite o token e o Gateway.** O servico so confirma as credenciais e
  devolve o `Usuario`; o Gateway monta o JWT com `id`, `login`, `nome` e `papel`.

## `proto/catalogo.proto` - `catalogo.CatalogoService`

| RPC | Request | Response | Quem chama | O que faz no banco |
|---|---|---|---|---|
| `ListarItens` | `ListarItensRequest{categoria}` | `ListarItensResponse{restaurante, itens[]}` | Gateway (`GET /cardapio`) | `SELECT` em `itens_cardapio`, com filtro de categoria sem diferenciar maiusculas |
| `ConsultarItens` | `ConsultarItensRequest{codigos[]}` | `ConsultarItensResponse{itens[]}` | Pedidos (ao criar pedido) | `SELECT ... WHERE codigo = ANY(...)`: busca todos os itens do pedido numa consulta so |
| `AtualizarItem` | `AtualizarItemRequest{codigo, optional disponivel, optional preco, optional nome, optional descricao, optional categoria, ListaOpcoes opcoes, ListaOpcoes opcoes_indisponiveis}` | `ItemCardapio` | Gateway (`PATCH /cardapio/{codigo}`) | `UPDATE ... RETURNING` so dos campos presentes |
| `CriarItem` | `CriarItemRequest{chave, nome, descricao, categoria, preco, disponivel, opcoes[]}` | `ItemCardapio` | Gateway (`POST /cardapio`) | trava `pg_advisory_xact_lock`, proximo codigo da categoria e `INSERT`; a mesma `chave` devolve o item ja criado |
| `ExcluirItem` | `ExcluirItemRequest{codigo}` | `ExcluirItemResponse{codigo}` | Gateway (`DELETE /cardapio/{codigo}`) | exclusao logica (`excluido_em`) e apaga a foto |
| `SalvarFoto` | `SalvarFotoRequest{codigo, tipo, conteudo}` | `ItemCardapio` | Gateway (`PUT /cardapio/{codigo}/foto`) | `UPSERT` em `fotos_itens` e a versao nova em `itens_cardapio.foto_versao` |
| `RemoverFoto` | `RemoverFotoRequest{codigo}` | `ItemCardapio` | Gateway (`DELETE /cardapio/{codigo}/foto`) | apaga a linha de `fotos_itens` e zera a versao |
| `ObterFoto` | `ObterFotoRequest{codigo}` | `Foto{codigo, tipo, conteudo, versao}` | Gateway (`GET /cardapio/{codigo}/foto`) | `SELECT` dos bytes |

`ItemCardapio`:

| Campo | Tipo | Tag | Observacao |
|---|---|---|---|
| `codigo` | string | 1 | 2 letras + 2 a 4 digitos (`PR01`); as letras vem da categoria |
| `nome` | string | 2 | |
| `descricao` | string | 3 | |
| `categoria` | string | 4 | Entradas, Pratos, Bebidas, Sobremesas |
| `preco` | double | 5 | em reais; `NUMERIC(10,2)` no banco |
| `disponivel` | bool | 6 | `false` = fora do cardapio do dia |
| `opcoes` | repeated string | 7 | submenu do item: sabores do refrigerante (`BE01`), agua sem ou com gas (`BE03`); vazio = sem escolha |
| `foto_versao` | string | 8 | 12 hex do SHA-256 da foto; vazia = sem foto. O Gateway monta a URL `/cardapio/{codigo}/foto?v=<versao>` |
| `opcoes_indisponiveis` | repeated string | 9 | opcoes fora do dia (ex.: so a agua `Com gás` acabou); subconjunto de `opcoes`. O Pedidos recusa a opcao fora do dia com `FAILED_PRECONDITION` (409) |

- **`ConsultarItens` nao falha por codigo inexistente.** O codigo simplesmente
  nao aparece na resposta, e quem chama decide o que fazer: o Pedidos responde
  `INVALID_ARGUMENT`.
- **Os campos de `AtualizarItemRequest` sao `optional`.** Em proto3 isso da
  *presenca* ao campo (`HasField("preco")`), o que diferencia "nao mexer no
  preco" de "preco = 0". Lista nao tem presenca, por isso `opcoes` vem dentro
  da mensagem `ListaOpcoes`: ausente = mantem; presente e vazia = tira as opcoes.
- **`CriarItem` e idempotente pela `chave`.** O Gateway gera um uuid por
  requisicao HTTP e o repete em todas as tentativas do retry: se a primeira
  gravou e so a resposta se perdeu, a segunda devolve o mesmo item em vez de
  cadastrar outro. O codigo sai da categoria (Entradas `EN`, Pratos `PR`,
  Bebidas `BE`, Sobremesas `SO`) com o proximo numero livre, contando os
  excluidos: um codigo nunca e reaproveitado.
- **Excluir e logico.** O item fica na tabela com `excluido_em` e some de
  `ListarItens` e `ConsultarItens` (um pedido com ele responde
  `INVALID_ARGUMENT`). Excluir de novo nao e erro; so codigo que nunca existiu
  responde `NOT_FOUND`.
- **Foto no banco.** `SalvarFoto` confere o tipo pelos primeiros bytes (JPEG,
  PNG ou WebP) e o tamanho (ate 2 MB, `FOTO_MAXIMO_KB`), e a versao muda junto
  com o conteudo. Bytes no PostgreSQL funcionam igual no compose e no Cloud
  SQL, sem disco no container (ver docs/01).

## `proto/pedidos.proto` - `pedidos.PedidoService`

| RPC | Request | Response | O que faz no banco | Erros |
|---|---|---|---|---|
| `CriarPedido` | `CriarPedidoRequest{cliente, endereco, itens[], usuario_id, pedido_id, telefone}` | `Pedido` | `INSERT ... ON CONFLICT (id) DO NOTHING` em `pedidos` + `itens_pedido` numa transacao | `INVALID_ARGUMENT`, `FAILED_PRECONDITION`, `UNAVAILABLE`, `ALREADY_EXISTS` |
| `ObterPedido` | `ObterPedidoRequest{pedido_id, usuario_id}` | `Pedido` | `SELECT` do pedido (filtrado pelo dono quando `usuario_id` vem preenchido) e das linhas | `INVALID_ARGUMENT`, `NOT_FOUND` |
| `ListarPedidos` | `ListarPedidosRequest{limite, usuario_id}` | `ListarPedidosResponse{pedidos[]}` | `SELECT ... WHERE usuario_id = ? ORDER BY criado_em DESC LIMIT` (sem filtro quando `usuario_id` vem vazio) | `INVALID_ARGUMENT` |
| `AtualizarStatus` | `AtualizarStatusRequest{pedido_id, status}` | `Pedido` | `UPDATE ... WHERE id = ? AND status = atual` + linha em `etapas_pedido` + `NOTIFY` | `INVALID_ARGUMENT`, `NOT_FOUND`, `FAILED_PRECONDITION` |
| `AcompanharPedidos` | `AcompanharPedidosRequest{usuario_id}` | `stream EventoPedido` | `LISTEN` no canal `pedidos`; para cada aviso, `SELECT` do pedido | `INVALID_ARGUMENT` |

**Opcoes do item.** `ItemPedido.opcao` (tag 3) leva a escolha do submenu e
`ItemConfirmado.opcao` (tag 6) a grava no pedido, como o nome e o preco. O
Pedidos confere com as `opcoes` que o Catalogo devolve: item com opcoes exige
uma delas (sem diferenciar maiusculas; grava a grafia do cardapio), item sem
opcoes nao aceita nenhuma. Os dois casos respondem `INVALID_ARGUMENT`.

`AcompanharPedidos` e **server streaming**: a resposta e uma sequencia de
`EventoPedido{tipo, pedido}` que so termina quando quem chamou fecha. `tipo` e
`PEDIDO_CRIADO`, `STATUS_ATUALIZADO` ou `BATIMENTO` (sem pedido, a cada 15 s sem
movimento, para manter a conexao viva). Os avisos saem de um `NOTIFY` gravado na
mesma transacao da mudanca, entao funcionam com varias instancias do Pedidos.

Campos de filtro do `ListarPedidosRequest` (vazio = sem filtro; varios
preenchidos se combinam):

| Campo | Tag | Filtro |
|---|---|---|
| `status` (repeated `StatusPedido`) | 3 | pedido em uma destas etapas |
| `criado_desde` | 4 | criado a partir deste instante (ISO 8601) |
| `codigo_item` | 5 | pedido que tem este item do cardapio |
| `cliente` | 6 | trecho do nome do cliente, sem diferenciar maiusculas |

Campos novos no Trabalho 3 (tags novas, nenhuma tag antiga mudou de numero, entao
mensagens antigas continuam compativeis):

| Mensagem | Campo | Tag | Quem preenche | Para que |
|---|---|---|---|---|
| `CriarPedidoRequest` | `usuario_id` | 4 | Gateway, com o `sub` do token | dono do pedido |
| `CriarPedidoRequest` | `pedido_id` | 5 | Gateway, UUID novo por requisicao HTTP | chave de idempotencia: repetir a chamada (retry) devolve o pedido ja gravado em vez de criar outro |
| `ObterPedidoRequest` | `usuario_id` | 2 | Gateway: vazio para a cozinha, o `sub` para cliente | pedido de outro usuario responde `NOT_FOUND`, sem revelar que o id existe |
| `ListarPedidosRequest` | `usuario_id` | 2 | idem | lista so os pedidos do dono |
| `Pedido` | `usuario_id` | 10 | Pedidos | dono do pedido (vazio nos pedidos anteriores ao Trabalho 3) |

O campo `cliente` continua no contrato, mas quem preenche e o Gateway, com o
nome que esta no token: o corpo HTTP do `POST /pedidos` nao tem mais esse campo.

`Pedido`:

| Campo | Tipo | Tag | Observacao |
|---|---|---|---|
| `pedido_id` | string | 1 | UUID4 gerado pelo Gateway (ou pelo servico, se vier vazio) |
| `cliente` | string | 2 | nome do dono no momento da compra |
| `endereco` | string | 3 | |
| `status` | `StatusPedido` | 4 | enum |
| `itens` | repeated `ItemConfirmado` | 5 | `codigo, nome, quantidade, preco_unitario, subtotal, opcao` |
| `total` | double | 6 | soma dos subtotais, arredondada |
| `tempo_estimado_minutos` | int32 | 7 | `15 + 3 x unidades` |
| `criado_em` | string | 8 | ISO 8601 com fuso (`2026-09-24T20:43:57-03:00`) |
| `atualizado_em` | string | 9 | muda a cada `AtualizarStatus` |
| `usuario_id` | string | 10 | UUID do dono (o `id` do `Usuario`) |
| `historico` | repeated `EtapaRegistrada{status, registrado_em}` | 11 | etapas ja alcancadas, em ordem, com o horario (tabela `etapas_pedido`) |
| `previsao_entrega` | string | 12 | ISO 8601: `criado_em` + `tempo_estimado_minutos` |

`StatusPedido`: `STATUS_DESCONHECIDO = 0` (obrigatorio em proto3),
`RECEBIDO`, `EM_PREPARO`, `PRONTO`, `SAIU_PARA_ENTREGA`, `ENTREGUE`. O pedido so
avanca para a etapa seguinte. Pular ou voltar responde `FAILED_PRECONDITION`;
pedir o status em que o pedido ja esta devolve o pedido sem alterar nada
(idempotente, para um retry nao virar erro).

## Servicos padrao em todos os servidores

| Servico | Para que |
|---|---|
| `grpc.health.v1.Health` | health check padrao do gRPC: `HEALTHCHECK` das imagens e `GET /saude/servicos` do Gateway |
| `grpc.reflection.v1alpha.ServerReflection` | `grpcurl` sem o `.proto` local |

Metadados gRPC usados entre os servicos:

| Metadado | Direcao | Para que |
|---|---|---|
| `traceparent` | quem chama -> servico | id da requisicao, para os logs de todos os servicos mostrarem o mesmo id |
| `x-falha-dependencia` (trailer) | servico -> quem chama | avisa que a falha foi de uma dependencia (ex.: `catalogo`); quem chama nao repete a chamada e nao abre o circuito do servico (ver [07-resiliencia.md](07-resiliencia.md)) |

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

Os tres servidores tem *reflection* habilitado. As portas sao publicadas so em
`127.0.0.1` da maquina onde rodam (na VM `servidor-delivery`, em `0.0.0.0`, mas o
firewall so aceita a VM do Gateway). Na maquina local ou dentro da VM:

```bash
grpcurl -plaintext localhost:9092 list
grpcurl -plaintext -d '{"login":"professor","senha":"SENHA_DO_ENV"}' localhost:9092 usuarios.UsuarioService/VerificarCredenciais
grpcurl -plaintext localhost:9091 list
grpcurl -plaintext -d '{"codigos":["PR01","BE02"]}' localhost:9091 catalogo.CatalogoService/ConsultarItens
grpcurl -plaintext -d '{"limite":3}' localhost:9090 pedidos.PedidoService/ListarPedidos
grpcurl -plaintext localhost:9091 grpc.health.v1.Health/Check
```

De fora (internet) as portas 9090-9092 nao respondem: so o Gateway e o frontend
sao publicos.
