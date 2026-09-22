# WSGI — collez CE FICHIER ENTIER dans PythonAnywhere
# Web → WSGI configuration file → effacez tout → collez → Save → Reload

import os
import sys
from pathlib import Path

# Compte PA : dossier home = /home/Steevy64 (casse réelle du système de fichiers)
candidates = [
    Path("/home/Steevy64/Gab-Event"),
    Path("/home/steevy64/Gab-Event"),
    Path("/home/Steevy64/ATC_Ceremony"),
    Path("/home/steevy64/ATC_Ceremony"),
]
project_home = None
for path in candidates:
    if (path / "manage.py").is_file():
        project_home = path
        break

if project_home is None:
    raise RuntimeError(
        "Projet introuvable. Vérifiez : ls /home/Steevy64/Gab-Event/manage.py"
    )

home = str(project_home)
if home not in sys.path:
    sys.path.insert(0, home)
os.chdir(home)

# --- Variables AVANT le chargement de Django ---
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
os.environ["DEBUG"] = "False"
os.environ["DJANGO_DEBUG"] = "0"
# Collez votre SECRET_KEY Django ici (ne pas committer la vraie clé sur GitHub)
os.environ["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    os.environ.get("DJANGO_SECRET_KEY", "change-me-on-pythonanywhere"),
)
os.environ["DJANGO_SECRET_KEY"] = os.environ["SECRET_KEY"]
os.environ["ALLOWED_HOSTS"] = (
    "steevy64.pythonanywhere.com,.pythonanywhere.com,localhost,127.0.0.1"
)
os.environ["CSRF_TRUSTED_ORIGINS"] = (
    "https://steevy64.pythonanywhere.com,https://*.pythonanywhere.com"
)

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
