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

**Causa:** quatro causas produzem exatamente a mesma mensagem: servidor parado,
IP externo desatualizado (muda quando a VM reinicia), regra de firewall VPC
ausente/sem a tag `grpc-server` na VM, ou servidor escutando so em `127.0.0.1`.

**Solucao:** o servidor escuta em `0.0.0.0` por padrao (`ENDERECO_ESCUTA`) e o
cliente passou a imprimir um checklist com as 4 causas na ordem de verificacao ao
receber `UNAVAILABLE`. O diagnostico detalhado esta na Etapa 8 de
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
