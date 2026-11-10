-- Schema do delivery. Idempotente: pode rodar a cada deploy sem apagar dados.
--
-- Cada microsservico e dono das suas tabelas:
--   usuarios -> usuarios
--   catalogo -> itens_cardapio, fotos_itens
--   pedidos  -> pedidos, itens_pedido
-- Nao ha chave estrangeira entre tabelas de servicos diferentes: itens_pedido
-- guarda uma copia (snapshot) do nome e do preco no momento da compra.

-- Usuarios ------------------------------------------------------------------
-- senha_hash guarda o hash bcrypt; a senha em texto puro nunca e gravada.
CREATE TABLE IF NOT EXISTS usuarios (
    id         UUID        PRIMARY KEY,
    login      TEXT        NOT NULL UNIQUE,
    nome       TEXT        NOT NULL,
    senha_hash TEXT        NOT NULL,
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- papel em ALTER separado para bancos que ja tinham a tabela sem a coluna.
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS papel TEXT NOT NULL DEFAULT 'cliente'
    CHECK (papel IN ('cliente', 'cozinha'));

-- Catalogo ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS itens_cardapio (
    codigo        VARCHAR(8)     PRIMARY KEY,
    nome          TEXT           NOT NULL,
    descricao     TEXT           NOT NULL DEFAULT '',
    categoria     TEXT           NOT NULL,
    preco         NUMERIC(10, 2) NOT NULL CHECK (preco > 0),
    disponivel    BOOLEAN        NOT NULL DEFAULT TRUE,
    atualizado_em TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- Opcoes do item (submenu: sabor do refrigerante, agua com ou sem gas).
-- Vazio = item sem escolha. Em ALTER separado para bancos que ja tinham a tabela.
ALTER TABLE itens_cardapio ADD COLUMN IF NOT EXISTS opcoes TEXT[] NOT NULL DEFAULT '{}';

-- Codigo com ate 4 digitos (PR100...): itens cadastrados pela cozinha nunca
-- reaproveitam o codigo de um item excluido. O IF evita o ALTER (e a trava da
-- tabela) quando a coluna ja tem o tamanho novo.
DO $$
BEGIN
    IF (SELECT character_maximum_length FROM information_schema.columns
         WHERE table_name = 'itens_cardapio' AND column_name = 'codigo') < 8 THEN
        ALTER TABLE itens_cardapio ALTER COLUMN codigo TYPE VARCHAR(8);
    END IF;
END $$;

-- Gestao do cardapio pela cozinha.
--   foto_versao   versao da foto (hash do conteudo); vazia = sem foto
--   editado_em    a cozinha mexeu no conteudo (nome, descricao, categoria,
--                 opcoes, foto ou exclusao): a carga inicial nao sobrescreve mais
--   excluido_em   exclusao logica: some do cardapio, o codigo fica reservado
--   chave_criacao idempotencia do CriarItem (uuid do Gateway)
ALTER TABLE itens_cardapio ADD COLUMN IF NOT EXISTS foto_versao TEXT NOT NULL DEFAULT '';
ALTER TABLE itens_cardapio ADD COLUMN IF NOT EXISTS editado_em TIMESTAMPTZ;
ALTER TABLE itens_cardapio ADD COLUMN IF NOT EXISTS excluido_em TIMESTAMPTZ;
ALTER TABLE itens_cardapio ADD COLUMN IF NOT EXISTS chave_criacao UUID UNIQUE;

-- Fotos dos pratos (bytes no banco: funcionam igual no compose e no Cloud SQL,
-- sem disco no container). Tabela separada: listar o cardapio nao carrega imagem.
CREATE TABLE IF NOT EXISTS fotos_itens (
    codigo        VARCHAR(8)  PRIMARY KEY REFERENCES itens_cardapio (codigo),
    tipo          TEXT        NOT NULL,
    conteudo      BYTEA       NOT NULL,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Pedidos -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pedidos (
    id                     UUID           PRIMARY KEY,
    cliente                TEXT           NOT NULL,
    endereco               TEXT           NOT NULL,
    status                 TEXT           NOT NULL,
    total                  NUMERIC(10, 2) NOT NULL,
    tempo_estimado_minutos INTEGER        NOT NULL,
    criado_em              TIMESTAMPTZ    NOT NULL DEFAULT now(),
    atualizado_em          TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS itens_pedido (
    pedido_id      UUID           NOT NULL REFERENCES pedidos (id) ON DELETE CASCADE,
    linha          INTEGER        NOT NULL,
    codigo         VARCHAR(8)     NOT NULL,
    nome           TEXT           NOT NULL,
    quantidade     INTEGER        NOT NULL CHECK (quantidade > 0),
    preco_unitario NUMERIC(10, 2) NOT NULL,
    subtotal       NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (pedido_id, linha)
);

-- Opcao escolhida em cada linha (snapshot, como nome e preco).
ALTER TABLE itens_pedido ADD COLUMN IF NOT EXISTS opcao TEXT NOT NULL DEFAULT '';

-- Mesmo tamanho de codigo do cardapio (ver itens_cardapio acima).
DO $$
BEGIN
    IF (SELECT character_maximum_length FROM information_schema.columns
         WHERE table_name = 'itens_pedido' AND column_name = 'codigo') < 8 THEN
        ALTER TABLE itens_pedido ALTER COLUMN codigo TYPE VARCHAR(8);
    END IF;
END $$;

-- Dono do pedido (id do usuario do token). Em ALTER separado porque o banco do
-- Trabalho 2 ja tinha a tabela; pedidos antigos ficam com NULL e so a cozinha
-- os ve. Sem FK para usuarios: a tabela e de outro microsservico.
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS usuario_id UUID;

CREATE INDEX IF NOT EXISTS idx_pedidos_criado_em ON pedidos (criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_pedidos_usuario ON pedidos (usuario_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_pedidos_status ON pedidos (status);
CREATE INDEX IF NOT EXISTS idx_itens_pedido_codigo ON itens_pedido (codigo);

-- Historico das etapas: uma linha por etapa alcancada, com o horario. Mesma
-- dona (Pedidos), entao a FK para pedidos vale.
CREATE TABLE IF NOT EXISTS etapas_pedido (
    pedido_id     UUID        NOT NULL REFERENCES pedidos (id) ON DELETE CASCADE,
    status        TEXT        NOT NULL,
    registrado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (pedido_id, status)
);
-- Pedidos de antes do historico: registra a etapa inicial e a atual com os
-- horarios que a tabela pedidos ja tem. ON CONFLICT: idempotente a cada deploy.
INSERT INTO etapas_pedido (pedido_id, status, registrado_em)
SELECT id, 'RECEBIDO', criado_em FROM pedidos
ON CONFLICT DO NOTHING;
INSERT INTO etapas_pedido (pedido_id, status, registrado_em)
SELECT id, status, atualizado_em FROM pedidos WHERE status <> 'RECEBIDO'
ON CONFLICT DO NOTHING;
