"""
Vérification des quotas d'invitations selon le plan / snapshot de l'événement.
"""
from __future__ import annotations

from dataclasses import dataclass

from .constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP
from .models import Event, Invitation


@dataclass
class QuotaStatus:
    allowed: bool
    message: str = ""
    regular_count: int = 0
    vip_count: int = 0
    regular_limit: int = 0
    vip_limit: int = 0
    total_count: int = 0
    total_limit: int | None = None
    remaining_regular: int = 0
    remaining_vip: int = 0
    remaining_total: int | None = None


def invitation_counts(event: Event) -> tuple[int, int]:
    qs = Invitation.objects.filter(event=event)
    regular = qs.filter(participant_type=PARTICIPANT_RECIPIENT).count()
    vip = qs.filter(participant_type=PARTICIPANT_VIP).count()
    return regular, vip


def quota_status(event: Event) -> QuotaStatus:
    regular, vip = invitation_counts(event)
    regular_limit = event.regular_limit
    vip_limit = event.vip_limit
    total_limit = event.total_limit
    total = regular + vip
    remaining_regular = max(0, regular_limit - regular)
    remaining_vip = max(0, vip_limit - vip)
    remaining_total = None if total_limit is None else max(0, total_limit - total)
    return QuotaStatus(
        allowed=True,
        regular_count=regular,
        vip_count=vip,
        regular_limit=regular_limit,
        vip_limit=vip_limit,
        total_count=total,
        total_limit=total_limit,
        remaining_regular=remaining_regular,
        remaining_vip=remaining_vip,
        remaining_total=remaining_total,
    )


def can_add_invitations(
    event: Event,
    *,
    regular_to_add: int = 0,
    vip_to_add: int = 0,
) -> QuotaStatus:
    status = quota_status(event)
    regular_to_add = max(0, int(regular_to_add))
    vip_to_add = max(0, int(vip_to_add))
    total_to_add = regular_to_add + vip_to_add

    if event.plan_id and event.plan.is_custom:
        return status

    if status.total_limit is not None:
        if status.total_count + total_to_add > status.total_limit:
            status.allowed = False
            status.message = (
                f"Limite atteinte. Votre formule permet jusqu'à "
                f"{status.total_limit} invitations au total."
            )
            return status
        # Avec limite totale (ex. gratuit), ne pas appliquer les plafonds séparés
        # si vip_limit/regular_limit sont 0 — sinon vérifier les deux.
        if status.regular_limit and status.regular_count + regular_to_add > status.regular_limit:
            status.allowed = False
            status.message = (
                f"Limite atteinte. Votre formule permet jusqu'à "
                f"{status.regular_limit} invitations standard."
            )
            return status
        if status.vip_limit and status.vip_count + vip_to_add > status.vip_limit:
            status.allowed = False
            status.message = (
                f"Limite atteinte. Votre formule permet jusqu'à "
                f"{status.vip_limit} invitations VIP."
            )
            return status
        return status

    if status.regular_count + regular_to_add > status.regular_limit:
        status.allowed = False
        status.message = (
            f"Limite atteinte. Votre formule permet jusqu'à "
            f"{status.regular_limit} invitations standard."
        )
        return status
    if status.vip_count + vip_to_add > status.vip_limit:
        status.allowed = False
        status.message = (
            f"Limite atteinte. Votre formule permet jusqu'à "
            f"{status.vip_limit} invitations VIP."
        )
        return status
    return status


def assert_can_create_invitation(event: Event, participant_type: str) -> QuotaStatus:
    if participant_type == PARTICIPANT_VIP:
        return can_add_invitations(event, vip_to_add=1)
    return can_add_invitations(event, regular_to_add=1)


def guest_registration_open(event: Event) -> QuotaStatus:
    """Le formulaire public reste ouvert tant qu’au moins une place existe."""
    regular = can_add_invitations(event, regular_to_add=1)
    if regular.allowed:
        return regular
    vip = can_add_invitations(event, vip_to_add=1)
    if vip.allowed:
        return vip
    status = quota_status(event)
    status.allowed = False
    status.message = (
        "Le nombre d’invités prévu pour cet événement est atteint. "
        "Les inscriptions sont fermées."
    )
    return status
