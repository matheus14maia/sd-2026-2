# 7. Tolerancia a falhas (resiliencia)

Um sistema distribuido falha por partes: um microsservico cai, fica lento ou
reinicia no meio de uma chamada. Este documento mostra como o delivery reage a
isso, onde fica cada mecanismo no codigo e como demonstrar tudo no seu
computador.

Resumo do que acontece quando o **Catalogo cai**:

| Rota | Resposta | Por que |
|---|---|---|
| `GET /cardapio` | **200**, com `"origem": "cache"` e um `"aviso"` | o Gateway devolve a ultima lista boa que guardou (fallback) |
| `POST /pedidos` | **503** em ~0,5 s, com `Retry-After: 5` e `"dependencia": "catalogo"` | sem o Catalogo nao da para confirmar preco e disponibilidade; nada e gravado |
| `GET /pedidos`, `/auth/*` | **200** normal | Pedidos e Usuarios continuam no ar: a falha fica isolada |
| depois de 3 falhas seguidas | **503 em ~1 ms** (circuito aberto) ou 200 do cache | o Gateway para de chamar o Catalogo por 15 s |
| Catalogo volta | tudo normal em ate ~15 s, sozinho | o circuito libera uma chamada de teste e fecha |

## Mecanismos

| Mecanismo | Onde | O que faz |
|---|---|---|
| Timeout e prazo total | `src/comum/resiliencia.py` (`ClienteResiliente`) | cada tentativa tem `GRPC_TIMEOUT` (5 s) e a soma das tentativas tem `GRPC_PRAZO_TOTAL` (12 s): nenhuma requisicao fica pendurada |
| Propagacao do prazo | `src/pedidos/cliente_catalogo.py` | o Pedidos usa o tempo que resta da chamada do Gateway (`context.time_remaining()`) para chamar o Catalogo e responde antes de o Gateway desistir |
| Retry com backoff exponencial e jitter | `ClienteResiliente.chamar` | ate `RETRY_TENTATIVAS` (3) tentativas, esperando ~0,2 s, ~0,4 s... com sorteio de 50% a 100% para varios clientes nao repetirem juntos |
| So repete o que e seguro | `SEMPRE_REPETIR` / `REPETIR_SE_IDEMPOTENTE` | `UNAVAILABLE` sempre (neste sistema ele sai antes de gravar qualquer coisa); `DEADLINE_EXCEEDED` e `CANCELLED` so em operacao idempotente |
| Idempotencia | `CriarPedido`, `AtualizarStatus` | o Gateway gera o `pedido_id` antes de chamar; repetir a chamada devolve o pedido ja gravado (`ON CONFLICT DO NOTHING`). Repetir o mesmo status responde 200 sem nova escrita |
| Circuit breaker | `Disjuntor` | `FECHADO` -> `ABERTO` apos `DISJUNTOR_FALHAS` (3) chamadas seguidas que falharam mesmo com retry; `ABERTO` recusa na hora por `DISJUNTOR_ABERTO_SEGUNDOS` (15 s); depois `MEIO_ABERTO` libera uma chamada de teste |
| Um circuito por servico | `ClientesGrpc.resiliencia` | Catalogo fora nao abre o circuito de Pedidos nem de Usuarios |
| Sem tempestade de retries | metadado gRPC `x-falha-dependencia` | quando o Pedidos responde "o Catalogo falhou", o Gateway nao repete o `CriarPedido` (o Pedidos ja repetiu) e nao conta a falha contra o Pedidos |
| Fallback (degradacao graciosa) | `ClientesGrpc.listar_cardapio` | a ultima lista boa de cada categoria fica em memoria por `CACHE_CARDAPIO_SEGUNDOS` (30 min) e e usada se o Catalogo nao responder |
| Reconexao rapida | `src/comum/canal.py` | no padrao do gRPC o canal pode levar ate 2 min para tentar reconectar; aqui o intervalo maximo e 5 s, o DNS e consultado de novo em 1 s, e a chamada de teste do circuito espera a conexao (`wait_for_ready`) |
| Banco fora vira 503 | `InterceptadorServidor` e `criar_pool` | erro de conexao com o PostgreSQL vira `UNAVAILABLE` ("Banco de dados indisponivel"), o pool testa a conexao antes de usar (`check`) e reabre sozinho |
| Health check | `grpc.health.v1` nos tres servicos | usado pelo `HEALTHCHECK` das imagens (`docker compose ps` mostra `healthy`) e pela rota `GET /saude/servicos` |
| Encerramento limpo | `executar()` em `src/comum/servidor_grpc.py` | no `SIGTERM` o servico marca o health como `NOT_SERVING` e termina as chamadas em andamento (5 s) |
| Reinicio automatico | `restart: always` no compose | container que cai volta sozinho |
| Tempo real que reconecta | `src/gateway/eventos.py`, `src/pedidos/eventos.py`, `assinarEventos` no frontend | se o Pedidos cair, o stream do Gateway tenta de novo (1 s ate 15 s) e os navegadores veem "Reconectando..."; se o banco cair, o `LISTEN` reconecta sozinho |

## Erros vistos pelo cliente

| Situacao | HTTP | Corpo |
|---|---|---|
| microsservico fora (depois do retry) | 503 + `Retry-After: 5` | `{"mensagem": "...", "codigo_grpc": "UNAVAILABLE"}` |
| dependencia do microsservico fora | 503 + `Retry-After: 5` | `{"mensagem": "Catalogo indisponivel no momento ...", "codigo_grpc": "UNAVAILABLE", "dependencia": "catalogo"}` |
| circuito aberto | 503 + `Retry-After: <segundos ate o teste>` | `{"mensagem": "Servico de catalogo temporariamente indisponivel (circuito aberto). Tente novamente em 12 s.", "servico": "catalogo", "circuito": "ABERTO"}` |
| servico demorou demais | 503 | `"codigo_grpc": "DEADLINE_EXCEEDED"` |
| cardapio servido do cache | 200 | lista normal + `"origem": "cache"`, `"salvo_em"` e `"aviso"` |

## Parametros

Todos tem padrao e podem ser trocados no `.env` (o compose repassa para o
Gateway e para o Pedidos).

| Variavel | Padrao | Efeito |
|---|---|---|
| `GRPC_TIMEOUT` | `5` | segundos de cada tentativa |
| `GRPC_PRAZO_TOTAL` | `12` | segundos para todas as tentativas de uma chamada |
| `RETRY_TENTATIVAS` | `3` | tentativas por chamada (1 = sem retry) |
| `RETRY_ESPERA_INICIAL` / `RETRY_ESPERA_MAXIMA` | `0.2` / `2.0` | base do backoff e teto, em segundos |
| `DISJUNTOR_FALHAS` | `3` | chamadas seguidas com falha para abrir o circuito |
| `DISJUNTOR_ABERTO_SEGUNDOS` | `15` | tempo com o circuito aberto antes da chamada de teste |
| `CACHE_CARDAPIO_SEGUNDOS` | `1800` | idade maxima da lista usada como fallback |

Injecao de falha (para a demonstracao), por servico:

| Variavel no `.env` | Efeito |
|---|---|
| `CATALOGO_FALHA_PERCENTUAL=50` | o Catalogo responde `UNAVAILABLE` em 50% das chamadas (0 a 100) |
| `CATALOGO_FALHA_ATRASO_MS=6000` | cada chamada ao Catalogo demora 6 s (maior que o timeout de 5 s) |
| `USUARIOS_...`, `PEDIDOS_...` | o mesmo para os outros servicos |

Depois de mudar o `.env`, recrie so o servico: `docker compose up -d catalogo`.
O log dele mostra `INJECAO DE FALHA LIGADA` na subida. Para voltar ao normal,
apague a linha (ou ponha `0`) e rode o mesmo comando.

## Demonstracao no seu computador

Com a pilha no ar (`docker compose up -d --build`, ver
[03-execucao-local.md](03-execucao-local.md)), entre no frontend
(`http://localhost` ou `http://127.0.0.1`) e abra a aba **Saude dos servicos**. Ela mostra, a cada 3 s,
o health check gRPC de cada microsservico e o estado do circuito no Gateway.

### 1. Queda de um microsservico

```bash
docker compose stop catalogo
```

1. Na aba Saude, o Catalogo aparece **Fora do ar**.
2. Clique em **Carregar cardapio**: 200, com o cardapio salvo (a aba Cardapio
   mostra a faixa "Catalogo fora do ar: cardapio salvo pelo Gateway").
3. Clique em **Fazer pedido de teste**: 503 em menos de 1 s, nada gravado.
4. Aba Pedidos: continua listando normalmente (isolamento).
5. Depois de 3 falhas o circuito fica **Aberto**: as chamadas falham em ~1 ms.

```bash
docker compose start catalogo
```

6. Em ate ~15 s o circuito passa por **Meio aberto** e volta a **Fechado**.

### 2. Falha parcial (retry)

No `.env`: `CATALOGO_FALHA_PERCENTUAL=50`, depois `docker compose up -d catalogo`.

```bash
python scripts/testar_resiliencia.py --rajada 30
docker compose logs gateway | grep repetindo        # PowerShell: | Select-String repetindo
```

Metade das chamadas ao Catalogo falha, mas quase todas as respostas vem do
Catalogo assim mesmo: o Gateway repete e o usuario nao percebe. As poucas que
falham 3 vezes seguidas caem no cache. Nos logs:

```text
[10:07:00] [176f0936] WARNING: catalogo.ListarItens falhou com UNAVAILABLE (tentativa 1/3); repetindo em 145 ms
[10:07:00] [176f0936] NOTICE: catalogo.ListarItens respondeu na tentativa 2
```

### 3. Servico lento (timeout)

No `.env`: `CATALOGO_FALHA_ATRASO_MS=6000`, depois `docker compose up -d catalogo`.
`GET /cardapio` desiste do Catalogo dentro do prazo total (12 s) e usa o cache.
`POST /pedidos` responde 503 em ~4,5 s: o Pedidos desistiu antes do Gateway
(prazo propagado), e o Gateway nao repetiu. Depois de 3 chamadas lentas o
circuito abre e as respostas voltam a ser imediatas.

### 4. Roteiro automatico

```bash
python scripts/testar_resiliencia.py          # usa DEMO_SENHA; derruba e religa o Catalogo
```

```text
== 1. Tudo no ar
OK   GET /cardapio vem do Catalogo  (status 200, origem catalogo)
== 2. Derrubando o Catalogo
    $ docker compose stop catalogo
== 3. Fallback do cardapio
OK   GET /cardapio responde 200 com a lista salva  (status 200, origem cache, 2561 ms)
== 4. Pedido com o Catalogo fora
OK   POST /pedidos responde 503 sem gravar  (status 503 em 2.4 s, Retry-After 5)
== 5. Isolamento: Pedidos continua no ar
OK   GET /pedidos responde 200  (status 200)
== 6. Circuit breaker
OK   Circuito do Catalogo ABERTO  ({"circuito": "ABERTO", "falhas_seguidas": 3, "reabre_em_segundos": 15})
OK   Com o circuito aberto, categoria sem lista salva falha na hora com 503  (status 503 em 2 ms, Retry-After 15)
== 7. Recuperacao
    $ docker compose start catalogo
OK   GET /cardapio volta a vir do Catalogo  (status 200, origem catalogo)
OK   Circuito do Catalogo FECHADO
OK   POST /pedidos volta a gravar (201)  (status 201)

Tolerancia a falhas OK.
```

`--derrubar` e `--religar` trocam os comandos usados (por exemplo, para
derrubar outro servico).

## Seguir uma requisicao pelos logs

Toda resposta do Gateway leva o cabecalho `X-Requisicao-Id`. O mesmo id vai para
os microsservicos nos metadados gRPC (`traceparent`), e cada linha de log mostra
os 8 primeiros caracteres dele:

```text
delivery-gateway   | [12:49:28] [e99430b1] POST /pedidos -> 201 (22 ms) [professor]
delivery-pedidos   | [12:49:28] [e99430b1] CriarPedido: pedido=c841893b-... usuario=46034422-... cliente='Professor' itens=[('PR02', 1)]
delivery-catalogo  | [12:49:28] [e99430b1] ConsultarItens: ['PR02'] -> 1 encontrados
delivery-pedidos   | [12:49:28] [e99430b1] Pedido c841893b-... gravado: 1 itens, 1 unidades, total R$ 74.00
```

No frontend, clique numa comanda do rodape para ver o id; depois
`docker compose logs | grep e99430b1` (PowerShell: `| Select-String e99430b1`).

Com `LOG_JSON=1` cada linha sai em JSON com `severity`, `message` e o trace nos
campos `logging.googleapis.com/trace` e `.../spanId`, o formato que o Cloud
Logging do GCP entende (usado quando o sistema for para o Cloud Run).

O mesmo id e o do trace: no Jaeger (local) ou no Cloud Trace da para ver cada
tentativa do retry como um span separado, com a falha simulada marcada (ver
[08-rastreamento.md](08-rastreamento.md)).
