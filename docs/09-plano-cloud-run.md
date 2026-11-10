# 9. Plano do deploy no Google Cloud (Trabalho 3)

> **Status: planejado.** O codigo ja esta pronto para estes servicos (porta por
> `PORT`, gRPC com TLS e token entre servicos do Cloud Run, logs em JSON,
> rastreamento para o Cloud Trace). Os scripts de deploy ainda vao ser escritos
> e nada abaixo foi executado no projeto.

## Cada componente num servico gerenciado

| Componente | No seu computador | No Google Cloud |
|---|---|---|
| Frontend | container nginx | Cloud Run `delivery-frontend`, publico (HTTPS) |
| Gateway | container | Cloud Run `delivery-gateway`, publico (HTTPS) |
| Usuarios, Catalogo, Pedidos | containers | Cloud Run `delivery-usuarios`, `delivery-catalogo`, `delivery-pedidos`, gRPC com HTTP/2 (`--use-http2`), **privados**: so quem tem o papel `roles/run.invoker` consegue chamar |
| Migrador | container que roda e termina | Cloud Run **job** `delivery-migrador`, executado a cada deploy |
| PostgreSQL | container | Cloud SQL `delivery-postgres` (ja existe), pelo conector do Cloud Run (`DB_HOST=/cloudsql/<conexao>`) |
| Imagens | build local | Artifact Registry `us-central1-docker.pkg.dev/<projeto>/delivery/<componente>` |
| Senhas | `.env` | **Secret Manager** |
| Fotos dos pratos | tabela `fotos_itens` do PostgreSQL | a mesma tabela no Cloud SQL: nada a mudar (o container do Cloud Run nao guarda arquivo) |
| Logs | `docker compose logs` | Cloud Logging (`LOG_JSON=1`) |
| Traces | Jaeger | **Cloud Trace** (`RASTREAMENTO=gcp`, ver [08-rastreamento.md](08-rastreamento.md)) |
| VMs do Trabalho 2 | - | excluidas no fim |

## Senhas no Secret Manager

| Segredo | Variavel que o Cloud Run preenche | Quem le |
|---|---|---|
| `delivery-db-senha` | `DB_PASSWORD` | Usuarios, Catalogo, Pedidos e o migrador |
| `delivery-jwt-segredo` | `JWT_SEGREDO` | Gateway |
| `delivery-demo-senha` | `DEMO_SENHA` | migrador (cria o usuario `professor`) |

- **O codigo nao muda.** Ele ja le tudo de variavel de ambiente. O Cloud Run
  coloca o valor do segredo na variavel quando a instancia sobe
  (`--set-secrets DB_PASSWORD=delivery-db-senha:latest`), e o painel do servico
  mostra a variavel apontando para o segredo, sem mostrar o valor.
- **Criar (uma vez):**

  ```bash
  gcloud services enable secretmanager.googleapis.com
  ```
  ```bash
  python -c "import secrets; print(secrets.token_hex(32), end='')" | gcloud secrets create delivery-jwt-segredo --data-file=-
  ```

  O mesmo para `delivery-db-senha` (a senha do usuario `postgres` do Cloud SQL)
  e `delivery-demo-senha` (a senha da cozinha). O `--data-file=-` le da entrada
  padrao: a senha nao fica no historico do terminal nem em arquivo.
- **Cada servico le so o que usa.** A conta de servico recebe
  `roles/secretmanager.secretAccessor` em cada segredo, nao no projeto inteiro:
  o Gateway nao consegue ler a senha do banco.
- **Trocar uma senha:** `gcloud secrets versions add <segredo> --data-file=-` e
  uma nova revisao do servico (o `:latest` e lido quando a instancia sobe).

## Variaveis de cada servico (painel do Cloud Run)

| Servico | Variaveis comuns | Segredos |
|---|---|---|
| Gateway | `USUARIOS_HOST`, `CATALOGO_HOST`, `PEDIDOS_HOST` (endereco `.run.app` de cada um, sem `https://`), `USUARIOS_PORTA`/`CATALOGO_PORTA`/`PEDIDOS_PORTA=443`, `CORS_ORIGENS=<URL do frontend>`, `LOG_JSON=1`, `GOOGLE_CLOUD_PROJECT`, `RASTREAMENTO=gcp` | `JWT_SEGREDO` |
| Usuarios, Catalogo | `DB_HOST=/cloudsql/<projeto>:us-central1:delivery-postgres`, `DB_NAME=delivery`, `DB_USER=postgres`, `DB_SSLMODE=disable`, `DB_POOL_MAX=3`, `LOG_JSON=1`, `GOOGLE_CLOUD_PROJECT`, `RASTREAMENTO=gcp` | `DB_PASSWORD` |
| Pedidos | as do Catalogo + `CATALOGO_HOST=<catalogo .run.app>`, `CATALOGO_PORTA=443` | `DB_PASSWORD` |
| Frontend | `API_URL=<URL do Gateway>` | - |
| Migrador (job) | `DB_*` como acima, `DEMO_LOGIN=professor` | `DB_PASSWORD`, `DEMO_SENHA` |

- **Porta 443 liga o TLS.** Com `*_PORTA=443`, o `src/comum/canal.py` usa TLS e
  manda o token de identidade da conta de servico em cada chamada gRPC.
- `DB_POOL_MAX=3` porque o Cloud SQL `db-f1-micro` aceita cerca de 25 conexoes.

## Contas de servico e papeis

| Conta | Papeis |
|---|---|
| `delivery-gateway` | `roles/run.invoker` nos tres microsservicos; `secretAccessor` em `delivery-jwt-segredo`; `roles/cloudtrace.agent` |
| `delivery-servicos` (Usuarios, Catalogo, Pedidos, migrador) | `roles/cloudsql.client`; `secretAccessor` em `delivery-db-senha` e `delivery-demo-senha`; `roles/cloudtrace.agent`; `roles/run.invoker` no Catalogo (para o Pedidos) |
| `delivery-frontend` | nenhum |

## Ordem do deploy

1. Ativar as APIs: Cloud Run, Artifact Registry, Secret Manager, Cloud Trace e Cloud SQL Admin.
2. Criar o repositorio no Artifact Registry e publicar as seis imagens (`docker/*.Dockerfile` e `frontend/Dockerfile`).
3. Criar os segredos e as contas de servico, com os papeis da tabela.
4. Ligar o Cloud SQL e executar o job do migrador.
5. Implantar Catalogo, Usuarios e Pedidos (privados), depois o Gateway e o frontend (publicos).
6. Conferir: `python scripts/testar_gateway.py --url https://<gateway>.run.app` e `scripts/testar_resiliencia.py` com a injecao de falha pelo painel (`FALHA_PERCENTUAL`).
7. Excluir as VMs do Trabalho 2 e os IPs estaticos.
