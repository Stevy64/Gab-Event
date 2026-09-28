"""Compteurs publics cumulatifs — ils ne redescendent jamais."""
from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import F


def _site():
    from .models import SiteSettings

    return SiteSettings.load()


def bump_lifetime(*, events: int = 0, invitations: int = 0, organizers: int = 0) -> None:
    updates = {}
    if events:
        updates["lifetime_events"] = F("lifetime_events") + int(events)
    if invitations:
        updates["lifetime_invitations"] = F("lifetime_invitations") + int(invitations)
    if organizers:
        updates["lifetime_organizers"] = F("lifetime_organizers") + int(organizers)
    if not updates:
        return
    site = _site()
    type(site).objects.filter(pk=site.pk).update(**updates)


def record_event_created(event) -> None:
    from .models import Event

    first_for_owner = Event.objects.filter(owner_id=event.owner_id).count() == 1
    bump_lifetime(events=1, organizers=1 if first_for_owner else 0)


def record_invitation_created() -> None:
    bump_lifetime(invitations=1)


def hero_lifetime_stats() -> dict[str, int]:
    """Plafond jamais inférieur au vivant ; rattrape les créations manquées."""
    from .models import Event, Invitation, SiteSettings

    site = SiteSettings.load()
    live_events = Event.objects.count()
    live_invitations = Invitation.objects.count()
    live_organizers = (
        User.objects.filter(is_active=True, events__isnull=False).distinct().count()
    )
    events = max(int(site.lifetime_events or 0), live_events)
    invitations = max(int(site.lifetime_invitations or 0), live_invitations)
    organizers = max(int(site.lifetime_organizers or 0), live_organizers)
    dirty = (
        events > int(site.lifetime_events or 0)
        or invitations > int(site.lifetime_invitations or 0)
        or organizers > int(site.lifetime_organizers or 0)
    )
    if dirty:
        SiteSettings.objects.filter(pk=site.pk).update(
            lifetime_events=events,
            lifetime_invitations=invitations,
            lifetime_organizers=organizers,
        )
    return {
        "events": events,
        "invitations": invitations,
        "organizers": organizers,
    }
