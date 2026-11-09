-- Carga inicial do cardapio do Hell's Kitchen.
--
-- Os nomes e descricoes sao texto da interface, por isso levam acento.
-- ON CONFLICT: rodar de novo atualiza so nome, descricao e categoria (corrige
-- bancos que ja tinham a carga antiga, sem acento) e nunca sobrescreve preco
-- nem disponibilidade, que a cozinha altera pela API. PR05 comeca indisponivel
-- de proposito, para demonstrar a recusa de item fora do cardapio do dia.
INSERT INTO itens_cardapio (codigo, nome, descricao, categoria, preco, disponivel) VALUES
    ('EN01', 'Bruschetta',              'Pão italiano, tomate, manjericão e azeite',          'Entradas',   18.90, TRUE),
    ('EN02', 'Bolinho de bacalhau',     'Seis unidades com limão-siciliano',                  'Entradas',   32.00, TRUE),
    ('EN03', 'Batata rústica',          'Batata assada com alecrim e parmesão',               'Entradas',   24.50, TRUE),
    ('PR01', 'Filé à parmegiana',       'Filé empanado, molho de tomate e queijo, com arroz', 'Pratos',     62.90, TRUE),
    ('PR02', 'Risoto de camarão',       'Arroz arbóreo, camarão-rosa e limão',                'Pratos',     74.00, TRUE),
    ('PR03', 'Feijoada individual',     'Acompanha arroz, couve, farofa e laranja',           'Pratos',     54.00, TRUE),
    ('PR04', 'Lasanha à bolonhesa',     'Massa fresca, molho à bolonhesa e bechamel',         'Pratos',     48.50, TRUE),
    ('PR05', 'Moqueca de peixe',        'Peixe branco, leite de coco e dendê',                'Pratos',     79.90, FALSE),
    ('BE01', 'Refrigerante lata',       '350 ml',                                             'Bebidas',     7.00, TRUE),
    ('BE02', 'Suco natural de laranja', '500 ml, sem açúcar',                                 'Bebidas',    12.00, TRUE),
    ('BE03', 'Água mineral',            '500 ml, com ou sem gás',                             'Bebidas',     5.50, TRUE),
    ('SO01', 'Pudim de leite',          'Fatia individual',                                   'Sobremesas', 16.00, TRUE),
    ('SO02', 'Petit gâteau',            'Com sorvete de creme',                               'Sobremesas', 27.90, TRUE)
ON CONFLICT (codigo) DO UPDATE
   SET nome = EXCLUDED.nome,
       descricao = EXCLUDED.descricao,
       categoria = EXCLUDED.categoria;

-- Nenhum usuario e criado aqui: o repositorio e publico, e um usuario com senha
-- conhecida daria a qualquer um o papel cozinha no sistema no ar. O usuario da
-- cozinha e criado pelo migrador a partir de DEMO_LOGIN/DEMO_SENHA do .env
-- (scripts/migrar_banco.py). Quem se cadastra por POST /auth/cadastro e cliente.
