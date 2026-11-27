#!/usr/bin/env bash
# Liga o Cloud SQL para usar o sistema (testes ou apresentacao). Leva uns 2 a
# 5 minutos. Os microsservicos e o frontend sobem sozinhos na primeira
# requisicao; o Gateway fica com 1 instancia sempre ligada ate o desligar.sh.
#
#   bash scripts/gcp/cloud-run/ligar.sh
#
# Depois de usar: bash scripts/gcp/cloud-run/desligar.sh

source "$(dirname "$0")/comum.sh"

etapa "Cloud SQL"
# --async: o gcloud desiste de esperar o patch antes de o banco terminar de
# ligar ("is taking longer than expected") e o script pararia; quem espera e o
# esperar_banco, ate 15 minutos (RUNNABLE e sem operacao pendente).
g sql instances patch "$BANCO" --activation-policy ALWAYS --async >/dev/null
esperar_banco

# Gateway com exatamente uma instancia enquanto o sistema esta ligado: o
# circuit breaker e o cardapio salvo (fallback) ficam na memoria da instancia.
# Com uma so, a demonstracao de falha ve sempre o mesmo circuito e o mesmo
# cache, e a primeira requisicao nao espera partida a frio. desligar.sh volta
# para 0 instancias (sem custo parado).
etapa "Gateway com 1 instancia fixa"
g run services update delivery-gateway --region "$REGIAO" --min-instances 1 --max-instances 1 >/dev/null
info "delivery-gateway: min 1, max 1"

etapa "Servicos"
bash "$(dirname "$0")/status.sh"
