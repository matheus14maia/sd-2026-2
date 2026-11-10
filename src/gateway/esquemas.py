"""Modelos de entrada do Gateway (validacao do payload JSON com Pydantic).

Cada modelo define os campos obrigatorios de negocio. Payload que nao passa
aqui nem chega aos microsservicos: o Gateway responde 400 na borda.
`extra="forbid"` recusa campo desconhecido (ex.: "preco" enviado pelo cliente,
que nao deve precificar nada).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, model_validator

# Regex dos campos com formato fixo. O erros.py usa as mesmas constantes para
# explicar o formato esperado na resposta 400.
PADRAO_CODIGO = r"^[A-Za-z]{2}[0-9]{2,4}$"
PADRAO_LOGIN = r"^[A-Za-z0-9_.]{3,30}$"
SENHA_MINIMO = 6

TextoObrigatorio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
CodigoItem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, pattern=PADRAO_CODIGO),
]
# O pattern e checado antes do to_lower, por isso a regex aceita maiuscula.
Login = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=PADRAO_LOGIN)]

Etapa = Literal["RECEBIDO", "EM_PREPARO", "PRONTO", "SAIU_PARA_ENTREGA", "ENTREGUE"]
ETAPAS = ("RECEBIDO", "EM_PREPARO", "PRONTO", "SAIU_PARA_ENTREGA", "ENTREGUE")


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemEntrada(Entrada):
    codigo: CodigoItem = Field(examples=["PR01"])
    quantidade: Annotated[StrictInt, Field(gt=0, le=99, examples=[2])]
    # Escolha do submenu (ex.: sabor do refrigerante). Quem confere se o item
    # tem opcoes e se esta e uma delas e o Pedidos, com os dados do Catalogo.
    opcao: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = Field(
        default=None, examples=["Guaraná"]
    )


class PedidoEntrada(Entrada):
    # Sem campo "cliente": o pedido e sempre feito em nome do dono do token. Um
    # "cliente" no corpo cai no extra="forbid" e responde 400.
    endereco: TextoObrigatorio = Field(examples=["Rua 10, 123 - Setor Universitario"])
    itens: list[ItemEntrada] = Field(min_length=1, max_length=30)


class StatusEntrada(Entrada):
    status: Etapa = Field(examples=["EM_PREPARO"])


# Campos de um item do cardapio. Os limites de negocio (categorias, opcoes
# repetidas) sao conferidos pelo Catalogo, dono do cardapio.
NomeItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
DescricaoItem = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
CategoriaItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Preco = Annotated[float, Field(gt=0, le=10000)]
Opcao = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
ListaOpcoes = Annotated[list[Opcao], Field(max_length=12)]


class ItemNovo(Entrada):
    nome: NomeItem = Field(examples=["Strogonoff de frango"])
    categoria: CategoriaItem = Field(examples=["Pratos"])
    preco: Preco = Field(examples=[46.9])
    descricao: DescricaoItem = Field(default="", examples=["Com arroz branco e batata palha"])
    disponivel: StrictBool = Field(default=True, examples=[True])
    opcoes: ListaOpcoes = Field(default_factory=list, examples=[[]])


class ItemAtualizacao(Entrada):
    """PATCH: so os campos enviados mudam (null conta como nao enviado)."""

    disponivel: StrictBool | None = Field(default=None, examples=[True])
    preco: Preco | None = Field(default=None, examples=[79.9])
    nome: NomeItem | None = None
    descricao: DescricaoItem | None = None
    categoria: CategoriaItem | None = None
    opcoes: ListaOpcoes | None = None

    @model_validator(mode="after")
    def algum_campo(self):
        if all(getattr(self, campo) is None for campo in type(self).model_fields):
            raise ValueError("informe ao menos um campo para alterar")
        return self


class CadastroEntrada(Entrada):
    login: Login = Field(examples=["maria.silva"])
    nome: TextoObrigatorio = Field(examples=["Maria Silva"])
    # 72 e o limite do bcrypt; a senha nao passa por strip.
    senha: Annotated[str, StringConstraints(min_length=SENHA_MINIMO, max_length=72)] = Field(
        examples=["minhasenha"]
    )


class LoginEntrada(Entrada):
    login: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)] = Field(
        examples=["professor"]
    )
    senha: Annotated[str, StringConstraints(min_length=1, max_length=72)] = Field(examples=["sua-senha"])
