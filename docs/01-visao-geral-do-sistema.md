# 1. Visao geral do sistema

## O que o sistema faz

O *Hell's Kitchen* e um restaurante com delivery. Pela API HTTP e possivel:

- consultar o cardapio (inteiro ou por categoria);
- montar um pedido com varios itens e a quantidade de cada um;
- consultar e listar pedidos;
- avancar o status do pedido (`RECEBIDO -> EM_PREPARO -> PRONTO -> SAIU_PARA_ENTREGA -> ENTREGUE`);
- tirar um item do cardapio do dia ou mudar o preco.

Tudo o que e consultado, criado ou alterado fica no PostgreSQL. Nao existe lista
estatica nem dicionario em memoria: reiniciar qualquer container nao perde nada.

## Componentes

| Componente | Papel | Protocolo de entrada | Dono de |
|---|---|---|---|
| **Gateway** (`src/gateway/`) | ponto unico de entrada; valida o JSON, traduz para Protobuf e despacha | HTTP/JSON na porta 8000 (publica) | nenhuma tabela |
| **Catalogo** (`src/catalogo/`) | cardapio: listar, consultar por codigo, alterar disponibilidade/preco | gRPC na porta 9091 (interna) | `itens_cardapio` |
| **Pedidos** (`src/pedidos/`) | cria, consulta, lista e avanca pedidos; consulta o Catalogo para precificar | gRPC na porta 9090 (interna) | `pedidos`, `itens_pedido` |
| **PostgreSQL** | persistencia | SQL na porta 5432 | - |
| **Migrador** | cria as tabelas e carrega o cardapio inicial a cada deploy e depois termina | - | - |

Cada microsservico so le e escreve as proprias tabelas. Pedidos nao faz `SELECT`
em `itens_cardapio`: ele pergunta ao Catalogo por gRPC. Por isso a linha do
pedido guarda uma copia do nome e do preco no momento da compra (snapshot):
mudar o preco no Catalogo depois nao altera pedidos antigos.

## Caminho de um `POST /pedidos`

```text
1. cliente  --HTTP POST /pedidos {JSON}-->  gateway
2. gateway: Pydantic valida o payload
            invalido -> 400 {"mensagem", "erros": {campo: motivo}}  (nao chega nos microsservicos)
3. gateway  --gRPC PedidoService.CriarPedido (Protobuf)-->  pedidos
4. pedidos  --gRPC CatalogoService.ConsultarItens-->  catalogo  --SELECT-->  itens_cardapio
5. pedidos: confere existencia/disponibilidade, calcula subtotal, total e tempo
6. pedidos  --INSERT pedidos + itens_pedido (uma transacao)-->  PostgreSQL
7. pedidos  --Pedido (Protobuf)-->  gateway  --201 Created {JSON}-->  cliente
```

## Como o sistema reage

| Situacao | Quem detecta | gRPC | HTTP | Mensagem |
|---|---|---|---|---|
| JSON malformado | Gateway (Pydantic) | - | 400 | `erros.<campo>: "JSON malformado"` |
| `cliente` ou `endereco` ausente | Gateway | - | 400 | `erros.cliente: "campo obrigatorio"` |
| `cliente` so com espacos | Gateway | - | 400 | `erros.cliente: "nao deve estar vazio"` |
| `itens` vazio | Gateway | - | 400 | `erros.itens: "deve ter pelo menos um item"` |
| `quantidade` <= 0 | Gateway | - | 400 | `erros.itens.0.quantidade: "deve ser maior que zero"` |
| `quantidade` nao inteira (`"2"`, `1.5`) | Gateway | - | 400 | `"deve ser um numero inteiro"` |
| codigo fora do formato (`P1`) | Gateway | - | 400 | `"codigo invalido: use 2 letras e 2 digitos (ex.: PR01)"` |
| campo desconhecido (ex.: `preco`) | Gateway | - | 400 | `"campo nao permitido"` |
| codigo valido mas inexistente (`XX99`) | Pedidos (via Catalogo) | `INVALID_ARGUMENT` | 400 | `Item 'XX99' nao existe no cardapio.` |
| item indisponivel (`PR05` na carga inicial) | Pedidos | `FAILED_PRECONDITION` | 409 | `Item 'PR05' (Moqueca de peixe) esta indisponivel hoje.` |
| pedido inexistente | Pedidos | `NOT_FOUND` | 404 | `Pedido '...' nao encontrado.` |
| id de pedido malformado | Pedidos | `INVALID_ARGUMENT` | 400 | `Id de pedido invalido: '...'.` |
| pular ou voltar etapa do status | Pedidos | `FAILED_PRECONDITION` | 409 | `Nao e possivel mudar de EM_PREPARO para ENTREGUE: a proxima etapa e PRONTO.` |
| status fora da lista | Gateway | - | 400 | `"valor nao permitido; use um de: RECEBIDO, ..."` |
| categoria inexistente | Catalogo | `NOT_FOUND` | 404 | `Categoria 'Pizzas' nao existe no cardapio.` |
| Catalogo fora do ar ao criar pedido | Pedidos | `UNAVAILABLE` | 503 | `Catalogo indisponivel no momento (...). Tente novamente.` |
| Pedidos fora do ar | Gateway | `UNAVAILABLE` | 503 | detalhe do gRPC |

A validacao de negocio existe nas duas camadas: o Gateway barra payload
invalido na borda, e o microsservico repete as checagens essenciais para nao
depender de quem o chama (defesa em profundidade).

## Decisoes de projeto

| Decisao | Motivo |
|---|---|
| FastAPI + Pydantic no Gateway | a validacao do payload fica declarada nos modelos (`src/gateway/esquemas.py`), e o Swagger em `/docs` sai de graca para a demonstracao |
| 400 no lugar do 422 padrao do FastAPI | o requisito pede `400 Bad Request` para dado invalido; o handler de `RequestValidationError` e sobrescrito em `src/gateway/erros.py` |
| Dois `.proto`, um por microsservico | cada servico tem o proprio contrato; o Gateway e o Pedidos importam so os stubs que usam |
| Pedidos chama Catalogo por gRPC | comunicacao entre microsservicos e dono unico de cada tabela |
| SQL puro com psycopg 3 (sem ORM) | as consultas ficam visiveis no repositorio de cada servico (`repositorio.py`) |
| Um banco, tabelas separadas por dono | uma unica instancia Cloud SQL mantem o custo baixo sem misturar responsabilidades |
| Status avanca so para a proxima etapa | evita estados impossiveis; o `UPDATE` e condicional (`WHERE status = atual`) para duas chamadas simultaneas nao avancarem duas vezes |
| So o Gateway publica porta | os microsservicos e o banco nao ficam expostos para a internet |
