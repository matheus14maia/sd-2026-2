# 4. Passo a passo: rodar o servidor numa VM do GCP

Este e o roteiro completo, do zero ate o cliente local fazendo pedido para a VM.
Reserve ~20 minutos na primeira vez. Faca isso **antes** do dia da apresentacao.

Ao final:

- o **servidor** (Microsservico B) roda em um container na VM do GCP;
- o **cliente** (Microsservico A) roda no seu notebook e conecta no IP externo da VM;
- a porta `50051/TCP` esta liberada por uma regra de firewall da VPC.

---

## Etapa 0 - Pre-requisitos

- Conta no Google Cloud com faturamento ativo (o credito gratuito cobre uma `e2-micro`).
- Projeto criado no GCP. Anote o **ID do projeto** (nao o nome).
- A **Compute Engine API** habilitada: Console > APIs e servicos > Ativar APIs >
  "Compute Engine API" > **Ativar**.
- Opcional, mas recomendado: `gcloud` instalado na sua maquina
  (<https://cloud.google.com/sdk/docs/install>), autenticado com:

```bash
gcloud auth login
gcloud config set project SEU_PROJETO_ID
```

---

## Etapa 1 - Criar a VM

### Pelo Console

1. Menu > **Compute Engine** > **Instancias de VM** > **Criar instancia**.
2. **Nome:** `restaurante-grpc`
3. **Regiao/Zona:** `southamerica-east1` / `southamerica-east1-a` (Sao Paulo -
   menor latencia; qualquer zona funciona).
4. **Tipo de maquina:** `e2-micro` (serie E2, uso geral) - suficiente.
5. **Disco de inicializacao:** Debian GNU/Linux 12 (bookworm), 10 GB.
6. **Rede > Tags de rede:** digite `grpc-server` e pressione ENTER.
   Essa tag e o que liga a regra de firewall a esta VM. **Nao pule este passo.**
7. **Firewall:** pode deixar HTTP/HTTPS desmarcados - nao usamos porta 80/443.
8. **Criar**.

### Ou por linha de comando

```bash
gcloud compute instances create restaurante-grpc \
  --zone=southamerica-east1-a \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=10GB \
  --tags=grpc-server
```

Anote o **IP externo** que aparece na coluna da lista de instancias. Ele muda a
cada vez que a VM e parada e reiniciada (a menos que voce reserve um IP estatico).

---

## Etapa 2 - Liberar a porta no firewall da VPC

Sem esta etapa o cliente recebe `UNAVAILABLE` e nada funciona. Esta e a parte de
"configuracao de regras de firewall VPC" exigida no trabalho.

### Pelo Console

1. Menu > **Rede VPC** > **Firewall** > **Criar regra de firewall**.
2. **Nome:** `permitir-grpc-50051`
3. **Rede:** `default`
4. **Direcao do trafego:** Entrada (ingress)
5. **Acao se houver correspondencia:** Permitir
6. **Destinos:** Tags de destino especificadas > **Tags de destino:** `grpc-server`
7. **Filtro de origem:** Intervalos IPv4 > **Intervalos de IP de origem:** `0.0.0.0/0`
8. **Protocolos e portas:** Protocolos e portas especificados > marque **TCP** >
   digite `50051`
9. **Criar**.

### Ou por linha de comando

```bash
gcloud compute firewall-rules create permitir-grpc-50051 \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:50051 \
  --target-tags=grpc-server \
  --source-ranges=0.0.0.0/0 \
  --description="Libera a porta do servidor gRPC do delivery"
```

Conferir:

```bash
gcloud compute firewall-rules list --filter="name=permitir-grpc-50051"
```

> **Sobre `0.0.0.0/0`:** libera a porta para qualquer origem, que e o mais simples
> para a demonstracao em sala (onde o IP da rede da faculdade pode ser
> desconhecido). Em producao restringiria ao IP de origem. Se quiser restringir,
> descubra seu IP com `curl ifconfig.me` e use `SEU_IP/32` em `--source-ranges`.

---

## Etapa 3 - Acessar a VM

Console > Compute Engine > Instancias de VM > botao **SSH** na linha da VM
(abre um terminal no navegador, sem configurar chave).

Ou pelo terminal:

```bash
gcloud compute ssh restaurante-grpc --zone=southamerica-east1-a
```

Os comandos das etapas 4 e 5 rodam **dentro da VM**.

---

## Etapa 4 - Instalar o Docker na VM

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

---

## Etapa 5 - Subir o servidor na VM

```bash
git clone https://github.com/matheus14maia/sd-2026-2.git
cd sd-2026-2

docker compose up -d --build servidor
```

Conferir que subiu:

```bash
docker compose ps
docker compose logs -f servidor
```

Saida esperada nos logs:

```text
restaurante-servidor  |  Cantina do Maia - servidor gRPC
restaurante-servidor  |  Servidor gRPC ouvindo em 0.0.0.0:50051
restaurante-servidor  |  Aguardando pedidos... (Ctrl+C encerra)
```

Conferir que a porta esta escutando na VM:

```bash
sudo ss -lntp | grep 50051
```

`Ctrl+C` sai do `logs -f` sem parar o container (ele subiu com `-d` e
`restart: unless-stopped`, entao volta sozinho se a VM reiniciar).

Deixe esta janela SSH aberta com `docker compose logs -f servidor` durante a
apresentacao: e o "terminal do restaurante".

---

## Etapa 6 - Rodar o cliente na maquina local

Na **sua maquina** (nao na VM), com o IP externo da VM em maos:

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

> `34.123.45.67` e so um exemplo. Use o IP externo mostrado no Console do GCP.

O cardapio deve aparecer no seu terminal e cada chamada deve aparecer no log da
VM. Esse e o fluxo completo pedido no trabalho: dois microsservicos, maquinas
diferentes, comunicacao gRPC com Protobuf.

---

## Etapa 7 - Checklist antes da apresentacao

| Verificacao | Comando | Resultado esperado |
|---|---|---|
| VM ligada | Console > Instancias de VM | status "Em execucao" |
| IP externo anotado | Console > Instancias de VM | o mesmo IP usado no `--host` |
| Container no ar | `docker compose ps` (na VM) | `Up`, porta `0.0.0.0:50051->50051/tcp` |
| Porta escutando | `sudo ss -lntp` (na VM) | linha `LISTEN` em `0.0.0.0:50051` |
| Regra de firewall | `gcloud compute firewall-rules list` | `permitir-grpc-50051` com `tcp:50051` |
| Conectividade ponta a ponta | no notebook: `python -m src.cliente.cliente --host IP --itens PR01:1 --cliente Teste --sem-acompanhar` | pedido confirmado |

---

## Etapa 8 - Problemas comuns

| Sintoma | Como identificar | Acao |
|---|---|---|
| `UNAVAILABLE: failed to connect to all addresses` | o cliente nao chega no servidor | siga as 4 verificacoes abaixo, nesta ordem |
| 1. IP errado | o IP externo mudou depois de parar/iniciar a VM | pegue o IP atual no Console e refaca a chamada |
| 2. Firewall | a regra nao existe, ou a VM esta sem a tag `grpc-server` | crie a regra (Etapa 2) ou adicione a tag com `gcloud compute instances add-tags restaurante-grpc --tags=grpc-server --zone=southamerica-east1-a` |
| 3. Container parado | `docker compose ps` sem linha `Up` | `docker compose up -d servidor` e depois `docker compose logs servidor` |
| 4. Porta so no localhost | `ss -lntp` mostra `127.0.0.1:50051` | o servidor precisa escutar em `0.0.0.0` (padrao do projeto); nao sobrescreva `ENDERECO_ESCUTA` |
| `permission denied` ao usar docker | `docker ps` reclama do socket | `sudo usermod -aG docker $USER` e depois `newgrp docker` |
| `NOT_FOUND: Pedido ... nao encontrado` | o servidor reiniciou entre o pedido e o acompanhamento | os pedidos ficam em memoria; refaca o pedido |
| Build lento na VM | `e2-micro` tem pouca memoria | normal na primeira vez (~3 min); depois o cache resolve |
| `docker compose` nao encontrado | foi instalado o `docker.io` do Debian | instale o `docker-compose-plugin` como na Etapa 4 |

---

## Etapa 9 - Encerrar e nao gastar credito

Na VM:

```bash
docker compose down
exit
```

No Console do GCP: **Instancias de VM > selecionar a VM > Parar**, ou:

```bash
gcloud compute instances stop restaurante-grpc --zone=southamerica-east1-a
```

Uma VM parada nao cobra CPU, mas o disco continua sendo cobrado. Se nao for mais
usar, exclua a instancia e a regra de firewall:

```bash
gcloud compute instances delete restaurante-grpc --zone=southamerica-east1-a
gcloud compute firewall-rules delete permitir-grpc-50051
```

> Ao ligar a VM de novo, o **IP externo muda** e o `--host` do cliente precisa ser
> atualizado. Para evitar isso, reserve um IP estatico em
> Rede VPC > Enderecos IP externos.
