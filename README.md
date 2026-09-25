# Gab Event

Plateforme **multi-événements** de gestion d'invitations avec QR Code, scan smartphone et formules Freemium.

Fork évolutif de l'application cérémonie ATC : `1 plateforme = plusieurs utilisateurs = plusieurs événements`.

---

## Fonctionnalités

| Zone | Contenu |
|------|---------|
| Landing | Création de compte, offres, CTA gratuit |
| Événements | Wizard type → infos → formule |
| Formules | Gratuit (30) · Petit · Moyen · Mariage · Grand (admin) |
| Invitations | QR uniques, cartes PNG, ZIP, flyer |
| Scan | Lookup + admission atomique (auth requise) |
| Quotas | Limites plan / snapshot vérifiées serveur + import |
| Paiement | Abstraction + MockProvider (dev uniquement) |
| Admin | `/platform-admin/` utilisateurs, événements, formules |
| PWA | Installable iPhone / Android |

---

## Installation locale

```powershell
cd Gab_Event
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

| Page | URL |
|------|-----|
| Landing | http://127.0.0.1:8000/ |
| Scanner | http://127.0.0.1:8000/app/ |
| Mes événements | http://127.0.0.1:8000/mes-evenements/ |
| Platform admin | http://127.0.0.1:8000/platform-admin/ |
| Django Admin | http://127.0.0.1:8000/admin/ |

---

## Tests et CI/CD

Chaque push sur `main` lance GitHub Actions : contrôles Django, tests SQLite, tests Postgres, puis (si les secrets sont en place) le déploiement PythonAnywhere.

```bash
python manage.py check --settings=config.test_settings
python manage.py test --settings=config.test_settings
python manage.py collectstatic --noinput
```

| Document | Usage |
|----------|--------|
| [DEPLOY_PYTHONANYWHERE.md](DEPLOY_PYTHONANYWHERE.md) | Production actuelle via GitHub → PythonAnywhere |
| [docs/DEPLOY_OVH.md](docs/DEPLOY_OVH.md) | Livraison VPS OVH Cloud (Docker, domaine, HTTPS) |

---

## Compatibilité legacy

Les codes `ATC24-XXXXXX` et `VIP-XXXXXX` restent valides.  
La migration crée l'événement historique **Ancienne cérémonie ATC** et y rattache les invitations existantes.

---

## Stack

Python 3.10+ / Django 5 / SQLite ou Postgres · openpyxl · qrcode · Pillow · WhiteNoise · GitHub Actions
