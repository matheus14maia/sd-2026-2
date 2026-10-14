# Best Practices

> Padroes e convencoes deste projeto. Ler inteiro antes de qualquer alteracao.
> Atualizar sempre que um padrao novo for descoberto durante o trabalho.

---

## Arquitetura geral

```text
navegador --HTTP :80--> frontend (nginx, VM delivery-frontend)
navegador --HTTP/JSON + Bearer :8000--> gateway (FastAPI, VM delivery-gateway)
gateway --gRPC--> usuarios :9092 | catalogo :9091 | pedidos :9090 (VM servidor-delivery)
pedidos --gRPC--> catalogo
usuarios, catalogo e pedidos --SQL--> PostgreSQL (Cloud SQL no GCP, container no profile banco-local)
```

- **Frontend** (`frontend/`) - React servido pelo nginx. So chama o Gateway, por
  `src/api.js`. Nao conhece os microsservicos.
- **Gateway** (`src/gateway/`) - ponto de entrada do backend. Autentica o JWT,
  confere o papel, valida o JSON, traduz para Protobuf e despacha. Nao acessa o
  banco.
- **Usuarios** (`src/usuarios/`) - dono da tabela `usuarios` (hash bcrypt, papel).
- **Catalogo** (`src/catalogo/`) - dono da tabela `itens_cardapio`.
- **Pedidos** (`src/pedidos/`) - dono de `pedidos` e `itens_pedido`; consulta o
  Catalogo por gRPC (`ConsultarItens`) para validar e precificar.
- **Migrador** (`scripts/migrar_banco.py`) - one-shot no compose; aplica
  `db/schema.sql` e `db/seed.sql` e termina. Usuarios, Catalogo e Pedidos so
  sobem depois dele (`service_completed_successfully`).

Os contratos `proto/usuarios.proto`, `proto/catalogo.proto` e
`proto/pedidos.proto` sao a fronteira entre os componentes. Nenhum lado assume
nada que nao esteja no contrato.

## Stack

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 (imagem) / 3.13 (venv local) |
| Frontend | React 18.3 + Vite 5.4, entregue pelo `nginx:1.27-alpine` |
| Gateway | FastAPI 0.141 + Pydantic 2.13 + Uvicorn 0.53 + PyJWT 2.10 (HS256) |
| Senhas | bcrypt 4.2 (so no microsservico de Usuarios) |
| Comunicacao interna | gRPC (grpcio 1.68.1) + Protocol Buffers proto3 (protobuf 5.29.1) |
| Banco | PostgreSQL 16 - Cloud SQL `delivery-postgres` no GCP; `postgres:16` no local |
| Driver | psycopg 3.3 + psycopg-pool (SQL puro, sem ORM) |
| Empacotamento | Docker + Docker Compose (imagem Python unica com papel pelo `command`, imagem propria do frontend, um profile por VM) |
| Infraestrutura | VMs `delivery-frontend`, `delivery-gateway` e `servidor-delivery` (us-central1-a, IPs estaticos) + Cloud SQL + firewall por tag |

## Padroes de codigo

- **O `.proto` e a fonte da verdade.** Mudou o contrato, regere os stubs e ajuste
  todos os lados que usam aquele servico na mesma alteracao.
- **Stubs sao artefato de build.** Ficam em `src/gerado/`, sao gerados por
  `scripts/gerar_stubs.py` (compila todos os `proto/*.proto`, e roda no
  `docker build`), nao sao versionados e nunca sao editados a mao.
- O `protoc` gera `import catalogo_pb2` (absoluto). O script reescreve para
  `from . import catalogo_pb2` em todo `*_pb2_grpc.py`. Novo `.proto` nao exige
  mudar o script.
- **Codigo e mensagens em portugues sem acento.**
- **Microsservico: erro sempre vira status code do gRPC** (`context.abort(...)`).
  **Gateway: erro sempre vira status HTTP** em `src/gateway/erros.py`, nunca
  `try/except` espalhado nas rotas. Mapa: `INVALID_ARGUMENT` 400, `NOT_FOUND` 404,
  `FAILED_PRECONDITION` 409, `UNAVAILABLE`/`DEADLINE_EXCEEDED` 503, resto 500.
- **Payload invalido responde 400, nao 422.** O FastAPI devolve 422 por padrao;
  o handler de `RequestValidationError` em `erros.py` troca para 400 e monta
  `{"mensagem", "erros": {campo: motivo}}` (mesmo formato da aula-6 da
  disciplina). Mensagens por tipo de erro do Pydantic ficam em `MENSAGENS`.
- **Validacao em duas camadas.** Campos obrigatorios e formato no Gateway
  (`esquemas.py`, `extra="forbid"`); regras que dependem de dado (item existe,
  esta disponivel, transicao de status) no microsservico. O microsservico repete
  as checagens basicas para nao depender de quem chama.
- **Rota do Gateway e fina:** recebe o modelo validado, chama um metodo de
  `ClientesGrpc` e devolve o dict. Conversao Protobuf -> dict com
  `MessageToDict(preserving_proto_field_name=True, always_print_fields_with_no_presence=True)`
  para manter `snake_case` e mostrar campos com valor padrao (ex.: `disponivel: false`).
- **SQL so no `repositorio.py`** de cada servico; regra de negocio so no `servico.py`.
- Toda configuracao que muda entre maquinas vem de variavel de ambiente com
  padrao: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
  `DB_SSLMODE`, `PORTA`, `USUARIOS_HOST/PORTA`, `CATALOGO_HOST/PORTA`,
  `PEDIDOS_HOST/PORTA`, `GRPC_TIMEOUT`, `CATALOGO_TIMEOUT`, `GRPC_BIND`,
  `JWT_SEGREDO`, `JWT_EXPIRACAO_MINUTOS`, `CORS_ORIGENS`, `API_URL`,
  `FRONTEND_PORTA`, `COMPOSE_PROFILES`.
- **Timeouts encadeados diminuem a cada salto.** Gateway -> Pedidos usa 5 s;
  Pedidos -> Catalogo usa 3 s. Se fossem iguais, com o Catalogo fora o Gateway
  estourava primeiro e respondia um `Deadline Exceeded` generico em vez de
  "Catalogo indisponivel".

## Padroes de dados

- Precos em `NUMERIC(10,2)` no banco e `double` no contrato; o `SELECT` converte
  com `::float8`. Quem precifica e o Pedidos, com o preco que o Catalogo
  devolve: o cliente envia so `codigo` e `quantidade`.
- `subtotal = round(preco * quantidade, 2)`; `total` = soma arredondada.
- Tempo estimado: `15 + 3 x unidades` minutos (`src/pedidos/servico.py`).
- `pedido_id` e UUID4 gerado no Pedidos (coluna `UUID`). Id malformado responde
  `INVALID_ARGUMENT` antes de ir ao banco (senao o PostgreSQL lancaria erro de cast).
- Codigo de item: 2 letras + 2 digitos. O Gateway aceita minusculo e normaliza;
  no Pydantic o `pattern` e checado **antes** do `to_upper`, por isso a regex
  aceita `[A-Za-z]`.
- **Snapshot no pedido:** `itens_pedido` guarda nome e preco da hora da compra.
  Nao ha FK entre tabelas de servicos diferentes.
- Datas em `TIMESTAMPTZ`; o contrato leva string ISO 8601 no fuso do container
  (`TZ=America/Sao_Paulo`), ex.: `2026-09-24T20:43:57-03:00`.
- Status em `TEXT` com os nomes do enum; em proto3 o enum tem
  `STATUS_DESCONHECIDO = 0`.
- `db/schema.sql` usa `CREATE ... IF NOT EXISTS` e `db/seed.sql` usa
  `ON CONFLICT DO NOTHING`: o migrador roda a cada deploy sem apagar dado nem
  desfazer alteracao feita pela API.

## Concorrencia

- Cada servidor gRPC atende com `ThreadPoolExecutor(max_workers=10)` e um
  `ConnectionPool` (max 5). Nenhum estado compartilhado em memoria: o estado
  e o banco.
- `AtualizarStatus` usa `UPDATE ... WHERE id = %s AND status = %s` e confere o
  `rowcount`: duas chamadas simultaneas nao avancam o mesmo pedido duas vezes.
- Pedido + itens sao gravados na mesma transacao (`with pool.connection()`
  faz commit ao sair sem erro e rollback se houver excecao).

## Regras de negocio

| Regra | Onde | Resposta |
|---|---|---|
| `cliente`, `endereco`, `itens` obrigatorios | `gateway/esquemas.py` e `pedidos/servico.py` | 400 |
| `quantidade` inteira de 1 a 99 | `gateway/esquemas.py` | 400 |
| Item precisa existir | `pedidos/servico.py` via `ConsultarItens` | 400 (`INVALID_ARGUMENT`) |
| Item com `disponivel = false` e recusado | `pedidos/servico.py` | 409 (`FAILED_PRECONDITION`) |
| Status so avanca para a proxima etapa | `pedidos/servico.py` (`ETAPAS`) | 409 |
| Categoria inexistente | `catalogo/servico.py` | 404 |
| Preco alterado precisa ser > 0 | `gateway/esquemas.py` e `catalogo/servico.py` | 400 |
| Toda rota fora de `ROTAS_PUBLICAS` exige Bearer valido | `gateway/autenticacao.py` (`MiddlewareJWT`) | 401 |
| Login ou senha errados | `usuarios/servico.py` (`UNAUTHENTICATED`) | 401 |
| Alterar cardapio ou avancar status exige papel `cozinha` | `gateway/autenticacao.py` (`exigir_papel`) | 403 |
| Login repetido | `usuarios/servico.py` (`ALREADY_EXISTS`, UNIQUE no banco) | 409 |

## Autenticacao e autorizacao

- **Token so no Gateway.** Ele emite (`POST /auth/login`) e confere o JWT; os
  microsservicos nao veem token. O Usuarios so confirma login e senha.
- **Barreira no middleware, nao em cada rota.** `MiddlewareJWT` barra tudo fora de
  `ROTAS_PUBLICAS`; rota nova ja nasce protegida. Para liberar uma rota, ela
  precisa entrar na lista de proposito.
- **401 e autenticacao, 403 e autorizacao.** Token ausente, invalido ou vencido
  -> 401 no middleware. Token valido de papel errado -> 403 na dependencia
  `exigir_papel`, que levanta `AcessoNegado` (handler em `erros.py`).
- **Nenhum segredo no codigo.** O repositorio e publico: sem `JWT_SEGREDO`, o
  Gateway sorteia uma chave a cada subida (`secrets.token_hex(32)`). Segredo fixo
  como valor padrao permitiria a qualquer leitor do GitHub assinar tokens.
- **Senha so como hash bcrypt, e so no Usuarios.** Nenhuma resposta nem log leva
  a senha; a mesma mensagem cobre login inexistente e senha errada.
- **Quem se cadastra pela API e `cliente`.** O papel `cozinha` so existe para o
  usuario que o migrador cria a partir de `DEMO_LOGIN`/`DEMO_SENHA` do `.env`
  (`garantir_usuario_cozinha` em `scripts/migrar_banco.py`). **Nunca ponha
  usuario com senha conhecida no `db/seed.sql`:** o repositorio e publico e o
  sistema fica no ar, entao qualquer leitor teria o papel `cozinha`. No GCP a
  senha e gerada pelo `preparar_vm.sh` (`openssl rand`) e fica so no `.env` do
  `servidor-delivery`; os scripts do notebook a leem por SSH (`SenhaCozinha`).
  A senha nao aparece na tela de login, nos slides nem na saida do `ligar.ps1`.
- **Coluna nova em tabela existente vai em `ALTER TABLE ... ADD COLUMN IF NOT
  EXISTS`**, separado do `CREATE TABLE IF NOT EXISTS`: o `CREATE` nao faz nada
  quando a tabela ja existe, e o Cloud SQL ja tinha `usuarios` sem `papel`.
- **CORS e o middleware mais externo.** No Starlette o ultimo `add_middleware` e
  o mais externo; o CORS e adicionado por ultimo para que ate o 401 saia com
  `Access-Control-Allow-Origin`. Sem isso o navegador esconde o 401 e o frontend
  ve so "falha de rede". `OPTIONS` (preflight) passa pelo JWT sem token.

## Frontend

- **Um unico modulo fala com o backend** (`frontend/src/api.js`). Ele monta a
  URL, poe o Bearer, registra a chamada no trilho e encerra a sessao num 401.
- **Formularios sem validacao no navegador** (`noValidate`, sem `required`): o
  400 do Gateway e o que aparece embaixo de cada campo. Validar no navegador
  esconderia o requisito de validacao no backend na demonstracao.
- **URL do Gateway em tempo de execucao.** O `index.html` carrega `/config.js`,
  que o nginx gera a partir de `API_URL` (template em `frontend/nginx/`). Mudar o
  Gateway de lugar nao exige rebuild da imagem.
- **Texto da interface com acento** (e o que o usuario le); codigo, mensagens da
  API e documentacao seguem sem acento.

## Deploy em varias VMs

- **Um compose, um profile por papel.** `servicos`, `gateway`, `frontend` e
  `banco-local`; cada VM poe o seu em `COMPOSE_PROFILES` no `.env`. Servicos de
  profiles diferentes nao tem `depends_on` entre si (estao em maquinas
  diferentes): o Gateway responde 503 ate o microsservico subir.
- **Portas gRPC em `${GRPC_BIND:-127.0.0.1}`.** Local, so a propria maquina
  alcanca; na VM `servidor-delivery`, `GRPC_BIND=0.0.0.0` e quem restringe e o
  firewall `delivery-grpc-interno` (origem = tag `delivery-gateway`).
- **Firewall por tag de origem, nao por IP.** A regra gRPC aceita a tag
  `delivery-gateway`; vale para o IP interno da VM do Gateway sem precisar
  conhece-lo.
- **Gateway acha os microsservicos pelo DNS interno da VPC**
  (`servidor-delivery.us-central1-a.c.<projeto>.internal`), que resolve tambem de
  dentro do container.
- **`.env` por VM, gravado por `scripts/gcp/preparar_vm.sh`**, que troca ou
  acrescenta chave sem apagar as demais (senha do banco, `JWT_SEGREDO`).
- **Scripts que rodam no Linux precisam de LF.** O `.gitattributes` forca
  `eol=lf` em `*.sh` e `*.template`; com `core.autocrlf=true` no Windows, um
  `preparar_vm.sh` com CRLF quebraria o `bash` na VM.

## Convencoes importantes

- **Os dados ficam no PostgreSQL, nunca em memoria.** Lista estatica, dicionario
  ou mock de repositorio zera o requisito de banco do Trabalho 2. O cardapio
  inicial vem de `db/seed.sql`, nao de codigo Python.
- **Cloud SQL so aceita as redes autorizadas.** A VM usa IP estatico
  (`ip-servidor-delivery`, 34.60.57.59) justamente porque ele esta cadastrado
  como `34.60.57.59/32` na instancia; com IP efemero, cada religada quebraria a
  conexao com o banco. Conexao ao Cloud SQL por IP publico usa `DB_SSLMODE=require`.
- **Ao ligar o ambiente, banco antes da VM.** Os servicos esperam o banco por
  cerca de 1 minuto (`DB_TENTATIVAS`) e depois o `restart: always` tenta de novo,
  mas ligar o Cloud SQL primeiro evita a espera na demonstracao.
- **Profiles do compose:** todo servico tem profile, entao `docker compose up`
  sem `COMPOSE_PROFILES` nao sobe nada. `postgres` so sobe com `banco-local`; no
  GCP o `.env` do `servidor-delivery` aponta para o Cloud SQL. Nenhum servico tem
  `depends_on` do `postgres` - senao o compose recusaria subir sem o profile; a
  espera pelo banco e feita em codigo (`src/comum/banco.aguardar_banco`).
- **O repositorio na VM pertence ao usuario `maia_matheus`**
  (`/home/maia_matheus/sd-2026-2`). Um SSH feito por outro usuario do `gcloud`
  (o nome local do notebook) nao enxerga a pasta; rode os comandos com
  `sudo -iu maia_matheus` ou pelo SSH do Console.
- **A porta do servico e escolhida a partir do que o firewall da VPC ja libera,
  nao o contrario.** A regra `trabalho-sd` do projeto libera
  `tcp:3000,5050,8000,9090-9292`; por isso a porta padrao e `9090` e nao a `50051`
  convencional do gRPC. Descobrir isso so na hora de conectar custa uma sessao de
  depuracao de `UNAVAILABLE` que parece problema de codigo e nao e.
- Portas publicas: `80` (frontend) e `8000` (Gateway), cada uma com a sua regra
  de firewall. As portas gRPC `9090` (Pedidos), `9091` (Catalogo) e `9092`
  (Usuarios) so aceitam a VM do Gateway. Mudou alguma porta? Ela aparece em
  `docker-compose.yml`, `Dockerfile` (`EXPOSE`), no default de `PORTA` do
  `servidor.py` do servico, nos defaults de `clientes_grpc.py` /
  `cliente_catalogo.py`, em `scripts/gcp/criar_infra.ps1` (firewall) e nas docs
  `README.md`, `docs/03`, `docs/04` e `docs/05`.
- **`UNAVAILABLE` e `DEADLINE_EXCEEDED` nao sao o mesmo problema.**
  `UNAVAILABLE` com `Connection refused` significa que o pacote chegou na maquina
  e nada escuta na porta (container parado, porta errada). `DEADLINE_EXCEEDED` ao
  conectar significa que nada voltou: o trafego esta sendo descartado antes do
  servidor, quase sempre firewall - regra que nao cobre a porta ou VM sem a tag
  de rede.
- **No GCP, o nome da regra de firewall e a tag alvo dela sao coisas diferentes.**
  Uma regra chamada `trabalho-sd` pode ter `targetTags: [portas-trabalho-sd]`. A
  VM precisa da **tag alvo**, nao do nome da regra. Conferir com
  `gcloud compute firewall-rules describe NOME --format="yaml(targetTags)"` e
  comparar com `gcloud compute instances list --format="table(name,tags.items.list())"`.
- **A tag de rede tem que estar na instancia, nao so na regra.** Uma regra de
  firewall com `targetTags` so vale para VMs marcadas com aquela tag. Regra
  correta + VM sem a tag produz exatamente o mesmo `UNAVAILABLE` de servidor
  desligado.
- **O container roda com `TZ=America/Sao_Paulo`.** A imagem `python:3.12-slim`
  usa UTC por padrao; sem a variavel, os horarios impressos pelo servidor (log e
  campo `horario` do stream) saem 3h a frente do relogio do notebook. Na
  demonstracao as duas telas aparecem juntas.
- **Os containers sobem sozinhos** (`restart: always` +
  `systemctl is-enabled docker` = `enabled`). Isso permite parar e religar a VM
  pelo Console sem nenhum comando Docker. `docker compose down` **remove** o
  container e derruba esse comportamento - por isso ele nao aparece no ciclo
  normal de `docs/04`.
- O canal e `insecure` (plaintext) de proposito: TLS exigiria certificado e sai
  do escopo da disciplina.
- O log e parte da demonstracao. Toda chamada recebida imprime uma linha com
  horario: RPC e parametros nos microsservicos (`comum.servidor_grpc.log`),
  metodo, rota, status e duracao no Gateway (middleware em `app.py`).
- Material da disciplina (`docs/Trabalho*`, `docs/Tutorial*`, `docs/*.pdf`) e
  o roteiro pessoal de demonstracao ficam fora do git pelo `.gitignore`.
- `docs/` e publico. Nao versione material da disciplina nem configuracao local
  de ferramenta (ver `.gitignore`).
- **Commit, PR e documentacao deste repositorio sao em portugues e assinados so
  pelo autor do trabalho.** O repositorio e publico e avaliado: mensagem em
  ingles no meio de um historico em portugues, ou trailer de coautor, destoa e
  chama atencao. Conferir antes de publicar com
  `git log --format='%h | %an <%ae> | %s'` e `git log --format='%B' -3`.
- **Reescrever o historico nao alcanca o que ja passou por um Pull Request.** O
  GitHub preserva `refs/pull/N/head` indefinidamente e nao oferece API para
  apagar um PR: force push e delete da branch nao removem o commit original nem
  o nome da branch de origem da pagina do PR. Corrigir autoria e texto **antes**
  de abrir o PR sai muito mais barato do que depois.
- **Ao reescrever o historico, limite o alcance e proteja o remoto.** Passar um
  intervalo ao `git filter-branch ... -- BASE..main` preserva o SHA de tudo que
  vem antes de `BASE` (e os merges de PR antigos continuam validos), e
  `git push --force-with-lease=main:SHA` recusa o push se o remoto tiver andado.
  Criar uma branch de backup do estado anterior antes de comecar.
