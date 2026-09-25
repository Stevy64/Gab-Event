"""Configuration runtime du site (console admin, puis .env)."""
from __future__ import annotations

from django.conf import settings


def get_site():
    try:
        from .models import SiteSettings

        return SiteSettings.load()
    except Exception:
        return None


def display_name() -> str:
    site = get_site()
    name = (getattr(site, "site_name", None) or "").strip()
    return name or "Gab Event"


def public_base_url() -> str:
    site = get_site()
    url = (getattr(site, "public_base_url", None) or "").strip()
    if url:
        return url.rstrip("/")
    return (getattr(settings, "PUBLIC_BASE_URL", "") or "http://127.0.0.1:8000").rstrip("/")


def outgoing_from_email() -> str:
    site = get_site()
    raw = (getattr(site, "default_from_email", None) or "").strip()
    if not raw:
        raw = (getattr(site, "support_email", None) or "").strip()
    if raw:
        if "<" in raw:
            return raw
        return f"{display_name()} <{raw}>"
    return getattr(settings, "DEFAULT_FROM_EMAIL", "") or f"{display_name()} <noreply@gabevent.local>"


def meta_description() -> str:
    site = get_site()
    text = (getattr(site, "meta_description", None) or "").strip()
    if text:
        return text
    return (getattr(site, "tagline", None) or "").strip() or (
        "Gérez vos invitations événementielles avec QR Code"
    )


def mock_payments_allowed() -> bool:
    if not getattr(settings, "DEBUG", False):
        return False
    site = get_site()
    if site is not None:
        return bool(getattr(site, "allow_mock_payments", True))
    return bool(getattr(settings, "ALLOW_MOCK_PAYMENTS", False))


def active_payment_provider() -> str:
    import os

    from . import singpay as singpay_api

    explicit = os.environ.get("PAYMENT_PROVIDER", "").strip().lower()
    if explicit:
        return explicit
    if singpay_api.is_configured():
        return "singpay"
    if mock_payments_allowed():
        return "mock"
    return (getattr(settings, "PAYMENT_PROVIDER", "mock") or "mock").lower()
