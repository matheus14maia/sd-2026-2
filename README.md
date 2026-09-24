# Delivery Hell's Kitchen - Sistemas Distribuidos 2026/2

Delivery de restaurante com **API Gateway HTTP/JSON** (FastAPI) na frente de dois
**microsservicos gRPC** (Catalogo e Pedidos) que persistem em **PostgreSQL**
(Cloud SQL no GCP).

```text
 cliente HTTP            VM do GCP (so a 8000 e publica)                  Cloud SQL
 (curl, Swagger,  +--------------------------------------------------+   +------------+
  frontend)       |                     gRPC            gRPC           |   | PostgreSQL |
 ---- JSON ---->  |  [ gateway :8000 ] ----> [ pedidos :9090 ] ----->  |   |            |
 <--- JSON -----  |   FastAPI+Pydantic  \        |  pedidos,         |   |  pedidos   |
   201/200/400/   |                      \       |  itens_pedido  ---+-->|  itens_... |
   404/409/503    |                       ---> [ catalogo :9091 ] ---+-->|  itens_    |
                  |                               itens_cardapio     |   |  cardapio  |
                  +--------------------------------------------------+   +------------+
```

## Stack

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 |
| API Gateway | FastAPI + Pydantic (validacao do payload), Uvicorn |
| Microsservicos | gRPC (grpcio 1.68) + Protocol Buffers proto3 |
| Banco de dados | PostgreSQL 16 (Cloud SQL no GCP, container no ambiente local), psycopg 3 |
| Execucao | Docker + Docker Compose (imagem unica, papel escolhido pelo `command`) |
| Infraestrutura | Compute Engine (VM `servidor-delivery`) + Cloud SQL + firewall VPC |

## Rotas do Gateway

| Metodo e rota | Microsservico | Sucesso | Erros |
|---|---|---|---|
| `GET /cardapio?categoria=` | Catalogo | 200 | 404 categoria inexistente |
| `PATCH /cardapio/{codigo}` | Catalogo | 200 | 400, 404 |
| `POST /pedidos` | Pedidos -> Catalogo | **201** | **400** payload invalido ou item inexistente, 409 item indisponivel |
| `GET /pedidos?limite=` | Pedidos | 200 | 400 |
| `GET /pedidos/{id}` | Pedidos | 200 | 400 id malformado, 404 |
| `PATCH /pedidos/{id}/status` | Pedidos | 200 | 400, 404, 409 transicao invalida |
| `GET /saude` | - | 200 | - |

A documentacao interativa (Swagger) fica em `http://HOST:8000/docs`.

## Comecando rapido (local, com banco em container)

```bash
docker compose --profile banco-local up -d --build
python scripts/testar_gateway.py --url http://localhost:8000
```

O segundo comando roda os cenarios de sucesso e de erro e confere o status HTTP
de cada um. Detalhes em [docs/03-execucao-local.md](docs/03-execucao-local.md).

## Documentacao

| Documento | Conteudo |
|---|---|
| [docs/01-visao-geral-do-sistema.md](docs/01-visao-geral-do-sistema.md) | arquitetura, fluxo de uma requisicao e como o sistema reage a cada situacao |
| [docs/02-contrato-grpc.md](docs/02-contrato-grpc.md) | os dois `.proto` explicados e a geracao dos stubs |
| [docs/03-execucao-local.md](docs/03-execucao-local.md) | subir tudo localmente, testar e consultar o banco |
| [docs/04-deploy-gcp-vm.md](docs/04-deploy-gcp-vm.md) | VM + Cloud SQL no GCP, deploy e ciclo liga/desliga |
| [docs/05-api-gateway.md](docs/05-api-gateway.md) | rotas, validacao, formato de erro e exemplos de requisicao |

O manual do projeto, o prontuario de problemas e o changelog ficam em
[markdown/](markdown/).

## Estrutura

```text
proto/catalogo.proto         contrato do microsservico de Catalogo
proto/pedidos.proto          contrato do microsservico de Pedidos
db/schema.sql, db/seed.sql   tabelas e carga inicial do cardapio (idempotentes)
src/gateway/                 API Gateway FastAPI (rotas, esquemas, erros, clientes gRPC)
src/catalogo/                microsservico de Catalogo (servidor, servico, repositorio)
src/pedidos/                 microsservico de Pedidos (servidor, servico, repositorio, cliente do Catalogo)
src/comum/                   conexao com o banco e inicializacao comum dos servidores gRPC
src/gerado/                  stubs gerados no build (nao versionados)
scripts/gerar_stubs.py       gera os stubs a partir de proto/*.proto
scripts/migrar_banco.py      aplica db/schema.sql e db/seed.sql
scripts/testar_gateway.py    smoke test dos cenarios 200/201/400/404/409
docker-compose.yml           postgres (profile banco-local), migrador, catalogo, pedidos, gateway
```

> Os arquivos em `src/gerado/` sao artefato de build: regerados por
> `scripts/gerar_stubs.py` e no `docker build`. Nunca edite a mao.
