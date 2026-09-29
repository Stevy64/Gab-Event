# Déploiement microservices — Gab Event (OVH + GitHub Actions)

Ce document complète [DEPLOY_OVH.md](DEPLOY_OVH.md) avec une vision **service par service** et le branchement **CI/CD**.

Les supports Word détaillés (formation + admin + install) sont dans [guides/](guides/).

---

## Cartographie des services

```
Internet
   │
   ▼
gabevent-nginx (80/443)  ── staticfiles + media
   │
   ▼
gabevent-web (Gunicorn :8000)
   │
   ├── gabevent-db (Postgres 16)
   └── gabevent-redis (Redis 7)
            ▲
            │
   gabevent-celery-worker
   gabevent-celery-beat
```

| Conteneur | Commande | Dépendances |
|-----------|----------|-------------|
| `gabevent-web` | migrate + collectstatic + gunicorn | db, redis healthy |
| `gabevent-celery-worker` | `celery -A config worker` | db, redis, web |
| `gabevent-celery-beat` | `celery -A config beat` | db, redis, web |
| `gabevent-nginx` | nginx | web healthy |

Fichiers clés :

- `docker-compose.yml` — stack production
- `Dockerfile` — image applicative unique (web/worker/beat)
- `nginx/conf.d/` — vhosts HTTP/HTTPS
- `deploy/ovh-setup.sh` — bootstrap Docker sur VPS
- `deploy/ovh.env.example` — modèle `.env` prod
- `.github/workflows/ci.yml` — contrôles + tests
- `.github/workflows/deploy-ovh.yml` — déploiement SSH

---

## Variables d’environnement production (minimum)

```env
DEBUG=False
ALLOW_MOCK_PAYMENTS=False
SECRET_KEY=<aléatoire long>
ALLOWED_HOSTS=domaine.com,www.domaine.com
CSRF_TRUSTED_ORIGINS=https://domaine.com,https://www.domaine.com
PUBLIC_BASE_URL=https://domaine.com
POSTGRES_PASSWORD=<fort>
PAYMENT_PROVIDER=singpay
SINGPAY_API_KEY=...
SINGPAY_API_SECRET=...
SINGPAY_MERCHANT_ID=...
SINGPAY_ENVIRONMENT=live
```

Ne jamais committer le fichier `.env`.

---

## Pipeline recommandé

1. **Push** sur `main` → workflow **CI** (check + tests SQLite + Postgres).
2. Si CI vert → déclencher **Déployer OVH** (`workflow_dispatch`) ou automatiser après CI.
3. Sur le VPS : `git pull` → `docker compose up -d --build` → `migrate` → `collectstatic` → healthcheck.

Secrets GitHub requis pour le deploy : `OVH_SSH_HOST`, `OVH_SSH_USER`, `OVH_SSH_KEY`.

---

## Commandes de référence

```bash
# Install initiale
git clone https://github.com/Stevy64/Gab-Event.git /opt/gab-event
cd /opt/gab-event
cp deploy/ovh.env.example .env
nano .env
docker compose up -d --build
curl -fsS http://127.0.0.1/health/

# Mise à jour
git pull --ff-only origin main
docker compose up -d --build
docker compose exec -T gabevent-web python manage.py migrate --noinput
docker compose exec -T gabevent-web python manage.py collectstatic --noinput

# Logs
docker compose logs -f --tail=200 gabevent-web gabevent-celery-worker

# Backup
docker compose exec -T gabevent-db pg_dump -U gabevent gabevent > backup.sql
```

---

## Séparation « mock / prod »

| Contexte | DEBUG | ALLOW_MOCK_PAYMENTS | Bouton « Simuler un achat » |
|----------|-------|---------------------|-------------------------------|
| Local | True | True | Visible |
| Staging | False ou True contrôlé | Selon besoin | Selon mock |
| Production | False | False | Masqué |

Le code refuse les callbacks mock si `DEBUG` est faux (`validation/payment_service.py`).

---

## Voir aussi

- [DEPLOY_OVH.md](DEPLOY_OVH.md) — pas-à-pas DNS, Certbot, checklist
- [../DEPLOY_PYTHONANYWHERE.md](../DEPLOY_PYTHONANYWHERE.md) — hébergement actuel alternatif
- [guides/03_Guide_Installation_Microservices_OVH.docx](guides/03_Guide_Installation_Microservices_OVH.docx) — guide Word exhaustif
