#!/usr/bin/env python3
"""Roteiro de tolerancia a falhas: derruba o Catalogo e confere a reacao do sistema.

So usa a biblioteca padrao (urllib). Com a pilha local no ar (docker compose):

    python scripts/testar_resiliencia.py --url http://127.0.0.1:8000

Passos (cada um imprime OK/ERRO):

 1. com tudo no ar, GET /cardapio vem do Catalogo (e o Gateway guarda a lista);
 2. derruba o Catalogo (padrao: `docker compose stop catalogo`);
 3. GET /cardapio continua 200, agora com "origem": "cache" (fallback);
 4. POST /pedidos responde 503 em poucos segundos (Catalogo indisponivel), sem
    gravar nada, com Retry-After;
 5. GET /pedidos continua 200: a queda do Catalogo nao derruba o Pedidos;
 6. depois de algumas falhas o circuito do Catalogo ABRE: uma categoria sem
    lista salva responde 503 na hora, sem esperar timeout;
 7. religa o Catalogo (padrao: `docker compose start catalogo`), espera o
    circuito liberar o teste e confere que tudo volta sozinho.

Modo rajada (falha parcial): com CATALOGO_FALHA_PERCENTUAL=50 no .env e
`docker compose up -d catalogo`, rode com --rajada 30 para ver quantas
respostas vieram do Catalogo gracas ao retry (os logs mostram as repeticoes).
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request


def chamar(base, metodo, rota, corpo=None, token=""):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    requisicao = urllib.request.Request(base + rota, data=dados, method=metodo)
    if dados is not None:
        requisicao.add_header("Content-Type", "application/json")
    if token:
        requisicao.add_header("Authorization", "Bearer " + token)
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(requisicao, timeout=30) as resposta:
            corpo_resposta = json.loads(resposta.read() or b"null")
            return resposta.status, corpo_resposta, resposta.headers, time.perf_counter() - inicio
    except urllib.error.HTTPError as erro:
        conteudo = erro.read()
        try:
            corpo_resposta = json.loads(conteudo)
        except ValueError:
            corpo_resposta = conteudo.decode(errors="replace")
        return erro.code, corpo_resposta, erro.headers, time.perf_counter() - inicio


def rodar(comando):
    print("    $ " + comando, flush=True)
    resultado = subprocess.run(comando, shell=True)
    if resultado.returncode != 0:
        print("    (o comando terminou com codigo %d)" % resultado.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--login", default=os.getenv("DEMO_LOGIN", "professor"))
    parser.add_argument("--senha", default=os.getenv("DEMO_SENHA", ""),
                        help="senha do usuario da cozinha (padrao: variavel DEMO_SENHA)")
    parser.add_argument("--derrubar", default="docker compose stop catalogo",
                        help="comando que derruba o Catalogo")
    parser.add_argument("--religar", default="docker compose start catalogo",
                        help="comando que religa o Catalogo")
    parser.add_argument("--espera-circuito", type=float, default=16,
                        help="segundos com o circuito aberto antes do teste (DISJUNTOR_ABERTO_SEGUNDOS + 1)")
    parser.add_argument("--rajada", type=int, default=0,
                        help="so faz N chamadas GET /cardapio e conta de onde veio cada resposta")
    args = parser.parse_args()
    if not args.senha:
        parser.error("informe a senha da cozinha com --senha ou na variavel DEMO_SENHA")
    base = args.url.rstrip("/")

    status, sessao, _, _ = chamar(base, "POST", "/auth/login", {"login": args.login, "senha": args.senha})
    if status != 200:
        print("Login falhou (%s): %s" % (status, sessao))
        return 1
    token = sessao["access_token"]

    if args.rajada:
        return rajada(base, token, args.rajada)

    falhas = 0

    def passo(titulo, condicao, detalhe=""):
        nonlocal falhas
        falhas += 0 if condicao else 1
        print("%s %s%s" % ("OK  " if condicao else "ERRO", titulo, ("  (" + detalhe + ")") if detalhe else ""),
              flush=True)

    def circuito_catalogo():
        _, saude, _, _ = chamar(base, "GET", "/saude")
        return (saude or {}).get("circuitos", {}).get("catalogo", {})

    print("== 1. Tudo no ar")
    status, cardapio, _, _ = chamar(base, "GET", "/cardapio", token=token)
    passo("GET /cardapio vem do Catalogo", status == 200 and cardapio.get("origem") == "catalogo",
          "status %s, origem %s" % (status, (cardapio or {}).get("origem") if isinstance(cardapio, dict) else "-"))

    print("\n== 2. Derrubando o Catalogo")
    rodar(args.derrubar)
    time.sleep(2)

    print("\n== 3. Fallback do cardapio")
    status, cardapio, _, duracao = chamar(base, "GET", "/cardapio", token=token)
    origem = cardapio.get("origem") if isinstance(cardapio, dict) else "-"
    passo("GET /cardapio responde 200 com a lista salva", status == 200 and origem == "cache",
          "status %s, origem %s, %.0f ms" % (status, origem, duracao * 1000))
    if isinstance(cardapio, dict) and cardapio.get("aviso"):
        print("    aviso: " + cardapio["aviso"])

    print("\n== 4. Pedido com o Catalogo fora")
    status, resposta, cabecalhos, duracao = chamar(
        base, "POST", "/pedidos", {"endereco": "Rua do Teste, 1", "itens": [{"codigo": "PR01", "quantidade": 1}]},
        token=token)
    passo("POST /pedidos responde 503 sem gravar", status == 503,
          "status %s em %.1f s, Retry-After %s" % (status, duracao, cabecalhos.get("Retry-After", "-")))
    if isinstance(resposta, dict):
        print("    mensagem: " + str(resposta.get("mensagem")))

    print("\n== 5. Isolamento: Pedidos continua no ar")
    status, _, _, _ = chamar(base, "GET", "/pedidos?limite=3", token=token)
    passo("GET /pedidos responde 200", status == 200, "status %s" % status)

    print("\n== 6. Circuit breaker")
    for _ in range(5):
        if circuito_catalogo().get("circuito") == "ABERTO":
            break
        chamar(base, "GET", "/cardapio?categoria=Sobremesas", token=token)
    estado = circuito_catalogo()
    passo("Circuito do Catalogo ABERTO", estado.get("circuito") == "ABERTO", json.dumps(estado))
    status, resposta, cabecalhos, duracao = chamar(base, "GET", "/cardapio?categoria=Entradas", token=token)
    passo("Com o circuito aberto, categoria sem lista salva falha na hora com 503",
          status == 503 and duracao < 1.0,
          "status %s em %.0f ms, Retry-After %s" % (status, duracao * 1000, cabecalhos.get("Retry-After", "-")))

    print("\n== 7. Recuperacao")
    rodar(args.religar)
    print("    aguardando %.0f s (circuito aberto) ..." % args.espera_circuito, flush=True)
    time.sleep(args.espera_circuito)
    status, cardapio = 0, {}
    for _ in range(30):
        status, cardapio, _, _ = chamar(base, "GET", "/cardapio", token=token)
        if status == 200 and isinstance(cardapio, dict) and cardapio.get("origem") == "catalogo":
            break
        time.sleep(2)
    origem = cardapio.get("origem") if isinstance(cardapio, dict) else "-"
    passo("GET /cardapio volta a vir do Catalogo", status == 200 and origem == "catalogo",
          "status %s, origem %s" % (status, origem))
    passo("Circuito do Catalogo FECHADO", circuito_catalogo().get("circuito") == "FECHADO")
    status, resposta, _, _ = chamar(
        base, "POST", "/pedidos", {"endereco": "Rua do Teste, 1", "itens": [{"codigo": "PR01", "quantidade": 1}]},
        token=token)
    passo("POST /pedidos volta a gravar (201)", status == 201, "status %s" % status)

    print("\n" + ("Tolerancia a falhas OK." if falhas == 0 else "%d passo(s) com ERRO." % falhas))
    return 0 if falhas == 0 else 1


def rajada(base, token, quantidade) -> int:
    contagem = {}
    for numero in range(1, quantidade + 1):
        status, resposta, _, duracao = chamar(base, "GET", "/cardapio", token=token)
        origem = resposta.get("origem", "-") if isinstance(resposta, dict) else "-"
        chave = "%s %s" % (status, origem)
        contagem[chave] = contagem.get(chave, 0) + 1
        print("%3d  %s  %4.0f ms" % (numero, chave, duracao * 1000), flush=True)
    print("\nResumo (status origem: quantidade)")
    for chave, total in sorted(contagem.items()):
        print("  %-16s %d" % (chave, total))
    print("Veja as repeticoes nos logs: docker compose logs gateway | grep -i repetindo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
