#!/usr/bin/env bash
# Implanta o Hell's Kitchen nos servicos gerenciados do Google Cloud (Etapa 3):
#
#   imagens   Cloud Build -> Artifact Registry (scripts/gcp/cloud-run/cloudbuild.yaml)
#   senhas    Secret Manager (nunca no repositorio nem em variavel comum)
#   banco     Cloud SQL (PostgreSQL), pelo conector do Cloud Run
#   migrador  job do Cloud Run (cria as tabelas e o usuario da cozinha)
#   servicos  Cloud Run: usuarios, catalogo e pedidos privados (gRPC + HTTP/2),
#             gateway e frontend publicos (HTTPS)
#
# No Cloud Shell, dentro da pasta do repositorio:
#
#   bash scripts/gcp/cloud-run/implantar.sh
#
# Pode rodar de novo a qualquer momento: o que ja existe e reaproveitado e cada
# servico ganha uma revisao nova com o codigo atual. Ao terminar de testar,
# rode desligar.sh para o Cloud SQL nao ficar cobrando.

source "$(dirname "$0")/comum.sh"
cd "$RAIZ"
TAG="${TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo manual)}"

echo "Projeto $PROJETO, regiao $REGIAO, imagens $IMAGENS:$TAG"
simulando && echo "(SIMULAR=1: so mostra os comandos)"

# --------------------------------------------------------------------- APIs
etapa "1/9 Ligando as APIs do projeto"
g services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  sqladmin.googleapis.com secretmanager.googleapis.com cloudtrace.googleapis.com \
  iam.googleapis.com logging.googleapis.com

# --------------------------------------------------------- Artifact Registry
etapa "2/9 Repositorio de imagens no Artifact Registry"
if existe g artifacts repositories describe "$REPOSITORIO" --location "$REGIAO"; then
  info "$REPOSITORIO ja existe"
else
  g artifacts repositories create "$REPOSITORIO" --repository-format docker --location "$REGIAO" \
    --description "Imagens do Hell's Kitchen (Etapa 3)"
fi

# ------------------------------------------------------------------ Cloud SQL
etapa "3/9 Banco no Cloud SQL"
if ! simulando && [[ "$(estado_do_banco)" == "INEXISTENTE" ]]; then
  info "criando a instancia $BANCO (leva uns 10 minutos)..."
  g sql instances create "$BANCO" --database-version POSTGRES_16 --edition enterprise \
    --tier db-f1-micro --region "$REGIAO" --storage-size 10 --storage-auto-increase
fi
g sql instances patch "$BANCO" --activation-policy ALWAYS
esperar_banco
CONEXAO="$(conexao_do_banco)"
info "conexao: $CONEXAO"
if existe g sql databases describe "$NOME_BANCO" --instance "$BANCO"; then
  info "banco $NOME_BANCO ja existe"
else
  g sql databases create "$NOME_BANCO" --instance "$BANCO"
fi

# ------------------------------------------------------------- Secret Manager
etapa "4/9 Senhas no Secret Manager"

# Grava a primeira versao do segredo. O valor vai pela entrada padrao
# (--data-file=-): nao aparece na tela, no historico nem em arquivo.
gravar_segredo() {
  local nome="$1" valor="$2"
  if simulando; then
    echo "+ gcloud secrets create $nome --data-file=- (valor oculto)" >&2
    return
  fi
  printf '%s' "$valor" | gcloud secrets create "$nome" --replication-policy automatic \
    --data-file=- --project "$PROJETO" --quiet >/dev/null
  info "$nome criado"
}

if existe g secrets describe delivery-db-senha; then
  info "delivery-db-senha ja existe (mantido)"
else
  # Sem SENHA_BANCO, o script sorteia uma senha nova e troca a do usuario
  # postgres: ninguem precisa saber, ela so existe no Secret Manager.
  senha_banco="${SENHA_BANCO:-}"
  if [[ -z "$senha_banco" ]]; then
    senha_banco="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    g sql users set-password "$USUARIO_BANCO" --instance "$BANCO" --password "$senha_banco" >/dev/null
    info "senha nova sorteada para o usuario $USUARIO_BANCO do Cloud SQL"
  fi
  gravar_segredo delivery-db-senha "$senha_banco"
fi

if existe g secrets describe delivery-demo-senha; then
  info "delivery-demo-senha ja existe (mantido)"
else
  senha_cozinha="${DEMO_SENHA:-}"
  while ! simulando && [[ ${#senha_cozinha} -lt 6 ]]; do
    read -r -s -p "   Senha do login '$DEMO_LOGIN' (cozinha), 6 ou mais caracteres: " senha_cozinha
    echo
  done
  gravar_segredo delivery-demo-senha "$senha_cozinha"
fi

if existe g secrets describe delivery-jwt-segredo; then
  info "delivery-jwt-segredo ja existe (mantido)"
else
  gravar_segredo delivery-jwt-segredo "$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
fi

# ------------------------------------------------- contas de servico e papeis
etapa "5/9 Contas de servico (cada componente so com o que precisa)"
criar_conta() {
  local id="$1" descricao="$2"
  if existe g iam service-accounts describe "$id@$PROJETO.iam.gserviceaccount.com"; then
    info "$id ja existe"
  else
    g iam service-accounts create "$id" --display-name "$descricao"
  fi
}
criar_conta delivery-gateway "Hell's Kitchen: API Gateway"
criar_conta delivery-servicos "Hell's Kitchen: microsservicos e migrador"
criar_conta delivery-frontend "Hell's Kitchen: frontend (sem permissoes)"

papel_no_projeto() {
  com_retentativa g projects add-iam-policy-binding "$PROJETO" --member "serviceAccount:$1" \
    --role "$2" --condition None >/dev/null
}
papel_no_projeto "$SA_SERVICOS" roles/cloudsql.client
papel_no_projeto "$SA_SERVICOS" roles/cloudtrace.agent
papel_no_projeto "$SA_GATEWAY" roles/cloudtrace.agent

acesso_ao_segredo() {
  com_retentativa g secrets add-iam-policy-binding "$1" --member "serviceAccount:$2" \
    --role roles/secretmanager.secretAccessor >/dev/null
}
acesso_ao_segredo delivery-db-senha "$SA_SERVICOS"
acesso_ao_segredo delivery-demo-senha "$SA_SERVICOS"
acesso_ao_segredo delivery-jwt-segredo "$SA_GATEWAY"

# Conta que o Cloud Build usa. Em projeto de organizacao ela pode vir sem
# permissao nenhuma; o build precisa ler o codigo enviado, escrever o log e
# publicar as imagens.
if simulando; then
  SA_BUILD="NUMERO-compute@developer.gserviceaccount.com"
else
  SA_BUILD="$(gcloud builds get-default-service-account --project "$PROJETO" \
    --format 'value(serviceAccountEmail)' 2>/dev/null | sed 's#.*/##')"
fi
if [[ -n "$SA_BUILD" ]]; then
  for papel in roles/artifactregistry.writer roles/logging.logWriter roles/storage.objectViewer; do
    papel_no_projeto "$SA_BUILD" "$papel"
  done
  info "Cloud Build ($SA_BUILD) pode publicar as imagens"
fi
info "papeis conferidos"

# ------------------------------------------------------------------- imagens
etapa "6/9 Imagens: Cloud Build -> Artifact Registry (uns 10 minutos)"
g builds submit --config scripts/gcp/cloud-run/cloudbuild.yaml \
  --substitutions "_IMAGENS=$IMAGENS,_TAG=$TAG" .

# ----------------------------------------------------------------- migrador
etapa "7/9 Migrador (job do Cloud Run): tabelas, cardapio e usuario da cozinha"
VARIAVEIS_BANCO="DB_HOST=/cloudsql/$CONEXAO,DB_NAME=$NOME_BANCO,DB_USER=$USUARIO_BANCO,DB_SSLMODE=disable"
g run jobs deploy delivery-migrador --image "$IMAGENS/migrador:$TAG" --region "$REGIAO" \
  --service-account "$SA_SERVICOS" --set-cloudsql-instances "$CONEXAO" \
  --set-env-vars "$VARIAVEIS_BANCO,DEMO_LOGIN=$DEMO_LOGIN" \
  --set-secrets "DB_PASSWORD=delivery-db-senha:latest,DEMO_SENHA=delivery-demo-senha:latest" \
  --max-retries 1 --task-timeout 10m
g run jobs execute delivery-migrador --region "$REGIAO" --wait

# ----------------------------------------------------------- microsservicos
etapa "8/9 Microsservicos no Cloud Run (privados, gRPC com HTTP/2)"
COMUM_SERVICOS="$VARIAVEIS_BANCO,DB_POOL_MAX=3,MAX_WORKERS=20,LOG_JSON=1,GOOGLE_CLOUD_PROJECT=$PROJETO,RASTREAMENTO=gcp"

implantar_microsservico() {
  local nome="$1" extra="${2:-}"
  # --no-allow-unauthenticated: so quem tem roles/run.invoker chama (o
  # Gateway e, no Catalogo, o Pedidos), com o token de identidade do Google.
  # --timeout 3600: o stream de tempo real (AcompanharPedidos) fica aberto.
  g run deploy "delivery-$nome" --image "$IMAGENS/$nome:$TAG" --region "$REGIAO" \
    --service-account "$SA_SERVICOS" --no-allow-unauthenticated --use-http2 \
    --set-cloudsql-instances "$CONEXAO" \
    --set-env-vars "$COMUM_SERVICOS${extra:+,$extra}" \
    --set-secrets "DB_PASSWORD=delivery-db-senha:latest" \
    --cpu 1 --memory 512Mi --concurrency 20 --min-instances 0 --max-instances "$MAX_INSTANCIAS" \
    --timeout 3600
}
implantar_microsservico catalogo
implantar_microsservico usuarios
HOST_CATALOGO="$(url_de delivery-catalogo)"
HOST_CATALOGO="${HOST_CATALOGO#https://}"
implantar_microsservico pedidos "CATALOGO_HOST=$HOST_CATALOGO,CATALOGO_PORTA=443"

pode_chamar() {
  com_retentativa g run services add-iam-policy-binding "$1" --region "$REGIAO" \
    --member "serviceAccount:$2" --role roles/run.invoker >/dev/null
}
for servico in delivery-usuarios delivery-catalogo delivery-pedidos; do
  pode_chamar "$servico" "$SA_GATEWAY"
done
pode_chamar delivery-catalogo "$SA_SERVICOS"
info "Gateway pode chamar os tres; Pedidos pode chamar o Catalogo"

# ------------------------------------------------------- gateway e frontend
etapa "9/9 Gateway e frontend no Cloud Run (publicos, HTTPS)"

# Publico: allUsers com roles/run.invoker. Organizacao que proibe allUsers no
# IAM (politica de compartilhamento restrito a dominio) recusa esse papel; ai a
# checagem de invocador e desligada no proprio servico, que da o mesmo efeito.
tornar_publico() {
  if g run services add-iam-policy-binding "$1" --region "$REGIAO" --member allUsers \
    --role roles/run.invoker >/dev/null 2>&1; then
    info "$1 publico"
  else
    g run services update "$1" --region "$REGIAO" --no-invoker-iam-check >/dev/null
    info "$1 publico (checagem de invocador desligada: a organizacao bloqueia allUsers)"
  fi
}

host_de() { local url; url="$(url_de "$1")"; echo "${url#https://}"; }
URL_FRONTEND="$(url_de delivery-frontend)"
g run deploy delivery-gateway --image "$IMAGENS/gateway:$TAG" --region "$REGIAO" \
  --service-account "$SA_GATEWAY" \
  --set-env-vars "USUARIOS_HOST=$(host_de delivery-usuarios),USUARIOS_PORTA=443,CATALOGO_HOST=$HOST_CATALOGO,CATALOGO_PORTA=443,PEDIDOS_HOST=$(host_de delivery-pedidos),PEDIDOS_PORTA=443,CORS_ORIGENS=${URL_FRONTEND:-*},LOG_JSON=1,GOOGLE_CLOUD_PROJECT=$PROJETO,RASTREAMENTO=gcp" \
  --set-secrets "JWT_SEGREDO=delivery-jwt-segredo:latest" \
  --cpu 1 --memory 512Mi --min-instances 0 --max-instances "$MAX_INSTANCIAS" --timeout 3600
tornar_publico delivery-gateway
URL_GATEWAY="$(url_de delivery-gateway)"

g run deploy delivery-frontend --image "$IMAGENS/frontend:$TAG" --region "$REGIAO" \
  --service-account "$SA_FRONTEND" --set-env-vars "API_URL=$URL_GATEWAY" --port 8080 \
  --cpu 1 --memory 256Mi --min-instances 0 --max-instances "$MAX_INSTANCIAS"
tornar_publico delivery-frontend
URL_FRONTEND="$(url_de delivery-frontend)"

# O navegador so pode chamar o Gateway a partir do endereco do frontend.
g run services update delivery-gateway --region "$REGIAO" --update-env-vars "CORS_ORIGENS=$URL_FRONTEND" >/dev/null
info "CORS do Gateway: $URL_FRONTEND"

# ----------------------------------------------------------------- resumo
etapa "Pronto. Links HTTPS de cada servico (tabela do relatorio):"
echo
echo "| Servico | Acesso | URL |"
echo "|---|---|---|"
for servico in "${SERVICOS[@]}"; do
  case "$servico" in
    delivery-frontend|delivery-gateway) acesso="publico" ;;
    *) acesso="privado (gRPC, IAM)" ;;
  esac
  echo "| $servico | $acesso | $(url_de "$servico") |"
done
echo
echo "Abra o frontend: $URL_FRONTEND"
echo "Teste ponta a ponta (84 cenarios):"
echo "  python3 scripts/testar_gateway.py --url $URL_GATEWAY --resumido --senha <senha da cozinha>"
echo "Quando terminar de testar, para o banco nao ficar cobrando:"
echo "  bash scripts/gcp/cloud-run/desligar.sh"
