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

from .models import Event, EventController, Invitation

CONTROLLER_SESSION_EVENT = "controller_event_id"
CONTROLLER_SESSION_TOKEN = "controller_token"


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


def controller_from_session(request) -> EventController | None:
    eid = request.session.get(CONTROLLER_SESSION_EVENT)
    token = (request.session.get(CONTROLLER_SESSION_TOKEN) or "").strip()
    if not eid or not token:
        return None
    return (
        EventController.objects.filter(token=token, event_id=eid, is_active=True)
        .select_related("event")
        .first()
    )


def controller_event_from_session(request) -> Event | None:
    ctrl = controller_from_session(request)
    if not ctrl:
        return None
    event = ctrl.event
    if event.needs_payment or event.status != Event.STATUS_ACTIVE:
        return None
    return event


def grant_controller_session(request, controller: EventController) -> None:
    request.session[CONTROLLER_SESSION_EVENT] = controller.event_id
    request.session[CONTROLLER_SESSION_TOKEN] = controller.token
    request.session["current_event_id"] = controller.event_id


def can_scan_event(request, event: Event | None) -> bool:
    if event is None:
        return False
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        if user.is_superuser or event.owner_id == user.id:
            return True
    session_event = controller_event_from_session(request)
    return bool(session_event and session_event.pk == event.pk)


def get_scan_event(request, event_id=None) -> Event | None:
    """Événement scannable : organisateur connecté ou contrôleur en session."""
    session_ctrl = controller_event_from_session(request)
    if event_id not in (None, ""):
        try:
            eid = int(event_id)
        except (TypeError, ValueError):
            eid = None
        if eid:
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated:
                qs = user_events_qs(user).filter(pk=eid)
                event = qs.first()
                if event:
                    return event
            if session_ctrl and session_ctrl.pk == eid:
                return session_ctrl
            return None
    if session_ctrl:
        return session_ctrl
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        eid = request.session.get("current_event_id")
        if eid:
            event = user_events_qs(user).filter(pk=eid).first()
            if event:
                return event
        return (
            user_events_qs(user)
            .filter(status=Event.STATUS_ACTIVE)
            .order_by("-created_at")
            .first()
        )
    return None
