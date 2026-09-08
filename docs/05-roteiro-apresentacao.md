# 5. Roteiro da apresentacao (5 minutos)

Ultrapassar 5 minutos zera o criterio de apresentacao oral. O roteiro abaixo
cabe em 4:30, deixando folga.

## Antes de comecar (fazer 15 minutos antes)

- [ ] VM ligada; **IP externo do dia** anotado (ele muda a cada boot - ver `docs/04`, Etapa 3)
- [ ] Na VM: `docker compose ps` mostrando `Up` (o container sobe sozinho com `restart: always`) e `docker compose logs -f servidor` na tela
- [ ] No notebook: dois terminais abertos, um com o log da VM (SSH), outro na pasta do projeto
- [ ] Um pedido de teste ja feito e funcionando (confirma firewall e IP)
- [ ] Fontes do terminal aumentadas para o projetor
- [ ] `proto/restaurante.proto` aberto no editor, pronto para mostrar

## Divisao do tempo

| Tempo | O que fazer | O que falar |
|---|---|---|
| 0:00 - 0:40 | Slide/tela do `docs/01` com o diagrama | "Tema: delivery. Microsservico A e o cliente, na minha maquina; Microsservico B e o restaurante, numa VM do GCP. Eles conversam por gRPC sobre HTTP/2 com mensagens serializadas em Protobuf." |
| 0:40 - 1:30 | Mostrar `proto/restaurante.proto` | "Este e o contrato. Tres RPCs: ObterCardapio e CriarPedido sao unarios; AcompanharPedido e streaming do servidor. O CriarPedidoRequest tem um `repeated ItemPedido`, que e como o cliente manda varios itens com a quantidade de cada um. Os stubs de Python dos dois lados sao gerados deste arquivo." |
| 1:30 - 2:00 | Mostrar a VM: `docker compose ps` e o log do servidor + a regra de firewall no Console | "O servidor esta em um container na VM, escutando na 9090. Essa e a regra de firewall da VPC: ela libera `tcp:9090-9292` so para as instancias com a tag de rede `trabalho-sd`, e a porta do servidor foi escolhida dentro desse range." |
| 2:00 - 3:30 | **Rodar o cliente ao vivo**: `python -m src.cliente.cliente --host IP` | Cardapio aparece -> escolher 2 ou 3 itens com quantidades diferentes -> confirmar. Apontar para o log da VM: "cada chamada aparece aqui, em outra maquina." Mostrar o total calculado pelo servidor. |
| 3:30 - 4:00 | Deixar o streaming rolar | "Aqui a conexao continua aberta: o servidor empurra cada mudanca de status pela mesma chamada, ate a entrega." |
| 4:00 - 4:30 | Um erro proposital: `--itens XX99:1` | "Se o item nao existe, o servidor responde com INVALID_ARGUMENT e a lista de codigos validos. Erro tratado pelo status code do gRPC, nao por texto solto." |

## Comandos exatos da demonstracao

```bash
# terminal 1 (SSH na VM) - deixar rodando
docker compose logs -f servidor

# terminal 2 (notebook) - demonstracao principal
python -m src.cliente.cliente --host 34.123.45.67

# terminal 2 - erro proposital, se sobrar tempo
python -m src.cliente.cliente --host 34.123.45.67 --itens XX99:1 --cliente Teste
```

## Plano B

| Se der errado | Faca |
|---|---|
| A VM nao responde (rede da sala, firewall) | suba o servidor local com `docker compose up -d servidor` e rode o cliente com `--host localhost`; mostre no Console que a VM esta no ar e a regra de firewall criada |
| Docker travado no notebook | use o caminho sem Docker: `python -m src.servidor.servidor` e `python -m src.cliente.cliente` |
| Sem tempo para digitar o pedido | use `--itens PR01:2,BE02:3,SO02:1 --cliente "Matheus" --endereco "Rua A, 10"` |

## Frases-chave para os criterios de avaliacao

- **Conexao gRPC estabelecida:** "o canal e aberto contra `IP:9090`; o log do
  servidor mostra a chamada chegando de outra maquina."
- **Serializacao:** "as mensagens nao trafegam como JSON: sao serializadas em
  binario pelo Protobuf, a partir das tags de campo definidas no `.proto`."
- **Firewall VPC:** "a regra `trabalho-sd` libera `tcp:9090-9292` para as VMs
  marcadas com a tag de rede `trabalho-sd`; o servidor escuta na 9090, dentro
  desse range."
