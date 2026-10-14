# 3. Execucao local

No ambiente local tudo roda na mesma maquina: o PostgreSQL em container
(profile `banco-local`, no papel que o Cloud SQL cumpre no GCP), os tres
microsservicos, o Gateway e o frontend. O codigo e o mesmo do GCP: so mudam as
variaveis do `.env`.

## Com Docker (recomendado)

```bash
cp .env.exemplo .env          # PowerShell: Copy-Item .env.exemplo .env
docker compose up -d --build
docker compose ps
```

O `.env.exemplo` ja traz `COMPOSE_PROFILES=banco-local,servicos,gateway,frontend`,
entao o `docker compose up` sobe todos os papeis. Sem o `.env`, passe os
profiles na linha de comando:
`docker compose --profile banco-local --profile servicos --profile gateway --profile frontend up -d --build`.

Servicos esperados:

| Container | Estado | Porta |
|---|---|---|
| `delivery-postgres` | Up | interna 5432 |
| `delivery-migrador` | Exited (0) | roda o schema e o seed e termina |
| `delivery-usuarios` | Up | `127.0.0.1:9092` |
| `delivery-catalogo` | Up | `127.0.0.1:9091` |
| `delivery-pedidos` | Up | `127.0.0.1:9090` |
| `delivery-gateway` | Up | `0.0.0.0:8000->8000/tcp` |
| `delivery-frontend` | Up | `0.0.0.0:80->80/tcp` |

- **Frontend:** `http://localhost` (conta `professor` / `delivery2026`).
- **Gateway:** `http://localhost:8000`, Swagger em `http://localhost:8000/docs`.
- A porta 80 ocupada na maquina? Troque `FRONTEND_PORTA=3000` no `.env` e use
  `http://localhost:3000`.
- As portas gRPC ficam so em `127.0.0.1`: da para usar o `grpcurl` local, mas
  nada na rede alcanca os microsservicos.

Log do migrador (`docker compose logs migrador`):

```text
Migrando banco em postgres:5432/delivery (sslmode=disable)
  aplicando db/schema.sql
  aplicando db/seed.sql
Banco pronto: 13 itens no cardapio, 0 pedidos, 1 usuarios.
```

Uma linha `Banco indisponivel (tentativa 1/30)` antes disso e normal: o
PostgreSQL leva alguns segundos para aceitar conexao, e o migrador espera.

## Testar

```bash
python scripts/testar_gateway.py --url http://localhost:8000 --resumido
```

O script so usa a biblioteca padrao do Python, entao roda sem instalar nada. Ele
faz login com o usuario de demonstracao, cria um usuario novo e passa por todos
os status:

```text
OK  Gateway no ar (rota publica)  (esperado 200, recebido 200)
OK  Sem token  (esperado 401, recebido 401)
OK  Cabecalho sem Bearer  (esperado 401, recebido 401)
OK  Token que nao e JWT  (esperado 401, recebido 401)
OK  Login sem senha  (esperado 400, recebido 400)
OK  Senha errada  (esperado 401, recebido 401)
OK  Cadastro com dados invalidos  (esperado 400, recebido 400)
OK  Cadastro de usuario novo  (esperado 201, recebido 201)
OK  Cadastro com login repetido  (esperado 409, recebido 409)
OK  Login valido devolve o token  (esperado 200, recebido 200)
OK  Token com assinatura adulterada  (esperado 401, recebido 401)
OK  Dono do token  (esperado 200, recebido 200)
OK  Login do cliente recem-criado  (esperado 200, recebido 200)
OK  Cliente tentando alterar o cardapio  (esperado 403, recebido 403)
OK  Cardapio de bebidas  (esperado 200, recebido 200)
OK  Pedido valido e gravado no banco  (esperado 201, recebido 201)
OK  Sem o campo cliente  (esperado 400, recebido 400)
OK  Quantidade zero e itens vazios  (esperado 400, recebido 400)
OK  Lista de itens vazia  (esperado 400, recebido 400)
OK  JSON malformado  (esperado 400, recebido 400)
OK  Item que nao existe no banco  (esperado 400, recebido 400)
OK  Item indisponivel (PR05)  (esperado 409, recebido 409)
OK  Consulta do pedido criado  (esperado 200, recebido 200)
OK  Pedido inexistente  (esperado 404, recebido 404)
OK  Avanca status RECEBIDO -> EM_PREPARO  (esperado 200, recebido 200)
OK  Pula etapa EM_PREPARO -> ENTREGUE  (esperado 409, recebido 409)
OK  Status fora da lista  (esperado 400, recebido 400)
OK  Cliente tentando avancar o status  (esperado 403, recebido 403)
OK  Lista os pedidos  (esperado 200, recebido 200)

Todos os cenarios passaram.
```

O mesmo fluxo pelo navegador esta em [06-frontend.md](06-frontend.md).

## Conferir no banco

```bash
docker compose exec postgres psql -U postgres -d delivery \
  -c "select login, nome, papel, left(senha_hash, 7) as hash, criado_em from usuarios order by criado_em;" \
  -c "select id, cliente, status, total, criado_em, atualizado_em from pedidos order by criado_em;" \
  -c "select pedido_id, linha, codigo, quantidade, subtotal from itens_pedido;" \
  -c "select codigo, preco, disponivel, atualizado_em from itens_cardapio where codigo = 'PR05';"
```

O `hash` sai como `$2b$12$`: so o hash bcrypt fica no banco.

Persistencia: `docker compose restart usuarios catalogo pedidos gateway` e o
`GET /pedidos/{id}` de um pedido anterior continua respondendo 200 (o token
continua valido se `JWT_SEGREDO` estiver no `.env`; sem ele, o Gateway sorteia
um segredo novo a cada subida e e preciso fazer login de novo).

## Logs (uma linha por chamada)

```bash
docker compose logs -f gateway usuarios pedidos catalogo
```

```text
delivery-usuarios  | [20:43:51] VerificarCredenciais: login='professor' -> ok
delivery-gateway   | [20:43:51] POST /auth/login -> 200 (212 ms)
delivery-pedidos   | [20:43:57] CriarPedido: cliente='Maria' itens=[('PR01', 2)]
delivery-catalogo  | [20:43:57] ConsultarItens: ['PR01'] -> 1 encontrados
delivery-pedidos   | [20:43:57] Pedido 4bb080f4-... gravado: 1 itens, 2 unidades, total R$ 125.80
delivery-gateway   | [20:43:57] POST /pedidos -> 201 (41 ms) [professor]
delivery-gateway   | [20:43:58] GET /pedidos -> 401 (0 ms)
```

A linha do Gateway mostra o login do dono do token. Um 401 aparece so no log do
Gateway: a requisicao nao chegou a nenhum microsservico.

## Sem Docker (desenvolvimento)

Precisa de um PostgreSQL acessivel. O mais simples e subir so o container do
banco e publicar a porta:

```bash
docker run -d --name pg-dev -e POSTGRES_DB=delivery -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16
python -m venv .venv          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/gerar_stubs.py
export DB_PASSWORD=postgres   # PowerShell: $env:DB_PASSWORD="postgres"
python scripts/migrar_banco.py
python -m src.usuarios.servidor                          # terminal 1
python -m src.catalogo.servidor                          # terminal 2
python -m src.pedidos.servidor                           # terminal 3
uvicorn src.gateway.app:app --host 0.0.0.0 --port 8000   # terminal 4
cd frontend && npm install && npm run dev                # terminal 5 (http://localhost:5173)
```

Os padroes das variaveis ja apontam para `localhost` (banco em 5432, Usuarios em
9092, Catalogo em 9091, Pedidos em 9090). O frontend em modo de desenvolvimento
chama o Gateway em `http://localhost:8000`.

## Desligar

```bash
docker compose stop      # para, mantem os dados
docker compose down      # remove os containers, o volume com os dados fica
docker compose down -v   # remove tambem o volume (zera o banco)
```
