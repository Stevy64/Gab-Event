"""Résolution d'identité (e-mail, téléphone, username)."""
from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


def normalize_phone(raw: str) -> str:
    """Garde + et chiffres ; retire espaces / tirets / points."""
    if not raw:
        return ""
    s = re.sub(r"[^\d+]", "", str(raw).strip())
    if s.count("+") > 1:
        s = s.replace("+", "")
        s = "+" + s
    elif "+" in s and not s.startswith("+"):
        s = s.replace("+", "")
    return s


def phone_digits_key(raw: str) -> str:
    """Clé comparable (Gabon : +241 / 0 initial ignorés)."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("241") and len(digits) >= 11:
        digits = digits[3:]
    return digits.lstrip("0")


def phones_match(a: str, b: str) -> bool:
    ka, kb = phone_digits_key(a), phone_digits_key(b)
    return bool(ka and kb and ka == kb)


def phone_lookup_variants(phone: str) -> list[str]:
    """Variantes utiles pour matcher un numéro déjà stocké."""
    n = normalize_phone(phone)
    if not n:
        return []
    variants = {n}
    digits = re.sub(r"\D", "", n)
    if digits:
        variants.add(digits)
        variants.add("+" + digits)
        if digits.startswith("0") and len(digits) >= 9:
            variants.add("+241" + digits.lstrip("0"))  # Gabon courant
            variants.add("241" + digits.lstrip("0"))
    return [v for v in variants if v]


def resolve_user(login_id: str):
    """Retrouve un User par username, e-mail ou téléphone profil."""
    raw = (login_id or "").strip()
    if not raw:
        return None

    user = User.objects.filter(username__iexact=raw).first()
    if user:
        return user

    if "@" in raw:
        user = User.objects.filter(email__iexact=raw).first()
        if user:
            return user

    variants = phone_lookup_variants(raw)
    if variants:
        q = Q()
        for v in variants:
            q |= Q(profile__phone=v) | Q(profile__phone__iexact=v)
        # Aussi comparer chiffres seuls côté DB approximatif
        user = (
            User.objects.filter(q)
            .select_related("profile")
            .first()
        )
        if user:
            return user
        if phone_digits_key(raw):
            for u in User.objects.filter(profile__phone__gt="").select_related("profile"):
                if phones_match(raw, u.profile.phone):
                    return u
    return None


OPERATOR_AIRTEL = "airtel"
OPERATOR_MOOV = "moov"
MOMO_OPERATOR_CHOICES = (
    (OPERATOR_AIRTEL, "Airtel Money"),
    (OPERATOR_MOOV, "Moov Money"),
)


def momo_msisdn(raw: str) -> str:
    """Format local Gabon (0XXXXXXXXX) attendu par SingPay."""
    key = phone_digits_key(raw)
    if not key:
        return ""
    return "0" + key


def validate_momo_number(operator: str, raw: str) -> tuple[bool, str]:
    msisdn = momo_msisdn(raw)
    digits = re.sub(r"\D", "", msisdn)
    if len(digits) < 8:
        return False, "Indiquez un numéro Mobile Money valide."
    if operator == OPERATOR_AIRTEL and digits.startswith("06"):
        return False, "Ce numéro ressemble à du Moov Money. Choisissez le bon opérateur."
    if operator == OPERATOR_MOOV and digits.startswith("07"):
        return False, "Ce numéro ressemble à de l’Airtel Money. Choisissez le bon opérateur."
    return True, msisdn


def unique_username(base: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9._]", "", (base or "user").lower())[:24] or "user"
    candidate = base
    n = 1
    while User.objects.filter(username=candidate).exists():
        suffix = str(n)
        candidate = f"{base[: 30 - len(suffix)]}{suffix}"
        n += 1
    return candidate
