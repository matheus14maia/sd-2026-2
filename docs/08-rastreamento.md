# 8. Rastreamento distribuido (Cloud Trace / Jaeger)

Cada requisicao vira um **trace**: uma arvore de **spans** (trechos com inicio,
fim e atributos) que mostra por onde ela passou, quanto tempo levou em cada
servico e onde falhou. O codigo usa o OpenTelemetry (`src/comum/rastreamento.py`)
e manda os mesmos spans para dois lugares:

| Onde | Para onde vao os spans | Como ver |
|---|---|---|
| Google Cloud (Trabalho 3) | **Cloud Trace** (`RASTREAMENTO=gcp`) | Console > Trace > Explorador de traces |
| Seu computador | **Jaeger** (`RASTREAMENTO=otlp`, profile `rastreamento`) | `http://127.0.0.1:16686` |

Sem `RASTREAMENTO`, os spans existem so para o id da requisicao seguir de um
servico para o outro e aparecer nos logs; nada e enviado.

## O que aparece num trace

Um `POST /pedidos` real (Jaeger, pilha local):

```text
gateway    POST /pedidos                                  28.4 ms
  gateway    pedidos.CriarPedido                            21.5 ms
    gateway    pedidos.CriarPedido tentativa 1                21.4 ms
      pedidos    pedidos.CriarPedido                            18.0 ms
        pedidos    banco pedidos.buscar                            2.3 ms
        pedidos    catalogo.ConsultarItens                         8.0 ms
          pedidos    catalogo.ConsultarItens tentativa 1             7.9 ms
            catalogo   catalogo.ConsultarItens                         3.4 ms
              catalogo   banco itens_cardapio.buscar_varios              3.1 ms
        pedidos    banco pedidos.inserir                           4.4 ms
        pedidos    banco pedidos.buscar                            2.5 ms
```

| Span | Onde nasce | Tipo |
|---|---|---|
| `POST /pedidos` (nome pela rota, ex.: `GET /pedidos/{pedido_id}`) | middleware do Gateway (`app.py`) | SERVER |
| `pedidos.CriarPedido` | `ClienteResiliente.chamar`: a chamada inteira, com os eventos de retry ("nova tentativa") e de circuito ("circuito aberto") | INTERNAL |
| `pedidos.CriarPedido tentativa N` | uma por tentativa gRPC; o contexto dela vai nos metadados | CLIENT |
| `pedidos.CriarPedido` (no servico `pedidos`) | `InterceptadorServidor`: o atendimento no microsservico, com os eventos "falha simulada" e "banco indisponivel" | SERVER |
| `banco <tabela>.<operacao>` | decorador `@rastrear_banco` nos repositorios | CLIENT |

Com o Catalogo falhando (injecao de falha a 60%), o retry fica visivel:

```text
gateway   GET /cardapio                           469.6 ms ERRO
gateway   catalogo.ListarItens                    467.7 ms ERRO eventos: nova tentativa, nova tentativa
gateway   catalogo.ListarItens tentativa 1          3.3 ms ERRO
catalogo  catalogo.ListarItens                      0.1 ms ERRO eventos: falha simulada
gateway   catalogo.ListarItens tentativa 2          2.6 ms ERRO
catalogo  catalogo.ListarItens                      0.2 ms ERRO eventos: falha simulada
gateway   catalogo.ListarItens tentativa 3          1.6 ms ERRO
catalogo  catalogo.ListarItens                      0.1 ms ERRO eventos: falha simulada
```

- **Erro de negocio nao e erro do span.** 400, 404 e 409 ficam como atributo
  (`rpc.grpc.status_code`, `http.response.status_code`); so falha do servico
  (`UNAVAILABLE`, `DEADLINE_EXCEEDED`, 5xx) marca o span como erro.
- **Sondas de saude nao viram trace.** `GET /saude` (HEALTHCHECK a cada 15 s) e
  `GET /saude/servicos` (tela Saude a cada 3 s) ficariam em milhares de traces
  iguais; elas continuam no log.
- **O mesmo id em todo lugar.** O trace id volta no cabecalho `X-Requisicao-Id`
  (o frontend mostra no trilho de comandas), aparece entre colchetes no log de
  cada servico e e o id do trace no Jaeger e no Cloud Trace.

## Ver no seu computador (Jaeger)

1. No `.env`, acrescente `rastreamento` ao `COMPOSE_PROFILES` e tire o `#` da
   linha do `RASTREAMENTO`:

   ```text
   COMPOSE_PROFILES=banco-local,servicos,gateway,frontend,rastreamento
   RASTREAMENTO=otlp
   ```

2. Suba de novo:

   ```bash
   docker compose up -d
   ```

3. Use o sistema (ou rode `python scripts/testar_gateway.py`) e abra
   `http://127.0.0.1:16686`. Em **Service**, escolha `gateway` e clique em
   **Find Traces**. Para achar uma requisicao especifica, cole o
   `X-Requisicao-Id` (o id da comanda no frontend) no campo de busca por trace id.

O Jaeger guarda os traces so na memoria: reiniciar o container apaga tudo.

## No Google Cloud (Cloud Trace)

Quando o sistema for para o Cloud Run (ver [09-plano-cloud-run.md](09-plano-cloud-run.md)):

| O que | Como |
|---|---|
| API | `gcloud services enable cloudtrace.googleapis.com` |
| Variavel em cada servico | `RASTREAMENTO=gcp` (o projeto vem do proprio ambiente) |
| Permissao | conta de servico de cada servico com o papel `roles/cloudtrace.agent` |
| Logs ligados ao trace | `LOG_JSON=1` e `GOOGLE_CLOUD_PROJECT=<projeto>`: cada linha leva `logging.googleapis.com/trace` e `.../spanId`, e o Cloud Logging mostra "Ver trace" na linha |
| Amostragem | `RASTREAMENTO_AMOSTRA` (padrao `1.0` = todos). O Cloud Trace cobra por span acima da cota gratis; para a demonstracao, todos |

- **Cabecalhos do Google.** O Cloud Run usa `traceparent` e
  `X-Cloud-Trace-Context`; o codigo le e escreve os dois
  (`CompositePropagator`), entao o trace do Gateway continua o que o Cloud Run
  abriu na entrada.
- **Envio em segundo plano.** Os spans saem em lotes (`BatchSpanProcessor`).
  Com CPU so durante a requisicao (padrao do Cloud Run, e o que o
  `implantar.sh` usa para nao gastar credito parado), o envio pode atrasar
  alguns segundos; se faltar trace na demonstracao, ligue CPU sempre alocada
  (`--no-cpu-throttling`) so durante a apresentacao.

## Variaveis

| Variavel | Padrao | Efeito |
|---|---|---|
| `RASTREAMENTO` | vazio | `gcp`, `otlp`, `console` ou vazio (nao envia) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://jaeger:4318` (compose) | destino do `otlp` |
| `RASTREAMENTO_AMOSTRA` | `1.0` | fracao dos traces gravados |
