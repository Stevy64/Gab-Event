"""
Suppression automatique selon la formule, et fermeture des liens d’invitation.

Durées par défaut (depuis la création) :
  Gratuit 14 j · Petit 21 j · Moyen 30 j · Grand 60 j
  Personnalisé : fin de la fenêtre définie à la création.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from django.utils import timezone

from .models import Event

_LAST_RUN = 0.0
_THROTTLE_SECONDS = 45


@dataclass
class ExpireResult:
    archived: int = 0
    deleted: int = 0
    links_closed: int = 0


def purge_event_files(event: Event) -> None:
    for field in ("flyer", "logo"):
        fh = getattr(event, field, None)
        if fh:
            fh.delete(save=False)


def delete_event(event: Event) -> None:
    purge_event_files(event)
    event.delete()


def close_expired_invite_links(*, now=None, today=None) -> int:
    now = now or timezone.now()
    today = today or timezone.localdate()
    closed = 0
    qs = Event.objects.filter(invite_link_enabled=True).exclude(is_legacy=True)
    for event in qs:
        ended = bool(event.expires_at and event.expires_at <= now)
        ended = ended or bool(event.invite_valid_until and event.invite_valid_until < today)
        if ended:
            event.invite_link_enabled = False
            event.save(update_fields=["invite_link_enabled", "updated_at"])
            closed += 1
    return closed


def expire_due_events(*, force: bool = False) -> ExpireResult:
    global _LAST_RUN
    now_mono = time.monotonic()
    if not force and now_mono - _LAST_RUN < _THROTTLE_SECONDS:
        return ExpireResult()
    _LAST_RUN = now_mono

    now = timezone.now()
    result = ExpireResult()
    result.links_closed = close_expired_invite_links(now=now)

    to_delete = list(
        Event.objects.filter(expires_at__isnull=False, expires_at__lte=now)
        .exclude(is_legacy=True)
        .select_related("plan")
    )
    for event in to_delete:
        delete_event(event)
        result.deleted += 1

    return result


def events_needing_delete_prompt(user):
    """Ancien popup J+7 : plus utilisé (suppression automatique par formule)."""
    from .access import user_events_qs

    return user_events_qs(user).none()


def dismiss_delete_prompt(event: Event) -> None:
    event.delete_prompt_dismissed_at = timezone.now()
    event.save(update_fields=["delete_prompt_dismissed_at", "updated_at"])


class EventLifecycleError(ValueError):
    """Transition de statut refusée."""


def available_actions(event: Event) -> dict:
    """Désactiver → Archiver → Supprimer, selon validité et événement en cours."""
    can_disable = event.status == Event.STATUS_ACTIVE and event.is_within_validity
    can_enable = event.is_disabled and event.is_within_validity
    can_archive = (
        not event.is_happening_now
        and event.status != Event.STATUS_ARCHIVED
        and (
            event.is_disabled
            or event.status == Event.STATUS_COMPLETED
            or (event.status == Event.STATUS_ACTIVE and not event.is_within_validity)
        )
    )
    can_delete = event.status in {
        Event.STATUS_ARCHIVED,
        Event.STATUS_DRAFT,
        Event.STATUS_PENDING_PAYMENT,
    }
    actions = []
    if can_disable:
        actions.append("disable")
    if can_enable:
        actions.append("enable")
    if can_archive:
        actions.append("archive")
    if can_delete:
        actions.append("delete")
    note = ""
    if event.is_happening_now:
        note = "Événement en cours : vous pouvez le désactiver, mais pas l’archiver ni le supprimer."
    elif event.status == Event.STATUS_ARCHIVED:
        note = "Archivage définitif : aucun retour en arrière n’est possible."
    return {
        "can_disable": can_disable,
        "can_enable": can_enable,
        "can_archive": can_archive,
        "can_delete": can_delete,
        "has_menu": bool(actions),
        "actions": actions,
        "note": note,
    }


def _close_invite_link(event: Event) -> None:
    if event.invite_link_enabled:
        event.invite_link_enabled = False


def apply_event_action(event: Event, action: str) -> str:
    action = (action or "").strip()
    flags = available_actions(event)
    now = timezone.now()

    if action == "disable":
        if not flags["can_disable"]:
            raise EventLifecycleError(
                "Cet événement ne peut pas être désactivé. "
                "La désactivation n’est possible que pendant la période de validité."
            )
        event.status = Event.STATUS_DISABLED
        _close_invite_link(event)
        event.save(update_fields=["status", "invite_link_enabled", "updated_at"])
        return f"« {event.name } » est désactivé. Vous pourrez le réactiver tant que sa validité n’est pas écoulée."

    if action == "enable":
        if not flags["can_enable"]:
            raise EventLifecycleError(
                "Impossible de réactiver cet événement. "
                "La période de validité est écoulée, ou l’événement est déjà archivé."
            )
        event.status = Event.STATUS_ACTIVE
        event.save(update_fields=["status", "updated_at"])
        return f"« {event.name } » est de nouveau actif."

    if action == "archive":
        if event.is_happening_now:
            raise EventLifecycleError(
                "Impossible d’archiver un événement en cours. Désactivez-le d’abord."
            )
        if not flags["can_archive"]:
            raise EventLifecycleError(
                "Désactivez d’abord l’événement. L’archivage est définitif et sans retour."
            )
        event.status = Event.STATUS_ARCHIVED
        event.archived_at = now
        _close_invite_link(event)
        event.save(update_fields=["status", "archived_at", "invite_link_enabled", "updated_at"])
        return f"« {event.name } » est archivé. Cette action est irréversible."

    if action == "delete":
        if event.is_happening_now:
            raise EventLifecycleError("Impossible de supprimer un événement en cours.")
        if not flags["can_delete"]:
            raise EventLifecycleError(
                "La suppression n’est possible qu’après archivage, "
                "ou pour un événement jamais activé (brouillon / paiement en attente)."
            )
        name = event.name
        delete_event(event)
        return f"« {name } » a été supprimé définitivement."

    raise EventLifecycleError("Action inconnue.")
