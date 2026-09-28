"""Codes OTP pour récupérer un compte par SMS ou WhatsApp."""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .identity import normalize_phone, phone_digits_key

logger = logging.getLogger(__name__)

OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 60


def hash_otp_code(code: str) -> str:
    raw = f"{(code or '').strip()}:{settings.SECRET_KEY}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def international_msisdn(raw: str) -> str:
    key = phone_digits_key(raw)
    if not key:
        return ""
    if len(key) <= 9:
        return "241" + key
    return key


def dispatch_otp(phone: str, code: str) -> str:
    """Envoie le code. Retourne le canal utilisé (whatsapp, sms, console)."""
    text = f"Votre code Gab Event : {code}. Valable {OTP_TTL_MINUTES} minutes."
    to = international_msisdn(phone)
    if _send_whatsapp(to, text):
        return "whatsapp"
    if _send_sms(to, text):
        return "sms"
    logger.info("OTP console %s → %s", to or phone, code)
    return "console"


def _send_whatsapp(to: str, text: str) -> bool:
    token = (getattr(settings, "WHATSAPP_ACCESS_TOKEN", "") or "").strip()
    phone_id = (getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "") or "").strip()
    if not token or not phone_id or not to:
        return False
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    payload = json.dumps(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text, "preview_url": False},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("WhatsApp OTP échoué : %s", exc)
        return False


def _send_sms(to: str, text: str) -> bool:
    url = (getattr(settings, "SMS_API_URL", "") or "").strip()
    key = (getattr(settings, "SMS_API_KEY", "") or "").strip()
    if not url or not to:
        return False
    payload = json.dumps({"to": to, "text": text}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("SMS OTP échoué : %s", exc)
        return False


def issue_otp(user, phone: str, *, code: str | None = None):
    from .models import RecoveryOtp

    phone = normalize_phone(phone)
    code = code or generate_otp_code()
    now = timezone.now()
    RecoveryOtp.objects.filter(user=user, consumed_at__isnull=True).update(consumed_at=now)
    otp = RecoveryOtp.objects.create(
        user=user,
        phone=phone,
        code_hash=hash_otp_code(code),
        expires_at=now + timedelta(minutes=OTP_TTL_MINUTES),
    )
    channel = dispatch_otp(phone, code)
    if channel != otp.channel:
        otp.channel = channel
        otp.save(update_fields=["channel"])
    return otp, code, channel


def can_resend(user) -> bool:
    from .models import RecoveryOtp

    latest = (
        RecoveryOtp.objects.filter(user=user).order_by("-created_at").first()
    )
    if latest is None:
        return True
    return (timezone.now() - latest.created_at).total_seconds() >= OTP_RESEND_SECONDS


def verify_otp(user, code: str) -> tuple[bool, str]:
    from .models import RecoveryOtp

    otp = (
        RecoveryOtp.objects.filter(user=user, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if otp is None:
        return False, "Aucun code en cours. Demandez-en un nouveau."
    if otp.expires_at and otp.expires_at < timezone.now():
        return False, "Ce code a expiré. Demandez-en un nouveau."
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        return False, "Trop d’essais. Demandez un nouveau code."
    otp.attempts += 1
    if otp.code_hash != hash_otp_code(code):
        otp.save(update_fields=["attempts"])
        return False, "Code incorrect."
    otp.consumed_at = timezone.now()
    otp.save(update_fields=["attempts", "consumed_at"])
    return True, ""


def channel_label(channel: str) -> str:
    return {
        "whatsapp": "WhatsApp",
        "sms": "SMS",
        "console": "SMS ou WhatsApp",
    }.get(channel or "", "SMS ou WhatsApp")
