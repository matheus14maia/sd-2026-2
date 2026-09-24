# 4. Deploy no GCP: VM + Cloud SQL

Infraestrutura do projeto `sistemas-distribuidos-505422`, regiao `us-central1`:

| Recurso | Nome | Detalhe |
|---|---|---|
| VM (Compute Engine) | `servidor-delivery` | zona `us-central1-a`, `e2-small`, Debian, tags `http-server`, `https-server`, `portas-trabalho-sd` |
| IP externo da VM | `ip-servidor-delivery` | **estatico** `34.60.57.59` (nao muda ao religar) |
| Banco (Cloud SQL) | `delivery-postgres` | PostgreSQL 16, edicao Enterprise, `db-f1-micro`, zona unica, IP publico `34.63.128.138`, banco `delivery`, usuario `postgres` |
| Rede autorizada no Cloud SQL | - | `34.60.57.59/32` (so a VM conecta no banco) |
| Firewall VPC | `trabalho-sd` | INGRESS `0.0.0.0/0`, `tcp:3000,5050,8000,9090-9292`, alvo `portas-trabalho-sd` |

Na VM rodam os containers `gateway` (porta 8000 publicada), `pedidos`,
`catalogo` e o one-shot `migrador`. O banco fica fora da VM, no Cloud SQL.

Os comandos `gcloud` abaixo rodam no notebook, com `gcloud auth login` feito na
conta do projeto. Se o projeto padrao do `gcloud` for outro, acrescente
`--project sistemas-distribuidos-505422` a cada comando (como abaixo) ou rode
`gcloud config set project sistemas-distribuidos-505422`.

---

## Etapa 1 - VM e IP estatico

A VM ja existe. Para criar do zero, veja a secao "Criar a VM do zero" no fim.

O IP externo foi promovido de efemero para estatico, porque o Cloud SQL so
aceita conexao das **redes autorizadas**. Com IP efemero, cada religada da VM
trocaria o IP e o banco passaria a recusar a conexao.

```bash
gcloud compute addresses create ip-servidor-delivery \
  --addresses=34.60.57.59 --region=us-central1 --project sistemas-distribuidos-505422
```

Um IP estatico reservado cobra um valor pequeno por hora tambem com a VM parada.

## Etapa 2 - Firewall

A regra `trabalho-sd` ja libera a `8000`, que e a porta do Gateway. Conferir:

```bash
gcloud compute firewall-rules describe trabalho-sd --project sistemas-distribuidos-505422 \
  --format="yaml(allowed,sourceRanges,targetTags)"
gcloud compute instances describe servidor-delivery --zone us-central1-a \
  --project sistemas-distribuidos-505422 --format="get(tags.items)"
```

A VM precisa ter a tag **alvo** da regra (`portas-trabalho-sd`), nao o nome da
regra. Ver `markdown/TROUBLESHOOTING.md` (2026-09-08).

As portas 9090 e 9091 dos microsservicos nao sao publicadas pelo compose: mesmo
com o firewall liberando o range, nada escuta nelas do lado de fora.

## Etapa 3 - Cloud SQL (PostgreSQL)

Pelo Console: **Cloud SQL > Criar instancia > PostgreSQL**. Escolha:

- edicao **Enterprise**;
- regiao **us-central1** (a mesma da VM);
- **zona unica**;
- em **Conexoes > Rede**, **IP publico** marcado e a rede autorizada `34.60.57.59/32`.

Pela linha de comando, que foi como a instancia foi criada:

```bash
gcloud services enable sqladmin.googleapis.com --project sistemas-distribuidos-505422

gcloud sql instances create delivery-postgres \
  --database-version=POSTGRES_16 --edition=ENTERPRISE --tier=db-f1-micro \
  --region=us-central1 --availability-type=zonal \
  --storage-size=10 --storage-type=HDD --no-backup \
  --authorized-networks=34.60.57.59/32 \
  --project sistemas-distribuidos-505422

gcloud sql databases create delivery --instance=delivery-postgres --project sistemas-distribuidos-505422
gcloud sql users set-password postgres --instance=delivery-postgres \
  --password='SENHA_DO_BANCO' --project sistemas-distribuidos-505422
```

- `db-f1-micro` (compartilhada, 0,6 GB) e a menor maquina da edicao Enterprise
  e basta para o trabalho.
- A senha nunca vai para o repositorio. Ela so fica no `.env` da VM (Etapa 5).

IP publico do banco:

```bash
gcloud sql instances describe delivery-postgres --project sistemas-distribuidos-505422 \
  --format="value(ipAddresses[0].ipAddress)"
```

## Etapa 4 - Acessar a VM

```bash
gcloud compute ssh servidor-delivery --zone us-central1-a --project sistemas-distribuidos-505422
```

Ou pelo botao **SSH** no Console. Docker e Git ja estao instalados. A instalacao
do zero esta na secao "Criar a VM do zero".

## Etapa 5 - Configurar o banco e subir os containers

Dentro da VM, na pasta do repositorio:

```bash
cd ~/sd-2026-2
git checkout main && git pull

cat > .env <<'EOF'
DB_HOST=34.63.128.138
DB_PORT=5432
DB_NAME=delivery
DB_USER=postgres
DB_PASSWORD=SENHA_DO_BANCO
DB_SSLMODE=require
EOF
chmod 600 .env

docker compose up -d --build --remove-orphans
```

- **Sem `--profile banco-local`**, o container `postgres` nao sobe e os
  servicos usam o Cloud SQL indicado no `.env`.
- O `--remove-orphans` remove containers de servicos que sairam do compose,
  como o `restaurante-servidor` do trabalho anterior.
- O `.env` fica na VM e esta no `.gitignore`. O `git pull` nao mexe nele.

Conferir:

```bash
docker compose ps
docker compose logs migrador catalogo pedidos
```

Saida esperada:

```text
delivery-migrador  | Migrando banco em 34.63.128.138:5432/delivery (sslmode=require)
delivery-migrador  |   aplicando db/schema.sql
delivery-migrador  |   aplicando db/seed.sql
delivery-migrador  | Banco pronto: 13 itens no cardapio, 0 pedidos.
delivery-catalogo  |  Servidor gRPC ouvindo em 0.0.0.0:9091
delivery-pedidos   |  Servidor gRPC ouvindo em 0.0.0.0:9090
```

e `delivery-gateway` com `0.0.0.0:8000->8000/tcp`.

### Atualizar o codigo depois

```bash
cd ~/sd-2026-2
git pull
docker compose up -d --build --remove-orphans
```

## Etapa 6 - Testar a partir do notebook

```bash
python scripts/testar_gateway.py --url http://34.60.57.59:8000
```

- Deve terminar com `Todos os cenarios passaram.`
- Swagger: `http://34.60.57.59:8000/docs`.

## Etapa 7 - Ver os dados no Cloud SQL Studio

Console > **Cloud SQL** > `delivery-postgres` > **Cloud SQL Studio**. Faca login
com banco `delivery`, usuario `postgres` e a senha do banco. Depois consulte:

```sql
SELECT id, cliente, status, total, criado_em, atualizado_em FROM pedidos ORDER BY criado_em DESC;
SELECT * FROM itens_pedido;
SELECT codigo, nome, preco, disponivel, atualizado_em FROM itens_cardapio ORDER BY codigo;
```

Escolha o banco **`delivery`**, nao o `postgres` padrao. As tabelas do projeto
estao no `delivery`.

## Etapa 8 - Ciclo liga/desliga (para economizar credito)

Os containers tem `restart: always` e o Docker sobe com a VM. Ao religar,
tudo volta sozinho, sem SSH.

Ligar, **banco primeiro**:

```bash
gcloud sql instances patch delivery-postgres --activation-policy=ALWAYS --project sistemas-distribuidos-505422
gcloud compute instances start servidor-delivery --zone us-central1-a --project sistemas-distribuidos-505422
```

Desligar:

```bash
gcloud compute instances stop servidor-delivery --zone us-central1-a --project sistemas-distribuidos-505422
gcloud sql instances patch delivery-postgres --activation-policy=NEVER --project sistemas-distribuidos-505422
```

- **Ordem ao ligar.** Se a VM subir antes do banco, o migrador e os
  microsservicos tentam conectar por cerca de 1 minuto (`Banco indisponivel
  (tentativa N/30)`) e o `restart` do Docker tenta de novo depois. Ligar o banco
  primeiro evita a espera.
- **Nao use `docker compose down`** no ciclo normal: ele remove os containers,
  e container removido nao volta no boot.

## Etapa 9 - Checklist antes da apresentacao

| Verificacao | Comando | Esperado |
|---|---|---|
| Banco ligado | `gcloud sql instances describe delivery-postgres --project sistemas-distribuidos-505422 --format="value(state)"` | `RUNNABLE` |
| VM ligada | `gcloud compute instances describe servidor-delivery --zone us-central1-a --project sistemas-distribuidos-505422 --format="value(status)"` | `RUNNING` |
| Gateway no ar | `curl http://34.60.57.59:8000/saude` | `{"status":"ok"}` |
| Fluxo completo | `python scripts/testar_gateway.py --url http://34.60.57.59:8000 --resumido` | `Todos os cenarios passaram.` |

## Problemas comuns

| Sintoma | Causa provavel | Acao |
|---|---|---|
| `Banco indisponivel (tentativa N/30): ... timeout` no log | Cloud SQL parado, ou IP da VM fora das redes autorizadas | ligar a instancia (Etapa 8); conferir `settings.ipConfiguration.authorizedNetworks` |
| `password authentication failed for user "postgres"` | senha do `.env` diferente da do Cloud SQL | corrigir o `.env` e rodar `docker compose up -d` |
| `database "delivery" does not exist` | banco nao criado na instancia | `gcloud sql databases create delivery --instance=delivery-postgres ...` |
| `curl` na 8000 da timeout | firewall/tag (Etapa 2) ou VM parada | conferir a tag `portas-trabalho-sd` |
| `503 Catalogo indisponivel` | container `catalogo` parado | `docker compose ps` e `docker compose up -d` |
| containers sumiram apos religar | foi usado `docker compose down` | `docker compose up -d` |

## Criar a VM do zero (referencia)

```bash
gcloud compute instances create servidor-delivery \
  --zone=us-central1-a --machine-type=e2-small \
  --image-family=debian-12 --image-project=debian-cloud --boot-disk-size=10GB \
  --tags=portas-trabalho-sd,http-server,https-server \
  --project sistemas-distribuidos-505422
```

Instalar Docker e Git na VM:

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER && newgrp docker
sudo systemctl is-enabled docker     # enabled
git clone https://github.com/matheus14maia/sd-2026-2.git
```

Depois siga a partir da Etapa 5.

## Encerrar de vez (depois da entrega)

```bash
gcloud sql instances delete delivery-postgres --project sistemas-distribuidos-505422
gcloud compute instances delete servidor-delivery --zone us-central1-a --project sistemas-distribuidos-505422
gcloud compute addresses delete ip-servidor-delivery --region us-central1 --project sistemas-distribuidos-505422
```
