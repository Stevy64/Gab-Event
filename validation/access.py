"""
Accès et isolation multi-tenant.

Règle : ne jamais charger un objet métier uniquement par pk
sans vérifier le propriétaire / permissions événement.
"""
from __future__ import annotations

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect

from .models import Event, Invitation


def user_events_qs(user):
    if not user.is_authenticated:
        return Event.objects.none()
    if user.is_superuser:
        return Event.objects.all()
    return Event.objects.filter(owner=user)


def get_user_event(user, event_id: int) -> Event:
    qs = user_events_qs(user)
    return get_object_or_404(qs, pk=event_id)


def event_workspace_required(view):
    """Bloque l'espace événement tant qu'un paiement payant n'est pas réglé."""

    @wraps(view)
    def wrapped(request, event_id, *args, **kwargs):
        event = get_user_event(request.user, event_id)
        if event.needs_payment:
            return redirect("event_payment", event_id=event.pk)
        return view(request, event_id, *args, **kwargs)

    return wrapped


def require_event_owner(user, event: Event) -> Event:
    if user.is_superuser:
        return event
    if not user.is_authenticated or event.owner_id != user.id:
        raise PermissionDenied("Accès refusé à cet événement.")
    return event


def event_invitations_qs(event: Event):
    return Invitation.objects.filter(event=event)


def get_event_invitation(user, event_id: int, invitation_id: int) -> Invitation:
    event = get_user_event(user, event_id)
    return get_object_or_404(Invitation, pk=invitation_id, event=event)


def get_owned_invitation(user, invitation_id: int) -> Invitation:
    """Invitation appartenant à un événement du user (ou staff)."""
    qs = Invitation.objects.select_related("event", "event__owner")
    invitation = get_object_or_404(qs, pk=invitation_id)
    if invitation.event_id is None:
        # Orpheline legacy : accessible aux utilisateurs authentifiés
        if not user.is_authenticated:
            raise Http404()
        return invitation
    require_event_owner(user, invitation.event)
    return invitation


def is_platform_admin(user) -> bool:
    return bool(
        user.is_authenticated and (user.is_superuser or user.is_staff)
    )


def require_platform_admin(user):
    if not is_platform_admin(user):
        raise PermissionDenied("Réservé aux administrateurs de la plateforme.")
    return user
