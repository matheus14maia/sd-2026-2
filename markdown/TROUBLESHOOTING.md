# Troubleshooting

> Problemas encontrados e resolvidos neste projeto. Registrar imediatamente apos
> resolver qualquer issue. Formato: titulo, sintoma (mensagem exata), causa,
> solucao e arquivos afetados. Mais recente no topo.

---

## Template de entrada

### Nome do problema

**Sintoma:** o que acontece de errado (mensagem de erro exata, comportamento observado).

**Causa:** por que acontece.

**Solucao:** o que foi feito para resolver.

**Arquivos:** arquivos afetados pela correcao.

---

## 2026-09-08

### DEADLINE_EXCEEDED ao conectar na VM (e nao UNAVAILABLE)

**Sintoma:**
```text
Conectando ao restaurante em 34.9.87.180:9090 ...

ERRO gRPC: DEADLINE_EXCEEDED
Detalhe: Deadline Exceeded
```

**Causa:** os dois erros de rede do gRPC apontam para lugares diferentes e a
distincao economiza tempo de diagnostico:

| Erro | O que aconteceu no TCP | Onde olhar |
|---|---|---|
| `UNAVAILABLE` (`Connection refused`) | o pacote **chegou** na maquina e o SO respondeu com RST porque ninguem escuta naquela porta | container parado, porta nao publicada, porta errada |
| `DEADLINE_EXCEEDED` | o pacote saiu e **nada voltou** ate o timeout | firewall descartando o trafego (regra nao cobre a porta, VM sem a tag de rede, VM desligada) |

Um firewall bem configurado descarta o pacote em silencio em vez de recusar a
conexao - por isso o sintoma e o timeout, nao a recusa.

**Solucao:** o cliente passou a tratar `DEADLINE_EXCEEDED` com o mesmo checklist
de `UNAVAILABLE`, precedido de uma linha explicando que o pacote esta sendo
descartado e mandando comecar pelos itens de firewall (regra e tag de rede).

**Arquivos:** `src/cliente/cliente.py`.

### Servidor gRPC inalcancavel na VM: a porta 50051 nao estava liberada

**Sintoma:** `UNAVAILABLE: failed to connect to all addresses` no cliente, com o
container `Up` na VM e `ss -lntp` mostrando `LISTEN` em `0.0.0.0:50051`.

**Causa:** a regra de firewall da VPC do projeto (tag de rede `trabalho-sd`)
libera `tcp:3000,5050,8000,9090-9292`. A `50051`, porta convencional do gRPC e
padrao do projeto ate entao, nao esta em nenhuma dessas faixas. Tudo dentro da VM
funcionava; o pacote morria antes de chegar nela.

**Solucao:** mover o servidor para a porta `9090`, que ja esta dentro do range
liberado, em vez de criar uma regra nova. Vale como padrao geral: conferir o que
o firewall libera **antes** de escolher a porta do servico.

**Arquivos:** `docker-compose.yml`, `Dockerfile`, `src/servidor/servidor.py`,
`src/cliente/cliente.py`, `README.md`, `docs/01` a `docs/05`.

### Container do servidor nao volta depois de religar a VM

**Sintoma:** VM parada pelo Console e religada; `docker compose ps` vazio e
`docker ps -a` sem o `restaurante-servidor`. O cliente recebe `UNAVAILABLE`.

**Causa:** o `docker compose down` que a Etapa 9 antiga de `docs/04` mandava
rodar antes de desligar a VM **remove** o container. Nenhuma politica de restart
ressuscita um container removido - `unless-stopped` e `always` so agem sobre
containers que ainda existem.

**Solucao:** `restart: always` no servico `servidor` (em vez de
`unless-stopped`, que tambem nao religa apos um `docker compose stop` manual) e
`docker compose down` retirado do ciclo normal em `docs/04`. Pre-requisito do
autostart: `sudo systemctl is-enabled docker` responder `enabled`.

**Arquivos:** `docker-compose.yml`, `docs/04-deploy-gcp-vm.md`.

---

## 2026-08-31

### Stubs gerados nao importam dentro do pacote

**Sintoma:** `ModuleNotFoundError: No module named 'restaurante_pb2'` ao importar
`src.gerado.restaurante_pb2_grpc`.

**Causa:** o `grpc_tools.protoc` gera `import restaurante_pb2 as restaurante__pb2`
(import absoluto), o que so funciona se o diretorio dos stubs estiver no
`sys.path`. Aqui os stubs ficam dentro do pacote `src.gerado`.

**Solucao:** `scripts/gerar_stubs.py` reescreve a linha para
`from . import restaurante_pb2 as restaurante__pb2` logo apos gerar. A alternativa
seria adicionar `src/gerado` ao `sys.path`, o que polui o import do projeto.

**Arquivos:** `scripts/gerar_stubs.py`.

### Cliente nao conecta na VM mesmo com o servidor rodando

**Sintoma:**
```text
ERRO gRPC: UNAVAILABLE
Detalhe: failed to connect to all addresses; last error: UNAVAILABLE: ipv4:...:50051: ConnectEx: Connection refused
```

**Causa:** cinco causas diferentes produzem exatamente a mesma mensagem: servidor
parado, IP externo desatualizado (muda quando a VM reinicia), porta do servidor
fora do range que a regra de firewall VPC libera, VM sem a tag de rede exigida
pela regra, ou servidor escutando so em `127.0.0.1`.

**Solucao:** o servidor escuta em `0.0.0.0` por padrao (`ENDERECO_ESCUTA`) e o
cliente imprime um checklist com as 5 causas na ordem de verificacao ao receber
`UNAVAILABLE`. O diagnostico detalhado esta na Etapa 10 de
`docs/04-deploy-gcp-vm.md`.

**Arquivos:** `src/cliente/cliente.py`, `src/servidor/servidor.py`, `docs/04-deploy-gcp-vm.md`.

### Acompanhamento devolve NOT_FOUND para um pedido que existia

**Sintoma:** `NOT_FOUND: Pedido '...' nao encontrado.` ao chamar
`AcompanharPedido` com um id que tinha acabado de funcionar.

**Causa:** os pedidos ficam em memoria (`RepositorioPedidos`). Reiniciar o
container ou o processo apaga tudo.

**Solucao:** comportamento aceito e documentado - o escopo do trabalho e a
comunicacao entre servicos, nao persistencia. Se o servidor reiniciar durante a
demonstracao, refaca o pedido antes de acompanhar.

**Arquivos:** `src/servidor/repositorio.py`, `docs/01-visao-geral-do-sistema.md`.
