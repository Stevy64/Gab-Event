# WSGI PythonAnywhere — Web → WSGI configuration file
# Effacez le contenu proposé, collez ce fichier, Save, Reload.

import os
import sys
from pathlib import Path

candidates = [
    Path("/home/Steevy64/Gab-Event"),
    Path("/home/steevy64/Gab-Event"),
    Path.home() / "Gab-Event",
]
project_home = None
for path in candidates:
    if (path / "manage.py").is_file():
        project_home = path
        break

if project_home is None:
    raise RuntimeError(
        "Projet introuvable. Vérifiez : ls ~/Gab-Event/manage.py"
    )

if str(project_home) not in sys.path:
    sys.path.insert(0, str(project_home))
os.chdir(project_home)

try:
    from dotenv import load_dotenv

    load_dotenv(project_home / ".env")
except Exception:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DEBUG", "False")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
