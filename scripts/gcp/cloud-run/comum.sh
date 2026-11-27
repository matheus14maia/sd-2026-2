#!/usr/bin/env bash
# Configuracao e funcoes compartilhadas pelos scripts do Cloud Run (Etapa 3).
# Carregado com "source" pelos outros scripts desta pasta.
#
# Feito para o Cloud Shell (console do GCP, icone >_ no alto): o gcloud ja vem
# autenticado com a conta de quem abriu. Tudo pode ser trocado por variavel de
# ambiente, ex.: REGIAO=southamerica-east1 bash implantar.sh
#
# SIMULAR=1 mostra os comandos do gcloud em vez de executar (confere o roteiro
# sem mexer no projeto e sem gastar credito).

set -euo pipefail

PROJETO="${PROJETO:-sistemas-distribuidos-505422}"
REGIAO="${REGIAO:-us-central1}"
ZONA="${ZONA:-us-central1-a}"
BANCO="${BANCO:-delivery-postgres}"          # instancia Cloud SQL (a mesma do Trabalho 2)
NOME_BANCO="${NOME_BANCO:-delivery}"
USUARIO_BANCO="${USUARIO_BANCO:-postgres}"
REPOSITORIO="${REPOSITORIO:-delivery}"        # repositorio Docker no Artifact Registry
DEMO_LOGIN="${DEMO_LOGIN:-professor}"
MAX_INSTANCIAS="${MAX_INSTANCIAS:-2}"         # teto de instancias por servico (controla o custo)
IMAGENS="$REGIAO-docker.pkg.dev/$PROJETO/$REPOSITORIO"

SA_GATEWAY="delivery-gateway@$PROJETO.iam.gserviceaccount.com"
SA_SERVICOS="delivery-servicos@$PROJETO.iam.gserviceaccount.com"
SA_FRONTEND="delivery-frontend@$PROJETO.iam.gserviceaccount.com"

# Servicos do Cloud Run, na ordem da tabela de links do relatorio.
SERVICOS=(delivery-frontend delivery-gateway delivery-usuarios delivery-catalogo delivery-pedidos)
# VMs classicas (Compute Engine) que a Etapa 3 manda desligar ou excluir: as tres
# do Trabalho 2 e a aula-sd-1, criada nas primeiras aulas.
VMS_TRABALHO2=(servidor-delivery delivery-gateway delivery-frontend aula-sd-1)
IPS_TRABALHO2=(ip-delivery-gateway ip-delivery-frontend ip-servidor-delivery)

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SIMULAR="${SIMULAR:-0}"

simulando() { [[ "$SIMULAR" == "1" ]]; }

# gcloud com projeto fixo e sem perguntas.
g() {
  if simulando; then
    echo "+ gcloud $*" >&2
    return 0
  fi
  gcloud "$@" --project "$PROJETO" --quiet
}

etapa() { printf '\n== %s\n' "$*"; }
info() { printf '   %s\n' "$*"; }

# O recurso existe? (no modo simulado, nunca: mostra o caminho da primeira implantacao)
existe() {
  simulando && return 1
  "$@" >/dev/null 2>&1
}

# Permissao recem-criada no IAM demora alguns segundos para valer.
com_retentativa() {
  local tentativa
  for tentativa in 1 2 3 4 5; do
    if "$@"; then
      return 0
    fi
    info "tentativa $tentativa falhou; de novo em $((tentativa * 5)) s"
    sleep $((tentativa * 5))
  done
  return 1
}

# URL https do servico no Cloud Run ("" se ainda nao existe).
url_de() {
  if simulando; then
    echo "https://$1-simulado-uc.a.run.app"
    return
  fi
  gcloud run services describe "$1" --region "$REGIAO" --project "$PROJETO" --quiet \
    --format 'value(status.url)' 2>/dev/null || true
}

# Nome de conexao do Cloud SQL (projeto:regiao:instancia), usado pelo conector.
conexao_do_banco() {
  if simulando; then
    echo "$PROJETO:$REGIAO:$BANCO"
    return
  fi
  gcloud sql instances describe "$BANCO" --project "$PROJETO" --quiet --format 'value(connectionName)'
}

estado_do_banco() {
  simulando && { echo "RUNNABLE"; return; }
  gcloud sql instances describe "$BANCO" --project "$PROJETO" --quiet --format 'value(state)' 2>/dev/null \
    || echo "INEXISTENTE"
}

# Operacoes do Cloud SQL ainda em andamento (o patch --async e uma delas).
operacoes_pendentes() {
  simulando && { echo 0; return; }
  gcloud sql operations list --instance "$BANCO" --project "$PROJETO" --quiet \
    --filter 'status!=DONE' --format 'value(name)' 2>/dev/null | grep -c . || true
}

# Pronto = RUNNABLE e sem operacao pendente. So o estado nao basta: logo depois
# do patch --async o banco ainda responde RUNNABLE e em seguida passa minutos em
# MAINTENANCE aplicando a mudanca (ver TROUBLESHOOTING 2026-11-27).
esperar_banco() {
  local espera
  for espera in $(seq 1 90); do
    if [[ "$(estado_do_banco)" == "RUNNABLE" && "$(operacoes_pendentes)" == "0" ]]; then
      info "Cloud SQL $BANCO: RUNNABLE"
      return 0
    fi
    info "aguardando o Cloud SQL ligar ($((espera * 10)) s)..."
    sleep 10
  done
  # A operacao as vezes fica RUNNING muito depois de o banco atender: com
  # RUNNABLE, segue com um aviso em vez de parar o script.
  if [[ "$(estado_do_banco)" == "RUNNABLE" ]]; then
    info "Cloud SQL $BANCO: RUNNABLE (operacao do patch ainda aberta; seguindo)"
    return 0
  fi
  echo "O Cloud SQL $BANCO nao ligou em 15 minutos." >&2
  return 1
}
