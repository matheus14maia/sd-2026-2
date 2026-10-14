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

## 2026-10-14

| Horario | Task | Detalhe |
|---------|------|---------|
| 20:30 | Documentacao do Trabalho 2 | `README.md` com rotas e coluna de token, conta de demonstracao e estrutura nova; `docs/01` (login, papeis, reacoes 401/403/409 de usuario), `docs/02` (`usuarios.proto`), `docs/03` (profiles, 29 cenarios, frontend local), `docs/04` reescrito para 3 VMs + firewall por tag + scripts, `docs/05` (JWT, papeis, CORS, variaveis, exemplos com token) e novo `docs/06-frontend.md`. Diagrama `docs/arquitetura.svg` (fonte) e `docs/arquitetura.png` (2x, para slides). `markdown/BEST_PRACTICES.md` com secoes de autenticacao, frontend e deploy em varias VMs. |
| 20:00 | Scripts do GCP | `scripts/gcp/`: `criar_infra.ps1` (IPs estaticos, 3 regras de firewall, VMs `delivery-gateway` e `delivery-frontend`, tags do `servidor-delivery`), `instalar_docker.sh` (startup-script), `preparar_vm.sh` (clona, grava o `.env` do papel e sobe o compose), `implantar.ps1`, `ligar.ps1` (Cloud SQL primeiro, depois VMs, e confere cada camada), `desligar.ps1` e `status.ps1`. `.gitattributes` com `eol=lf` para `*.sh` e `*.template`. |
| 19:25 | Correcoes de seguranca: segredo, portas gRPC e papel | (1) Sem `JWT_SEGREDO`, o Gateway usava um segredo fixo escrito no codigo publico, e qualquer um podia assinar token valido; agora sorteia `secrets.token_hex(32)` a cada subida e avisa no log. (2) As portas 9090-9092 eram publicadas em todas as interfaces; agora `${GRPC_BIND:-127.0.0.1}` e so a VM dos microsservicos usa `GRPC_BIND=0.0.0.0` (o firewall restringe a origem). (3) Qualquer cadastrado alterava preco e status; coluna `usuarios.papel` (`cliente`/`cozinha`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`), claim `papel` no token e dependencia `exigir_papel` -> **403** em `PATCH /cardapio/{codigo}` e `PATCH /pedidos/{id}/status`. `professor` passa a ser `cozinha`. Teste ponta a ponta com 29 cenarios OK. Arquivos: `src/gateway/autenticacao.py`, `erros.py`, `app.py`, `rotas/*.py`, `proto/usuarios.proto`, `src/usuarios/*`, `db/*.sql`, `docker-compose.yml`, `frontend/src/*`, `scripts/testar_gateway.py`. |
| 19:00 | Testes ponta a ponta do Trabalho 2 | `scripts/testar_gateway.py` agora faz login com o usuario `professor` e manda o Bearer nas rotas protegidas; cenarios novos: 401 sem token, sem `Bearer`, token que nao e JWT, assinatura adulterada e senha errada; 400 no login e no cadastro; 201 no cadastro; 409 em login repetido; 200 em `/auth/eu`. Os 26 cenarios passaram com a pilha local completa (`COMPOSE_PROFILES=banco-local,servicos,gateway,frontend`). Jornada no navegador (Edge headless): todas as chamadas `fetch` foram para `localhost:8000`. |
| 18:58 | Frontend React | Novo `frontend/` (Vite 5 + React 18, sem roteador): login/cadastro, cardapio com filtro no servidor, sacola e `POST /pedidos`, pedidos com etapas (avancar 200 / pular 409), cozinha (`PATCH /cardapio`), tela de testes de seguranca (401/400/409) e trilho de comandas no rodape com o status de cada chamada ao Gateway. `src/api.js` e o unico modulo que fala com o backend. Imagem propria: build com `node:20-alpine` e entrega pelo `nginx:1.27-alpine`; a URL do Gateway vem da variavel `API_URL`, entregue ao navegador em `/config.js` pelo template do nginx. |
| 18:55 | Compose por profile (uma VM por papel) | `docker-compose.yml` dividido nos profiles `servicos` (migrador, usuarios, catalogo, pedidos), `gateway`, `frontend` e `banco-local`. Cada maquina escolhe o que sobe pelo `COMPOSE_PROFILES` do seu `.env`. Portas gRPC 9090-9092 publicadas no host porque o Gateway passa a rodar em outra VM; sem `depends_on` entre profiles. `.env.exemplo` documenta o `.env` de cada VM. |
| 18:50 | JWT no Gateway | `src/gateway/autenticacao.py`: `MiddlewareJWT` barra com 401 (e `WWW-Authenticate: Bearer`) toda rota fora de `ROTAS_PUBLICAS` sem token HS256 valido, antes de qualquer chamada gRPC; `emitir_token` assina `sub/login/nome/iat/exp` com `JWT_SEGREDO`. Rotas novas `POST /auth/cadastro` (201), `POST /auth/login` (200) e `GET /auth/eu`. `UNAUTHENTICATED` -> 401 no mapa de erros. `CORSMiddleware` como camada mais externa. Mensagens de 400 por regex (`FORMATOS`) e por tamanho minimo. |
| 18:45 | Microsservico de Usuarios | `proto/usuarios.proto` (`CadastrarUsuario`, `VerificarCredenciais`), `src/usuarios/` na porta 9092, tabela `usuarios` com hash bcrypt e usuario de demonstracao no `db/seed.sql`. Login repetido -> `ALREADY_EXISTS`; credencial errada -> `UNAUTHENTICATED` com a mesma mensagem para login inexistente e senha errada. Dependencias `bcrypt` e `PyJWT`. |

---

## 2026-09-24

| Horario | Task | Detalhe |
|---------|------|---------|
| 20:58 | Documentacao do Trabalho 2 | `README.md` e `docs/01` a `docs/04` reescritos para a arquitetura Gateway + Catalogo + Pedidos + PostgreSQL; novo `docs/05-api-gateway.md` (rotas, regras de validacao, formato do 400, mapa gRPC -> HTTP, exemplos curl/PowerShell). `docs/04` passa a documentar a infraestrutura real: VM `servidor-delivery` com IP estatico, Cloud SQL `delivery-postgres`, `.env` na VM e ciclo liga/desliga com o banco primeiro. `markdown/BEST_PRACTICES.md` com arquitetura, stack e padroes novos. |
| 20:53 | Deploy validado no GCP | `main` (`4d59475`, merge do PR #4) na VM `servidor-delivery`: migrador aplicou schema e seed no Cloud SQL (`Banco pronto: 13 itens no cardapio`), `scripts/testar_gateway.py --url http://34.60.57.59:8000` com os 15 cenarios `OK` a partir do notebook e o pedido criado conferido na tabela `pedidos` do Cloud SQL (PostgreSQL 16.15) com status `EM_PREPARO`. O container `restaurante-servidor` do trabalho anterior foi removido pelo `--remove-orphans`. |
| 20:47 | Cloud SQL criado | Instancia `delivery-postgres` (PostgreSQL 16, Enterprise, `db-f1-micro`, `us-central1`, zona unica, IP publico `34.63.128.138`, sem backup automatico), banco `delivery`, rede autorizada `34.60.57.59/32`. Antes, o IP externo da VM foi promovido a estatico (`ip-servidor-delivery`), porque a rede autorizada do Cloud SQL quebraria a cada religada com IP efemero. Mesmos parametros do tutorial da disciplina, com maquina menor para gastar menos credito. |
| 20:45 | Timeout Pedidos -> Catalogo menor que o do Gateway | Com o Catalogo parado, o `POST /pedidos` respondia `503 {"mensagem":"Deadline Exceeded"}`: o Gateway (5 s) desistia no mesmo instante em que o Pedidos (5 s) desistia do Catalogo. `CATALOGO_TIMEOUT` passou a 3 s e a resposta virou `503 Catalogo indisponivel no momento (UNAVAILABLE)`. Arquivo: `src/pedidos/cliente_catalogo.py`. |
| 20:44 | Codigo de item em minusculo recusado | `{"codigo":"be02"}` respondia 400 apesar do `to_upper=True`, porque o Pydantic confere o `pattern` antes de transformar. Regex passou para `^[A-Za-z]{2}[0-9]{2}$`. Arquivo: `src/gateway/esquemas.py`. |
| 20:40 | API Gateway FastAPI + microsservicos Catalogo e Pedidos + PostgreSQL | O servico unico `RestauranteService` (cardapio em tupla estatica, pedidos em dicionario) virou: Gateway HTTP/JSON (`src/gateway/`) com validacao Pydantic (400 com `erros` por campo, 201 na criacao) e mapa gRPC -> HTTP; microsservico Catalogo (`proto/catalogo.proto`, tabela `itens_cardapio`); microsservico Pedidos (`proto/pedidos.proto`, tabelas `pedidos`/`itens_pedido`, chama o Catalogo por gRPC). Consulta, insercao e alteracao (status do pedido, disponibilidade/preco do item) gravam no banco. Schema e seed idempotentes em `db/`, aplicados pelo servico one-shot `migrador`. `scripts/gerar_stubs.py` compila todos os `.proto`; novo `scripts/testar_gateway.py`. Removidos `src/servidor/`, `src/cliente/` e `proto/restaurante.proto` - o cliente passa a falar so com o Gateway. |
| 20:15 | Material da disciplina fora do git | `.gitignore` passou de `docs/Trabalho1*` para `docs/Trabalho*`, `docs/Tutorial*` e `docs/*.pdf` (enunciado do Trabalho 2 e tutorial de Cloud SQL). A linha anterior usava barra invertida (`docs\Trabalho2-...`), que o git nao reconhece como separador. |

---

## 2026-09-10

| Horario | Task | Detalhe |
|---------|------|---------|
| 09:40 | Historico da `main` padronizado em autoria e idioma | Os tres commits do topo tinham mensagem em ingles e um deles estava assinado por um autor que nao e o dono do trabalho - fora do padrao dos oito commits anteriores. Reescritos com `git filter-branch` limitado ao intervalo `917335d..main`, o que preserva o SHA de tudo que vem antes e mantem os merges dos PRs #1 e #2 intactos. O conteudo das arvores nao mudou: `git diff origin/main main` saiu vazio antes do push. Force push com `--force-with-lease` fixado no SHA esperado do remoto. Topo agora: `d64492f`, `fad45fa`, `79fe8c0`. |
| 09:41 | Branches ja integradas removidas do remoto | As duas branches remanescentes do PR #3 (a de origem e a de revert) foram apagadas. Restam no remoto `main`, `fix/porta-9090-e-autostart-na-vm` e `fix/renomeia-restaurante-e-trata-deadline-exceeded`. |
| 09:42 | PR #3 reescrito em portugues | Titulo e descricao estavam em ingles, diferente dos PRs #1 e #2. Reescritos no mesmo formato ("O que muda" / "Como testar"), explicando por que `docs/05-roteiro-apresentacao.md` saiu do repositorio: era preparacao pessoal para o evento (divisao do tempo, planos B, frases por criterio), nao documentacao do sistema. |

---

## 2026-09-08

| Horario | Task | Detalhe |
|---------|------|---------|
| 19:55 | Deploy validado na VM do GCP | Primeiro pedido ponta a ponta contra `servidor-delivery` (`34.9.87.180:9090`, projeto `sistemas-distribuidos-505422`): cardapio, `CriarPedido` com total calculado no servidor e o stream completo `RECEBIDO -> ENTREGUE`. Antes disso, o trafego era descartado porque a regra de firewall `trabalho-sd` tem `targetTags: portas-trabalho-sd` e a VM estava marcada com `trabalho-sd`, que e o nome da regra. Registrado em `markdown/TROUBLESHOOTING.md` com a tecnica de sondagem de portas usada no diagnostico. |
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
