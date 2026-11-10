"""Modelos de entrada do Gateway (validacao do payload JSON com Pydantic).

Cada modelo define os campos obrigatorios de negocio. Payload que nao passa
aqui nem chega aos microsservicos: o Gateway responde 400 na borda.
`extra="forbid"` recusa campo desconhecido (ex.: "preco" enviado pelo cliente,
que nao deve precificar nada).
"""

import re
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

# Regex dos campos com formato fixo. O erros.py usa as mesmas constantes para
# explicar o formato esperado na resposta 400.
PADRAO_CODIGO = r"^[A-Za-z]{2}[0-9]{2,4}$"
PADRAO_LOGIN = r"^[A-Za-z0-9_.]{3,30}$"
PADRAO_TELEFONE = r"^[0-9 ()+.-]*$"
SENHA_MINIMO = 6
TELEFONE_INVALIDO = "telefone invalido: use DDD e numero (ex.: (62) 99999-0000)"
NOME_INVALIDO = "nome invalido: use so letras, espaco, apostrofo e hifen (ex.: Maria da Silva)"
# Letras de qualquer idioma (com acento), separadas por espaco, apostrofo,
# ponto ou hifen: "Maria da Silva", "D'Avila", "Ana-Clara", "J. Souza".
_NOME_DE_PESSOA = re.compile(r"[^\W\d_]+(?:[ '.-]+[^\W\d_]+)*\.?")


def _nome_de_pessoa(valor: str) -> str:
    nome = " ".join(valor.split())
    if not _NOME_DE_PESSOA.fullmatch(nome) or sum(c.isalpha() for c in nome) < 2:
        raise ValueError(NOME_INVALIDO)
    return nome


def _digitos_do_telefone(valor: str) -> str:
    """Vazio apaga o telefone; preenchido precisa de DDD + numero (10 a 13 digitos)."""
    if valor and not 10 <= sum(c.isdigit() for c in valor) <= 13:
        raise ValueError(TELEFONE_INVALIDO)
    return valor

TextoObrigatorio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
CodigoItem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, pattern=PADRAO_CODIGO),
]
# O pattern e checado antes do to_lower, por isso a regex aceita maiuscula.
Login = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=PADRAO_LOGIN)]
Telefone = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=20, pattern=PADRAO_TELEFONE),
    AfterValidator(_digitos_do_telefone),
]
Senha = Annotated[str, StringConstraints(min_length=SENHA_MINIMO, max_length=72)]
NomePessoa = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100), AfterValidator(_nome_de_pessoa)
]

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
    # Contato para a entrega (opcional); o frontend preenche com o de "Meus dados".
    telefone: Telefone | None = Field(default=None, examples=["(62) 99999-0000"])


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


class AlteracaoParcial(Entrada):
    """Base dos PATCH: so os campos enviados mudam (null conta como nao enviado)."""

    @model_validator(mode="after")
    def algum_campo(self):
        if all(getattr(self, campo) is None for campo in type(self).model_fields):
            raise ValueError("informe ao menos um campo para alterar")
        return self


class ItemAtualizacao(AlteracaoParcial):
    disponivel: StrictBool | None = Field(default=None, examples=[True])
    preco: Preco | None = Field(default=None, examples=[79.9])
    nome: NomeItem | None = None
    descricao: DescricaoItem | None = None
    categoria: CategoriaItem | None = None
    opcoes: ListaOpcoes | None = None
    # Opcoes fora do dia (ex.: ["Com gás"]); lista vazia = todas disponiveis.
    opcoes_indisponiveis: ListaOpcoes | None = Field(default=None, examples=[["Com gás"]])


class ContaAtualizacao(AlteracaoParcial):
    """PATCH /conta. Telefone ou endereco vazio ("") apaga o dado."""

    nome: NomePessoa | None = Field(
        default=None, examples=["Maria Silva"]
    )
    telefone: Telefone | None = Field(default=None, examples=["(62) 99999-0000"])
    endereco: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = Field(
        default=None, examples=["Rua 10, 123 - Setor Universitario"]
    )


class TrocaSenha(Entrada):
    senha_atual: Annotated[str, StringConstraints(min_length=1, max_length=72)] = Field(examples=["senha-atual"])
    nova_senha: Senha = Field(examples=["senha-nova"])
    confirmar_senha: Annotated[str, StringConstraints(min_length=1, max_length=72)] = Field(examples=["senha-nova"])

    @field_validator("confirmar_senha")
    @classmethod
    def confere(cls, valor: str, info):
        # Se a nova senha ja foi recusada, ela nao esta em info.data: um erro so.
        if valor != info.data.get("nova_senha", valor):
            raise ValueError("as senhas nao conferem")
        return valor


class CadastroEntrada(Entrada):
    login: Login = Field(examples=["maria.silva"])
    nome: NomePessoa = Field(examples=["Maria Silva"])
    # 72 e o limite do bcrypt; a senha nao passa por strip.
    senha: Senha = Field(examples=["minhasenha"])


class LoginEntrada(Entrada):
    login: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)] = Field(
        examples=["professor"]
    )
    senha: Annotated[str, StringConstraints(min_length=1, max_length=72)] = Field(examples=["sua-senha"])
