"""
Django settings — Gab Event (plateforme multi-événements).

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
    "0.0.0.0",
    "web",
    "nginx",
    "gabevent-web",
    "gabevent-nginx",
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
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:8000",
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
    "django.forms",
    "validation.apps.ValidationConfig",
]

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

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

WHITENOISE_MAX_AGE = 60 * 60 * 24 * 7

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
                "validation.context_processors.user_profile",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Postgres dans Docker ; SQLite en local / PythonAnywhere
if _env("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _env("POSTGRES_DB", default="gabevent"),
            "USER": _env("POSTGRES_USER", default="gabevent"),
            "PASSWORD": _env("POSTGRES_PASSWORD", default=""),
            "HOST": _env("POSTGRES_HOST"),
            "PORT": _env("POSTGRES_PORT", default="5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 6},
    },
]

# --- E-mail (récupération de compte) ----------------------------------------
_email_host = _env("EMAIL_HOST", default="")
_email_backend = _env("EMAIL_BACKEND", default="")
if _email_backend:
    EMAIL_BACKEND = _email_backend
elif _email_host:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
EMAIL_HOST = _email_host
EMAIL_PORT = int(_env("EMAIL_PORT", default="587") or "587")
EMAIL_HOST_USER = _env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = _env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = _env("EMAIL_USE_TLS", default="True").lower() in ("1", "true", "yes")
EMAIL_USE_SSL = _env("EMAIL_USE_SSL", default="").lower() in ("1", "true", "yes")
DEFAULT_FROM_EMAIL = _env(
    "DEFAULT_FROM_EMAIL",
    default="Gab Event <noreply@gabevent.local>",
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

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
LOGIN_REDIRECT_URL = "my_events"
LOGOUT_REDIRECT_URL = "landing"

AUTHENTICATION_BACKENDS = [
    "validation.auth_backends.EmailPhoneUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# --- Médias (flyers, avatars) ------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Paiement ----------------------------------------------------------------
# mock uniquement en DEBUG ; SingPay si les identifiants sont présents
SINGPAY_API_KEY = _env("SINGPAY_API_KEY", "SINGPAY_CLIENT_ID", default="")
SINGPAY_API_SECRET = _env("SINGPAY_API_SECRET", "SINGPAY_CLIENT_SECRET", default="")
SINGPAY_MERCHANT_ID = _env("SINGPAY_MERCHANT_ID", "SINGPAY_WALLET", default="")
SINGPAY_DISBURSEMENT_ID = _env("SINGPAY_DISBURSEMENT_ID", default="")
SINGPAY_ENVIRONMENT = _env("SINGPAY_ENVIRONMENT", default="sandbox")
PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL", default="http://127.0.0.1:8000")
_explicit_provider = os.environ.get("PAYMENT_PROVIDER", "").strip().lower()
if _explicit_provider:
    PAYMENT_PROVIDER = _explicit_provider
elif SINGPAY_API_KEY and SINGPAY_API_SECRET and SINGPAY_MERCHANT_ID:
    PAYMENT_PROVIDER = "singpay"
else:
    PAYMENT_PROVIDER = "mock"
ALLOW_MOCK_PAYMENTS = _env("ALLOW_MOCK_PAYMENTS", default="True").lower() in (
    "1",
    "true",
    "yes",
)

# --- Identité legacy / codes invitation -------------------------------------
from datetime import date as _date

RECIPIENT_CODE_PREFIX = os.environ.get(
    "RECIPIENT_CODE_PREFIX",
    f"GAE{_date.today().strftime('%y')}",
)
VIP_CODE_PREFIX = os.environ.get("VIP_CODE_PREFIX", "VIP")
# Alphabet sans caractères ambigus (I, O, 0, 1)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# Fallback affichage si aucun Event (landing / legacy)
CEREMONY = {
    "title": os.environ.get("CEREMONY_TITLE", "Gab Event"),
    "subtitle": os.environ.get("CEREMONY_SUBTITLE", "Invitations événementielles"),
    "date": os.environ.get("CEREMONY_DATE", ""),
    "time": os.environ.get("CEREMONY_TIME", ""),
    "venue": os.environ.get("CEREMONY_VENUE", ""),
    "organizer": os.environ.get("CEREMONY_ORGANIZER", "Gab Event"),
    "footer": "Veuillez présenter cette invitation à l'entrée.",
}

# --- Celery / Redis ----------------------------------------------------------
CELERY_BROKER_URL = _env(
    "CELERY_BROKER_URL",
    "REDIS_URL",
    default="redis://127.0.0.1:6379/0",
)
CELERY_RESULT_BACKEND = _env("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "expire-events-hourly": {
        "task": "validation.tasks.expire_events_task",
        "schedule": 3600.0,
    },
}

# --- Durcissement production ------------------------------------------------
if _env("BEHIND_PROXY", default="").lower() in ("1", "true", "yes"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    _public = _env("PUBLIC_BASE_URL", default="")
    _force_ssl = _env("SECURE_SSL", default="").lower() in ("1", "true", "yes")
    if _force_ssl or _public.startswith("https://"):
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
        SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
        SECURE_HSTS_INCLUDE_SUBDOMAINS = False
        if not _env("BEHIND_PROXY"):
            SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
