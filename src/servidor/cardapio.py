"""Cardapio do restaurante.

Catalogo em memoria: e o "banco de dados" do servico. Cada item tem um codigo
curto porque e o codigo que o cliente digita no terminal.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    codigo: str
    nome: str
    descricao: str
    categoria: str
    preco: float
    disponivel: bool = True


NOME_RESTAURANTE = "Cantina do Maia"

CARDAPIO = (
    Item("EN01", "Bruschetta", "Pao italiano, tomate, manjericao e azeite", "Entradas", 18.90),
    Item("EN02", "Bolinho de bacalhau", "Seis unidades com limao siciliano", "Entradas", 32.00),
    Item("EN03", "Batata rustica", "Batata assada com alecrim e parmesao", "Entradas", 24.50),
    Item("PR01", "File a parmegiana", "File empanado, molho de tomate e queijo, com arroz", "Pratos", 62.90),
    Item("PR02", "Risoto de camarao", "Arroz arboreo, camarao rosa e limao", "Pratos", 74.00),
    Item("PR03", "Feijoada individual", "Acompanha arroz, couve, farofa e laranja", "Pratos", 54.00),
    Item("PR04", "Lasanha bolonhesa", "Massa fresca, molho bolonhesa e bechamel", "Pratos", 48.50),
    Item("PR05", "Moqueca de peixe", "Peixe branco, leite de coco e dende", "Pratos", 79.90, disponivel=False),
    Item("BE01", "Refrigerante lata", "350 ml", "Bebidas", 7.00),
    Item("BE02", "Suco natural de laranja", "500 ml, sem acucar", "Bebidas", 12.00),
    Item("BE03", "Agua mineral", "500 ml, com ou sem gas", "Bebidas", 5.50),
    Item("SO01", "Pudim de leite", "Fatia individual", "Sobremesas", 16.00),
    Item("SO02", "Petit gateau", "Com sorvete de creme", "Sobremesas", 27.90),
)

POR_CODIGO = {item.codigo: item for item in CARDAPIO}


def listar(categoria: str = "") -> tuple:
    """Itens do cardapio, filtrados por categoria quando informada."""
    if not categoria:
        return CARDAPIO
    alvo = categoria.strip().lower()
    return tuple(item for item in CARDAPIO if item.categoria.lower() == alvo)


def buscar(codigo: str) -> Item | None:
    return POR_CODIGO.get((codigo or "").strip().upper())


def codigos_validos() -> str:
    return ", ".join(item.codigo for item in CARDAPIO)
