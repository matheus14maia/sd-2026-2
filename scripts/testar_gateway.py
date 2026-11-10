#!/usr/bin/env python3
"""Smoke test do API Gateway: roda os cenarios de sucesso e de erro em sequencia.

So usa a biblioteca padrao (urllib), entao roda em qualquer maquina com Python,
sem instalar nada:

    python scripts/testar_gateway.py --url http://127.0.0.1:8000
    python scripts/testar_gateway.py --url http://IP_DA_VM:8000

Primeiro faz login com o usuario da cozinha (senha em DEMO_SENHA ou --senha) e
usa o token JWT em todas as rotas protegidas; os cenarios de 401 mandam token ausente, adulterado ou errado.

Tambem confere a posse dos pedidos: o pedido sai em nome do dono do token (o
corpo nao tem "cliente"), o cliente so lista e consulta os proprios pedidos e a
cozinha ve todos. E a gestao do cardapio pela cozinha: cadastrar, editar, enviar
e tirar foto e excluir um prato (cada execucao cadastra e exclui um prato de
teste; o codigo dele nunca e reaproveitado).

Cada cenario imprime o metodo, a rota, o status esperado, o status recebido e o
corpo da resposta. Alguns cenarios tambem conferem o conteudo da resposta. Sai
com codigo 1 se algum cenario nao sair como esperado.
"""

import argparse
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

ID_INEXISTENTE = "00000000-0000-0000-0000-000000000000"
SEM_TOKEN = ""
# Foto JPEG de 8x8 px (774 bytes) para os cenarios de upload.
FOTO_TESTE = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/4gHYSUNDX1BST0ZJTEUAAQEAAAHIAAAAAAQwAABtbnRyUkdC"
    "IFhZWiAH4AABAAEAAAAAAABhY3NwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAA9tYAAQAA"
    "AADTLQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAlk"
    "ZXNjAAAA8AAAACRyWFlaAAABFAAAABRnWFlaAAABKAAAABRiWFlaAAABPAAAABR3dHB0AAABUAAA"
    "ABRyVFJDAAABZAAAAChnVFJDAAABZAAAAChiVFJDAAABZAAAAChjcHJ0AAABjAAAADxtbHVjAAAA"
    "AAAAAAEAAAAMZW5VUwAAAAgAAAAcAHMAUgBHAEJYWVogAAAAAAAAb6IAADj1AAADkFhZWiAAAAAA"
    "AABimQAAt4UAABjaWFlaIAAAAAAAACSgAAAPhAAAts9YWVogAAAAAAAA9tYAAQAAAADTLXBhcmEA"
    "AAAAAAQAAAACZmYAAPKnAAANWQAAE9AAAApbAAAAAAAAAABtbHVjAAAAAAAAAAEAAAAMZW5VUwAA"
    "ACAAAAAcAEcAbwBvAGcAbABlACAASQBuAGMALgAgADIAMAAxADb/2wBDAAoHBwgHBgoICAgLCgoL"
    "DhgQDg0NDh0VFhEYIx8lJCIfIiEmKzcvJik0KSEiMEExNDk7Pj4+JS5ESUM8SDc9Pjv/2wBDAQoL"
    "Cw4NDhwQEBw7KCIoOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7"
    "Ozs7Ozv/wAARCAAIAAgDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAT/xAAXEAEBAQEA"
    "AAAAAAAAAAAAAAAABSIy/8QAFAEBAAAAAAAAAAAAAAAAAAAABv/EABcRAAMBAAAAAAAAAAAAAAAA"
    "AAACAxL/2gAMAwEAAhEDEQA/AK6tXrQA1KS5GM0XJ//Z"
)


def chamar(base: str, metodo: str, rota: str, corpo=None, bruto: bytes | None = None, autorizacao: str = SEM_TOKEN,
           tipo: str = "application/json"):
    """(status, corpo). Corpo JSON vira dict/list; qualquer outro (ex.: foto) volta em bytes."""
    dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
    requisicao = urllib.request.Request(base + rota, data=dados, method=metodo)
    if dados is not None:
        requisicao.add_header("Content-Type", tipo)
    if autorizacao:
        requisicao.add_header("Authorization", autorizacao)
    try:
        with urllib.request.urlopen(requisicao, timeout=15) as resposta:
            conteudo = resposta.read()
            if resposta.headers.get_content_type() != "application/json":
                return resposta.status, conteudo
            return resposta.status, json.loads(conteudo or b"null")
    except urllib.error.HTTPError as erro:
        conteudo = erro.read()
        try:
            return erro.code, json.loads(conteudo)
        except ValueError:
            return erro.code, conteudo.decode(errors="replace")


def ouvir_eventos(base: str, autorizacao: str, destino: list, pronto: threading.Event) -> None:
    """Le o fluxo GET /pedidos/eventos (Server-Sent Events) e guarda (evento, dados)."""
    requisicao = urllib.request.Request(base + "/pedidos/eventos", headers={"Authorization": autorizacao})
    try:
        with urllib.request.urlopen(requisicao, timeout=60) as resposta:
            pronto.set()
            evento = "message"
            for linha in resposta:
                linha = linha.decode("utf-8").rstrip("\r\n")
                if linha.startswith("event:"):
                    evento = linha[6:].strip()
                elif linha.startswith("data:"):
                    destino.append((evento, json.loads(linha[5:])))
    except Exception:
        pronto.set()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--resumido", action="store_true", help="nao imprime o corpo das respostas")
    parser.add_argument("--login", default=os.getenv("DEMO_LOGIN", "professor"))
    parser.add_argument("--senha", default=os.getenv("DEMO_SENHA", ""),
                        help="senha do usuario da cozinha (padrao: variavel DEMO_SENHA)")
    args = parser.parse_args()
    if not args.senha:
        parser.error("informe a senha da cozinha com --senha ou na variavel DEMO_SENHA")
    base = args.url.rstrip("/")
    falhas = 0
    total = 0
    bearer = SEM_TOKEN

    def cenario(titulo, esperado, metodo, rota, corpo=None, bruto=None, autorizacao=None, conferir=None,
                tipo="application/json"):
        """`conferir(resposta)` devolve uma mensagem de erro se o conteudo nao for o esperado."""
        nonlocal falhas, total
        total += 1
        status, resposta = chamar(base, metodo, rota, corpo, bruto, bearer if autorizacao is None else autorizacao,
                                  tipo)
        problema = ""
        if status == esperado and conferir is not None:
            problema = conferir(resposta) or ""
        ok = status == esperado and not problema
        falhas += 0 if ok else 1
        print("\n%s %s  (esperado %d, recebido %d)  %s" % ("OK " if ok else "ERRO", titulo, esperado, status, problema))
        print("    %s %s" % (metodo, rota))
        if corpo is not None:
            print("    corpo enviado:", json.dumps(corpo, ensure_ascii=False))
        if bruto is not None:
            enviado = bruto.decode() if tipo == "application/json" else "<%d bytes, %s>" % (len(bruto), tipo)
            print("    corpo enviado:", enviado)
        if not args.resumido:
            if isinstance(resposta, bytes):
                texto = "<%d bytes>" % len(resposta)
            else:
                texto = json.dumps(resposta, ensure_ascii=False, indent=2)
            print("    resposta:", texto.replace("\n", "\n    "))
        return resposta

    print("Gateway:", base)
    cenario("Gateway no ar (rota publica)", 200, "GET", "/saude")

    # Autenticacao ---------------------------------------------------------
    cenario("Sem token", 401, "GET", "/cardapio")
    cenario("Cabecalho sem Bearer", 401, "GET", "/pedidos", autorizacao="Token abc")
    cenario("Token que nao e JWT", 401, "GET", "/pedidos", autorizacao="Bearer abc.def.ghi")
    cenario("Login sem senha", 400, "POST", "/auth/login", {"login": args.login})
    cenario("Senha errada", 401, "POST", "/auth/login", {"login": args.login, "senha": "chute-errado"})

    novo_login = "teste%d" % int(time.time())
    cenario("Cadastro com dados invalidos", 400, "POST", "/auth/cadastro", {"login": "a b", "nome": "", "senha": "123"})
    cenario("Cadastro de usuario novo", 201, "POST", "/auth/cadastro",
            {"login": novo_login, "nome": "Usuario de Teste", "senha": "senha-teste"})
    cenario("Cadastro com login repetido", 409, "POST", "/auth/cadastro",
            {"login": novo_login, "nome": "Outro", "senha": "senha-teste"})

    sessao = cenario("Login valido devolve o token", 200, "POST", "/auth/login", {"login": args.login, "senha": args.senha})
    token = (sessao or {}).get("access_token", "") if isinstance(sessao, dict) else ""
    cozinha = (sessao or {}).get("usuario", {}) if isinstance(sessao, dict) else {}
    bearer = "Bearer " + token
    cabecalho, _, resto = token.partition(".")
    carga = resto.partition(".")[0]
    cenario("Token com assinatura adulterada", 401, "GET", "/pedidos",
            autorizacao="Bearer %s.%s.assinatura-falsa" % (cabecalho, carga))
    cenario("Dono do token", 200, "GET", "/auth/eu")

    # Autorizacao: quem se cadastra pela API e cliente e nao mexe no cardapio.
    sessao_cliente = cenario("Login do cliente recem-criado", 200, "POST", "/auth/login",
                             {"login": novo_login, "senha": "senha-teste"})
    token_cliente = (sessao_cliente or {}).get("access_token", "") if isinstance(sessao_cliente, dict) else ""
    cliente = (sessao_cliente or {}).get("usuario", {}) if isinstance(sessao_cliente, dict) else {}
    bearer_cliente = "Bearer " + token_cliente
    cenario("Cliente tentando alterar o cardapio", 403, "PATCH", "/cardapio/PR01",
            {"disponivel": True, "preco": 1.0}, autorizacao=bearer_cliente)

    # Rotas de negocio (com token) -----------------------------------------
    cenario("Cardapio de bebidas", 200, "GET", "/cardapio?categoria=Bebidas")

    # Gestao do cardapio pela cozinha: cadastro, edicao, foto e exclusao.
    def campo_igual(nome, valor):
        def conferir(resposta):
            atual = resposta.get(nome) if isinstance(resposta, dict) else None
            return None if atual == valor else "%s deveria ser %r, veio %r" % (nome, valor, atual)
        return conferir

    cenario("Cliente tentando cadastrar prato", 403, "POST", "/cardapio",
            {"nome": "Prato do cliente", "categoria": "Pratos", "preco": 10}, autorizacao=bearer_cliente)
    cenario("Prato sem nome e sem preco", 400, "POST", "/cardapio", {"categoria": "Pratos"})
    cenario("Prato em categoria que nao existe", 400, "POST", "/cardapio",
            {"nome": "Hamburguer", "categoria": "Lanches", "preco": 30})
    prato = cenario(
        "Cozinha cadastra um prato (codigo sai da categoria)", 201, "POST", "/cardapio",
        {"nome": "Prato de teste", "categoria": "Sobremesas", "preco": 19.9, "descricao": "Criado pelo teste",
         "opcoes": ["Com calda", "Sem calda"]},
        conferir=lambda r: None if str((r or {}).get("codigo", "")).startswith("SO") else "codigo deveria comecar com SO",
    )
    codigo_prato = prato.get("codigo", "SO99") if isinstance(prato, dict) else "SO99"
    rota_prato = "/cardapio/%s" % codigo_prato
    cenario("Edicao sem nenhum campo", 400, "PATCH", rota_prato, {})
    cenario("Cozinha edita a descricao (o resto fica igual)", 200, "PATCH", rota_prato,
            {"descricao": "Descricao editada"}, conferir=campo_igual("descricao", "Descricao editada"))
    cenario("Cliente tentando enviar foto", 403, "PUT", rota_prato + "/foto", bruto=FOTO_TESTE, tipo="image/jpeg",
            autorizacao=bearer_cliente)
    cenario("Arquivo que nao e foto", 415, "PUT", rota_prato + "/foto", bruto=b"isto nao e uma foto",
            tipo="image/jpeg")
    com_foto = cenario("Cozinha envia a foto do prato", 200, "PUT", rota_prato + "/foto", bruto=FOTO_TESTE,
                       tipo="image/jpeg", conferir=lambda r: None if r.get("foto") else "item sem a URL da foto")
    url_foto = (com_foto.get("foto") if isinstance(com_foto, dict) else None) or rota_prato + "/foto"
    cenario("Foto do prato e publica (sem token)", 200, "GET", url_foto, autorizacao=SEM_TOKEN,
            conferir=lambda r: None if r == FOTO_TESTE else "bytes da foto diferentes do enviado")
    cenario("Cozinha tira a foto do prato", 200, "DELETE", rota_prato + "/foto", conferir=campo_igual("foto", None))
    cenario("Foto que nao existe mais", 404, "GET", rota_prato + "/foto", autorizacao=SEM_TOKEN)
    cenario("Cliente tentando excluir prato", 403, "DELETE", rota_prato, autorizacao=bearer_cliente)
    cenario("Cozinha exclui o prato", 200, "DELETE", rota_prato)
    cenario("Excluir de novo nao e erro (idempotente)", 200, "DELETE", rota_prato)
    cenario("Pedido com prato excluido", 400, "POST", "/pedidos",
            {"endereco": "Rua 10", "itens": [{"codigo": codigo_prato, "quantidade": 1}]})

    def dono_e(usuario):
        """Confere que o pedido criado saiu em nome do usuario do token."""
        def conferir(resposta):
            pedido = (resposta or {}).get("pedido", {}) if isinstance(resposta, dict) else {}
            if pedido.get("usuario_id") != usuario.get("id") or pedido.get("cliente") != usuario.get("nome"):
                return "pedido deveria ser de %s (%s), veio de %s (%s)" % (
                    usuario.get("nome"), usuario.get("id"), pedido.get("cliente"), pedido.get("usuario_id"))
            return None
        return conferir

    criado = cenario(
        "Pedido valido gravado em nome do dono do token", 201, "POST", "/pedidos",
        {"endereco": "Rua 10, 123", "itens": [{"codigo": "PR01", "quantidade": 2}, {"codigo": "be02", "quantidade": 1}]},
        conferir=dono_e(cozinha),
    )
    pedido_id = (criado or {}).get("pedido", {}).get("pedido_id", ID_INEXISTENTE)

    cenario("Campo cliente no corpo e recusado (o nome vem do token)", 400, "POST", "/pedidos",
            {"cliente": "Outra Pessoa", "endereco": "Rua 10, 123", "itens": [{"codigo": "PR01", "quantidade": 1}]},
            conferir=lambda r: None if "cliente" in (r or {}).get("erros", {}) else "faltou o erro do campo cliente")
    cenario("Sem o campo endereco", 400, "POST", "/pedidos", {"itens": [{"codigo": "PR01", "quantidade": 1}]})
    cenario("Quantidade zero e endereco vazio", 400, "POST", "/pedidos",
            {"endereco": "  ", "itens": [{"codigo": "PR01", "quantidade": 0}]})
    cenario("Lista de itens vazia", 400, "POST", "/pedidos", {"endereco": "Rua 10", "itens": []})
    cenario("JSON malformado", 400, "POST", "/pedidos", bruto=b'{"endereco": "Rua 10", ')
    cenario("Item que nao existe no banco", 400, "POST", "/pedidos",
            {"endereco": "Rua 10", "itens": [{"codigo": "XX99", "quantidade": 1}]})
    cenario("Item indisponivel (PR05)", 409, "POST", "/pedidos",
            {"endereco": "Rua 10", "itens": [{"codigo": "PR05", "quantidade": 1}]})

    # Opcoes do item (submenu): o Pedidos confere a escolha com o Catalogo -----
    cenario("Refrigerante sem escolher o sabor", 400, "POST", "/pedidos",
            {"endereco": "Rua 10", "itens": [{"codigo": "BE01", "quantidade": 1}]})
    cenario("Sabor que nao existe no cardapio", 400, "POST", "/pedidos",
            {"endereco": "Rua 10", "itens": [{"codigo": "BE01", "quantidade": 1, "opcao": "Fanta Morango"}]})
    cenario("Opcao em prato sem opcoes", 400, "POST", "/pedidos",
            {"endereco": "Rua 10", "itens": [{"codigo": "PR01", "quantidade": 1, "opcao": "Grande"}]})

    def opcoes_gravadas(esperadas):
        def conferir(resposta):
            itens = (resposta or {}).get("pedido", {}).get("itens", []) if isinstance(resposta, dict) else []
            gravadas = [i.get("opcao") for i in itens]
            return None if gravadas == esperadas else "opcoes gravadas %s, esperadas %s" % (gravadas, esperadas)
        return conferir

    cenario("Agua com gas e dois sabores de refrigerante", 201, "POST", "/pedidos",
            {"endereco": "Rua 10", "itens": [{"codigo": "BE03", "quantidade": 1, "opcao": "com gás"},
                                             {"codigo": "BE01", "quantidade": 2, "opcao": "Coca-Cola Zero"},
                                             {"codigo": "BE01", "quantidade": 1, "opcao": "Fanta Uva"}]},
            conferir=opcoes_gravadas(["Com gás", "Coca-Cola Zero", "Fanta Uva"]))

    cenario("Consulta do pedido criado", 200, "GET", "/pedidos/" + pedido_id)
    cenario("Pedido inexistente", 404, "GET", "/pedidos/" + ID_INEXISTENTE)
    cenario("Avanca status RECEBIDO -> EM_PREPARO", 200, "PATCH", "/pedidos/%s/status" % pedido_id, {"status": "EM_PREPARO"})
    cenario("Repetir o mesmo status e idempotente", 200, "PATCH", "/pedidos/%s/status" % pedido_id,
            {"status": "EM_PREPARO"})
    cenario("Pula etapa EM_PREPARO -> ENTREGUE", 409, "PATCH", "/pedidos/%s/status" % pedido_id, {"status": "ENTREGUE"})
    cenario("Status fora da lista", 400, "PATCH", "/pedidos/%s/status" % pedido_id, {"status": "CANCELADO"})
    cenario("Cliente tentando avancar o status", 403, "PATCH", "/pedidos/%s/status" % pedido_id,
            {"status": "PRONTO"}, autorizacao=bearer_cliente)

    # Posse dos pedidos: cliente so ve os seus, cozinha ve todos ----------------
    criado_cliente = cenario(
        "Cliente faz o proprio pedido", 201, "POST", "/pedidos",
        {"endereco": "Av. Universitaria, 1", "itens": [{"codigo": "BE01", "quantidade": 1, "opcao": "Guaraná"}]},
        autorizacao=bearer_cliente, conferir=dono_e(cliente),
    )
    pedido_cliente = (criado_cliente or {}).get("pedido", {}).get("pedido_id", ID_INEXISTENTE)

    def so_do_cliente(resposta):
        pedidos = (resposta or {}).get("pedidos", []) if isinstance(resposta, dict) else []
        if (resposta or {}).get("escopo") != "meus":
            return "escopo deveria ser 'meus'"
        if any(p.get("usuario_id") != cliente.get("id") for p in pedidos):
            return "a lista do cliente trouxe pedido de outro usuario"
        if pedido_cliente not in [p.get("pedido_id") for p in pedidos]:
            return "o pedido do proprio cliente nao apareceu"
        return None

    cenario("Cliente lista so os proprios pedidos", 200, "GET", "/pedidos?limite=50",
            autorizacao=bearer_cliente, conferir=so_do_cliente)
    cenario("Cliente consulta o proprio pedido", 200, "GET", "/pedidos/" + pedido_cliente, autorizacao=bearer_cliente)
    cenario("Cliente nao ve o pedido de outro usuario", 404, "GET", "/pedidos/" + pedido_id, autorizacao=bearer_cliente)

    def cozinha_ve_todos(resposta):
        ids = [p.get("pedido_id") for p in (resposta or {}).get("pedidos", [])] if isinstance(resposta, dict) else []
        if (resposta or {}).get("escopo") != "todos":
            return "escopo deveria ser 'todos'"
        if pedido_id not in ids or pedido_cliente not in ids:
            return "a cozinha deveria ver o pedido dela e o do cliente"
        return None

    cenario("Cozinha lista os pedidos de todos", 200, "GET", "/pedidos?limite=50", conferir=cozinha_ve_todos)
    cenario("Cozinha consulta o pedido do cliente", 200, "GET", "/pedidos/" + pedido_cliente)

    # Filtros da listagem (aplicados no banco) --------------------------------
    def todos(condicao, descricao):
        def conferir(resposta):
            pedidos = (resposta or {}).get("pedidos", []) if isinstance(resposta, dict) else []
            if not pedidos:
                return "a lista veio vazia"
            fora = [p.get("pedido_id", "")[:8] for p in pedidos if not condicao(p)]
            return "pedidos fora do filtro (%s): %s" % (descricao, ", ".join(fora)) if fora else None
        return conferir

    agora = datetime.now(timezone.utc)
    cenario("Filtro por etapa", 200, "GET", "/pedidos?etapa=EM_PREPARO",
            conferir=todos(lambda p: p.get("status") == "EM_PREPARO", "etapa"))
    cenario("Filtro por prato", 200, "GET", "/pedidos?item=BE01",
            conferir=todos(lambda p: any(i.get("codigo") == "BE01" for i in p.get("itens", [])), "prato"))
    cenario("Filtro por periodo (hoje)", 200, "GET", "/pedidos?periodo=hoje",
            conferir=todos(lambda p: agora - datetime.fromisoformat(p["criado_em"]) < timedelta(days=1), "periodo"))
    cenario("Filtro por cliente (cozinha)", 200, "GET", "/pedidos?cliente=teste",
            conferir=todos(lambda p: "teste" in p.get("cliente", "").lower(), "cliente"))
    cenario("Filtro com etapa invalida", 400, "GET", "/pedidos?etapa=CANCELADO")

    # Historico: horario de cada etapa e previsao de entrega -------------------
    def historico_completo(resposta):
        etapas = [e.get("status") for e in (resposta or {}).get("historico", [])] if isinstance(resposta, dict) else []
        if etapas[:1] != ["RECEBIDO"] or not all(e.get("registrado_em") for e in resposta.get("historico", [])):
            return "historico sem a etapa RECEBIDO ou sem horario: %s" % etapas
        if not (resposta or {}).get("previsao_entrega"):
            return "faltou previsao_entrega"
        return None

    cenario("Historico com o horario de cada etapa", 200, "GET", "/pedidos/" + pedido_id, conferir=historico_completo)

    # Tempo real: o cliente recebe a mudanca de etapa sem pedir de novo --------
    eventos_cliente = []
    conectado = threading.Event()
    threading.Thread(target=ouvir_eventos, args=(base, bearer_cliente, eventos_cliente, conectado), daemon=True).start()
    conectado.wait(10)
    time.sleep(1.0)

    def esperar_evento(pid, status_esperado, segundos=8.0):
        limite = time.time() + segundos
        while time.time() < limite:
            for evento, dados in list(eventos_cliente):
                pedido = dados.get("pedido", {}) if isinstance(dados, dict) else {}
                if evento == "pedido" and pedido.get("pedido_id") == pid and pedido.get("status") == status_esperado:
                    return None
            time.sleep(0.2)
        return "o evento nao chegou em %.0f s" % segundos

    cenario("Tempo real: cliente recebe a nova etapa sem recarregar", 200, "PATCH",
            "/pedidos/%s/status" % pedido_cliente, {"status": "EM_PREPARO"},
            conferir=lambda r: esperar_evento(pedido_cliente, "EM_PREPARO"))

    def sem_evento_de(pid):
        def conferir(_resposta):
            time.sleep(2.0)
            vistos = [d.get("pedido", {}).get("pedido_id") for e, d in eventos_cliente if e == "pedido"]
            return "o cliente recebeu evento do pedido de outro usuario" if pid in vistos else None
        return conferir

    cenario("Tempo real: cliente nao recebe pedido de outro usuario", 200, "PATCH",
            "/pedidos/%s/status" % pedido_id, {"status": "PRONTO"}, conferir=sem_evento_de(pedido_id))

    # Saude: health check gRPC dos tres microsservicos ------------------------
    def todos_no_ar(resposta):
        servicos = (resposta or {}).get("servicos", {}) if isinstance(resposta, dict) else {}
        fora = [nome for nome, info in servicos.items() if info.get("health_check") != "SERVING"]
        return "fora do ar: %s" % ", ".join(fora) if fora or len(servicos) != 3 else None

    cenario("Health check dos microsservicos", 200, "GET", "/saude/servicos", conferir=todos_no_ar)
    cenario("Cliente tentando ver a saude dos servicos", 403, "GET", "/saude/servicos", autorizacao=bearer_cliente)

    print("\n" + ("Todos os %d cenarios passaram." % total if falhas == 0
                  else "%d de %d cenario(s) nao sairam como esperado." % (falhas, total)))
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
