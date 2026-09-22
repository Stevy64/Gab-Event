"""
Configuration centralisée : préfixes de codes, alphabet, infos cérémonie.
"""
from django.conf import settings

# Business identity of the promotion — not the system year.
RECIPIENT_CODE_PREFIX = getattr(settings, "RECIPIENT_CODE_PREFIX", "ATC24")
VIP_CODE_PREFIX = getattr(settings, "VIP_CODE_PREFIX", "VIP")

CODE_ALPHABET = getattr(
    settings,
    "CODE_ALPHABET",
    "ABCDEFGHJKLMNPQRSTUVWXYZ23456789",
)
CODE_SUFFIX_LENGTH = 6

PARTICIPANT_RECIPIENT = "RECIPIENT"
PARTICIPANT_VIP = "VIP"

DEFAULT_CEREMONY = {
    "title": "Cérémonie de remise des diplômes",
    "subtitle": "Contrôleurs Aériens",
    "date": "Samedi 20 Décembre",
    "time": "18 h 00",
    "venue": "Grande salle de cérémonie",
    "organizer": "ATC",
    "footer": "Veuillez présenter cette invitation à l'entrée.",
}


def ceremony_settings() -> dict:
    cfg = dict(DEFAULT_CEREMONY)
    cfg.update(getattr(settings, "CEREMONY", {}) or {})
    return cfg
