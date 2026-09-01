# Delivery via gRPC - Sistemas Distribuidos 2026/2

Comunicacao interna de backend entre dois microsservicos usando **gRPC** e
**Protocol Buffers**, com o servidor rodando em uma VM do **Google Cloud
Platform** e o cliente na maquina local.

**Tema:** delivery de restaurante. O servidor e a *Cantina do Maia*, que publica
um cardapio variado e processa pedidos; o cliente monta o pedido escolhendo os
itens e a quantidade de cada um.

```text
  MAQUINA LOCAL                                VM DO GCP (50051/TCP)
+---------------------+                     +--------------------------+
| Microsservico A     |  gRPC / HTTP2       | Microsservico B          |
| cliente.py          | <-----------------> | servidor.py              |
| monta o pedido      |  Protobuf (binario) | valida, precifica, serve |
+---------------------+                     +--------------------------+
```

## Stack

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 |
| Comunicacao | gRPC sobre HTTP/2 |
| Serializacao | Protocol Buffers (proto3) |
| Execucao | Docker + Docker Compose |
| Infraestrutura | Google Compute Engine (Debian 12) + regra de firewall VPC |

## Os tres RPCs

| RPC | Tipo | O que faz |
|---|---|---|
| `ObterCardapio` | unario | devolve os itens, precos e disponibilidade |
| `CriarPedido` | unario | valida os itens, calcula o total e registra o pedido |
| `AcompanharPedido` | server streaming | envia `RECEBIDO -> EM_PREPARO -> PRONTO -> SAIU_PARA_ENTREGA -> ENTREGUE` |

## Comecando rapido

```bash
# terminal 1 - servidor
docker compose up --build servidor

# terminal 2 - cliente
docker compose run --rm cliente
```

Apontando o cliente para a VM do GCP:

```bash
python -m src.cliente.cliente --host SEU_IP_EXTERNO
```

Sem Docker:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/gerar_stubs.py
python -m src.servidor.servidor     # terminal 1
python -m src.cliente.cliente       # terminal 2
```

## Documentacao

| Documento | Conteudo |
|---|---|
| [docs/01-visao-geral-do-sistema.md](docs/01-visao-geral-do-sistema.md) | o que o sistema faz, o fluxo e como ele reage a cada situacao |
| [docs/02-contrato-grpc.md](docs/02-contrato-grpc.md) | o `.proto` explicado campo a campo e a geracao dos stubs |
| [docs/03-execucao-local.md](docs/03-execucao-local.md) | rodar nos dois terminais, com e sem Docker, e as saidas esperadas |
| [docs/04-deploy-gcp-vm.md](docs/04-deploy-gcp-vm.md) | passo a passo completo na VM do GCP, incluindo o firewall da VPC |
| [docs/05-roteiro-apresentacao.md](docs/05-roteiro-apresentacao.md) | roteiro cronometrado da demonstracao |

O manual do projeto, o prontuario de problemas e o changelog ficam em
[markdown/](markdown/).

## Estrutura

```text
proto/restaurante.proto      contrato compartilhado (fonte da verdade)
scripts/gerar_stubs.py       gera os stubs Python a partir do .proto
src/servidor/                Microsservico B (cardapio, servico, repositorio)
src/cliente/cliente.py       Microsservico A (terminal do pedido)
src/gerado/                  stubs gerados no build (nao versionados)
docker-compose.yml           servicos "servidor" e "cliente"
```

> Os arquivos em `src/gerado/` sao artefato de build: regerados por
> `scripts/gerar_stubs.py` e no `docker build`. Nunca edite a mao.
