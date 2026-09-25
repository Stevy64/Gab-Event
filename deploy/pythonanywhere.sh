#!/usr/bin/env bash
# Mise à jour Gab Event sur PythonAnywhere (à lancer sur le serveur).
set -euo pipefail

PROJECT="${PA_PROJECT_DIR:-$HOME/Gab-Event}"
VENV="${PA_VENV:-$PROJECT/.venv}"
BRANCH="${PA_BRANCH:-main}"
HOST="${PYTHONANYWHERE_HOST:-www.pythonanywhere.com}"
USER_NAME="${PYTHONANYWHERE_USERNAME:-$(whoami)}"
DOMAIN="${PYTHONANYWHERE_DOMAIN:-${USER_NAME}.pythonanywhere.com}"

if [ ! -f "$PROJECT/manage.py" ]; then
  echo "Projet introuvable : $PROJECT/manage.py"
  exit 1
fi

cd "$PROJECT"

if [ -d .git ]; then
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
fi

if [ -f "$VENV/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
else
  echo "Virtualenv introuvable : $VENV"
  echo "Créez-le : python3.10 -m venv $VENV && source $VENV/bin/activate && pip install -r requirements.txt"
  exit 1
fi

python -m pip install -q -U pip
python -m pip install -q -r requirements.txt
python manage.py check
python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ -n "${PYTHONANYWHERE_API_TOKEN:-}" ]; then
  curl -fsS -X POST \
    -H "Authorization: Token ${PYTHONANYWHERE_API_TOKEN}" \
    "https://${HOST}/api/v0/user/${USER_NAME}/webapps/${DOMAIN}/reload/" \
    >/dev/null
  echo "Web app rechargée : https://${DOMAIN}/"
else
  echo "Reload API ignoré (PYTHONANYWHERE_API_TOKEN vide)."
  echo "Rechargez l’appli depuis l’onglet Web PythonAnywhere."
fi

echo "Déploiement PythonAnywhere terminé."
