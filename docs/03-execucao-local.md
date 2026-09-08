# 3. Execucao local (dois terminais)

Antes de subir na nuvem, rode tudo no proprio notebook. O terminal 1 e o
restaurante (servidor), o terminal 2 e o cliente.

## 3.1 Caminho recomendado: Docker

### Terminal 1 - servidor

```bash
docker compose up --build servidor
```

Saida esperada:

```text
restaurante-servidor  | ==============================================================
restaurante-servidor  |  Cantina do Maia - servidor gRPC
restaurante-servidor  |  Servidor gRPC ouvindo em 0.0.0.0:9090
restaurante-servidor  |  Servico: restaurante.RestauranteService
restaurante-servidor  |  Aguardando pedidos... (Ctrl+C encerra)
restaurante-servidor  | ==============================================================
```

Deixe esse terminal aberto: e nele que aparece cada chamada recebida.

### Terminal 2 - cliente

```bash
docker compose run --rm cliente
```

O `docker compose run` ja conecta o cliente ao servico `servidor` pela rede
interna do Compose.

## 3.2 Caminho alternativo: Python direto (sem Docker)

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python scripts/gerar_stubs.py
```

Terminal 1:

```bash
python -m src.servidor.servidor
```

Terminal 2:

```bash
python -m src.cliente.cliente
```

## 3.3 O que acontece no terminal do cliente

1. O cardapio completo e listado por categoria, com preco e itens esgotados
   marcados como `[INDISPONIVEL HOJE]`:

```text
==============================================================
CARDAPIO - Cantina do Maia
==============================================================

PRATOS
--------------------------------------------------------------
  PR01  File a parmegiana                R$ 62,90
        File empanado, molho de tomate e queijo, com arroz
  PR05  Moqueca de peixe                 R$ 79,90   [INDISPONIVEL HOJE]
        Peixe branco, leite de coco e dende
```

2. O cliente informa nome e endereco, e monta o pedido item a item:

```text
==============================================================
MONTE O SEU PEDIDO
==============================================================
Digite o codigo do item (ex: PR01) e a quantidade.
Deixe o codigo em branco para finalizar.

Codigo do item (ENTER para finalizar): PR01
  Quantidade de 'File a parmegiana': 2
  > Adicionado: 2x File a parmegiana
  > Carrinho: 2 unidade(s), parcial R$ 125,80
```

3. Ao dar ENTER com o campo vazio, o pedido e enviado e o servidor responde:

```text
==============================================================
PEDIDO CONFIRMADO
==============================================================
ID do pedido : dbcabd4b-6287-46cb-ad37-421ec092f8d7
Status       : RECEBIDO

Item                              Qtd       Unit.     Subtotal
--------------------------------------------------------------
File a parmegiana                   2    R$ 62,90    R$ 125,80
Suco natural de laranja             3    R$ 12,00     R$ 36,00
Petit gateau                        1    R$ 27,90     R$ 27,90
--------------------------------------------------------------
TOTAL                                                R$ 189,70

Tempo estimado: 33 minutos
Pedido recebido pela Cantina do Maia. Entrega estimada em 33 minutos.
```

4. Em seguida o stream de acompanhamento imprime cada status conforme chega:

```text
==============================================================
ACOMPANHAMENTO EM TEMPO REAL (streaming gRPC)
==============================================================
[22:24:11] RECEBIDO           Pedido confirmado pela cozinha.
[22:24:13] EM_PREPARO         A cozinha comecou a preparar o seu pedido.
[22:24:15] PRONTO             Pedido pronto, aguardando o entregador.
[22:24:17] SAIU_PARA_ENTREGA  Entregador a caminho do endereco informado.
[22:24:19] ENTREGUE           Pedido entregue. Bom apetite!

Acompanhamento encerrado pelo servidor.
```

## 3.4 O que aparece no terminal do servidor

```text
[22:24:10] ObterCardapio: categoria='todas' -> 13 itens
[22:24:11] CriarPedido: cliente='Matheus' itens=[('PR01', 2), ('BE02', 3), ('SO02', 1)]
[22:24:11] Pedido dbcabd4b-6287-46cb-ad37-421ec092f8d7 aceito: 3 itens, 6 unidades, total R$ 189.70
[22:24:11] AcompanharPedido: pedido_id='dbcabd4b-6287-46cb-ad37-421ec092f8d7'
[22:24:13] Pedido dbcabd4b-6287-46cb-ad37-421ec092f8d7 -> EM_PREPARO
```

## 3.5 Modo nao interativo (util para ensaiar a apresentacao)

```bash
python -m src.cliente.cliente --itens PR01:2,BE02:3,SO02:1 \
  --cliente "Matheus" --endereco "Rua das Flores, 100"
```

Outras opcoes do cliente:

| Opcao | Efeito |
|---|---|
| `--host` / `--porta` | endereco do servidor (padrao `localhost:9090`) |
| `--cliente` / `--endereco` | preenche os dados sem perguntar |
| `--categoria Pratos` | pede so uma categoria do cardapio |
| `--itens PR01:2,BE01:1` | monta o pedido sem interacao |
| `--sem-acompanhar` | encerra apos a confirmacao, sem abrir o stream |

Tambem funcionam as variaveis de ambiente `SERVIDOR_HOST` e `SERVIDOR_PORTA`.

## 3.6 Testando os erros

```bash
python -m src.cliente.cliente --itens XX99:1 --cliente Teste   # INVALID_ARGUMENT
python -m src.cliente.cliente --itens PR01:0 --cliente Teste   # INVALID_ARGUMENT
python -m src.cliente.cliente --itens PR05:1 --cliente Teste   # FAILED_PRECONDITION
python -m src.cliente.cliente --categoria Pizzas --itens PR01:1 --cliente Teste  # NOT_FOUND
```

Com o servidor parado, qualquer chamada devolve `UNAVAILABLE` e o cliente
imprime o checklist de causas provaveis.

## 3.7 Encerrando

```bash
docker compose down
```
