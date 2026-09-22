# Déploiement sur PythonAnywhere

Guide pour livrer **ATC Graduation Check** en production (compte gratuit ou payant).

---

## 1. Prérequis

- Compte [PythonAnywhere](https://www.pythonanywhere.com)
- Dépôt GitHub à jour (`main`)
- Une `SECRET_KEY` Django longue et aléatoire (ne pas réutiliser celle du `.env` local)

Générer une clé rapidement :

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## 2. Cloner le projet

**Bash console** PythonAnywhere :

```bash
cd ~
git clone https://github.com/Stevy64/Gab-Event.git
cd Gab-Event
```

Mises à jour ultérieures :

```bash
cd ~/Gab-Event
git pull origin main
```

---

## 3. Virtualenv

```bash
# Adapter la version Python proposée dans l’onglet Web / Account
mkvirtualenv --python=/usr/bin/python3.10 atc-ceremony
workon atc-ceremony
cd ~/Gab-Event
pip install -r requirements.txt
```

Si `mkvirtualenv` n’existe pas :

```bash
python3.10 -m venv ~/.virtualenvs/atc-ceremony
source ~/.virtualenvs/atc-ceremony/bin/activate
pip install -r requirements.txt
```

---

## 4. Fichier `.env` (recommandé)

```bash
cd ~/Gab-Event
nano .env
```

Exemple :

```env
SECRET_KEY=collez-ici-la-cle-generee
DEBUG=False
ALLOWED_HOSTS=steevy64.pythonanywhere.com,.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://steevy64.pythonanywhere.com
CEREMONY_TITLE=Cérémonie de remise des diplômes
CEREMONY_SUBTITLE=Contrôleurs Aériens
CEREMONY_DATE=Samedi 20 Décembre
CEREMONY_TIME=18 h 00
CEREMONY_VENUE=Grande salle de cérémonie
CEREMONY_ORGANIZER=ATC
```

`python-dotenv` charge **`/home/steevy64/Gab-Event/.env`** au démarrage (chemin absolu du projet, pas le cwd WSGI).

Sans `.env`, Django autorise quand même `*.pythonanywhere.com`, mais **créez quand même un `.env`** pour `SECRET_KEY` et `DEBUG=False`.

---

## 5. Migrations & superutilisateur

```bash
workon atc-ceremony
cd ~/Gab-Event
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

Import éventuel :

```bash
python manage.py import_invitations data/invitations.xlsx
python manage.py generate_invitations
```

---

## 6. Application Web

Onglet **Web** → **Add a new web app** → **Manual configuration** → Python 3.10 (ou version du venv).

### Virtualenv

Chemin typique :

```text
/home/steevy64/.virtualenvs/atc-ceremony
```

### Source code

```text
/home/steevy64/Gab-Event
```

### Fichiers statiques

| URL | Directory |
|-----|-----------|
| `/static/` | `/home/steevy64/Gab-Event/staticfiles` |

Puis `python manage.py collectstatic --noinput` après chaque changement CSS/JS.

### WSGI

Ouvrez le **WSGI configuration file** et remplacez-le par le contenu de  
[`deploy/pythonanywhere_wsgi.py`](deploy/pythonanywhere_wsgi.py)  
(en adaptant `steevy64` et, si besoin, les `os.environ[...]`).

Cliquez **Reload** sur l’onglet Web.

---

## 7. Vérifications

1. `https://steevy64.pythonanywhere.com/` → flyer d’accueil  
2. Connexion admin → dashboard  
3. Sur **smartphone en HTTPS** : Scanner → autoriser la caméra  
4. Sans caméra : saisie manuelle d’un code `ATC24-…` ou `VIP-…`

> Sans HTTPS, la plupart des navigateurs bloquent `getUserMedia` (caméra).

---

## 8. Mise à jour en prod

```bash
cd ~/Gab-Event
git pull origin main
workon atc-ceremony
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Puis **Reload** l’appli Web.

---

## 9. Limites compte gratuit

- Une seule web app  
- Processus web endormi après inactivité (réveil au premier hit)  
- SQLite convient pour un **événement ponctuel** ; pour un fort trafic concurrent, envisager MySQL (PA) ou un plan payant  

Sauvegarder régulièrement `db.sqlite3` (onglet Files → téléchargement).

---

## 10. Checklist livraison jour J

- [ ] `DEBUG=False`
- [ ] Mot de passe admin fort
- [ ] Invitations importées + ZIP généré
- [ ] Quelques QR de test scannés sur un vrai téléphone
- [ ] Backup SQLite téléchargé
- [ ] Adresse HTTPS communiquée aux agents d’accueil

Bon événement.
