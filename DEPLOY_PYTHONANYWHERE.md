# Déploiement sur PythonAnywhere via GitHub

Gab Event se livre depuis **GitHub**. GitHub Actions fait d’abord les tests. Si tout est vert, la production PythonAnywhere peut se mettre à jour toute seule.

---

## 1. Ce que fait le CI/CD

À chaque push ou pull request sur `main` :

1. Contrôles Django (`check`, migrations à jour)
2. Tests SQLite (non-régression + intégration)
3. Tests Postgres (même logique que OVH)
4. `collectstatic` pour vérifier les fichiers statiques

Si le push est sur `main` **et** que les secrets PythonAnywhere sont renseignés :

5. `git pull` + `migrate` + `collectstatic` sur le serveur (via SSH, plan Hacker)
6. Rechargement de l’appli Web (API PythonAnywhere)

Commandes équivalentes en local :

```bash
python manage.py check --settings=config.test_settings
python manage.py test --settings=config.test_settings
python manage.py collectstatic --noinput
```

---

## 2. Première installation sur PythonAnywhere

### 2.1 Cloner le dépôt

**Bash console** :

```bash
cd ~
git clone https://github.com/Stevy64/Gab-Event.git
cd Gab-Event
```

### 2.2 Virtualenv (même version Python que l’onglet Web)

```bash
cd /home/VOTRE_COMPTE/Gab-Event
python3.10 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

Dans l’onglet **Web** : Python **3.10**, Virtualenv = `/home/VOTRE_COMPTE/Gab-Event/.venv`.

### 2.3 Fichier `.env`

```bash
cd ~/Gab-Event
nano .env
```

```env
SECRET_KEY=collez-ici-une-cle-longue
DEBUG=False
ALLOWED_HOSTS=VOTRE_COMPTE.pythonanywhere.com,.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://VOTRE_COMPTE.pythonanywhere.com
PUBLIC_BASE_URL=https://VOTRE_COMPTE.pythonanywhere.com
ALLOW_MOCK_PAYMENTS=False
```

Générez la clé :

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 2.4 Base et fichiers statiques

```bash
source ~/Gab-Event/.venv/bin/activate
cd ~/Gab-Event
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

Onglet **Web** → **Static files** :

| URL | Directory |
|-----|-----------|
| `/static/` | `/home/VOTRE_COMPTE/Gab-Event/staticfiles` |
| `/media/` | `/home/VOTRE_COMPTE/Gab-Event/media` |

### 2.5 WSGI

Ouvrez le **WSGI configuration file**, remplacez tout par le contenu de [`deploy/pythonanywhere_wsgi.py`](deploy/pythonanywhere_wsgi.py), **Save**, **Reload**.

### 2.6 Vérifier

1. `https://VOTRE_COMPTE.pythonanywhere.com/`
2. `https://VOTRE_COMPTE.pythonanywhere.com/health/` → `{"status": "ok"}`
3. Connexion + un événement test
4. Scan sur téléphone (HTTPS obligatoire pour la caméra)

---

## 3. Brancher GitHub Actions

Dans le dépôt GitHub : **Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Exemple | Obligatoire |
|--------|---------|-------------|
| `PYTHONANYWHERE_USERNAME` | `Steevy64` | oui pour déployer |
| `PYTHONANYWHERE_API_TOKEN` | token de Account → API token | recommandé |
| `PYTHONANYWHERE_DOMAIN` | `Steevy64.pythonanywhere.com` | si différent du défaut |
| `PYTHONANYWHERE_SSH_KEY` | clé privée SSH (plan Hacker) | pour le `git pull` auto |

### Token API

1. PythonAnywhere → **Account** → **API token** → Create
2. Collez-le dans `PYTHONANYWHERE_API_TOKEN`

### Clé SSH (plan payant)

Sur votre PC :

```bash
ssh-keygen -t ed25519 -C "gab-event-deploy" -f gabevent-pa -N ""
```

- La **clé privée** (`gabevent-pa`) → secret `PYTHONANYWHERE_SSH_KEY`
- La **clé publique** (`gabevent-pa.pub`) → PythonAnywhere **SSH keys** (ou `~/.ssh/authorized_keys`)

Sans SSH (compte gratuit) : le CI teste quand même. Pour livrer, ajoutez une **tâche planifiée** (Tasks) :

```bash
/home/VOTRE_COMPTE/Gab-Event/.venv/bin/bash /home/VOTRE_COMPTE/Gab-Event/deploy/pythonanywhere.sh
```

Fréquence : toutes les heures, ou après chaque merge en lançant à la main :

```bash
cd ~/Gab-Event && bash deploy/pythonanywhere.sh
```

Le script fait : `git pull`, `pip install`, `migrate`, `collectstatic`, reload API.

---

## 4. Livraison quotidienne

1. Poussez sur `main` (ou mergez la PR).
2. Onglet **Actions** : le workflow **CI** doit être vert.
3. Si les secrets SSH sont là, PythonAnywhere est à jour tout seul.
4. Sinon, lancez `bash deploy/pythonanywhere.sh` dans la console PA.

Ne jamais committer `.env`.

---

## 5. Limites compte gratuit

- Une seule web app
- Pas de SSH depuis GitHub : utilisez le script + Tasks
- SQLite suffit pour un trafic léger ; sauvegardez `db.sqlite3` régulièrement
- Processus endormi après inactivité (premier hit plus lent)

---

## 6. Checklist jour J

- [ ] `DEBUG=False`
- [ ] Mot de passe admin fort
- [ ] Static files pointent vers `staticfiles`
- [ ] `/health/` répond ok
- [ ] Un QR testé sur un vrai téléphone en HTTPS
- [ ] Backup de `db.sqlite3` téléchargé
