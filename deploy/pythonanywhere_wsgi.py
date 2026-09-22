# WSGI — PythonAnywhere (steevy64 / Gab-Event)
#
# Collez ce fichier ENTIER dans : Web → WSGI configuration file → Save → Reload

import os
import sys
from pathlib import Path

# --- Chemins possibles du projet --------------------------------------------
candidates = [
    Path("/home/steevy64/Gab-Event"),
    Path("/home/steevy64/ATC_Ceremony"),
    Path("/home/steevy64/gab-event"),
]
project_home = None
for path in candidates:
    if (path / "manage.py").exists() and (path / "config" / "settings.py").exists():
        project_home = path
        break

if project_home is None:
    raise RuntimeError(
        "Projet Django introuvable. Attendu : /home/steevy64/Gab-Event "
        "(avec manage.py). Adaptez 'candidates' dans ce fichier WSGI."
    )

project_home_str = str(project_home)
if project_home_str not in sys.path:
    sys.path.insert(0, project_home_str)
os.chdir(project_home_str)

# Forcer les hôtes PA AVANT le chargement de Django (évite DisallowedHost)
os.environ["ALLOWED_HOSTS"] = (
    "steevy64.pythonanywhere.com,.pythonanywhere.com,localhost,127.0.0.1"
)
os.environ.setdefault(
    "CSRF_TRUSTED_ORIGINS",
    "https://steevy64.pythonanywhere.com,https://*.pythonanywhere.com",
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
