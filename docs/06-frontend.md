# 6. Frontend

O frontend (`frontend/`) e uma aplicacao React (Vite) servida pelo nginx. Ele
**so conversa com o API Gateway**: nao conhece endereco nem protocolo dos
microsservicos. Todas as chamadas saem de um unico modulo, `src/api.js`.

## Telas

| Tela | O que faz | Chamadas ao Gateway |
|---|---|---|
| Entrar / Criar conta | login e cadastro; os formularios nao validam no navegador, entao o 400 do Gateway aparece embaixo de cada campo | `POST /auth/login`, `POST /auth/cadastro` |
| Cardapio | lista os pratos, filtra por categoria (o filtro e feito no servidor), monta a sacola e faz o pedido | `GET /cardapio`, `GET /cardapio?categoria=`, `POST /pedidos` |
| Pedidos | lista os pedidos, mostra itens e etapas; a cozinha avanca a etapa e pode tentar pular uma (409) | `GET /pedidos`, `GET /pedidos/{id}`, `PATCH /pedidos/{id}/status` |
| Cozinha (so papel `cozinha`) | liga e desliga pratos do cardapio do dia e ajusta preco | `GET /cardapio`, `PATCH /cardapio/{codigo}` |
| Testes de seguranca | botoes que mandam requisicoes erradas de proposito: sem token, token adulterado, token editado, senha errada (401), cliente mudando preco (403), payload invalido (400), item inexistente (400), item indisponivel (409) | varias |

No rodape fica o **trilho de comandas**: cada chamada feita ao Gateway aparece
como uma comanda com horario, metodo, rota, duracao, se foi com token e o status
HTTP carimbado (verde 2xx, laranja 4xx, vermelho 401). Clicar numa comanda mostra
o corpo enviado e a resposta do Gateway.

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

No container (como no GCP):

```bash
docker compose --profile frontend up -d --build frontend
```

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
  nginx/default.conf.template      /config.js com ${API_URL} e fallback de SPA
  Dockerfile                       build com node:20-alpine, entrega com nginx:1.27-alpine
  src/api.js                       unico modulo que chama o Gateway; sessao e registro das chamadas
  src/App.jsx                      cabecalho, abas e escolha da tela
  src/telas/                       Login, Cardapio, Pedidos, Cozinha, Testes
  src/componentes/                 Campo (erro por campo), Trilho (comandas)
  src/estilos.css                  identidade visual
```
