# 3. Execucao local

No ambiente local o PostgreSQL roda em container (profile `banco-local`), no
papel que o Cloud SQL cumpre no GCP. O codigo e o mesmo nos dois casos: so
mudam as variaveis `DB_*`.

## Com Docker (recomendado)

```bash
docker compose --profile banco-local up -d --build
docker compose ps
```

Servicos esperados:

| Container | Estado | Porta |
|---|---|---|
| `delivery-postgres` | Up | interna 5432 |
| `delivery-migrador` | Exited (0) | roda o schema e o seed e termina |
| `delivery-catalogo` | Up | interna 9091 |
| `delivery-pedidos` | Up | interna 9090 |
| `delivery-gateway` | Up | `0.0.0.0:8000->8000/tcp` |

Log do migrador (`docker compose logs migrador`):

```text
Migrando banco em postgres:5432/delivery (sslmode=disable)
  aplicando db/schema.sql
  aplicando db/seed.sql
Banco pronto: 13 itens no cardapio, 0 pedidos.
```

Uma linha `Banco indisponivel (tentativa 1/30)` antes disso e normal: o
PostgreSQL leva alguns segundos para aceitar conexao, e o migrador espera.

## Testar

```bash
python scripts/testar_gateway.py --url http://localhost:8000
```

O script so usa a biblioteca padrao do Python, entao roda sem instalar nada.
Saida resumida (`--resumido`):

```text
OK  Gateway no ar  (esperado 200, recebido 200)
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
OK  Lista os pedidos  (esperado 200, recebido 200)

Todos os cenarios passaram.
```

O Swagger (`http://localhost:8000/docs`) permite testar cada rota pelo navegador.

## Conferir no banco

```bash
docker compose exec postgres psql -U postgres -d delivery \
  -c "select id, cliente, status, total, criado_em, atualizado_em from pedidos order by criado_em;" \
  -c "select pedido_id, linha, codigo, quantidade, subtotal from itens_pedido;" \
  -c "select codigo, preco, disponivel, atualizado_em from itens_cardapio where codigo = 'PR05';"
```

Persistencia: `docker compose restart catalogo pedidos gateway` e o
`GET /pedidos/{id}` de um pedido anterior continua respondendo 200.

## Logs (uma linha por chamada)

```bash
docker compose logs -f gateway pedidos catalogo
```

```text
delivery-pedidos   | [20:43:57] CriarPedido: cliente='Maria' itens=[('PR01', 2)]
delivery-catalogo  | [20:43:57] ConsultarItens: ['PR01'] -> 1 encontrados
delivery-pedidos   | [20:43:57] Pedido 4bb080f4-... gravado: 1 itens, 2 unidades, total R$ 125.80
delivery-gateway   | [20:43:57] POST /pedidos -> 201 (41 ms)
```

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
python -m src.catalogo.servidor                          # terminal 1
python -m src.pedidos.servidor                           # terminal 2
uvicorn src.gateway.app:app --host 0.0.0.0 --port 8000   # terminal 3
```

Os padroes das variaveis ja apontam para `localhost` (banco em 5432, Catalogo
em 9091, Pedidos em 9090).

## Desligar

```bash
docker compose --profile banco-local stop    # para, mantem os dados
docker compose --profile banco-local down    # remove os containers, o volume com os dados fica
docker compose --profile banco-local down -v # remove tambem o volume (zera o banco)
```
