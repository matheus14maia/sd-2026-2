#!/usr/bin/env bash
# Liga o Cloud SQL para usar o sistema (testes ou apresentacao). Leva uns 2 a
# 5 minutos. Os servicos do Cloud Run sobem sozinhos na primeira requisicao.
#
#   bash scripts/gcp/cloud-run/ligar.sh
#
# Depois de usar: bash scripts/gcp/cloud-run/desligar.sh

source "$(dirname "$0")/comum.sh"

etapa "Cloud SQL"
g sql instances patch "$BANCO" --activation-policy ALWAYS
esperar_banco

etapa "Servicos"
bash "$(dirname "$0")/status.sh"
