"""
WSGI entrypoint (Django local / serveurs génériques).

Sur PythonAnywhere, préférez le modèle documenté dans
`deploy/pythonanywhere_wsgi.py` (chemins + variables d'env).
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
