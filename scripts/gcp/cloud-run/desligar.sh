#!/usr/bin/env bash
# Deixa o projeto sem gastar credito entre os testes e a apresentacao:
#
#   Cloud SQL  desligado (activation-policy NEVER): para de cobrar CPU e
#              memoria; o disco continua guardando os dados.
#   Cloud Run  ja nao cobra parado (0 instancias sem requisicao); nada a fazer.
#   VMs        as do Trabalho 2 ficam paradas. A Etapa 3 exige "VM desligada ou
#              excluida": com --excluir-vms elas sao excluidas, os IPs fixos
#              liberados e o IP antigo da VM sai das redes autorizadas do Cloud
#              SQL (o Cloud Run usa o conector, nao precisa dela). Nao da para
#              desfazer.
#
#   bash scripts/gcp/cloud-run/desligar.sh
#   bash scripts/gcp/cloud-run/desligar.sh --excluir-vms
#
# Para religar antes da apresentacao: bash scripts/gcp/cloud-run/ligar.sh

source "$(dirname "$0")/comum.sh"
EXCLUIR_VMS=0
[[ "${1:-}" == "--excluir-vms" ]] && EXCLUIR_VMS=1

etapa "Cloud SQL"
estado="$(estado_do_banco)"
if [[ "$estado" == "INEXISTENTE" ]]; then
  info "nao ha instancia $BANCO"
else
  if (( EXCLUIR_VMS )); then
    # A rede autorizada era o IP da VM servidor-delivery (Trabalho 2). Liberado,
    # esse IP pode ir para outro cliente do Google; o Cloud Run nao usa a lista.
    if g sql instances patch "$BANCO" --clear-authorized-networks >/dev/null; then
      info "redes autorizadas do $BANCO removidas (o Cloud Run usa o conector)"
    else
      info "nao deu para limpar as redes autorizadas agora; rode de novo com o banco ligado"
    fi
  fi
  g sql instances patch "$BANCO" --activation-policy NEVER
  info "$BANCO desligado (estava $estado); os dados ficam guardados"
fi

etapa "VMs do Trabalho 2 (Compute Engine)"
VMS_PARADAS=0
for vm in "${VMS_TRABALHO2[@]}"; do
  if simulando; then
    situacao="RUNNING"
  else
    situacao="$(gcloud compute instances describe "$vm" --zone "$ZONA" --project "$PROJETO" --quiet \
      --format 'value(status)' 2>/dev/null || true)"
  fi
  if [[ -z "$situacao" ]]; then
    info "$vm: nao existe"
  elif (( EXCLUIR_VMS )); then
    g compute instances delete "$vm" --zone "$ZONA"
    info "$vm excluida"
  elif [[ "$situacao" != "TERMINATED" ]]; then
    g compute instances stop "$vm" --zone "$ZONA"
    info "$vm parada"
    VMS_PARADAS=1
  else
    info "$vm ja estava parada"
    VMS_PARADAS=1
  fi
done
if (( EXCLUIR_VMS )); then
  for ip in "${IPS_TRABALHO2[@]}"; do
    if simulando || gcloud compute addresses describe "$ip" --region "$REGIAO" --project "$PROJETO" --quiet \
      >/dev/null 2>&1; then
      g compute addresses delete "$ip" --region "$REGIAO"
      info "IP fixo $ip liberado"
    fi
  done
fi

etapa "Situacao"
bash "$(dirname "$0")/status.sh" --curto
echo
echo "Ficam cobrando so centavos: o disco do Cloud SQL, as imagens no Artifact"
echo "Registry e os segredos. O Cloud Run nao cobra parado."
if (( VMS_PARADAS )); then
  echo "As VMs paradas ainda cobram o disco e os IPs fixos; para zerar (sem volta):"
  echo "  bash scripts/gcp/cloud-run/desligar.sh --excluir-vms"
fi
