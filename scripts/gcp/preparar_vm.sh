#!/usr/bin/env bash
# Prepara uma VM para o seu papel e sobe os containers dela.
#
#   bash preparar_vm.sh servicos                       # VM servidor-delivery
#   bash preparar_vm.sh gateway  <host-dos-servicos> <url-do-frontend>
#   bash preparar_vm.sh frontend <url-do-gateway>
#
# Clona (ou atualiza) o repositorio em ~/sd-2026-2, grava no .env as variaveis
# do papel sem apagar as que ja existem (senha do banco, segredo do JWT) e roda
# `docker compose up -d --build`. Pode rodar de novo a cada atualizacao.
set -euo pipefail

PAPEL="${1:?informe o papel: servicos, gateway ou frontend}"
BRANCH="${BRANCH:-trabalho-parte2}"
REPO="https://github.com/matheus14maia/sd-2026-2.git"
PASTA="$HOME/sd-2026-2"

# Grava CHAVE=valor no .env, trocando a linha se a chave ja existir.
definir() {
  touch .env
  if grep -q "^$1=" .env; then
    sed -i "s|^$1=.*|$1=$2|" .env
  else
    echo "$1=$2" >> .env
  fi
}

echo "== Aguardando o Docker (o startup-script instala no primeiro boot)"
for _ in $(seq 1 60); do
  if command -v git >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then break; fi
  sleep 5
done
sudo docker compose version

echo "== Codigo na branch $BRANCH"
if [ ! -d "$PASTA/.git" ]; then
  git clone "$REPO" "$PASTA"
fi
cd "$PASTA"
git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo "== Configurando o .env do papel $PAPEL"
case "$PAPEL" in
  servicos)
    # O .env desta VM ja tem DB_* do Cloud SQL; so o profile muda.
    grep -q '^DB_HOST=' .env || { echo "ERRO: .env sem DB_HOST (ver .env.exemplo)"; exit 1; }
    definir COMPOSE_PROFILES servicos
    definir GRPC_BIND 0.0.0.0
    # O Gateway saiu desta VM: remove o container antigo, se ainda existir.
    sudo docker rm -f delivery-gateway >/dev/null 2>&1 || true
    ;;
  gateway)
    HOST_SERVICOS="${2:?informe o host interno da VM dos microsservicos}"
    URL_FRONTEND="${3:?informe a URL do frontend (CORS)}"
    definir COMPOSE_PROFILES gateway
    definir USUARIOS_HOST "$HOST_SERVICOS"
    definir CATALOGO_HOST "$HOST_SERVICOS"
    definir PEDIDOS_HOST "$HOST_SERVICOS"
    definir CORS_ORIGENS "$URL_FRONTEND"
    definir JWT_EXPIRACAO_MINUTOS 60
    # O segredo e gerado uma vez e fica so nesta VM.
    grep -q '^JWT_SEGREDO=.' .env || definir JWT_SEGREDO "$(openssl rand -hex 32)"
    ;;
  frontend)
    URL_GATEWAY="${2:?informe a URL do Gateway}"
    definir COMPOSE_PROFILES frontend
    definir API_URL "$URL_GATEWAY"
    ;;
  *)
    echo "papel desconhecido: $PAPEL"; exit 1 ;;
esac
chmod 600 .env

echo "== Subindo os containers"
sudo docker compose up -d --build --remove-orphans
sudo docker compose ps
