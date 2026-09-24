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

## 2026-09-24

### 503 "Deadline Exceeded" em vez de "Catalogo indisponivel"

**Sintoma:** com o container `catalogo` parado, o `POST /pedidos` respondia:

```text
{"mensagem":"Deadline Exceeded","codigo_grpc":"DEADLINE_EXCEEDED"} -> 503
```

A mensagem nao dizia qual servico estava fora.

**Causa:** o Gateway chama o Pedidos com prazo de 5 s, e o Pedidos chamava o
Catalogo tambem com 5 s. Os dois prazos venciam juntos e o Gateway desistia
antes de o Pedidos conseguir devolver o `UNAVAILABLE` com a mensagem propria.

**Solucao:** prazo menor a cada salto. `CATALOGO_TIMEOUT` passou a 3 s, e agora
a resposta e `503 {"mensagem":"Catalogo indisponivel no momento (UNAVAILABLE). Tente novamente."}`.

**Arquivos:** `src/pedidos/cliente_catalogo.py`.

### `to_upper` do Pydantic nao evita erro de `pattern`

**Sintoma:** `{"codigo":"be02","quantidade":1}` respondia 400 com
`"itens.0.codigo": "codigo invalido: use 2 letras e 2 digitos (ex.: PR01)"`.
O campo estava declarado com `StringConstraints(to_upper=True, pattern=r"^[A-Z]{2}[0-9]{2}$")`.

**Causa:** o Pydantic confere o `pattern` sobre o valor recebido, antes de
aplicar o `to_upper`.

**Solucao:** regex que aceita as duas caixas (`^[A-Za-z]{2}[0-9]{2}$`); o
`to_upper` continua normalizando o valor que segue para o gRPC.

**Arquivos:** `src/gateway/esquemas.py`.

### `gcloud compute ssh` nao enxerga o repositorio da VM

**Sintoma:** pelo `gcloud compute ssh` a partir do notebook (Windows):

```text
bash: line 1: cd: /home/maia_matheus/sd-2026-2: Permission denied
```

Antes disso, a primeira conexao parou no prompt do Plink
`Store key in cache? (y/n, Return cancels connection, i for more info)` e o
comando nao prosseguiu.

**Causa:** o `gcloud` entra na VM com o nome de usuario do notebook (`mathe`).
O repositorio foi clonado pelo SSH do Console, que usa o usuario da conta
(`maia_matheus`), e o home desse usuario nao e legivel pelos outros. O prompt
do Plink e a confirmacao da chave do host, que num comando nao interativo nunca
e respondida.

**Solucao:** `--strict-host-key-checking=no` na primeira conexao e rodar os
comandos como o dono do repositorio:

```bash
gcloud compute ssh servidor-delivery --zone us-central1-a --project sistemas-distribuidos-505422 \
  --strict-host-key-checking=no \
  --command "sudo -iu maia_matheus bash -c 'cd ~/sd-2026-2 && docker compose ps'"
```

**Arquivos:** nenhum (acesso a infraestrutura).

---

## 2026-09-10

### Reescrever o historico nao apaga o que ja passou por um Pull Request

**Sintoma:** depois de reescrever a `main`, dar force push e apagar as branches
antigas, a lista de contribuidores do repositorio continuava trazendo um autor
que nao existe mais em nenhum commit da branch padrao:

```text
$ gh api repos/OWNER/REPO/contributors --jq '.[] | "\(.login) - \(.contributions)"'
matheus14maia - 7
<autor-antigo> - 1        <- nao existe mais no historico da main
```

**Causa:** dois mecanismos independentes, os dois fora do alcance de um force push.

1. O GitHub guarda **para sempre** os commits que passaram por um Pull Request,
   em `refs/pull/N/head`. Nem o force push na `main` nem o
   `git push origin --delete` da branch de origem tocam nessa ref: o commit
   original continua acessivel pelo SHA, e a pagina do PR continua exibindo o
   nome da branch de origem e o autor original na aba *Commits*. Nao existe API
   para apagar um Pull Request.
2. A lista de contribuidores nao e calculada a cada request - e um agregado em
   cache, que o GitHub recalcula de forma assincrona. Logo apos o push ela ainda
   responde com o valor antigo, mesmo com o historico ja correto.

**Solucao:** conferir pela fonte real, que e o historico da branch, e nao pelo
agregado em cache:

```bash
gh api "repos/OWNER/REPO/commits?per_page=20" --jq '.[] | "\(.sha[0:7]) | \(.commit.author.name) | \(.author.login)"'
```

Se todas as linhas trazem o autor correto, o historico esta certo e a lista de
contribuidores se ajusta sozinha quando o cache expira. Para zerar tambem o que
ficou preso na pagina do PR, a unica saida e recriar o repositorio - o que custa
todos os PRs, issues e stars.

**Arquivos:** nenhum (operacao sobre o historico do Git, sem mudanca de conteudo:
`git diff` entre o estado antigo e o reescrito saiu vazio).

---

## 2026-09-08

### Firewall aparentemente correto, mas todo o trafego era descartado

**Sintoma:** `DEADLINE_EXCEEDED` ao conectar em `34.9.87.180:9090`, com a VM
ligada, o container no ar e a regra de firewall criada. A VM tinha uma tag de
rede chamada `trabalho-sd` e a regra de firewall tambem se chamava `trabalho-sd`.

**Causa:** o **nome** da regra e a **tag alvo** da regra sao campos diferentes, e
estavam diferentes:

```text
REGRA          TARGET_TAGS
trabalho-sd    portas-trabalho-sd     <- a regra so vale para esta tag

VM servidor-delivery, tags: http-server, https-server, trabalho-sd
                                                       ^ o NOME da regra
```

Nenhuma instancia tinha `portas-trabalho-sd`, entao a regra nao se aplicava a
ninguem e as portas continuavam fechadas apesar de tudo parecer certo no Console.

**Solucao:** adicionar a tag `portas-trabalho-sd` na VM. Vale imediatamente, sem
reiniciar a instancia.

**Como diagnosticar sem acesso ao Console:** sondar varias portas por TCP e
comparar o tipo de falha. O contraste isola a camada:

```powershell
$c = New-Object System.Net.Sockets.TcpClient
$c.BeginConnect('IP_DA_VM', PORTA, $null, $null).AsyncWaitHandle.WaitOne(6000, $false)
```

| Resultado | Significado |
|---|---|
| porta 22 conecta, portas da regra em timeout | VM viva e roteavel; a regra de firewall nao esta valendo |
| porta sem servico responde "recusada" | o firewall liberou; o pacote chega na VM |
| todas em timeout, inclusive a 22 | VM desligada ou IP errado |

A porta 22 serve de controle: ela e liberada pela `default-allow-ssh`, que
independe da regra do trabalho. Portas liberadas pela regra mas sem nada
escutando (`3000`, `8000`) devem responder "recusada" - se derem timeout, o
problema e firewall, nao container.

**Arquivos:** nenhum (configuracao de infraestrutura no GCP).

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
