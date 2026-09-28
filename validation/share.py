"""Liens de partage WhatsApp (organisateur + invité)."""
from __future__ import annotations

from urllib.parse import quote

from .models import Event, Invitation


def whatsapp_share_href(text: str) -> str:
    return f"https://wa.me/?text={quote(text or '')}"


def organizer_invite_message(event: Event, url: str) -> str:
    parts = [f"Vous êtes invité(e) à « {event.name} »"]
    if event.date:
        parts.append(f"le {event.date.strftime('%d/%m/%Y')}")
    if event.venue:
        parts.append(f"— {event.venue}")
    parts.append(f"Inscrivez-vous ici : {url}")
    return " ".join(parts)


def guest_invite_message(invitation: Invitation, url: str) -> str:
    event = invitation.event
    return (
        f"Voici mon invitation pour « {event.name} » — "
        f"{invitation.full_name}. Carte : {url}"
    )


def organizer_invite_href(event: Event, url: str) -> str:
    return whatsapp_share_href(organizer_invite_message(event, url))


def guest_invite_href(invitation: Invitation, url: str) -> str:
    return whatsapp_share_href(guest_invite_message(invitation, url))
