#!/usr/bin/env bash
# Mostra como esta o projeto: Cloud SQL, links dos servicos do Cloud Run e VMs
# (na apresentacao, prova que nenhuma VM esta ligada).
#
#   bash scripts/gcp/cloud-run/status.sh

source "$(dirname "$0")/comum.sh"

echo "Cloud SQL $BANCO: $(estado_do_banco)"
echo
echo "| Servico | URL |"
echo "|---|---|"
for servico in "${SERVICOS[@]}"; do
  echo "| $servico | $(url_de "$servico") |"
done
echo
echo "VMs no Compute Engine (a Etapa 3 exige nenhuma ligada):"
if simulando; then
  echo "+ gcloud compute instances list"
else
  gcloud compute instances list --project "$PROJETO" --quiet --format 'table(name,zone.basename(),status)' 2>/dev/null \
    || echo "   (Compute Engine sem instancias ou API desligada)"
fi
