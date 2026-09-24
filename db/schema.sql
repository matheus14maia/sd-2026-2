-- Schema do delivery. Idempotente: pode rodar a cada deploy sem apagar dados.
--
-- Cada microsservico e dono das suas tabelas:
--   catalogo -> itens_cardapio
--   pedidos  -> pedidos, itens_pedido
-- Nao ha chave estrangeira entre tabelas de servicos diferentes: itens_pedido
-- guarda uma copia (snapshot) do nome e do preco no momento da compra.

-- Catalogo ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS itens_cardapio (
    codigo        VARCHAR(4)     PRIMARY KEY,
    nome          TEXT           NOT NULL,
    descricao     TEXT           NOT NULL DEFAULT '',
    categoria     TEXT           NOT NULL,
    preco         NUMERIC(10, 2) NOT NULL CHECK (preco > 0),
    disponivel    BOOLEAN        NOT NULL DEFAULT TRUE,
    atualizado_em TIMESTAMPTZ    NOT NULL DEFAULT now()
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
    codigo         VARCHAR(4)     NOT NULL,
    nome           TEXT           NOT NULL,
    quantidade     INTEGER        NOT NULL CHECK (quantidade > 0),
    preco_unitario NUMERIC(10, 2) NOT NULL,
    subtotal       NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (pedido_id, linha)
);

CREATE INDEX IF NOT EXISTS idx_pedidos_criado_em ON pedidos (criado_em DESC);
