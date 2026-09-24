"""Modelos de entrada do Gateway (validacao do payload JSON com Pydantic).

Cada modelo define os campos obrigatorios de negocio. Payload que nao passa
aqui nem chega aos microsservicos: o Gateway responde 400 na borda.
`extra="forbid"` recusa campo desconhecido (ex.: "preco" enviado pelo cliente,
que nao deve precificar nada).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints

TextoObrigatorio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
CodigoItem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{2}[0-9]{2}$"),
]

Etapa = Literal["RECEBIDO", "EM_PREPARO", "PRONTO", "SAIU_PARA_ENTREGA", "ENTREGUE"]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemEntrada(Entrada):
    codigo: CodigoItem = Field(examples=["PR01"])
    quantidade: Annotated[StrictInt, Field(gt=0, le=99, examples=[2])]


class PedidoEntrada(Entrada):
    cliente: TextoObrigatorio = Field(examples=["Maria"])
    endereco: TextoObrigatorio = Field(examples=["Rua 10, 123 - Setor Universitario"])
    itens: list[ItemEntrada] = Field(min_length=1, max_length=30)


class StatusEntrada(Entrada):
    status: Etapa = Field(examples=["EM_PREPARO"])


class ItemAtualizacao(Entrada):
    disponivel: StrictBool = Field(examples=[True])
    preco: Annotated[float, Field(gt=0, le=10000)] | None = Field(default=None, examples=[79.9])
