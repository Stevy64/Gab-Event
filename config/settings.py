"""
Django settings — ATC Graduation Check.

Configuration via variables d'environnement (fichier `.env` en local / prod).
Voir `.env.example` et `DEPLOY_PYTHONANYWHERE.md`.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Charger depuis le dossier projet (sur PythonAnywhere, le cwd WSGI ≠ projet)
load_dotenv(BASE_DIR / ".env")

# --- Sécurité ---------------------------------------------------------------
def _env(*names: str, default: str = "") -> str:
    """Lit la première variable non vide (aliases Django / DJANGO_* / PA)."""
    for name in names:
        value = os.environ.get(name)
        if value is not None and str(value).strip() != "":
            return str(value)
    return default


SECRET_KEY = _env(
    "SECRET_KEY",
    "DJANGO_SECRET_KEY",
    default="django-insecure-dev-only-change-in-production",
)

DEBUG = _env("DEBUG", "DJANGO_DEBUG", default="True").lower() in (
    "1",
    "true",
    "yes",
)

ALLOWED_HOSTS = [
    h.strip()
    for h in _env(
        "ALLOWED_HOSTS",
        "DJANGO_ALLOWED_HOSTS",
        default="localhost,127.0.0.1,steevy64.pythonanywhere.com,.pythonanywhere.com",
    ).split(",")
    if h.strip()
]
# Toujours autoriser ce compte PA + wildcard (évite DisallowedHost même si .env est incomplet)
for _host in (
    "steevy64.pythonanywhere.com",
    ".pythonanywhere.com",
    "localhost",
    "127.0.0.1",
):
    if _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)

# Origines HTTPS de confiance pour CSRF (obligatoire derrière PythonAnywhere)
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in _env(
        "CSRF_TRUSTED_ORIGINS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        default="https://steevy64.pythonanywhere.com",
    ).split(",")
    if o.strip()
]
for _origin in (
    "https://steevy64.pythonanywhere.com",
    "https://*.pythonanywhere.com",
):
    if _origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_origin)

# --- Applications -----------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "validation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# WhiteNoise optionnel : si le paquet n'est pas installé dans le venv PA, ne pas planter (500)
try:
    import whitenoise  # noqa: F401

    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    _STATICFILES_BACKEND = "whitenoise.storage.CompressedStaticFilesStorage"
except ImportError:
    _STATICFILES_BACKEND = "django.contrib.staticfiles.storage.StaticFilesStorage"

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite : suffisant pour un événement ponctuel (sauvegarder db.sqlite3 régulièrement)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Niamey"
USE_I18N = True
USE_TZ = True

# --- Fichiers statiques -----------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# collectstatic → ce dossier ; pointer /static/ dessus dans PythonAnywhere
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": _STATICFILES_BACKEND,
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

# --- Identité cérémonie / codes invitation ----------------------------------
RECIPIENT_CODE_PREFIX = os.environ.get("RECIPIENT_CODE_PREFIX", "ATC24")
VIP_CODE_PREFIX = os.environ.get("VIP_CODE_PREFIX", "VIP")
# Alphabet sans caractères ambigus (I, O, 0, 1)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

CEREMONY = {
    "title": os.environ.get("CEREMONY_TITLE", "Cérémonie de remise des diplômes"),
    "subtitle": os.environ.get("CEREMONY_SUBTITLE", "Contrôleurs Aériens"),
    "date": os.environ.get("CEREMONY_DATE", "Samedi 20 Décembre"),
    "time": os.environ.get("CEREMONY_TIME", "18 h 00"),
    "venue": os.environ.get("CEREMONY_VENUE", "Grande salle de cérémonie"),
    "organizer": os.environ.get("CEREMONY_ORGANIZER", "ATC"),
    "footer": "Veuillez présenter cette invitation à l'entrée.",
}

# --- Durcissement production ------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    # HSTS léger (PythonAnywhere termine déjà le TLS)
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
