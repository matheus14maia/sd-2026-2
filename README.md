# Delivery Hell's Kitchen - Sistemas Distribuidos 2026/2

Delivery de restaurante com **frontend React**, **API Gateway HTTP/JSON**
(FastAPI, autenticacao JWT) e **tres microsservicos gRPC** (Usuarios, Catalogo e
Pedidos) que persistem em **PostgreSQL** (Cloud SQL no GCP). No GCP cada camada
roda em uma VM propria.

![Arquitetura](docs/arquitetura.png)

```text
 navegador --HTTP :80-->  [VM delivery-frontend]  React servido pelo nginx
     |
     +--HTTP/JSON + Bearer :8000-->  [VM delivery-gateway]  FastAPI
                                       CORS -> log -> JWT (401) -> papel (403) -> Pydantic (400)
                                       |  gRPC / Protobuf pela rede interna da VPC
                                       v
                              [VM servidor-delivery]  usuarios :9092  catalogo :9091  pedidos :9090
                                       |                              ^-- gRPC ConsultarItens --'
                                       |  SQL / TLS
                                       v
                              [Cloud SQL delivery-postgres]  usuarios, itens_cardapio, pedidos, itens_pedido
```

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React 18 + Vite 5, servido pelo nginx |
| API Gateway | FastAPI + Pydantic (validacao), PyJWT (HS256), Uvicorn |
| Microsservicos | Python 3.12, gRPC (grpcio 1.68) + Protocol Buffers proto3, bcrypt |
| Banco de dados | PostgreSQL 16 (Cloud SQL no GCP, container no ambiente local), psycopg 3 |
| Execucao | Docker + Docker Compose, um profile por papel |
| Infraestrutura | 3 VMs no Compute Engine + Cloud SQL + firewall VPC por tag |

## Rotas do Gateway

| Metodo e rota | Token | Microsservico | Sucesso | Erros |
|---|---|---|---|---|
| `POST /auth/cadastro` | nao | Usuarios | **201** | 400, 409 login em uso |
| `POST /auth/login` | nao | Usuarios | 200 + token | 400, **401** senha errada |
| `GET /auth/eu` | sim | - | 200 | 401 |
| `GET /cardapio?categoria=` | sim | Catalogo | 200 | 401, 404 categoria inexistente |
| `PATCH /cardapio/{codigo}` | sim, papel `cozinha` | Catalogo | 200 | 400, 401, **403**, 404 |
| `POST /pedidos` | sim | Pedidos -> Catalogo | **201** | **400**, 401, 409 item indisponivel |
| `GET /pedidos?limite=` | sim | Pedidos | 200 | 400, 401 |
| `GET /pedidos/{id}` | sim | Pedidos | 200 | 400, 401, 404 |
| `PATCH /pedidos/{id}/status` | sim, papel `cozinha` | Pedidos | 200 | 400, 401, 403, 404, 409 |
| `GET /saude` | nao | - | 200 | - |

Sem `Authorization: Bearer <token>` valido, toda rota marcada com token responde
**401** antes de qualquer chamada gRPC. Swagger em `http://HOST:8000/docs`.

Conta de demonstracao (papel `cozinha`): login **`professor`**, senha
**`delivery2026`**. Quem se cadastra pela API entra com papel `cliente`.

## Comecando rapido (local, tudo em containers)

```bash
cp .env.exemplo .env
docker compose up -d --build
python scripts/testar_gateway.py --url http://localhost:8000
```

- O `.env.exemplo` ja vem com `COMPOSE_PROFILES=banco-local,servicos,gateway,frontend`.
- Frontend em `http://localhost`, Gateway em `http://localhost:8000`.
- O teste roda 29 cenarios (200/201/400/401/403/404/409) e confere o status de cada um.

Detalhes em [docs/03-execucao-local.md](docs/03-execucao-local.md).

## Documentacao

| Documento | Conteudo |
|---|---|
| [docs/01-visao-geral-do-sistema.md](docs/01-visao-geral-do-sistema.md) | arquitetura, fluxo de uma requisicao e como o sistema reage a cada situacao |
| [docs/02-contrato-grpc.md](docs/02-contrato-grpc.md) | os tres `.proto` explicados e a geracao dos stubs |
| [docs/03-execucao-local.md](docs/03-execucao-local.md) | subir tudo localmente, testar e consultar o banco |
| [docs/04-deploy-gcp-vm.md](docs/04-deploy-gcp-vm.md) | 3 VMs + Cloud SQL no GCP, firewall, scripts de deploy e liga/desliga |
| [docs/05-api-gateway.md](docs/05-api-gateway.md) | rotas, JWT, papeis, validacao, formato de erro e exemplos |
| [docs/06-frontend.md](docs/06-frontend.md) | telas do frontend, como ele chama o Gateway e como roda |
| [apresentacao/](apresentacao/) | slides da arquitetura (`.pptx` e `.pdf`) |

O manual do projeto, o prontuario de problemas e o changelog ficam em
[markdown/](markdown/).

## Estrutura

```text
proto/usuarios.proto         contrato do microsservico de Usuarios
proto/catalogo.proto         contrato do microsservico de Catalogo
proto/pedidos.proto          contrato do microsservico de Pedidos
db/schema.sql, db/seed.sql   tabelas, cardapio inicial e usuario de demonstracao (idempotentes)
src/gateway/                 API Gateway FastAPI (autenticacao, rotas, esquemas, erros, clientes gRPC)
src/usuarios/                microsservico de Usuarios (servidor, servico, repositorio)
src/catalogo/                microsservico de Catalogo (servidor, servico, repositorio)
src/pedidos/                 microsservico de Pedidos (servidor, servico, repositorio, cliente do Catalogo)
src/comum/                   conexao com o banco e inicializacao comum dos servidores gRPC
src/gerado/                  stubs gerados no build (nao versionados)
frontend/                    frontend React (Vite) + Dockerfile do nginx
scripts/gerar_stubs.py       gera os stubs a partir de proto/*.proto
scripts/migrar_banco.py      aplica db/schema.sql e db/seed.sql
scripts/testar_gateway.py    teste ponta a ponta dos cenarios 200/201/400/401/403/404/409
scripts/gcp/                 criar a infraestrutura, implantar, ligar, desligar e conferir no GCP
docker-compose.yml           profiles servicos, gateway, frontend e banco-local
```

> Os arquivos em `src/gerado/` sao artefato de build: regerados por
> `scripts/gerar_stubs.py` e no `docker build`. Nunca edite a mao.
