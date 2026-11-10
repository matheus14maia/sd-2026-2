# 6. Frontend

O frontend (`frontend/`) e uma aplicacao React (Vite) servida pelo nginx. Ele
**so conversa com o API Gateway**: nao conhece endereco nem protocolo dos
microsservicos. Todas as chamadas saem de um unico modulo, `src/api.js`.

## Telas

| Tela | O que faz | Chamadas ao Gateway |
|---|---|---|
| Entrar / Criar conta | login e cadastro (quem cria a conta ja entra); campos obrigatorios com asterisco (dica "Campo obrigatorio" ao passar o mouse); os formularios nao validam no navegador, entao o 400 do Gateway aparece embaixo de cada campo. Depois de entrar, o cliente cai no Cardapio e a cozinha em Pedidos | `POST /auth/login`, `POST /auth/cadastro` |
| Cardapio | abas por categoria (Todos, Entradas, Pratos principais, Sobremesas, Bebidas; o filtro e feito no servidor), foto de cada prato com zoom, submenu de opcoes (sabor do refrigerante, agua sem ou com gas) em que cada opcao vira uma linha da sacola, pedido em etapas na sacola (ver abaixo); botao "Finalizar pedido e acender as chamas" so na etapa de entrega, com fogo de particulas ao confirmar; o cardapio se atualiza a cada 30 s e a sacola marca o que a cozinha mudou; se o Catalogo cair, mostra a faixa "cardapio em modo de seguranca" | `GET /cardapio`, `GET /cardapio?categoria=`, `POST /pedidos`, `GET /cardapio/{codigo}/foto` |
| Meus dados (so papel `cliente`) | nome, telefone e endereco de entrega padrao (preenchem a entrega do pedido) e troca de senha com a senha atual; o nome do topo tambem leva a esta aba | `GET /conta`, `PATCH /conta`, `PUT /conta/senha` |
| Pedidos | "Meus pedidos" para cliente, "Todos os pedidos" para a cozinha; telefone de contato no detalhe; filtros por etapa, periodo, prato e (cozinha) cliente; horario de cada etapa, previsao de entrega com o tempo que falta; a cozinha avanca a etapa e pode tentar pular uma (409); tudo se atualiza sozinho | `GET /pedidos?...`, `GET /pedidos/{id}`, `PATCH /pedidos/{id}/status`, `GET /pedidos/eventos` |
| Cozinha (so papel `cozinha`) | lista os pratos por categoria com foto, preco e o interruptor "Disponivel"; "Novo prato" e "Editar" abrem um formulario (nome, categoria, preco, descricao que o cliente le, opcoes, disponivel hoje e foto); "Excluir prato" pede confirmacao | `GET /cardapio`, `POST /cardapio`, `PATCH /cardapio/{codigo}`, `DELETE /cardapio/{codigo}`, `PUT` e `DELETE /cardapio/{codigo}/foto` |
| Saude dos servicos (so papel `cozinha`) | a cada 3 s, health check gRPC de cada microsservico, o estado do circuit breaker no Gateway e da conexao de tempo real; botoes para carregar o cardapio e fazer um pedido de teste durante uma falha (ver [07-resiliencia.md](07-resiliencia.md)) | `GET /saude/servicos`, `GET /cardapio`, `POST /pedidos` |
| Testes de seguranca (so papel `cozinha`) | botoes que mandam requisicoes erradas de proposito: sem token, token adulterado, token editado, senha errada (401), cliente mudando preco ou vendo a saude (403), payload invalido (400), item inexistente (400), item indisponivel (409), pedido em nome de outra pessoa (400), cliente vendo pedido de outro (404) | varias |

**Tempo real.** Depois do login o app abre uma conexao com `GET /pedidos/eventos`
(ver [05-api-gateway.md](05-api-gateway.md#tempo-real-server-sent-events)). A
lista e o detalhe do pedido se atualizam sozinhos e aparecem avisos: a cozinha e
avisada de cada pedido novo e o cliente de cada etapa do pedido dele. O estado
dessa conexao aparece so na aba "Saude dos servicos" (cozinha).

**Fotos dos pratos.** A cozinha escolhe a foto no formulario do prato (aba
Cozinha > Editar > Escolher foto) e troca quando quiser, sem reiniciar nada. O
navegador reduz a foto para 800 px em JPEG (uma foto de celular de 5 MB vira uns
100 KB) e envia em `PUT /cardapio/{codigo}/foto`; a foto fica no banco, e o
cardapio mostra a URL que vem no campo `foto` de cada item. Prato sem foto (ou
com a foto fora do ar) mostra as iniciais no lugar. Fotos iniciais tambem podem
vir no repositorio, em `db/fotos/<CODIGO>.jpg` (ver o `LEIA-ME.txt` da pasta):
o migrador carrega no banco quando o sistema sobe.

**Fogo ao confirmar o pedido.** O botao "Finalizar pedido e acender as chamas"
tem uma chama de duas camadas que tremula sob o mouse. Com o pedido confirmado,
o `componentes/Fogo.jsx` desenha num `<canvas>` sete linguas de fogo que sobem
do botao por uns 2 s: particulas que nascem amarelas e esfriam para laranja e
vermelho enquanto sobem e afinam, com faiscas. Com "reduzir movimento" ligado no
sistema, nada e animado.

**Quando a cozinha muda o cardapio.** O cardapio do cliente e consultado de
novo a cada 30 s e quando a aba do navegador volta a ficar visivel. Se um prato
da sacola ficou indisponivel, saiu do cardapio ou perdeu a opcao escolhida, a
linha aparece marcada com o motivo e o botao "Retirar"; se o preco mudou, a
linha avisa o preco anterior. A garantia final e do servidor: ao finalizar, o
Pedidos confere cada item com o Catalogo e recusa o pedido inteiro (409 ou 400,
nada e gravado) se algum nao puder ser vendido; a tela mostra o motivo e
atualiza a sacola.

**Mensagens.** A API responde sem acento (convencao do backend); o
`src/mensagens.js` transforma as mensagens conhecidas em frases com acento para a
tela (por exemplo, `nao deve estar vazio` no endereco vira "Informe o endereco de
entrega."). A aba de testes e o trilho de comandas mostram a resposta crua.

No rodape fica o **trilho de comandas**: cada chamada feita ao Gateway aparece
como uma comanda com horario, metodo, rota, duracao, se foi com token e o status
HTTP carimbado (verde 2xx, laranja 4xx, vermelho 401). Clicar numa comanda mostra
o corpo enviado, a resposta do Gateway e o id da requisicao (`X-Requisicao-Id`),
que serve para achar a mesma requisicao nos logs de todos os servicos. Ele abre
sozinho para a cozinha (demonstracao); para o cliente e na tela de login fica
recolhido numa faixa fina com a ultima chamada, e qualquer um abre e fecha.

**Fluxo do pedido.** A sacola tem tres etapas, e o formulario so aparece quando
ja ha prato escolhido:

1. **Sacola.** Vazia, so diz como escolher. Com pratos, mostra cada linha com
   - e + (cada sabor e uma linha), a estimativa e "Continuar para a entrega".
2. **Entrega.** Endereco (obrigatorio) e telefone ja vem de "Meus dados"; no
   primeiro pedido a caixa "Guardar em Meus dados" vem marcada. Aqui fica o
   botao "Finalizar pedido e acender as chamas".
3. **Confirmado.** Depois do fogo: numero do pedido, total calculado pelo
   servidor, previsao de entrega, "Acompanhar pedido" e "Fazer outro pedido".

No celular a sacola fica embaixo do cardapio: enquanto ela esta fora da tela,
uma barra "Ver sacola · N itens · R$" leva ate ela. O zoom dos cards so existe
com mouse (no toque o card nao muda de tamanho embaixo do dedo).

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
| `API_URL` | `http://127.0.0.1:8000` | endereco do Gateway entregue ao navegador (`127.0.0.1` e nao `localhost`: no Windows o `localhost` pode ir para o IPv6 e falhar) |
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
  src/componentes/                 Campo (obrigatorio, erro por campo, Aviso, Resultado), Trilho (comandas), IconeChama, Fogo, FotoPrato
  src/estilos.css                  identidade visual
```
