#!/usr/bin/env bash
# Premier démarrage d’un VPS Ubuntu OVH pour Gab Event (Docker).
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Lancez ce script en root : sudo bash deploy/ovh-setup.sh"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git ufw

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

systemctl enable --now docker
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo
echo "Docker est prêt. Ensuite :"
echo "  1. git clone https://github.com/Stevy64/Gab-Event.git /opt/gab-event"
echo "  2. cp /opt/gab-event/.env.example /opt/gab-event/.env  (puis éditer)"
echo "  3. cd /opt/gab-event && docker compose up -d --build"
echo "  4. Suivre docs/DEPLOY_OVH.md pour le nom de domaine et le HTTPS"
