#!/usr/bin/env bash
# Startup-script das VMs novas (delivery-gateway e delivery-frontend).
#
# O GCP roda este script como root a cada boot. Na primeira vez ele instala
# Docker (repositorio oficial, com o plugin compose) e Git; nas seguintes so
# confere que o Docker esta habilitado, entao o boot continua rapido. Os
# containers voltam sozinhos pelo `restart: always` do compose.
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y ca-certificates curl git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

systemctl enable --now docker
