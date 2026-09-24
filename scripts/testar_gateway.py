#!/usr/bin/env python3
"""Smoke test do API Gateway: roda os cenarios de sucesso e de erro em sequencia.

So usa a biblioteca padrao (urllib), entao roda em qualquer maquina com Python,
sem instalar nada:

    python scripts/testar_gateway.py --url http://localhost:8000
    python scripts/testar_gateway.py --url http://IP_DA_VM:8000

Cada cenario imprime o metodo, a rota, o status esperado, o status recebido e o
corpo da resposta. Sai com codigo 1 se algum status vier diferente do esperado.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

ID_INEXISTENTE = "00000000-0000-0000-0000-000000000000"


def chamar(base: str, metodo: str, rota: str, corpo=None, bruto: bytes | None = None):
    dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
    requisicao = urllib.request.Request(base + rota, data=dados, method=metodo)
    if dados is not None:
        requisicao.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(requisicao, timeout=15) as resposta:
            return resposta.status, json.loads(resposta.read() or b"null")
    except urllib.error.HTTPError as erro:
        conteudo = erro.read()
        try:
            return erro.code, json.loads(conteudo)
        except ValueError:
            return erro.code, conteudo.decode(errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--resumido", action="store_true", help="nao imprime o corpo das respostas")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    falhas = 0

    def cenario(titulo, esperado, metodo, rota, corpo=None, bruto=None):
        nonlocal falhas
        status, resposta = chamar(base, metodo, rota, corpo, bruto)
        ok = status == esperado
        falhas += 0 if ok else 1
        print("\n%s %s  (esperado %d, recebido %d)  %s" % ("OK " if ok else "ERRO", titulo, esperado, status, ""))
        print("    %s %s" % (metodo, rota))
        if corpo is not None:
            print("    corpo enviado:", json.dumps(corpo, ensure_ascii=False))
        if bruto is not None:
            print("    corpo enviado:", bruto.decode())
        if not args.resumido:
            texto = json.dumps(resposta, ensure_ascii=False, indent=2)
            print("    resposta:", texto.replace("\n", "\n    "))
        return resposta

    print("Gateway:", base)
    cenario("Gateway no ar", 200, "GET", "/saude")
    cenario("Cardapio de bebidas", 200, "GET", "/cardapio?categoria=Bebidas")

    criado = cenario(
        "Pedido valido e gravado no banco", 201, "POST", "/pedidos",
        {"cliente": "Maria", "endereco": "Rua 10, 123", "itens": [{"codigo": "PR01", "quantidade": 2}, {"codigo": "be02", "quantidade": 1}]},
    )
    pedido_id = (criado or {}).get("pedido", {}).get("pedido_id", ID_INEXISTENTE)

    cenario("Sem o campo cliente", 400, "POST", "/pedidos",
            {"endereco": "Rua 10, 123", "itens": [{"codigo": "PR01", "quantidade": 1}]})
    cenario("Quantidade zero e itens vazios", 400, "POST", "/pedidos",
            {"cliente": "  ", "endereco": "Rua 10", "itens": [{"codigo": "PR01", "quantidade": 0}]})
    cenario("Lista de itens vazia", 400, "POST", "/pedidos",
            {"cliente": "Joao", "endereco": "Rua 10", "itens": []})
    cenario("JSON malformado", 400, "POST", "/pedidos", bruto=b'{"cliente": "Joao", ')
    cenario("Item que nao existe no banco", 400, "POST", "/pedidos",
            {"cliente": "Joao", "endereco": "Rua 10", "itens": [{"codigo": "XX99", "quantidade": 1}]})
    cenario("Item indisponivel (PR05)", 409, "POST", "/pedidos",
            {"cliente": "Joao", "endereco": "Rua 10", "itens": [{"codigo": "PR05", "quantidade": 1}]})

    cenario("Consulta do pedido criado", 200, "GET", "/pedidos/" + pedido_id)
    cenario("Pedido inexistente", 404, "GET", "/pedidos/" + ID_INEXISTENTE)
    cenario("Avanca status RECEBIDO -> EM_PREPARO", 200, "PATCH", "/pedidos/%s/status" % pedido_id, {"status": "EM_PREPARO"})
    cenario("Pula etapa EM_PREPARO -> ENTREGUE", 409, "PATCH", "/pedidos/%s/status" % pedido_id, {"status": "ENTREGUE"})
    cenario("Status fora da lista", 400, "PATCH", "/pedidos/%s/status" % pedido_id, {"status": "CANCELADO"})
    cenario("Lista os pedidos", 200, "GET", "/pedidos?limite=3")

    print("\n" + ("Todos os cenarios passaram." if falhas == 0 else "%d cenario(s) com status diferente do esperado." % falhas))
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
