# 6. Frontend

O frontend (`frontend/`) e uma aplicacao React (Vite) servida pelo nginx. Ele
**so conversa com o API Gateway**: nao conhece endereco nem protocolo dos
microsservicos. Todas as chamadas saem de um unico modulo, `src/api.js`.

## Telas

| Tela | O que faz | Chamadas ao Gateway |
|---|---|---|
| Entrar / Criar conta | login e cadastro; campos obrigatorios com asterisco (dica "Campo obrigatorio" ao passar o mouse); os formularios nao validam no navegador, entao o 400 do Gateway aparece embaixo de cada campo | `POST /auth/login`, `POST /auth/cadastro` |
| Cardapio | abas por categoria (Todos, Entradas, Pratos principais, Sobremesas, Bebidas; o filtro e feito no servidor), sacola e pedido em nome de quem esta logado (so pede o endereco); botao "Finalizar pedido e acender as chamas" com animacao de chamas; se o Catalogo cair, mostra a faixa "cardapio em modo de seguranca" | `GET /cardapio`, `GET /cardapio?categoria=`, `POST /pedidos` |
| Pedidos | "Meus pedidos" para cliente, "Todos os pedidos" para a cozinha; filtros por etapa, periodo, prato e (cozinha) cliente; horario de cada etapa, previsao de entrega com o tempo que falta; a cozinha avanca a etapa e pode tentar pular uma (409); tudo se atualiza sozinho | `GET /pedidos?...`, `GET /pedidos/{id}`, `PATCH /pedidos/{id}/status`, `GET /pedidos/eventos` |
| Cozinha (so papel `cozinha`) | liga e desliga pratos do cardapio do dia e ajusta preco | `GET /cardapio`, `PATCH /cardapio/{codigo}` |
| Saude dos servicos (so papel `cozinha`) | a cada 3 s, health check gRPC de cada microsservico, o estado do circuit breaker no Gateway e da conexao de tempo real; botoes para carregar o cardapio e fazer um pedido de teste durante uma falha (ver [07-resiliencia.md](07-resiliencia.md)) | `GET /saude/servicos`, `GET /cardapio`, `POST /pedidos` |
| Testes de seguranca (so papel `cozinha`) | botoes que mandam requisicoes erradas de proposito: sem token, token adulterado, token editado, senha errada (401), cliente mudando preco ou vendo a saude (403), payload invalido (400), item inexistente (400), item indisponivel (409), pedido em nome de outra pessoa (400), cliente vendo pedido de outro (404) | varias |

**Tempo real.** Depois do login o app abre uma conexao com `GET /pedidos/eventos`
(ver [05-api-gateway.md](05-api-gateway.md#tempo-real-server-sent-events)). O
topo mostra "Ao vivo" (ou "Reconectando..."), a lista e o detalhe do pedido se
atualizam sozinhos, e aparecem avisos: a cozinha e avisada de cada pedido novo e
o cliente de cada etapa do pedido dele.

**Mensagens.** A API responde sem acento (convencao do backend); o
`src/mensagens.js` transforma as mensagens conhecidas em frases com acento para a
tela (por exemplo, `nao deve estar vazio` no endereco vira "Informe o endereco de
entrega."). A aba de testes e o trilho de comandas mostram a resposta crua.

No rodape fica o **trilho de comandas**: cada chamada feita ao Gateway aparece
como uma comanda com horario, metodo, rota, duracao, se foi com token e o status
HTTP carimbado (verde 2xx, laranja 4xx, vermelho 401). Clicar numa comanda mostra
o corpo enviado, a resposta do Gateway e o id da requisicao (`X-Requisicao-Id`),
que serve para achar a mesma requisicao nos logs de todos os servicos.

## Como ele chama o Gateway

- **URL do Gateway.** O `index.html` carrega `/config.js` antes do app. No
  container, o nginx responde esse arquivo com o valor da variavel `API_URL`
  (template `frontend/nginx/default.conf.template`):

  ```js
  window.API_URL = 'http://IP_DO_GATEWAY:8000';
  ```

  Trocar o endereco do Gateway e so mudar o `.env` da VM e reiniciar o
  container, sem rebuild. Sem `API_URL`, o frontend usa o mesmo host da pagina
  na porta 8000.
- **Token.** O `POST /auth/login` devolve `access_token`; o frontend guarda o
  token e os dados do usuario no `sessionStorage` (some ao fechar a aba) e
  manda `Authorization: Bearer <token>` em toda chamada.
- **401.** Se uma chamada com o token da sessao volta 401 (token vencido, por
  exemplo), a sessao e encerrada e a tela de login volta.
- **CORS.** O frontend e o Gateway estao em origens diferentes (portas ou VMs
  diferentes). O Gateway libera as origens de `CORS_ORIGENS` e o cabecalho
  `Authorization`.
- **Papel.** A aba Cozinha e os botoes de avancar etapa so aparecem para o papel
  `cozinha`. Esconder e so conveniencia: quem barra de verdade e o Gateway (403).

## Rodar

No container:

```bash
docker compose --profile frontend up -d --build frontend
```

A imagem final e o `nginxinc/nginx-unprivileged` (nginx sem root, escutando na
porta 8080 do container, publicada na `FRONTEND_PORTA` da maquina).

| Variavel (`.env`) | Padrao | Uso |
|---|---|---|
| `API_URL` | `http://localhost:8000` | endereco do Gateway entregue ao navegador |
| `FRONTEND_PORTA` | `80` | porta publicada na maquina |

Desenvolvimento, com recarga automatica:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, chama o Gateway em http://localhost:8000
```

## Estrutura

```text
frontend/
  index.html                       carrega /config.js e o app
  nginx/default.conf.template      porta ${PORT}, /config.js com ${API_URL}, gzip e fallback de SPA
  Dockerfile                       build com node:22-alpine, entrega com nginx-unprivileged:1.28-alpine
  src/api.js                       unico modulo que chama o Gateway; sessao, registro das chamadas e tempo real
  src/mensagens.js                 mensagens da API -> texto da tela (com acento)
  src/App.jsx                      cabecalho, abas e escolha da tela
  src/telas/                       Login, Cardapio, Pedidos, Cozinha, Saude, Testes
  src/componentes/                 Campo (obrigatorio, erro por campo, Aviso, Resultado), Trilho (comandas), IconeChama
  src/estilos.css                  identidade visual
```
