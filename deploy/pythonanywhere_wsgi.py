# WSGI — modèle pour PythonAnywhere (compte steevy64 / dépôt Gab-Event)
#
# Copiez ce fichier dans l’éditeur « WSGI configuration file » de l’onglet Web,
# ou adaptez le fichier généré par PythonAnywhere.
#
# Si votre chemin local diffère, changez project_home.

import os
import sys

# --- Chemins projet ---------------------------------------------------------
# Cloné depuis https://github.com/Stevy64/Gab-Event.git → souvent ~/Gab-Event
project_home = "/home/steevy64/Gab-Event"
# Variante si vous avez cloné sous un autre nom :
# project_home = "/home/steevy64/ATC_Ceremony"

if project_home not in sys.path:
    sys.path.insert(0, project_home)

# S’assurer que le cwd pointe sur le projet (utile pour chemins relatifs)
os.chdir(project_home)

# --- Variables d'environnement ---------------------------------------------
# Préférez un fichier .env dans project_home (chargé par config/settings.py).
# Décommentez seulement si vous n’utilisez pas de .env :
#
# os.environ["SECRET_KEY"] = "remplacez-par-une-cle-longue"
# os.environ["DEBUG"] = "False"
# os.environ["ALLOWED_HOSTS"] = "steevy64.pythonanywhere.com,.pythonanywhere.com"
# os.environ["CSRF_TRUSTED_ORIGINS"] = "https://steevy64.pythonanywhere.com"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
