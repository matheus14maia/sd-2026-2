# Best Practices

> Padroes e convencoes deste projeto. Ler inteiro antes de qualquer alteracao.
> Atualizar sempre que um padrao novo for descoberto durante o trabalho.

---

## Arquitetura geral

```text
HTTP/JSON :8000 -> gateway (FastAPI) --gRPC--> pedidos :9090 --gRPC--> catalogo :9091
                                     \--gRPC--> catalogo
pedidos e catalogo --SQL--> PostgreSQL (Cloud SQL no GCP, container no profile banco-local)
```

- **Gateway** (`src/gateway/`) - unico componente com porta publicada. Valida o
  JSON, traduz para Protobuf e despacha. Nao acessa o banco.
- **Catalogo** (`src/catalogo/`) - dono da tabela `itens_cardapio`.
- **Pedidos** (`src/pedidos/`) - dono de `pedidos` e `itens_pedido`; consulta o
  Catalogo por gRPC (`ConsultarItens`) para validar e precificar.
- **Migrador** (`scripts/migrar_banco.py`) - one-shot no compose; aplica
  `db/schema.sql` e `db/seed.sql` e termina. Catalogo e Pedidos so sobem depois
  dele (`service_completed_successfully`).

Os contratos `proto/catalogo.proto` e `proto/pedidos.proto` sao a fronteira
entre os componentes. Nenhum lado assume nada que nao esteja no contrato.

## Stack

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 (imagem) / 3.13 (venv local) |
| Gateway | FastAPI 0.141 + Pydantic 2.13 + Uvicorn 0.53 |
| Comunicacao interna | gRPC (grpcio 1.68.1) + Protocol Buffers proto3 (protobuf 5.29.1) |
| Banco | PostgreSQL 16 - Cloud SQL `delivery-postgres` no GCP; `postgres:16` no local |
| Driver | psycopg 3.3 + psycopg-pool (SQL puro, sem ORM) |
| Empacotamento | Docker + Docker Compose (imagem unica, papel pelo `command`) |
| Infraestrutura | VM `servidor-delivery` (us-central1-a, IP estatico 34.60.57.59) + Cloud SQL + firewall `trabalho-sd` |

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
  `DB_SSLMODE`, `PORTA`, `CATALOGO_HOST/PORTA`, `PEDIDOS_HOST/PORTA`,
  `GRPC_TIMEOUT`, `CATALOGO_TIMEOUT`.
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
- **Profiles do compose:** `postgres` so sobe com `--profile banco-local`. No
  GCP roda-se `docker compose up -d --build` sem profile e o `.env` aponta para o
  Cloud SQL. Nenhum servico tem `depends_on` do `postgres` - senao o compose
  recusaria subir sem o profile; a espera pelo banco e feita em codigo
  (`src/comum/banco.aguardar_banco`).
- **O repositorio na VM pertence ao usuario `maia_matheus`**
  (`/home/maia_matheus/sd-2026-2`). Um SSH feito por outro usuario do `gcloud`
  (o nome local do notebook) nao enxerga a pasta; rode os comandos com
  `sudo -iu maia_matheus` ou pelo SSH do Console.
- **A porta do servico e escolhida a partir do que o firewall da VPC ja libera,
  nao o contrario.** A regra `trabalho-sd` do projeto libera
  `tcp:3000,5050,8000,9090-9292`; por isso a porta padrao e `9090` e nao a `50051`
  convencional do gRPC. Descobrir isso so na hora de conectar custa uma sessao de
  depuracao de `UNAVAILABLE` que parece problema de codigo e nao e.
- A porta publica agora e a `8000` do Gateway (tambem liberada pela regra
  `trabalho-sd`). As portas gRPC `9090` (Pedidos) e `9091` (Catalogo) sao
  internas ao compose. Mudou alguma porta? Ela aparece em `docker-compose.yml`,
  `Dockerfile` (`EXPOSE`), no default de `PORTA` do `servidor.py` do servico, nos
  defaults de `clientes_grpc.py` / `cliente_catalogo.py` e nas docs `README.md`,
  `docs/03`, `docs/04` e `docs/05`.
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
