# Gab Event

Plateforme **multi-événements** pour invitations QR, contrôle d’accès smartphone et **billetterie publique** (ventes de billets en F CFA).

Deux espaces organisateur **distincts** :

| Espace | Usage | Navigation |
|--------|--------|------------|
| **Événements** | Invitations, cartes, scan, présence | Dock Accueil / Créer / Profil / Menu |
| **Billetterie** | Ventes payantes, agenda public, encaissements | Dock Ventes / Créer / Agenda / Menu |

---

## Fonctionnalités

| Zone | Contenu |
|------|---------|
| Landing | Offres, CTA, menu mobile animé |
| Événements | Wizard type → infos → formule, style, scan |
| Billetterie | Hub ventes, setup affiche/tarifs, dashboard, recover ticket |
| Agenda public | Bottom sheet, countdown, CTA vert « Acheter un billet » |
| Paiement | SingPay (prod) · MockProvider **uniquement** si DEBUG + mock autorisé |
| Admin | `/platform-admin/` + `/admin/` |
| PWA | Installable iPhone / Android |

---

## Installation locale

```powershell
cd Gab_Event
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# DEBUG=True et ALLOW_MOCK_PAYMENTS=True uniquement en local
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

| Page | URL |
|------|-----|
| Landing | http://127.0.0.1:8000/ |
| Mes événements | http://127.0.0.1:8000/mes-evenements/ |
| Billetterie | http://127.0.0.1:8000/billetterie/ |
| Platform admin | http://127.0.0.1:8000/platform-admin/ |
| Health | http://127.0.0.1:8000/health/ |

---

## Documentation

| Document | Public |
|----------|--------|
| [docs/README.md](docs/README.md) | Index documentation |
| [docs/guides/01_Guide_Utilisateur_Partenaires.docx](docs/guides/01_Guide_Utilisateur_Partenaires.docx) | Formation partenaires |
| [docs/guides/02_Guide_Technique_Admin.docx](docs/guides/02_Guide_Technique_Admin.docx) | Admin / maintenance |
| [docs/guides/03_Guide_Installation_Microservices_OVH.docx](docs/guides/03_Guide_Installation_Microservices_OVH.docx) | DevOps VPS + Actions |
| [DEPLOY_PYTHONANYWHERE.md](DEPLOY_PYTHONANYWHERE.md) | Prod actuelle PA |
| [docs/DEPLOY_OVH.md](docs/DEPLOY_OVH.md) | VPS OVH pas-à-pas |
| [docs/DEPLOY_MICROSERVICES.md](docs/DEPLOY_MICROSERVICES.md) | Architecture Compose + CI/CD |

Régénérer les guides Word :

```bash
pip install -r requirements-docs.txt
python scripts/build_prod_guides.py
```

---

## Tests et CI/CD

Chaque push sur `main` lance GitHub Actions : contrôles Django, tests SQLite, tests Postgres. Le déploiement OVH est disponible via workflow manuel (secrets SSH).

```bash
python manage.py check --settings=config.test_settings
python manage.py test --settings=config.test_settings
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --noinput
```

---

## Production — points non négociables

1. `DEBUG=False`
2. `ALLOW_MOCK_PAYMENTS=False`
3. `SECRET_KEY` unique et secret
4. `ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS` HTTPS
5. Migrations appliquées (`migrate --noinput`)
6. Aucun bouton « Simuler un achat » visible (réservé au mock)

---

## Stack

Python 3.10+ · Django 5 · Postgres / SQLite · Redis · Celery · Gunicorn · Nginx · Docker Compose · openpyxl · qrcode · Pillow · WhiteNoise · GitHub Actions
