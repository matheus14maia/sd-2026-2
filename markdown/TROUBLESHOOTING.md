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

## 2026-11-11

### PDF do relatorio com fontes Type 3 e diagrama cortado nas laterais

**Sintoma:** o PDF gerado do `apresentacao/Trabalho3-relatorio.html` pelo
Chromium (Playwright `page.pdf` ou Ctrl+P > Salvar como PDF) saia com
`pdffonts` listando `Inter-Regular Type 3` (o `pdftoppm` avisava `Bad bounding
box in Type 3 glyph`), e o texto do corpo em Liberation Serif em vez do Charter
pedido no CSS. Ao alargar o diagrama com margem negativa (`margin-left: -10mm`),
a borda do projeto GCP e o comeco da legenda sumiam na pagina.

**Causa:** o Chromium embute fonte OpenType com contornos CFF (os `.otf` do
Inter) e fonte variavel (Inter e Source Serif 4 do Google Fonts) como Type 3,
que alguns leitores de PDF mostram sem suavizacao; o Bitstream Charter
instalado e Type 1 (`.pfb`), que o Chromium nem carrega, por isso caia no
substituto. Na impressao, o que passa da area util da pagina (dentro das
margens do `@page`) e recortado.

**Solucao:** fontes TrueType estaticas: Carlito e Caladea (mesmas metricas de
Calibri e Cambria, que o Chrome usa no Windows) e JetBrains Mono; o diagrama
embutido usa a mesma fonte do texto por CSS (`figure svg text`). Conferir com
`pdffonts` (todas `CID TrueType`). O diagrama fica com 100% da largura do texto.

**Arquivos:** `apresentacao/Trabalho3-relatorio.html`.

---

## 2026-11-10

### No celular o cardapio fica mais largo que a tela e o + nao responde

**Sintoma:** no Playwright com `devices['iPhone 13']` (390 px), o clique no `+`
de um prato falhava por 30 s com `<div class="prato-pe"> intercepts pointer
events` (e `<header class="topo">`, `<ul class="pratos">`). Medindo:
`document.documentElement.scrollWidth` = 749 e `innerWidth` = 749 numa tela de
390 px: a pagina inteira estava mais larga que o celular e reduzida para caber.

**Causa:** a fileira de abas do cardapio (Todos, Entradas, Pratos principais...)
nao quebra linha. No desktop a coluna e `minmax(0, 1fr)`, mas a regra do
celular trocava para `1fr`, que nao deixa a coluna encolher abaixo do conteudo:
as abas forcavam a coluna (e a pagina) a 733 px. Por cima, o zoom do card no
`:hover` (que no toque fica "grudado") mudava o tamanho do card embaixo do dedo.

**Solucao:** colunas do celular com `minmax(0, 1fr)` (as abas, que ja tinham
`overflow-x: auto`, passam a rolar de lado) e o zoom do card e o `:hover` dos
botoes de quantidade so dentro de `@media (hover: hover)`. Conferido: largura da
pagina = 390, `+` responde, barra "Ver sacola" aparece e leva a sacola.

**Arquivos:** `frontend/src/estilos.css`.

### Fogo do botao nao aparece: a animacao termina no primeiro quadro

**Sintoma:** depois de confirmar o pedido, o `<canvas class="fogo">` aparecia
por um instante e sumia sem desenhar nada; o botao nem chegava a acender. Nas
capturas (Playwright, servidor do Vite) nenhum quadro tinha fogo.

**Causa:** o horario que o `requestAnimationFrame` passa para o quadro e o do
inicio do quadro, que pode ser um pouco anterior ao `performance.now()` lido
quando a animacao comecou. No primeiro quadro `t = agora - inicio` saia
negativo, a intensidade (`t / SUBIDA_MS`) ficava abaixo de zero, nenhuma
particula nascia e a condicao de continuar (`forca > 0 || particulas`) dava
falso: a animacao chamava `aoTerminar` antes de comecar. Dependia do tempo da
maquina, por isso na primeira versao (imagem de producao) funcionou.

**Solucao:** `t` e `dt` presos em zero (`Math.max(0, ...)`) e a animacao so
termina pelo relogio (`t < EMISSAO_MS`) ou quando nao sobra particula.

**Arquivos:** `frontend/src/componentes/Fogo.jsx`.

### Microsservico termina com `TypeError` no `docker stop`

**Sintoma:** com o rastreamento ligado, o `docker stop` de um microsservico
terminava assim (os testes passavam, porque so olham as respostas):

```text
Encerrando o servidor...
    encerrar()  # envia os spans que ainda estao na fila
TypeError: executar.<locals>.encerrar() missing 2 required positional arguments: '_sinal' and '_frame'
```

O `ao_encerrar` do servico (fechar o pool e o canal com o Catalogo) nao rodava
e o "Servidor encerrado." nao aparecia.

**Causa:** `servidor_grpc.py` importava `encerrar` do `rastreamento.py` e, dentro
do `executar()`, definia o tratador de sinal tambem como `encerrar(_sinal,
_frame)`. O nome local escondia o importado: a chamada `encerrar()` depois do
`wait_for_termination()` ia para o tratador de sinal, sem os dois argumentos.

**Solucao:** importar como `encerrar_rastreamento` e chamar o tratador de
`ao_receber_sinal`. Conferido com `docker stop` nos tres servicos: codigo de
saida 0 e "Servidor encerrado." no log.

**Arquivos:** `src/comum/servidor_grpc.py`.

### Login do `professor` recusado: `DEMO_SENHA ausente ou curta`

**Sintoma:** depois de `docker compose up -d --build`, o login com `professor`
respondia "Login ou senha invalidos", e o log do migrador dizia:

```text
  DEMO_SENHA ausente ou curta: usuario da cozinha nao criado.
```

`findstr DEMO_SENHA .env` mostrava a senha preenchida.

**Causa:** o `.env.exemplo` tinha duas linhas `DEMO_SENHA`: a que vale, vazia,
no bloco local, e outra comentada (`# DEMO_SENHA=<senha da cozinha>`) na secao
das VMs do Trabalho 2. A senha foi escrita na linha comentada.

**Solucao:** no `.env`, uma linha `DEMO_SENHA=...` sem `#` e
`docker compose up -d --force-recreate migrador` (o migrador cria ou atualiza o
usuario). Para nao acontecer de novo, o `.env.exemplo` passou a ter so o bloco
do computador, com a `DEMO_SENHA` no topo (obrigatorio), e o exemplo de cada VM
foi para o `docs/04`. A senha tambem nao pode ter `$`: o compose le como
variavel e corta o valor.

**Arquivos:** `.env.exemplo`, `docs/03-execucao-local.md`, `docs/04-deploy-gcp-vm.md`.

## 2026-11-09

### No Windows, `localhost` nao abre, mas `127.0.0.1` abre

**Sintoma:** num Windows com Docker Desktop (WSL 2) e duas redes extras criadas
no Hyper-V, todos os containers `Up (healthy)` e as portas publicadas
(`0.0.0.0:80->8080/tcp, [::]:80->8080/tcp`), mas no navegador:

```text
http://localhost            Nao e possivel acessar esse site. A conexao foi redefinida. ERR_CONNECTION_RESET
http://localhost:8000/saude pagina em branco, carregando sem fim
http://127.0.0.1:8000/saude {"status":"ok", ...}
```

**Causa:** o navegador resolve `localhost` primeiro para o IPv6 `::1`. O Docker
Desktop tambem publica as portas em IPv6 (`[::]:80`) e aceita a conexao, mas
nessa maquina o encaminhamento IPv6 ate o container nao funcionava: a conexao
era cortada (porta 80) ou ficava pendurada (porta 8000), e o navegador nao tenta
o IPv4 depois de uma conexao aceita. Pelo IPv4 (`127.0.0.1`) tudo funciona. O
frontend aberto pelo `127.0.0.1` ainda falhava no login, porque o `/config.js`
mandava o navegador chamar o Gateway em `http://localhost:8000` (60 s esperando
e "Gateway fora do ar").

**Solucao:** as portas do Gateway e do frontend sao publicadas so em IPv4
(`0.0.0.0:8000:8000` e `0.0.0.0:${FRONTEND_PORTA}:8080`): sem porta em IPv6, o
`::1` e recusado na hora e o navegador passa para o `127.0.0.1`. O `API_URL`
padrao e o `--url` padrao dos scripts de teste viraram `http://127.0.0.1:8000`.
Quem ja tem um `.env` precisa trocar a linha `API_URL` para
`http://127.0.0.1:8000` e recriar o frontend
(`docker compose up -d --force-recreate frontend`; `restart` nao rele o `.env`).

**Arquivos:** `docker-compose.yml`, `.env.exemplo`, `scripts/testar_gateway.py`,
`scripts/testar_resiliencia.py`, `README.md`, `docs/03-execucao-local.md`,
`docs/05-api-gateway.md`, `docs/06-frontend.md`, `docs/07-resiliencia.md`.

### Catalogo volta, mas o Gateway continua sem conseguir chamar ele

**Sintoma:** depois de `pkill`/`docker compose stop` e de religar o Catalogo, o
Pedidos voltava a falar com ele na hora, mas o Gateway continuava servindo o
cardapio do cache por mais de 1 minuto. A cada chamada de teste do circuito:

```text
[12:43:40] NOTICE: Circuito de catalogo MEIO_ABERTO: liberando uma chamada de teste
[12:43:41] ERROR: catalogo.ListarItens falhou com UNAVAILABLE apos 3 tentativa(s): failed to connect to all addresses; last error: UNKNOWN: ipv4:127.0.0.1:9091: Failed to connect to remote host: Timeout occurred: FD Shutdown
[12:43:41] ERROR: Circuito de catalogo ABERTO apos 7 falhas seguidas: chamadas recusadas na hora por 15 s
```

**Causa:** backoff de reconexao do canal gRPC. No padrao, o intervalo entre
tentativas de reconexao cresce (1 s, 1,6 s, 2,6 s... ate 120 s) e cada tentativa
pode esperar ate 20 s (`min_reconnect_backoff`). Com o canal em
`TRANSIENT_FAILURE`, toda chamada falha na hora, sem tentar conectar; a chamada
de teste do circuito caia nisso e reabria o circuito. O canal do Pedidos tinha
falhado menos vezes, entao o backoff dele era menor e ele voltou antes.

**Solucao:** opcoes do canal em `OPCOES_CANAL` (`initial_reconnect_backoff_ms`
500, `max_reconnect_backoff_ms` 5000, `min_reconnect_backoff_ms` 2000 e
`dns_min_time_between_resolutions_ms` 1000, porque o container pode voltar com
outro IP) e `wait_for_ready=True` so na chamada de teste do circuito: ela espera
o canal conectar (ate o timeout) em vez de falhar na hora. Depois disso o
circuito fecha no primeiro teste depois que o servico volta.

**Arquivos:** `src/comum/canal.py`, `src/comum/resiliencia.py`,
`src/gateway/clientes_grpc.py`, `src/pedidos/cliente_catalogo.py`.

### `GET /cardapio` responde 500 logo depois de derrubar o Catalogo

**Sintoma:** com o Catalogo recebendo `SIGTERM`, a primeira chamada respondeu
`500 Erro interno ao processar a requisicao.` em 2 ms, sem retry e sem usar o
cardapio salvo. Uma sonda direta no gRPC mostrou:

```text
 0.0s CANCELLED: CANCELLED
 0.5s UNAVAILABLE: failed to connect to all addresses; ...
```

**Causa:** durante o encerramento (`servidor.stop(5)`), o servidor gRPC cancela
as chamadas que chegam, e o cliente recebe `CANCELLED`. Esse codigo nao estava
em `FALHAS_DO_SERVICO` nem no mapa de `erros.py`: virava erro "de negocio", nao
tinha retry nem fallback e caia no 500 generico.

**Solucao:** `CANCELLED` entrou em `REPETIR_SE_IDEMPOTENTE` (o Gateway nunca
cancela chamada, entao ele so chega vindo do servidor) e no mapa para 503, junto
com `RESOURCE_EXHAUSTED`. Agora a mesma situacao responde 200 com o cardapio
salvo.

**Arquivos:** `src/comum/resiliencia.py`, `src/gateway/erros.py`.

## 2026-10-14

### `remove-tags` nao remove nada quando chamado do PowerShell

**Sintoma:** `scripts/gcp/criar_infra.ps1` terminou sem erro, mas a VM
`servidor-delivery` continuou com `portas-trabalho-sd` (regra `trabalho-sd`, que
abre 9090-9292 para a internet). A saida do gcloud foi:

```text
No change requested; skipping update for [servidor-delivery].
```

**Causa:** no PowerShell, `--tags portas-trabalho-sd,http-server,https-server`
sem aspas vira um array, e o comando nativo recebe as tags como argumentos
separados. O gcloud nao interpretou a lista e nao alterou nada, sem falhar.

**Solucao:** passar a lista entre aspas
(`--tags "portas-trabalho-sd,http-server,https-server"`) e conferir as tags
depois de qualquer mudanca:
`gcloud compute instances describe servidor-delivery --zone us-central1-a --format="value(tags.items)"`
(esperado: so `delivery-servicos`).

**Arquivos:** `scripts/gcp/criar_infra.ps1`.

### Regra `default-allow-internal` libera o gRPC para qualquer VM da VPC

**Sintoma:** com so a regra `delivery-grpc-interno` (ALLOW da tag
`delivery-gateway`), qualquer outra VM da rede `default` (a do frontend, a
`aula-sd-1`) tambem alcancaria as portas 9090-9092 do `servidor-delivery`.

**Causa:** a rede `default` do projeto tem `default-allow-internal`
(`10.128.0.0/9`, todas as portas, prioridade 65534). Regras ALLOW se somam: a
regra com tag de origem nao restringe nada, so libera.

**Solucao:** regra `delivery-grpc-bloqueio` (DENY `tcp:9090-9092` de
`0.0.0.0/0` para a tag `delivery-servicos`, prioridade 900) e o ALLOW do Gateway
com prioridade 800, que vale antes. Conferido de dentro das VMs com
`timeout 4 bash -c 'echo > /dev/tcp/servidor-delivery.us-central1-a.c.sistemas-distribuidos-505422.internal/9090'`:
`delivery-frontend` -> bloqueada, `delivery-gateway` -> aberta.

**Arquivos:** `scripts/gcp/criar_infra.ps1`, `docs/04-deploy-gcp-vm.md`.

---

## 2026-09-24

### Cloud SQL Studio: `relation "itens_pedido" does not exist`

**Sintoma:** no Cloud SQL Studio da instancia `delivery-postgres`:

```text
Execution failed. All statements are aborted. Details: pq: relation "itens_pedido" does not exist
```

O Explorador mostra `postgres > public` sem as tabelas do projeto.

**Causa:** o login do Studio foi feito no banco padrao `postgres`. As tabelas
do projeto ficam no banco `delivery` (`DB_NAME` do `.env`), que e outro banco
na mesma instancia. No PostgreSQL um banco nao enxerga as tabelas de outro.

**Solucao:** trocar a sessao do Studio para o banco `delivery` (icone de
usuario ao lado de "Explorador", ou sair e entrar de novo), com usuario
`postgres` e a senha do banco. O Explorador passa a mostrar
`delivery > public > Tabelas 3`.

**Arquivos:** nenhum (acesso pelo Console).

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
