# Best Practices

> Padroes e convencoes deste projeto. Ler inteiro antes de qualquer alteracao.
> Atualizar sempre que um padrao novo for descoberto durante o trabalho.

---

## Arquitetura geral

Dois microsservicos que conversam por gRPC sobre HTTP/2, com mensagens
serializadas em Protocol Buffers:

- **Microsservico A (cliente)** - `src/cliente/cliente.py`, roda na maquina local.
- **Microsservico B (servidor)** - `src/servidor/`, roda em container numa VM do GCP.

O contrato `proto/restaurante.proto` e a fronteira entre os dois. Nenhum dos
lados assume nada que nao esteja no contrato.

## Stack

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 |
| Comunicacao | gRPC (grpcio 1.68.1) sobre HTTP/2 |
| Serializacao | Protocol Buffers proto3 (protobuf 5.29.1) |
| Empacotamento | Docker + Docker Compose (imagem unica para os dois papeis) |
| Infraestrutura | Google Compute Engine, Debian 12, firewall VPC (tag de rede `trabalho-sd`, range `tcp:9090-9292`) |

## Padroes de codigo

- **O `.proto` e a fonte da verdade.** Mudou o contrato, regere os stubs e ajuste
  os dois lados na mesma alteracao. Nunca deixe cliente e servidor com contratos
  diferentes.
- **Stubs sao artefato de build.** Ficam em `src/gerado/`, sao gerados por
  `scripts/gerar_stubs.py` (e no `docker build`), nao sao versionados e nunca sao
  editados a mao.
- O `protoc` gera `import restaurante_pb2` (absoluto). Como os stubs vivem dentro
  do pacote `src.gerado`, `scripts/gerar_stubs.py` reescreve para
  `from . import restaurante_pb2`. Se trocar o layout de pastas, ajuste esse
  passo do script.
- **Codigo e mensagens em portugues sem acento.** Evita problema de encoding em
  terminal de VM e no Console do GCP.
- **Erro sempre vira status code do gRPC** (`context.abort(...)`), nunca uma
  resposta "vazia" ou um campo `erro` na mensagem. O cliente trata `grpc.RpcError`
  em um lugar so (`main()` do cliente).
- Toda configuracao que muda entre maquinas vem de variavel de ambiente com
  valor padrao: `PORTA`, `ENDERECO_ESCUTA`, `MAX_WORKERS`, `SERVIDOR_HOST`,
  `SERVIDOR_PORTA`.

## Padroes de dados

- Precos em `double`, em reais. O **servidor** e o unico que precifica: o cliente
  envia apenas `codigo` e `quantidade`.
- `subtotal = round(preco * quantidade, 2)`; o `total` e a soma dos subtotais,
  tambem arredondada.
- Tempo estimado: `15 + 3 x unidades` minutos (`TEMPO_BASE_MINUTOS` e
  `TEMPO_POR_UNIDADE_MINUTOS` em `src/servidor/servico.py`).
- `pedido_id` e um UUID4 gerado no servidor.
- Codigos de item tem 4 caracteres: 2 letras da categoria + 2 digitos
  (`EN01`, `PR01`, `BE01`, `SO01`). O cliente normaliza para maiusculo antes de
  enviar, entao `pr01` tambem funciona.
- Em proto3, todo `enum` precisa do valor `0`: e o `STATUS_DESCONHECIDO`.

## Concorrencia

- O servidor atende com `ThreadPoolExecutor(max_workers=10)`: **todo** estado
  compartilhado precisa de lock. `RepositorioPedidos` usa `threading.Lock`.
- Em stream longo, checar `context.is_active()` antes de cada `yield`, senao o
  servidor continua trabalhando para um cliente que ja fechou o terminal.

## Regras de negocio

| Regra | Onde |
|---|---|
| Nome do cliente obrigatorio | `servico.CriarPedido` |
| Pedido precisa de >= 1 item | `servico.CriarPedido` |
| Quantidade > 0 por item | `servico.CriarPedido` |
| Item precisa existir no cardapio | `cardapio.buscar` |
| Item com `disponivel = False` e recusado (`FAILED_PRECONDITION`) | `servico.CriarPedido` |
| Acompanhar exige pedido existente (`NOT_FOUND`) | `servico.AcompanharPedido` |

## Convencoes importantes

- Os pedidos ficam **em memoria**: reiniciou o servidor, perdeu os pedidos. E
  proposital (o escopo do trabalho e comunicacao, nao persistencia), mas explica
  o `NOT_FOUND` ao acompanhar um pedido antigo.
- **A porta do servico e escolhida a partir do que o firewall da VPC ja libera,
  nao o contrario.** A regra `trabalho-sd` do projeto libera
  `tcp:3000,5050,8000,9090-9292`; por isso a porta padrao e `9090` e nao a `50051`
  convencional do gRPC. Descobrir isso so na hora de conectar custa uma sessao de
  depuracao de `UNAVAILABLE` que parece problema de codigo e nao e.
- Mudou a porta? Ela aparece em seis lugares que precisam andar juntos:
  `docker-compose.yml` (env `PORTA`, mapeamento `ports`, default de
  `SERVIDOR_PORTA`), `Dockerfile` (`EXPOSE`), `src/servidor/servidor.py`
  (default de `PORTA`), `src/cliente/cliente.py` (`PORTA_PADRAO`), a regra de
  firewall do GCP e as docs `README.md`, `docs/01`, `docs/02`, `docs/03`,
  `docs/04` e `docs/05`.
- **A tag de rede tem que estar na instancia, nao so na regra.** Uma regra de
  firewall com `targetTags` so vale para VMs marcadas com aquela tag. Regra
  correta + VM sem a tag produz exatamente o mesmo `UNAVAILABLE` de servidor
  desligado.
- **O container roda com `TZ=America/Sao_Paulo`.** A imagem `python:3.12-slim`
  usa UTC por padrao; sem a variavel, os horarios impressos pelo servidor (log e
  campo `horario` do stream) saem 3h a frente do relogio do notebook. Na
  demonstracao as duas telas aparecem juntas.
- **O container do servidor sobe sozinho** (`restart: always` +
  `systemctl is-enabled docker` = `enabled`). Isso permite parar e religar a VM
  pelo Console sem nenhum comando Docker. `docker compose down` **remove** o
  container e derruba esse comportamento - por isso ele nao aparece no ciclo
  normal de `docs/04`.
- O canal e `insecure` (plaintext) de proposito: TLS exigiria certificado e sai
  do escopo da disciplina.
- O log do servidor e parte da demonstracao. Toda chamada recebida deve imprimir
  uma linha com horario, RPC e parametros relevantes.
- `docs/` e publico. Nao versione material da disciplina nem configuracao local
  de ferramenta (ver `.gitignore`).
