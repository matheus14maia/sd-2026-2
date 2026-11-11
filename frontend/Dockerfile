# Frontend React. Multi-stage: o Node so existe no estagio de build; a imagem
# final e o nginx sem root (nginx-unprivileged, porta 8080) com os arquivos
# estaticos gerados pelo Vite.
#
#   docker build -t delivery-frontend frontend/

# --------------------------------------------------------------------- build
# Imagens base: Docker Hub por padrao; o Cloud Build usa o espelho do Google
# (mirror.gcr.io) para nao esbarrar no limite de downloads do Docker Hub.
ARG IMAGEM_NODE=node:22-alpine
ARG IMAGEM_NGINX=nginxinc/nginx-unprivileged:1.28-alpine

FROM ${IMAGEM_NODE} AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY index.html vite.config.js ./
COPY public/ public/
COPY src/ src/
RUN npm run build

# --------------------------------------------------------------------- final
FROM ${IMAGEM_NGINX}
# PORT: porta em que o nginx escuta. API_URL: endereco do Gateway que o
# navegador chama, entregue em /config.js (muda sem rebuild da imagem).
ENV PORT=8080 \
    API_URL=http://localhost:8000
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO /dev/null "http://127.0.0.1:${PORT}/" || exit 1
