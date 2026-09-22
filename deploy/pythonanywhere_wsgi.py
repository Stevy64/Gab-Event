# WSGI — modèle pour PythonAnywhere
#
# Copiez ce fichier dans l’éditeur « WSGI configuration file » de l’onglet Web,
# ou adaptez le fichier généré par PythonAnywhere.
#
# Remplacez VOTRE_USER par votre identifiant PA.

import os
import sys

# --- Chemins projet ---------------------------------------------------------
project_home = "/home/VOTRE_USER/ATC_Ceremony"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# --- Variables d'environnement (si vous n'utilisez pas de fichier .env) -----
# Décommentez et renseignez, OU créez ~/ATC_Ceremony/.env (recommandé).
#
# os.environ["SECRET_KEY"] = "remplacez-par-une-cle-longue"
# os.environ["DEBUG"] = "False"
# os.environ["ALLOWED_HOSTS"] = "VOTRE_USER.pythonanywhere.com"
# os.environ["CSRF_TRUSTED_ORIGINS"] = "https://VOTRE_USER.pythonanywhere.com"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
