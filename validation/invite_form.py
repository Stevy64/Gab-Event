"""Formulaire public d’inscription — champs standard + verrouillage après mise en ligne."""
from __future__ import annotations

import re
import secrets
from decimal import Decimal

from .code_service import create_invitation_with_unique_code
from .constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP
from .models import Event, Invitation, SiteSettings, TicketTier
from .quota_service import assert_can_create_invitation

CORE_FIELD_KEYS = ("first_name", "last_name", "participant_type")

OPTIONAL_FIELDS = (
    ("email", "E-mail"),
    ("phone", "Téléphone"),
    ("category", "Catégorie / table"),
    ("organization", "Organisation"),
    ("dietary", "Régime / note"),
)

FIELD_LABELS = {
    "first_name": "Prénom",
    "last_name": "Nom",
    "participant_type": "Type d’invitation",
    **dict(OPTIONAL_FIELDS),
}

DEFAULT_ENABLED = [
    "first_name",
    "last_name",
    "participant_type",
    "email",
    "phone",
]


def default_fields() -> list[str]:
    return list(DEFAULT_ENABLED)


def catalog() -> list[dict]:
    items = []
    for key in CORE_FIELD_KEYS:
        items.append({"key": key, "label": FIELD_LABELS[key], "core": True})
    for key, label in OPTIONAL_FIELDS:
        items.append({"key": key, "label": label, "core": False})
    return items


def normalize_fields(keys) -> list[str]:
    seen = set()
    out = []
    for key in CORE_FIELD_KEYS:
        out.append(key)
        seen.add(key)
    allowed = {item[0] for item in OPTIONAL_FIELDS}
    for raw in keys or []:
        key = str(raw).strip()
        if key in allowed and key not in seen:
            out.append(key)
            seen.add(key)
    return out


def event_fields(event: Event) -> list[str]:
    stored = event.invite_form_fields or []
    fields = default_fields() if not stored else normalize_fields(stored)
    if getattr(event, "is_ticketing", False) and "phone" not in fields:
        fields.append("phone")
    return fields


def merge_locked_fields(existing, incoming) -> list[str]:
    """Après publication : on peut ajouter des champs, jamais en retirer."""
    current = normalize_fields(existing)
    posted = normalize_fields(incoming)
    extra = [key for key in posted if key not in current]
    return current + extra


def field_specs(event: Event) -> list[dict]:
    enabled = set(event_fields(event))
    specs = []
    for item in catalog():
        specs.append({**item, "enabled": item["key"] in enabled or item["core"]})
    return specs


def ensure_invite_token(event: Event) -> str:
    if event.invite_token:
        return event.invite_token
    event.invite_token = secrets.token_urlsafe(12).replace("_", "x").replace("-", "x")[:22]
    event.save(update_fields=["invite_token"])
    return event.invite_token


def fee_schedule(site: SiteSettings | None = None) -> tuple[Decimal, Decimal]:
    """Taux unique (7 %) par billet. Pas de frais fixe ; transfert à l’organisateur."""
    site = site or SiteSettings.load()
    pct = Decimal(getattr(site, "commission_pct", None) or site.commission_regular_pct or 7)
    return pct, Decimal("0")


def commission_rate(participant_type: str | None = None) -> Decimal:
    pct, _fixed = fee_schedule()
    return pct


def commission_fixed_fee() -> Decimal:
    _pct, fixed = fee_schedule()
    return fixed


def guest_price_for(event: Event, participant_type: str, tier: TicketTier | None = None) -> Decimal:
    if tier is not None:
        return Decimal(tier.price or 0)
    if participant_type == PARTICIPANT_VIP:
        value = event.guest_price_vip
        if value is None and event.plan_id:
            value = event.plan.price_per_vip
    else:
        value = event.guest_price_regular
        if value is None and event.plan_id:
            value = event.plan.price_per_regular
    return Decimal(value or 0)


def payload_from_post(event: Event, post) -> dict:
    enabled = set(event_fields(event))
    first = (post.get("first_name") or "").strip()
    last = (post.get("last_name") or "").strip()
    ptype = post.get("participant_type") or PARTICIPANT_RECIPIENT
    if ptype not in {PARTICIPANT_RECIPIENT, PARTICIPANT_VIP}:
        ptype = PARTICIPANT_RECIPIENT
    extra = {}
    for key, _label in OPTIONAL_FIELDS:
        if key in ("email", "phone"):
            continue
        if key in enabled:
            extra[key] = (post.get(key) or "").strip()
    tier = None
    if getattr(event, "is_ticketing", False):
        raw_tier = post.get("ticket_tier") or post.get("ticket_tier_id")
        if raw_tier:
            try:
                tier = event.ticket_tiers.filter(pk=int(raw_tier), is_active=True).first()
            except (TypeError, ValueError):
                tier = None
        if tier:
            extra["ticket_tier"] = tier.name
            extra["ticket_tier_id"] = tier.pk
            ptype = PARTICIPANT_VIP if "vip" in (tier.name or "").casefold() else PARTICIPANT_RECIPIENT
    return {
        "first_name": first,
        "last_name": last,
        "participant_type": ptype,
        "email": (post.get("email") or "").strip() if "email" in enabled else "",
        "phone": (post.get("phone") or "").strip()
        if ("phone" in enabled or getattr(event, "is_ticketing", False))
        else "",
        "extra_data": extra,
        "category": extra.get("category") or (tier.name if tier else ""),
        "ticket_tier": tier,
    }


def validate_payload(event: Event, payload: dict) -> list[str]:
    errors = []
    if not payload.get("first_name"):
        errors.append("Le prénom est obligatoire.")
    if not payload.get("last_name"):
        errors.append("Le nom est obligatoire.")
    quota = assert_can_create_invitation(event, payload.get("participant_type") or PARTICIPANT_RECIPIENT)
    if not quota.allowed:
        errors.append(quota.message)
    if event.uses_paid_guest_link:
        price = guest_price_for(event, payload["participant_type"], payload.get("ticket_tier"))
        if price <= 0:
            errors.append("Le tarif de cette catégorie n’est pas encore défini par l’organisateur.")
    if getattr(event, "is_ticketing", False):
        tier = payload.get("ticket_tier")
        if not tier:
            errors.append("Choisissez une catégorie de billet.")
        elif tier.sold_out:
            errors.append("Cette catégorie de billet est épuisée.")
        digits = re.sub(r"\D", "", payload.get("phone") or "")
        if len(digits) < 8:
            errors.append("Le téléphone est obligatoire pour l’achat et le contrôle du billet.")
    return errors


def create_free_guest_invitation(event: Event, payload: dict) -> Invitation:
    return create_invitation_with_unique_code(
        event=event,
        first_name=payload["first_name"],
        last_name=payload["last_name"],
        participant_type=payload["participant_type"],
        category=payload.get("category") or "",
        email=payload.get("email") or "",
        phone=payload.get("phone") or "",
        extra_data=payload.get("extra_data") or {},
        source=Invitation.SOURCE_FORM,
        places=1,
        status=Invitation.STATUS_VALID,
        ticket_tier=payload.get("ticket_tier"),
    )


def split_amounts(
    amount: Decimal,
    participant_type: str | None = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Commission = 7 % du prix. Les frais de transfert restent à l’organisateur."""
    pct, _fixed = fee_schedule()
    gross = Decimal(amount or 0)
    commission = (gross * pct / Decimal("100")).quantize(Decimal("0.01"))
    if commission > gross:
        commission = gross
    net = (gross - commission).quantize(Decimal("0.01"))
    return pct, commission, net


def invite_unlock_key(event: Event) -> str:
    return f"invite_unlocked_{event.pk}"


def invite_code_unlocked(request, event: Event) -> bool:
    code = (event.invite_access_code or "").strip()
    if not code:
        return True
    return request.session.get(invite_unlock_key(event)) == code


def try_unlock_invite(request, event: Event, submitted: str) -> bool:
    expected = (event.invite_access_code or "").strip()
    if not expected:
        return True
    if (submitted or "").strip() == expected:
        request.session[invite_unlock_key(event)] = expected
        return True
    return False
