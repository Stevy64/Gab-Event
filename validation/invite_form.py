"""Formulaire public d’inscription — champs standard + verrouillage après mise en ligne."""
from __future__ import annotations

import secrets
from decimal import Decimal

from .code_service import create_invitation_with_unique_code
from .constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP
from .models import Event, Invitation, SiteSettings
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
    if not stored:
        return default_fields()
    return normalize_fields(stored)


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


def commission_rate(participant_type: str) -> Decimal:
    site = SiteSettings.load()
    if participant_type == PARTICIPANT_VIP:
        return Decimal(site.commission_vip_pct or 20)
    return Decimal(site.commission_regular_pct or 10)


def guest_price_for(event: Event, participant_type: str) -> Decimal:
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
    return {
        "first_name": first,
        "last_name": last,
        "participant_type": ptype,
        "email": (post.get("email") or "").strip() if "email" in enabled else "",
        "phone": (post.get("phone") or "").strip() if "phone" in enabled else "",
        "extra_data": extra,
        "category": extra.get("category") or "",
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
        price = guest_price_for(event, payload["participant_type"])
        if price <= 0:
            errors.append("Le tarif de cette catégorie n’est pas encore défini par l’organisateur.")
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
    )


def split_amounts(amount: Decimal, participant_type: str) -> tuple[Decimal, Decimal, Decimal]:
    rate = commission_rate(participant_type)
    commission = (Decimal(amount) * rate / Decimal("100")).quantize(Decimal("0.01"))
    net = (Decimal(amount) - commission).quantize(Decimal("0.01"))
    return rate, commission, net
