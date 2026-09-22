# ATC Graduation Check

Application web **mobile-first** pour contrôler les invitations d’une cérémonie de remise de diplômes (contrôleurs aériens).

Parcours terrain : **Accueil flyer → Scanner QR → Confirmer les places → Suivant**.

---

## Fonctionnalités

| Zone | Contenu |
|------|---------|
| Accueil | Flyer d’invitation (fond photo, typo cérémonie) |
| Scanner | Bottom sheet caméra + saisie manuelle + modal de résultat |
| Validation | Lookup puis admission atomique (places restantes) |
| Codes | `ATC24-XXXXXX` (récipiendaire) · `VIP-XXXXXX` (VIP) |
| Admin | Dashboard type Zanalyze (cartes, graphiques, popups) |
| Invitations | Cartes PNG + ZIP + QR seuls |
| Import / Export | Excel openpyxl |
| PWA | Installable iPhone / Android (manifest + service worker) |

---

## Application installable (PWA)

L’app est une **Progressive Web App** : icône sur l’écran d’accueil, mode plein écran (`standalone`).  
La **validation des invitations reste online** (pas de file d’attente hors-ligne).

| Plateforme | Comment installer |
|------------|-------------------|
| **Android** (Chrome / Edge) | Bannière *Installer*, ou menu ⋮ → **Installer l’application** / **Ajouter à l’écran d’accueil** |
| **iPhone / iPad** (Safari) | Bouton **Partager** → **Sur l’écran d’accueil** → Ajouter |

Prérequis : site servi en **HTTPS** (ou `localhost` en démo). Sur iOS, utiliser **Safari** (pas Chrome).

Fichiers clés : `static/manifest.json`, `static/sw.js` (exposé en `/sw.js`), `static/icons/*`, `static/js/pwa.js`.

---

## Stack

- Python 3.10+ / Django 5 / SQLite
- HTML / CSS / JavaScript vanilla
- `openpyxl`, `qrcode[pil]`, `Pillow`, `python-dotenv`
- Caméra : [html5-qrcode](https://github.com/mebjas/html5-qrcode) (CDN)

---

## Installation locale

```bash
git clone https://github.com/Stevy64/Gab-Event.git
cd Gab-Event
python -m venv venv
```

**Windows (PowerShell)**

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

**Linux / macOS**

```bash
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Compte de démo possible : créer `admin` / `admin` via `createsuperuser` (à changer en prod).

### URLs utiles

| Page | URL |
|------|-----|
| Accueil / scanner | http://127.0.0.1:8000/ |
| Dashboard | http://127.0.0.1:8000/dashboard/ |
| Import | http://127.0.0.1:8000/import/ |
| Recherche | http://127.0.0.1:8000/search/ |
| Admin Django | http://127.0.0.1:8000/admin/ |

---

## Données Excel

Fichier d’exemple : [`data/invitations.xlsx`](data/invitations.xlsx)

Colonnes reconnues (noms souples) :

| Colonne | Rôle |
|---------|------|
| Code | Optionnel — généré si vide (`ATC24-…` / `VIP-…`) |
| Nom / Prenom | Identité |
| Type / Categorie | RECIPIENT, VIP, ou catégorie métier |
| Places | Nombre de personnes autorisées |
| Statut | Valide / Invalide / Désactivé |

```bash
python manage.py import_invitations data/invitations.xlsx
```

Les validations déjà enregistrées **ne sont jamais effacées** au réimport.

---

## Génération des invitations

```bash
# QR PNG seuls
python manage.py generate_qr

# Cartes PNG + archive ZIP (recommandé)
python manage.py generate_invitations
```

Sorties : `generated_qr/`, `generated_invitations/`, `invitations_ceremonie.zip`.

Le QR encode **uniquement** le code (`ATC24-XXXXXX` ou `VIP-XXXXXX`).

---

## API (scan)

Toutes les routes POST exigent le cookie CSRF + en-tête `X-CSRFToken`.

### 1. Lookup — `POST /api/validate/`

Ne consomme **aucune** place.

```json
{ "code": "ATC24-QTKLXQ" }
```

| `status` | Signification |
|----------|----------------|
| `recognized` | Invitation OK — afficher le choix du nombre de personnes |
| `already_used` | Places épuisées |
| `invalid` | Code inconnu / billet désactivé |

### 2. Admission — `POST /api/admit/`

Consomme N places de façon atomique.

```json
{ "code": "ATC24-QTKLXQ", "persons": 2 }
```

| `status` | Signification |
|----------|----------------|
| `admitted` | Entrée enregistrée |
| `already_used` | Plus assez de places |
| `invalid` / `error` | Refus |

---

## Tests

```bash
python manage.py test
```

---

## Variables d’environnement

Voir [`.env.example`](.env.example). **Ne jamais committer** `.env` ni une `SECRET_KEY` de production.

| Variable | Prod |
|----------|------|
| `SECRET_KEY` | Chaîne longue aléatoire |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `votrecompte.pythonanywhere.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://votrecompte.pythonanywhere.com` |
| `CEREMONY_*` | Titre, date, lieu affichés sur le flyer |

---

## Déploiement

Guide pas à pas PythonAnywhere : **[DEPLOY_PYTHONANYWHERE.md](DEPLOY_PYTHONANYWHERE.md)**  
Fichier WSGI d’exemple : [`deploy/pythonanywhere_wsgi.py`](deploy/pythonanywhere_wsgi.py)

### Push GitHub (première fois)

```bash
git init
git add .
git commit -m "Initial commit: ATC Graduation Check"
git branch -M main
git remote add origin https://github.com/VOTRE_COMPTE/ATC_Ceremony.git
git push -u origin main
```

Sur PythonAnywhere : `git clone` ce dépôt, puis suivre le guide de déploiement.

---

## Structure du dépôt

```text
ATC_Ceremony/
├── manage.py
├── requirements.txt
├── .env.example
├── README.md
├── DEPLOY_PYTHONANYWHERE.md
├── deploy/
│   └── pythonanywhere_wsgi.py   # modèle WSGI pour PA
├── config/                      # settings, urls, wsgi
├── validation/                  # métier + API + commandes + tests
├── templates/                   # pages + partials (scanner, admin)
├── static/                      # css, js, img, icons, PWA
├── data/                        # Excel d’exemple
├── generated_qr/                # QR générés (gitignored sauf .gitkeep)
└── generated_invitations/       # cartes PNG (gitignored)
```

### Modules métier (`validation/`)

| Fichier | Rôle |
|---------|------|
| `models.py` | Invitation, ScanLog, Admission |
| `code_service.py` | Génération / normalisation des codes |
| `services.py` | Import, lookup, admit, stats, export |
| `qr_service.py` | PNG QR |
| `card_service.py` | Cartes invitation + ZIP |
| `views.py` | Pages + API |
| `management/commands/` | import / generate_qr / generate_invitations |

---

## Sécurité événement

1. `DEBUG=False` + `SECRET_KEY` unique en prod  
2. HTTPS (PythonAnywhere le fournit) — **requis pour la caméra**  
3. Compte admin fort (pas `admin`/`admin` en prod)  
4. Ne pas exposer les codes complets hors écran agent  

---

## Priorités produit

1. Fiabilité de la validation  
2. Simplicité sur smartphone  
3. Rapidité du scan  
4. Design cérémonie + admin clair  
5. Déploiement gratuit / léger  

Bon événement.
