# 3. Execucao local

No seu computador tudo roda em containers: o PostgreSQL (profile `banco-local`),
o migrador, os tres microsservicos, o Gateway e o frontend. Nao precisa de
conta nem de nada na nuvem.

## Pre-requisitos

| Programa | Para que | Onde baixar |
|---|---|---|
| **Docker Desktop** (Windows/macOS) ou Docker Engine com o plugin Compose (Linux) | construir as imagens e subir os containers | docker.com/products/docker-desktop |
| **Git** | clonar o repositorio | git-scm.com |
| **Python 3.10+** (opcional) | rodar os scripts de teste, que so usam a biblioteca padrao | python.org |

No Windows, o Docker Desktop precisa estar aberto (icone da baleia parado na
bandeja) antes dos comandos abaixo. Confira com `docker version`.

## Subir tudo

PowerShell (Windows):

```powershell
git clone https://github.com/matheus14maia/sd-2026-2.git
cd sd-2026-2
Copy-Item .env.exemplo .env
notepad .env        # troque a linha DEMO_SENHA= por uma senha sua, ex.: DEMO_SENHA=minha-senha-123
docker compose up -d --build
docker compose ps
```

Bash (Linux/macOS):

```bash
git clone https://github.com/matheus14maia/sd-2026-2.git
cd sd-2026-2
cp .env.exemplo .env      # e edite DEMO_SENHA
docker compose up -d --build
docker compose ps
```

A primeira vez demora alguns minutos (baixa as imagens base e instala as
dependencias); depois o Docker reaproveita o cache.

`DEMO_SENHA` e a senha do usuario `professor` (papel `cozinha`), que o migrador
cria. Vazia ou igual a um valor que ja apareceu no repositorio, o migrador nao
cria o usuario. Nenhuma senha fica no repositorio.

O `.env.exemplo` ja traz `COMPOSE_PROFILES=banco-local,servicos,gateway,frontend`,
entao o `docker compose up` sobe todos os papeis. Sem o `.env`, passe os
profiles na linha de comando:
`docker compose --profile banco-local --profile servicos --profile gateway --profile frontend up -d --build`.

Servicos esperados (`docker compose ps`):

| Container | Estado | Porta |
|---|---|---|
| `delivery-postgres` | Up (healthy) | interna 5432 |
| `delivery-migrador` | Exited (0) | roda o schema e o seed e termina |
| `delivery-usuarios` | Up (healthy) | `127.0.0.1:9092` |
| `delivery-catalogo` | Up (healthy) | `127.0.0.1:9091` |
| `delivery-pedidos` | Up (healthy) | `127.0.0.1:9090` |
| `delivery-gateway` | Up (healthy) | `0.0.0.0:8000->8000/tcp` |
| `delivery-frontend` | Up (healthy) | `0.0.0.0:80->8080/tcp` |

O `(healthy)` vem do `HEALTHCHECK` de cada imagem: os microsservicos respondem
ao health check gRPC, o Gateway ao `GET /saude` e o nginx a pagina inicial.

- **Frontend:** `http://localhost` (login `professor` com a `DEMO_SENHA` do `.env`, ou crie uma conta).
- **Gateway:** `http://localhost:8000`, Swagger em `http://localhost:8000/docs`.
- A porta 80 ocupada na maquina? Troque `FRONTEND_PORTA=3000` no `.env`, rode
  `docker compose up -d frontend` e use `http://localhost:3000`.
- As portas gRPC ficam so em `127.0.0.1`: da para usar o `grpcurl` local, mas
  nada na rede alcanca os microsservicos.

Log do migrador (`docker compose logs migrador`):

```text
Migrando banco em postgres:5432/delivery (sslmode=disable)
  aplicando db/schema.sql
  aplicando db/seed.sql
  usuario da cozinha: professor
Banco pronto: 13 itens no cardapio, 0 pedidos, 1 usuarios.
```

Uma linha `Banco indisponivel (tentativa 1/30)` antes disso e normal: o
PostgreSQL leva alguns segundos para aceitar conexao, e o migrador espera.

## Testar

### Teste ponta a ponta (37 cenarios)

PowerShell:

```powershell
$env:DEMO_SENHA = "a-senha-do-.env"
python scripts\testar_gateway.py --url http://localhost:8000 --resumido
```

Bash:

```bash
DEMO_SENHA=a-senha-do-.env python scripts/testar_gateway.py --url http://localhost:8000 --resumido
```

O script so usa a biblioteca padrao do Python, entao roda sem instalar nada. Ele
faz login com o usuario da cozinha, cria um cliente novo e confere status e
conteudo de cada resposta:

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
OK  Pedido valido gravado em nome do dono do token  (esperado 201, recebido 201)
OK  Campo cliente no corpo e recusado (o nome vem do token)  (esperado 400, recebido 400)
OK  Sem o campo endereco  (esperado 400, recebido 400)
OK  Quantidade zero e endereco vazio  (esperado 400, recebido 400)
OK  Lista de itens vazia  (esperado 400, recebido 400)
OK  JSON malformado  (esperado 400, recebido 400)
OK  Item que nao existe no banco  (esperado 400, recebido 400)
OK  Item indisponivel (PR05)  (esperado 409, recebido 409)
OK  Consulta do pedido criado  (esperado 200, recebido 200)
OK  Pedido inexistente  (esperado 404, recebido 404)
OK  Avanca status RECEBIDO -> EM_PREPARO  (esperado 200, recebido 200)
OK  Repetir o mesmo status e idempotente  (esperado 200, recebido 200)
OK  Pula etapa EM_PREPARO -> ENTREGUE  (esperado 409, recebido 409)
OK  Status fora da lista  (esperado 400, recebido 400)
OK  Cliente tentando avancar o status  (esperado 403, recebido 403)
OK  Cliente faz o proprio pedido  (esperado 201, recebido 201)
OK  Cliente lista so os proprios pedidos  (esperado 200, recebido 200)
OK  Cliente consulta o proprio pedido  (esperado 200, recebido 200)
OK  Cliente nao ve o pedido de outro usuario  (esperado 404, recebido 404)
OK  Cozinha lista os pedidos de todos  (esperado 200, recebido 200)
OK  Cozinha consulta o pedido do cliente  (esperado 200, recebido 200)
OK  Health check dos microsservicos  (esperado 200, recebido 200)

Todos os 37 cenarios passaram.
```

### Teste de tolerancia a falhas

```bash
python scripts/testar_resiliencia.py
```

Derruba o Catalogo (`docker compose stop catalogo`), confere o fallback do
cardapio, o 503 do pedido, o isolamento do Pedidos e o circuit breaker, religa
o Catalogo e confere a recuperacao. Detalhes e outros cenarios (falha parcial,
lentidao) em [07-resiliencia.md](07-resiliencia.md).

O mesmo fluxo pelo navegador esta em [06-frontend.md](06-frontend.md).

## Conferir no banco

```bash
docker compose exec postgres psql -U postgres -d delivery \
  -c "select login, nome, papel, left(senha_hash, 7) as hash, criado_em from usuarios order by criado_em;" \
  -c "select id, usuario_id, cliente, status, total, criado_em from pedidos order by criado_em;" \
  -c "select pedido_id, linha, codigo, quantidade, subtotal from itens_pedido;" \
  -c "select codigo, preco, disponivel, atualizado_em from itens_cardapio where codigo = 'PR05';"
```

No PowerShell, junte tudo numa linha so (sem as barras invertidas) ou rode um
`-c` por vez.

- O `hash` sai como `$2b$12$`: so o hash bcrypt fica no banco.
- `usuario_id` e o dono do pedido (o `sub` do token); `cliente` e o nome dele
  no momento da compra.

Persistencia: `docker compose restart usuarios catalogo pedidos gateway` e o
`GET /pedidos/{id}` de um pedido anterior continua respondendo 200 (o token
continua valido se `JWT_SEGREDO` estiver no `.env`; sem ele, o Gateway sorteia
um segredo novo a cada subida e e preciso fazer login de novo).

## Logs (uma linha por chamada)

```bash
docker compose logs -f gateway usuarios pedidos catalogo
```

```text
delivery-usuarios  | [20:43:51] [5d270bae] VerificarCredenciais: login='professor' -> ok
delivery-gateway   | [20:43:51] [5d270bae] POST /auth/login -> 200 (212 ms)
delivery-pedidos   | [20:43:57] [e99430b1] CriarPedido: pedido=c841893b-... usuario=46034422-... cliente='Professor' itens=[('PR01', 2)]
delivery-catalogo  | [20:43:57] [e99430b1] ConsultarItens: ['PR01'] -> 1 encontrados
delivery-pedidos   | [20:43:57] [e99430b1] Pedido c841893b-... gravado: 1 itens, 2 unidades, total R$ 125.80
delivery-gateway   | [20:43:57] [e99430b1] POST /pedidos -> 201 (41 ms) [professor]
delivery-gateway   | [20:43:58] [7a51c0de] GET /pedidos -> 401 (0 ms)
```

- O colchete e o id da requisicao: o mesmo id aparece em todos os servicos que
  a atenderam (ver [07-resiliencia.md](07-resiliencia.md#seguir-uma-requisicao-pelos-logs)).
- A linha do Gateway mostra o login do dono do token. Um 401 aparece so no log
  do Gateway: a requisicao nao chegou a nenhum microsservico.

## Imagens

Cada componente tem o seu Dockerfile multi-stage, em `docker/` e `frontend/`:

| Imagem | Dockerfile | Base final | O que leva |
|---|---|---|---|
| usuarios, catalogo, pedidos | `docker/microsservico.Dockerfile` (`--build-arg SERVICO=...`) | `python:3.12-slim` | venv com gRPC, psycopg e bcrypt + o codigo do servico |
| gateway | `docker/gateway.Dockerfile` | `python:3.12-slim` | venv com FastAPI, Uvicorn, PyJWT e gRPC + o codigo do Gateway |
| migrador | `docker/migrador.Dockerfile` | `python:3.12-slim` | psycopg, bcrypt, `db/` e o script |
| frontend | `frontend/Dockerfile` | `nginxinc/nginx-unprivileged:1.28-alpine` | os arquivos estaticos do Vite |

Boas praticas aplicadas: estagios separados para gerar os stubs (o `grpcio-tools`
nao vai para a imagem final) e instalar dependencias; camada de dependencias
antes do codigo (mudar o codigo nao reinstala nada); `requirements/` separado
por papel (o Gateway nao leva driver de banco, os servicos nao levam FastAPI);
usuario sem root; `HEALTHCHECK`; `.dockerignore` em lista de permissao.

Comparacao medida no `docker image inspect` (inclui a base `python:3.12-slim`):
a imagem unica do Trabalho 2 tinha **308 MB**; agora gateway **229 MB**,
microsservicos **233 MB**, migrador **208 MB** e frontend **82 MB**.

## Sem Docker (desenvolvimento)

Precisa de um PostgreSQL acessivel. O mais simples e subir so o container do
banco e publicar a porta:

```bash
docker run -d --name pg-dev -e POSTGRES_DB=delivery -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16
python -m venv .venv          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/gerar_stubs.py
export DB_PASSWORD=postgres DB_SSLMODE=disable DEMO_SENHA=minha-senha   # PowerShell: $env:DB_PASSWORD="postgres"; ...
python scripts/migrar_banco.py
python -m src.usuarios.servidor          # terminal 1
python -m src.catalogo.servidor          # terminal 2
python -m src.pedidos.servidor           # terminal 3
python -m src.gateway                    # terminal 4 (porta 8000)
cd frontend && npm install && npm run dev   # terminal 5 (http://localhost:5173)
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

## Problemas comuns

| Sintoma | Causa provavel | Acao |
|---|---|---|
| `error during connect` / `Cannot connect to the Docker daemon` | Docker Desktop fechado | abra o Docker Desktop e espere ficar pronto |
| `Bind for 0.0.0.0:80 failed: port is already allocated` | outro programa usa a porta 80 | `FRONTEND_PORTA=3000` no `.env` e `docker compose up -d frontend` |
| Login do `professor` responde 401 | `DEMO_SENHA` vazia ou trocada depois do primeiro `up` | defina a senha no `.env` e rode `docker compose up -d migrador` (ele atualiza a senha) |
| Frontend abre, mas toda acao da "Gateway fora do ar" | Gateway parado ou `API_URL` errado | `docker compose ps` e `curl http://localhost:8000/saude` |
| `delivery-migrador` reiniciando | banco ainda subindo | espere; o migrador tenta de novo sozinho |
