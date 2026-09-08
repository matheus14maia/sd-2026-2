# Changelog

> Registro das alteracoes do projeto. Atualizar apos cada entrega.

---

## Regra de uso

- Apos **cada** alteracao (correcao, funcionalidade, ajuste, refatoracao),
  registrar imediatamente.
- Formato: data (YYYY-MM-DD) como secao, itens com horario (HH:MM) + titulo + detalhe.
- Ordem cronologica decrescente (mais recente no topo).
- Cada item informa: modulo afetado, o que mudou, por que mudou e quais arquivos.

---

## 2026-09-08

| Horario | Task | Detalhe |
|---------|------|---------|
| 19:23 | Porta padrao 50051 -> 9090 | A regra de firewall da VPC do projeto (tag de rede `trabalho-sd`) libera `tcp:3000,5050,8000,9090-9292`, e a `50051` nao esta em nenhuma dessas faixas: o cliente nunca alcancaria a VM. Em vez de criar regra nova, o servidor passou a escutar na `9090`, dentro do range ja liberado. Arquivos: `docker-compose.yml`, `Dockerfile`, `src/servidor/servidor.py`, `src/cliente/cliente.py`, `README.md`, `docs/01`, `docs/02`, `docs/03`, `docs/05`. |
| 19:23 | Autostart do servidor na VM | `restart: unless-stopped` -> `restart: always` no servico `servidor`, para o container voltar sozinho a cada boot da VM (que sera parada e religada com frequencia ate a apresentacao, para nao gastar credito). `unless-stopped` nao religa apos um `docker compose stop` manual. Arquivo: `docker-compose.yml`. |
| 19:23 | Reescrita do passo a passo do GCP | `docs/04-deploy-gcp-vm.md` alinhado a infraestrutura real: tag de rede `trabalho-sd` no lugar de `grpc-server`, firewall como etapa de **conferencia** (a regra ja cobre a 9090) em vez de criacao, etapa dedicada a descobrir o IP externo efemero a cada boot, fluxo de `git pull` + rebuild na VM, secao de ciclo do dia a dia e nota sobre swap na `e2-micro`. O `docker compose down` saiu do fluxo de desligar a VM: ele remove o container e quebra o autostart. |
| 19:39 | Restaurante renomeado para Hell's Kitchen | `NOME_RESTAURANTE` e a unica fonte do nome, entao a troca foi em um ponto so; o resto foi concordancia ("recebido **pelo** Hell's Kitchen") e as saidas de exemplo nas docs. Arquivos: `src/servidor/cardapio.py`, `src/servidor/servico.py`, `README.md`, `docs/01`, `docs/03`, `docs/04`. |
| 19:39 | `DEADLINE_EXCEEDED` tratado como erro de rede | O checklist de diagnostico so disparava em `UNAVAILABLE`, mas conexao bloqueada por firewall aparece como `DEADLINE_EXCEEDED`: o pacote e descartado em silencio e nada volta ate o timeout, em vez de a conexao ser recusada. O cliente passou a mostrar o mesmo checklist nos dois casos, com uma linha extra no timeout mandando comecar pelos itens de firewall. Arquivo: `src/cliente/cliente.py`. |
| 19:26 | Fuso horario do container | `TZ: "America/Sao_Paulo"` no servico `servidor`. Sem isso o container roda em UTC e os horarios do log da VM e do stream de acompanhamento saem 3h a frente do relogio do notebook - na apresentacao as duas telas ficam lado a lado e a diferenca confunde. Arquivo: `docker-compose.yml`. |
| 19:23 | Checklist de `UNAVAILABLE` com 5 causas | O cliente passou a listar tambem "a VM tem a tag de rede exigida pela regra de firewall?" - regra correta com a VM sem a tag da exatamente o mesmo erro de servidor desligado. Arquivo: `src/cliente/cliente.py`. |

---

## 2026-08-31

| Horario | Task | Detalhe |
|---------|------|---------|
| 22:40 | Documentacao completa | Escritos `README.md` e `docs/01` a `docs/05`: visao geral e tabela de reacao do sistema, contrato explicado campo a campo, execucao local, passo a passo do GCP (VM + firewall VPC + Docker) e roteiro de 5 minutos da apresentacao. |
| 22:30 | Empacotamento em Docker | `Dockerfile` (python:3.12-slim, gera os stubs no build) e `docker-compose.yml` com os servicos `servidor` (publica 50051) e `cliente` (profile, tty). Validado: cliente local -> container e cliente em container -> servidor. |
| 22:20 | Cliente gRPC | `src/cliente/cliente.py`: lista o cardapio por categoria, monta o pedido item a item com quantidade, envia `CriarPedido`, consome o stream de acompanhamento e trata `grpc.RpcError` com checklist para `UNAVAILABLE`. Modo `--itens CODIGO:QTD` para ensaio. |
| 22:10 | Servidor gRPC | `src/servidor/`: `cardapio.py` (13 itens em 4 categorias, um indisponivel de proposito), `repositorio.py` (memoria + `threading.Lock`), `servico.py` (3 RPCs e validacoes por status code), `servidor.py` (ThreadPool, reflection, `PORTA` por env, shutdown limpo). |
| 22:00 | Contrato Protobuf | `proto/restaurante.proto` com `RestauranteService`: `ObterCardapio` e `CriarPedido` unarios e `AcompanharPedido` em server streaming; `CriarPedidoRequest` com `repeated ItemPedido` para varios itens e quantidades. `scripts/gerar_stubs.py` gera os stubs e corrige o import relativo. |
