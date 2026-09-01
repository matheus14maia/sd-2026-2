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

## 2026-08-31

| Horario | Task | Detalhe |
|---------|------|---------|
| 22:40 | Documentacao completa | Escritos `README.md` e `docs/01` a `docs/05`: visao geral e tabela de reacao do sistema, contrato explicado campo a campo, execucao local, passo a passo do GCP (VM + firewall VPC + Docker) e roteiro de 5 minutos da apresentacao. |
| 22:30 | Empacotamento em Docker | `Dockerfile` (python:3.12-slim, gera os stubs no build) e `docker-compose.yml` com os servicos `servidor` (publica 50051) e `cliente` (profile, tty). Validado: cliente local -> container e cliente em container -> servidor. |
| 22:20 | Cliente gRPC | `src/cliente/cliente.py`: lista o cardapio por categoria, monta o pedido item a item com quantidade, envia `CriarPedido`, consome o stream de acompanhamento e trata `grpc.RpcError` com checklist para `UNAVAILABLE`. Modo `--itens CODIGO:QTD` para ensaio. |
| 22:10 | Servidor gRPC | `src/servidor/`: `cardapio.py` (13 itens em 4 categorias, um indisponivel de proposito), `repositorio.py` (memoria + `threading.Lock`), `servico.py` (3 RPCs e validacoes por status code), `servidor.py` (ThreadPool, reflection, `PORTA` por env, shutdown limpo). |
| 22:00 | Contrato Protobuf | `proto/restaurante.proto` com `RestauranteService`: `ObterCardapio` e `CriarPedido` unarios e `AcompanharPedido` em server streaming; `CriarPedidoRequest` com `repeated ItemPedido` para varios itens e quantidades. `scripts/gerar_stubs.py` gera os stubs e corrige o import relativo. |
