-- Carga inicial do cardapio do Hell's Kitchen.
--
-- ON CONFLICT DO NOTHING: rodar de novo nao sobrescreve alteracoes feitas
-- depois pela API (preco, disponibilidade). PR05 comeca indisponivel de
-- proposito, para demonstrar a recusa de item fora do cardapio do dia.
INSERT INTO itens_cardapio (codigo, nome, descricao, categoria, preco, disponivel) VALUES
    ('EN01', 'Bruschetta',              'Pao italiano, tomate, manjericao e azeite',          'Entradas',   18.90, TRUE),
    ('EN02', 'Bolinho de bacalhau',     'Seis unidades com limao siciliano',                  'Entradas',   32.00, TRUE),
    ('EN03', 'Batata rustica',          'Batata assada com alecrim e parmesao',               'Entradas',   24.50, TRUE),
    ('PR01', 'File a parmegiana',       'File empanado, molho de tomate e queijo, com arroz', 'Pratos',     62.90, TRUE),
    ('PR02', 'Risoto de camarao',       'Arroz arboreo, camarao rosa e limao',                'Pratos',     74.00, TRUE),
    ('PR03', 'Feijoada individual',     'Acompanha arroz, couve, farofa e laranja',           'Pratos',     54.00, TRUE),
    ('PR04', 'Lasanha bolonhesa',       'Massa fresca, molho bolonhesa e bechamel',           'Pratos',     48.50, TRUE),
    ('PR05', 'Moqueca de peixe',        'Peixe branco, leite de coco e dende',                'Pratos',     79.90, FALSE),
    ('BE01', 'Refrigerante lata',       '350 ml',                                             'Bebidas',     7.00, TRUE),
    ('BE02', 'Suco natural de laranja', '500 ml, sem acucar',                                 'Bebidas',    12.00, TRUE),
    ('BE03', 'Agua mineral',            '500 ml, com ou sem gas',                             'Bebidas',     5.50, TRUE),
    ('SO01', 'Pudim de leite',          'Fatia individual',                                   'Sobremesas', 16.00, TRUE),
    ('SO02', 'Petit gateau',            'Com sorvete de creme',                               'Sobremesas', 27.90, TRUE)
ON CONFLICT (codigo) DO NOTHING;
