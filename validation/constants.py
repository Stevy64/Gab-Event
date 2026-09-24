"""
Configuration centralisée : préfixes, alphabet, types de participants.
Les textes d'événement viennent désormais du modèle Event.
"""
from django.conf import settings

from .branding import DEFAULT_PRIMARY_COLOR, default_cover_url, default_logo_url, year_code_prefix

# Préfixe fallback (désormais choisi par événement, ex. GAE26)
RECIPIENT_CODE_PREFIX = getattr(settings, "RECIPIENT_CODE_PREFIX", None) or year_code_prefix()
VIP_CODE_PREFIX = getattr(settings, "VIP_CODE_PREFIX", "VIP")

CODE_ALPHABET = getattr(
    settings,
    "CODE_ALPHABET",
    "ABCDEFGHJKLMNPQRSTUVWXYZ23456789",
)
CODE_SUFFIX_LENGTH = 6

PARTICIPANT_RECIPIENT = "RECIPIENT"
PARTICIPANT_VIP = "VIP"

DEFAULT_WELCOME = "Vous êtes cordialement invité(e)"
DEFAULT_INVITATION_FOOTER = "Veuillez présenter cette invitation à l'entrée."

# Fallback uniquement si aucun Event n'est fourni (affichage legacy)
DEFAULT_CEREMONY = {
    "title": "Votre événement",
    "subtitle": "Gab Event",
    "date": "Date à confirmer",
    "time": "Heure à confirmer",
    "venue": "Lieu à confirmer",
    "organizer": "Organisateur",
    "footer": DEFAULT_INVITATION_FOOTER,
    "description": "",
    "welcome": DEFAULT_WELCOME,
    "primary_color": DEFAULT_PRIMARY_COLOR,
    "flyer_url": "",
    "logo_url": "",
}


def ceremony_settings(event=None) -> dict:
    """Contexte d'affichage : Event prioritaire, sinon settings / défauts."""
    if event is not None:
        return event.ceremony_context()
    cfg = dict(DEFAULT_CEREMONY)
    cfg.update(getattr(settings, "CEREMONY", {}) or {})
    cfg.setdefault("primary_color", DEFAULT_PRIMARY_COLOR)
    cfg.setdefault("flyer_url", default_cover_url())
    cfg.setdefault("logo_url", default_logo_url())
    cfg.setdefault("welcome", DEFAULT_WELCOME)
    cfg.setdefault("footer", DEFAULT_INVITATION_FOOTER)
    cfg.setdefault("description", "")
    return cfg
