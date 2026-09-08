# 1. Visao geral do sistema

Leia este documento **antes** de rodar qualquer comando. Ele explica o que o
sistema faz, quem sao os dois microsservicos e como o sistema reage a cada
situacao.

## 1.1 O dominio: delivery de restaurante

O tema escolhido e um sistema de **delivery**. A **Cantina do Maia** publica um
cardapio variado (entradas, pratos, bebidas e sobremesas) e recebe pedidos com
varios itens e quantidades diferentes de cada item.

A comunicacao interna de backend entre os dois microsservicos e feita por
**gRPC** sobre **HTTP/2**, com as mensagens serializadas em **Protocol Buffers**
(formato binario definido em `proto/restaurante.proto`).

## 1.2 Os dois microsservicos

| | Microsservico A | Microsservico B |
|---|---|---|
| Papel | Cliente gRPC | Servidor gRPC |
| Onde roda | Maquina local (notebook) | VM do Google Cloud Platform |
| Codigo | `src/cliente/cliente.py` | `src/servidor/` |
| O que faz | Consulta o cardapio, monta o pedido e acompanha a entrega | Publica o cardapio, valida e precifica o pedido, evolui o status |

O cliente **nunca** calcula o preco. Ele envia apenas codigos de item e
quantidades; quem consulta o cardapio, valida, precifica e decide e o servidor.
Essa separacao e o que caracteriza a comunicacao interna entre servicos.

## 1.3 Fluxo de comunicacao

```text
  MAQUINA LOCAL                              VM DO GCP (porta 9090/TCP)
+----------------------+                  +------------------------------+
|  Microsservico A     |                  |  Microsservico B             |
|  cliente.py          |                  |  servidor.py                 |
|                      |                  |    +----------------------+  |
|  1. ObterCardapio  --|---- gRPC/HTTP2 ->|--> | RestauranteService   |  |
|     <---- cardapio --|<--- Protobuf ----|--- |   servico.py         |  |
|                      |                  |    |   cardapio.py        |  |
|  2. CriarPedido    --|---- gRPC/HTTP2 ->|--> |   repositorio.py     |  |
|     <-- confirmacao -|<--- Protobuf ----|--- |                      |  |
|                      |                  |    |                      |  |
|  3. AcompanharPedido-|---- gRPC/HTTP2 ->|--> |                      |  |
|     <-- status 1..N -|<=== stream ======|=== |                      |  |
+----------------------+                  |    +----------------------+  |
                                          +------------------------------+
```

1. **ObterCardapio** (RPC unario) - o cliente pede o cardapio; o servidor
   responde com a lista de itens, precos e disponibilidade.
2. **CriarPedido** (RPC unario) - o cliente envia nome, endereco e a lista de
   `(codigo, quantidade)`; o servidor valida item a item, calcula o total, gera
   um UUID e guarda o pedido.
3. **AcompanharPedido** (streaming do servidor) - uma requisicao, varias
   respostas na mesma conexao: `RECEBIDO -> EM_PREPARO -> PRONTO ->
   SAIU_PARA_ENTREGA -> ENTREGUE`. E a prova visual de que a conexao gRPC fica
   aberta e as mensagens sao serializadas em sequencia.

## 1.4 Como o sistema reage

O servidor responde com **status codes do gRPC**. Uma requisicao invalida nunca
devolve uma resposta pela metade: devolve codigo + mensagem, e o cliente mostra
os dois no terminal.

| Situacao | Status gRPC | Mensagem do servidor | O que o cliente mostra |
|---|---|---|---|
| Pedido sem nome do cliente | `INVALID_ARGUMENT` | `Informe o nome do cliente.` | erro e encerra com codigo 1 |
| Pedido sem nenhum item | `INVALID_ARGUMENT` | `O pedido precisa de pelo menos um item.` | erro e encerra |
| Quantidade zero ou negativa | `INVALID_ARGUMENT` | `Quantidade invalida (0) para o item PR01...` | erro e encerra |
| Codigo de item inexistente | `INVALID_ARGUMENT` | `Item 'XX99' nao existe no cardapio. Codigos validos: ...` | erro com a lista de codigos validos |
| Item esgotado (`disponivel = false`) | `FAILED_PRECONDITION` | `Item 'PR05' (Moqueca de peixe) esta indisponivel hoje.` | erro e encerra |
| Categoria inexistente no cardapio | `NOT_FOUND` | `Categoria 'Pizzas' nao existe no cardapio.` | erro e encerra |
| Acompanhar pedido inexistente | `NOT_FOUND` | `Pedido 'nao-existe' nao encontrado.` | erro e encerra |
| Servidor parado, IP errado ou firewall fechado | `UNAVAILABLE` | (erro de transporte) | erro + checklist de 4 causas provaveis |
| Cliente fecha o terminal no meio do stream | - | - | servidor detecta `context.is_active() == False`, encerra o stream e loga a desconexao |

No caminho feliz, o servidor:

- calcula `subtotal = preco * quantidade` de cada linha e o `total` do pedido;
- estima a entrega em `15 + 3 x (unidades)` minutos;
- gera um `pedido_id` UUID novo a cada pedido;
- registra tudo no terminal (esse terminal e o que aparece na demonstracao).

## 1.5 Estrutura do projeto

```text
proto/restaurante.proto     contrato compartilhado (fonte da verdade)
scripts/gerar_stubs.py      gera os stubs Python a partir do .proto
src/servidor/servidor.py    sobe o servidor gRPC (porta, threads, reflection)
src/servidor/servico.py     implementa os 3 RPCs e as regras de validacao
src/servidor/cardapio.py    catalogo de itens do restaurante
src/servidor/repositorio.py armazenamento dos pedidos em memoria (thread-safe)
src/cliente/cliente.py      terminal interativo do pedido
src/gerado/                 stubs gerados (artefato de build, nao versionado)
docs/                       esta documentacao
markdown/                   manual, prontuario de problemas e changelog
```

## 1.6 Escolhas tecnicas

| Decisao | Motivo |
|---|---|
| gRPC + Protobuf | exigencia do trabalho; binario e mais compacto e rapido que JSON |
| Porta 9090/TCP | esta dentro do range que a regra de firewall da VPC ja libera para a VM; configuravel por `PORTA` e `--porta` |
| Canal `insecure` (plaintext) | o objetivo e demonstrar o fluxo de comunicacao; TLS exigiria certificado e sairia do escopo |
| Armazenamento em memoria | o dominio do trabalho e a comunicacao entre servicos, nao persistencia |
| Docker | mesma execucao no notebook e na VM; nao depende de Python instalado na VM |
| Reflection habilitada | permite provar o servico no ar com `grpcurl`, sem copiar o `.proto` |
