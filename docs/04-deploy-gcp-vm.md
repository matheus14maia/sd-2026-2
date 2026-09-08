# 4. Passo a passo: rodar o servidor numa VM do GCP

Este e o roteiro completo, do zero ate o cliente local fazendo pedido para a VM.
Reserve ~20 minutos na primeira vez. Faca isso **antes** do dia da apresentacao.

Ao final:

- o **servidor** (Microsservico B) roda em um container na VM do GCP;
- o **cliente** (Microsservico A) roda no seu notebook e conecta no IP externo da VM;
- a porta `9090/TCP` esta liberada por uma regra de firewall da VPC;
- o container sobe **sozinho** toda vez que a VM e religada, sem precisar de SSH.

> **Por que a porta 9090?** A regra de firewall do projeto (`trabalho-sd`) libera
> um conjunto fixo de portas, entre elas o range `9090-9292`. Em vez de criar uma
> regra nova, o servidor foi configurado para escutar dentro do range que ja
> existe. A porta continua configuravel: `PORTA` no servidor, `--porta` ou
> `SERVIDOR_PORTA` no cliente.

---

## Etapa 0 - Pre-requisitos

- Conta no Google Cloud com faturamento ativo.
- Projeto criado no GCP. Anote o **ID do projeto** (nao o nome).
- A **Compute Engine API** habilitada: Console > APIs e servicos > Ativar APIs >
  "Compute Engine API" > **Ativar**.
- Opcional, mas recomendado: `gcloud` instalado na sua maquina
  (<https://cloud.google.com/sdk/docs/install>), autenticado com:

```bash
gcloud auth login
gcloud config set project SEU_PROJETO_ID
```

Ao longo do documento, substitua `NOME_DA_VM` e `ZONA` pelos valores da sua
instancia (ex: `restaurante-grpc` e `southamerica-east1-a`).

---

## Etapa 1 - Criar a VM

### Pelo Console

1. Menu > **Compute Engine** > **Instancias de VM** > **Criar instancia**.
2. **Nome:** `restaurante-grpc`
3. **Regiao/Zona:** `southamerica-east1` / `southamerica-east1-a` (Sao Paulo -
   menor latencia; qualquer zona funciona).
4. **Tipo de maquina:** `e2-micro` (serie E2, uso geral) - suficiente.
5. **Disco de inicializacao:** Debian GNU/Linux 12 (bookworm), 10 GB.
6. **Rede > Tags de rede:** digite `trabalho-sd` e pressione ENTER.
   Essa tag e o que liga a regra de firewall a esta VM. **Nao pule este passo** -
   e a causa numero um de `UNAVAILABLE` mesmo com o container no ar.
7. **Criar**.

### Ou por linha de comando

```bash
gcloud compute instances create restaurante-grpc \
  --zone=southamerica-east1-a \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=10GB \
  --tags=trabalho-sd
```

---

## Etapa 2 - Conferir o firewall da VPC

Esta e a parte de "configuracao de regras de firewall VPC" exigida no trabalho.
A regra `trabalho-sd` libera `tcp:3000,5050,8000,9090-9292` para as instancias
marcadas com a tag de rede `trabalho-sd`. Como o servidor escuta na `9090`,
**nao ha regra nova a criar** - so conferir tres coisas.

### 2.1 A VM tem a tag de rede?

```bash
gcloud compute instances describe NOME_DA_VM --zone=ZONA \
  --format="yaml(name,status,tags,networkInterfaces[0].accessConfigs[0].natIP)"
```

O campo `tags.items` precisa listar `trabalho-sd`. Se faltar:

```bash
gcloud compute instances add-tags NOME_DA_VM --zone=ZONA --tags=trabalho-sd
```

Pelo Console: Compute Engine > a VM > **Editar** > Rede > Tags de rede.

### 2.2 A regra cobre a porta 9090 e aceita origem externa?

```bash
gcloud compute firewall-rules list \
  --format="table(name,direction,sourceRanges.list(),allowed[].map().firewall_rule().list(),targetTags.list())"
```

Na linha `trabalho-sd`, confira:

| Campo | Valor esperado |
|---|---|
| direction | `INGRESS` |
| allowed | inclui `tcp:9090-9292` (ou outra faixa que cubra a 9090) |
| sourceRanges | `0.0.0.0/0` |
| targetTags | `trabalho-sd` |

Pelo Console: **Rede VPC > Firewall >** clicar na regra.

> **Sobre `0.0.0.0/0`:** libera a porta para qualquer origem, que e o mais simples
> para a demonstracao em sala (onde o IP da rede da faculdade pode ser
> desconhecido). Em producao restringiria ao IP de origem. Se quiser restringir,
> descubra seu IP com `curl ifconfig.me` e use `SEU_IP/32` em `--source-ranges`.

### 2.3 Se a porta nao estivesse liberada

Para referencia (nao e necessario neste projeto), o comando que criaria uma regra
dedicada seria:

```bash
gcloud compute firewall-rules create permitir-grpc-9090 \
  --direction=INGRESS --action=ALLOW \
  --rules=tcp:9090 \
  --target-tags=trabalho-sd \
  --source-ranges=0.0.0.0/0
```

---

## Etapa 3 - Descobrir o IP externo (repetir a cada boot da VM)

O IP externo desta VM e **efemero**: muda toda vez que a instancia e parada e
religada. Pegue o IP atual **sempre** antes de rodar o cliente.

```bash
gcloud compute instances describe NOME_DA_VM --zone=ZONA \
  --format="get(networkInterfaces[0].accessConfigs[0].natIP)"
```

Pelo Console: Compute Engine > Instancias de VM > coluna **IP externo**.

> Para fixar o IP, reserve um endereco estatico em Rede VPC > Enderecos IP
> externos. Tem um custo pequeno por hora enquanto a VM esta parada, por isso o
> projeto ficou com o IP efemero.

---

## Etapa 4 - Acessar a VM

Console > Compute Engine > Instancias de VM > botao **SSH** na linha da VM
(abre um terminal no navegador, sem configurar chave).

Ou pelo terminal:

```bash
gcloud compute ssh NOME_DA_VM --zone=ZONA
```

Os comandos das etapas 5 e 6 rodam **dentro da VM**.

---

## Etapa 5 - Instalar o Docker na VM (uma vez so)

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# permite usar docker sem sudo
sudo usermod -aG docker $USER
newgrp docker

docker --version
docker compose version
```

Confirme que o Docker sobe junto com a VM - e o pre-requisito para o container
voltar sozinho depois de religar a instancia:

```bash
sudo systemctl is-enabled docker    # deve responder: enabled
```

Se responder `disabled`: `sudo systemctl enable --now docker`.

---

## Etapa 6 - Levar o codigo e subir o servidor (uma vez so)

O repositorio e publico, entao o `git clone` nao pede credencial:

```bash
git clone https://github.com/matheus14maia/sd-2026-2.git
cd sd-2026-2

docker compose up -d --build servidor
```

Conferir que subiu:

```bash
docker compose ps           # Up, 0.0.0.0:9090->9090/tcp
docker compose logs servidor
sudo ss -lntp | grep 9090   # LISTEN em 0.0.0.0:9090
```

Saida esperada nos logs:

```text
restaurante-servidor  |  Hell's Kitchen - servidor gRPC
restaurante-servidor  |  Servidor gRPC ouvindo em 0.0.0.0:9090
restaurante-servidor  |  Aguardando pedidos... (Ctrl+C encerra)
```

O build leva ~3 minutos na primeira vez em uma `e2-micro` (1 GB de RAM). Se o
`pip install` for encerrado por falta de memoria, adicione swap e repita:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
```

### Atualizar o codigo depois

Sempre que a `main` mudar:

```bash
cd ~/sd-2026-2
git pull
docker compose up -d --build servidor   # recria o container com o codigo novo
```

---

## Etapa 7 - Rodar o cliente na maquina local

Na **sua maquina** (nao na VM), com o IP externo atual em maos (Etapa 3):

```bash
# com Docker
SERVIDOR_HOST=34.123.45.67 docker compose run --rm cliente

# ou com Python direto
python -m src.cliente.cliente --host 34.123.45.67
```

No Windows (PowerShell):

```powershell
python -m src.cliente.cliente --host 34.123.45.67
```

> `34.123.45.67` e so um exemplo. Use o IP externo obtido na Etapa 3.

O cardapio deve aparecer no seu terminal e cada chamada deve aparecer no log da
VM. Esse e o fluxo completo pedido no trabalho: dois microsservicos, maquinas
diferentes, comunicacao gRPC com Protobuf.

Deixe uma janela SSH aberta com `docker compose logs -f servidor` durante a
apresentacao: e o "terminal do restaurante". `Ctrl+C` sai do `logs -f` sem parar
o container.

---

## Etapa 8 - Ciclo do dia a dia (parar e religar a VM)

O servico `servidor` esta declarado com `restart: always` no
`docker-compose.yml`. Combinado com o Docker habilitado no boot (Etapa 5), o
container volta sozinho toda vez que a VM e religada - **sem SSH e sem rodar
nenhum comando Docker**.

| Quando | O que fazer |
|---|---|
| Terminar de usar | Console > selecionar a VM > **Parar**. Nada mais. |
| Voltar a usar | Console > **Iniciar**. O container sobe sozinho. |
| Antes de testar | Pegar o IP externo atual (Etapa 3) - ele mudou |
| Conferir que voltou | SSH + `docker compose ps` (opcional), ou so rodar o cliente |
| So se o codigo mudou | SSH + `git pull` + `docker compose up -d --build servidor` |

Por linha de comando:

```bash
gcloud compute instances stop NOME_DA_VM --zone=ZONA
gcloud compute instances start NOME_DA_VM --zone=ZONA
```

> **Nao use `docker compose down` no ciclo normal.** Esse comando **remove** o
> container, e um container removido nao volta sozinho no proximo boot - seria
> preciso rodar `docker compose up -d servidor` de novo por SSH. Para desligar,
> basta parar a VM.

Uma VM parada nao cobra CPU, mas o disco continua sendo cobrado.

---

## Etapa 9 - Checklist antes da apresentacao

| Verificacao | Comando | Resultado esperado |
|---|---|---|
| VM ligada | Console > Instancias de VM | status "Em execucao" |
| Tag de rede na VM | `gcloud compute instances describe NOME_DA_VM --zone=ZONA --format="get(tags.items)"` | inclui `trabalho-sd` |
| Regra de firewall | `gcloud compute firewall-rules list` | `trabalho-sd` cobrindo `tcp:9090-9292` |
| IP externo atual | `gcloud compute instances describe NOME_DA_VM --zone=ZONA --format="get(networkInterfaces[0].accessConfigs[0].natIP)"` | o mesmo IP usado no `--host` |
| Container no ar | `docker compose ps` (na VM) | `Up`, porta `0.0.0.0:9090->9090/tcp` |
| Porta escutando | `sudo ss -lntp` (na VM) | linha `LISTEN` em `0.0.0.0:9090` |
| Conectividade ponta a ponta | no notebook: `python -m src.cliente.cliente --host IP --itens PR01:1 --cliente Teste --sem-acompanhar` | pedido confirmado |

---

## Etapa 10 - Problemas comuns

| Sintoma | Como identificar | Acao |
|---|---|---|
| `UNAVAILABLE: failed to connect to all addresses` | o cliente nao chega no servidor | siga as verificacoes abaixo, nesta ordem |
| 1. IP errado | o IP externo mudou depois de parar/iniciar a VM | pegue o IP atual (Etapa 3) e refaca a chamada |
| 2. VM sem a tag | o `describe` nao lista `trabalho-sd` em `tags.items` | `gcloud compute instances add-tags NOME_DA_VM --zone=ZONA --tags=trabalho-sd` |
| 3. Porta fora do range liberado | o servidor escuta numa porta que a regra nao cobre | use uma porta dentro de `9090-9292` (padrao do projeto: `9090`) ou crie a regra da secao 2.3 |
| 4. Container parado | `docker compose ps` sem linha `Up` | `docker compose up -d servidor` e depois `docker compose logs servidor` |
| 5. Porta so no localhost | `ss -lntp` mostra `127.0.0.1:9090` | o servidor precisa escutar em `0.0.0.0` (padrao do projeto); nao sobrescreva `ENDERECO_ESCUTA` |
| Container sumiu depois de religar a VM | `docker ps -a` sem o `restaurante-servidor` | foi rodado `docker compose down` antes de parar a VM; suba com `docker compose up -d servidor` e nao use `down` no ciclo normal (Etapa 8) |
| Container existe mas nao volta no boot | `sudo systemctl is-enabled docker` responde `disabled` | `sudo systemctl enable --now docker` |
| `permission denied` ao usar docker | `docker ps` reclama do socket | `sudo usermod -aG docker $USER` e depois `newgrp docker` |
| `NOT_FOUND: Pedido ... nao encontrado` | o servidor reiniciou entre o pedido e o acompanhamento | os pedidos ficam em memoria; refaca o pedido |
| Build morto por falta de memoria | `Killed` durante o `pip install` na `e2-micro` | adicione swap (Etapa 6) e repita o build |
| `docker compose` nao encontrado | foi instalado o `docker.io` do Debian | instale o `docker-compose-plugin` como na Etapa 5 |

---

## Etapa 11 - Encerrar de vez

Apenas quando o trabalho estiver entregue e a VM nao for mais usada:

```bash
gcloud compute instances delete NOME_DA_VM --zone=ZONA
```

A regra de firewall `trabalho-sd` nao gera custo e pode ser mantida, ou removida
com `gcloud compute firewall-rules delete trabalho-sd`.
