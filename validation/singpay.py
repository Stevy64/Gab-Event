"""
Client SingPay — même contrat que Gabomazone (gateway.singpay.ga /v1/ext).
"""
from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)
LOG_PREFIX = "[SingPay]"


def _base_url() -> str:
    return "https://gateway.singpay.ga"


def credentials() -> dict[str, str]:
    creds = {
        "api_key": getattr(settings, "SINGPAY_API_KEY", "") or "",
        "api_secret": getattr(settings, "SINGPAY_API_SECRET", "") or "",
        "merchant_id": getattr(settings, "SINGPAY_MERCHANT_ID", "") or "",
        "disbursement_id": getattr(settings, "SINGPAY_DISBURSEMENT_ID", "") or "",
    }
    try:
        from .models import SiteSettings

        site = SiteSettings.objects.first()
    except Exception:
        site = None
    if site:
        if site.singpay_api_key:
            creds["api_key"] = site.singpay_api_key
        if site.singpay_api_secret:
            creds["api_secret"] = site.singpay_api_secret
        if site.singpay_merchant_id:
            creds["merchant_id"] = site.singpay_merchant_id
        if site.singpay_disbursement_id:
            creds["disbursement_id"] = site.singpay_disbursement_id
        if site.singpay_environment:
            creds["environment"] = site.singpay_environment
    creds.setdefault(
        "environment",
        getattr(settings, "SINGPAY_ENVIRONMENT", "sandbox") or "sandbox",
    )
    return creds


def is_configured() -> bool:
    creds = credentials()
    return bool(creds["api_key"] and creds["api_secret"] and creds["merchant_id"])


def _headers() -> dict[str, str]:
    creds = credentials()
    return {
        "Content-Type": "application/json",
        "accept": "*/*",
        "x-client-id": creds["api_key"],
        "x-client-secret": creds["api_secret"],
        "x-wallet": creds["merchant_id"],
    }


def init_payment(
    *,
    amount: float,
    reference: str,
    return_url: str,
    error_url: str,
    logo_url: str = "",
    is_transfer: bool = False,
) -> tuple[bool, dict[str, Any]]:
    if not is_configured():
        return False, {"error": "Identifiants SingPay manquants."}
    creds = credentials()
    data = {
        "portefeuille": creds["merchant_id"],
        "reference": reference,
        "redirect_success": return_url,
        "redirect_error": error_url,
        "amount": float(amount),
        "disbursement": creds["disbursement_id"],
        "logoURL": logo_url,
        "isTransfer": bool(is_transfer),
    }
    url = f"{_base_url()}/v1/ext"
    logger.info("%s init reference=%s amount=%s", LOG_PREFIX, reference, amount)
    try:
        response = requests.post(url, headers=_headers(), json=data, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        details: dict[str, Any] = {"error": str(exc)}
        if getattr(exc, "response", None) is not None:
            try:
                details["api_error"] = exc.response.json()
            except Exception:
                details["response_text"] = (exc.response.text or "")[:400]
        logger.error("%s init failed %s", LOG_PREFIX, details)
        return False, details

    payment_url = payload.get("link") or payload.get("payment_url") or payload.get("url")
    if not payment_url:
        return False, {"error": "Lien de paiement manquant.", "response": payload}
    transaction_id = payload.get("transaction_id") or payload.get("id") or ""
    if not transaction_id and "/payment/" in payment_url:
        transaction_id = payment_url.split("/payment/")[-1].split("/")[0].split("?")[0]
    return True, {
        "payment_url": payment_url,
        "transaction_id": transaction_id or reference,
        "reference": payload.get("reference") or reference,
        "raw": payload,
    }


def verify_transaction(transaction_id: str) -> tuple[bool, dict[str, Any]]:
    if not is_configured() or not transaction_id:
        return False, {"error": "Vérification impossible."}
    url = f"{_base_url()}/v1/transaction/{transaction_id}"
    try:
        response = requests.get(url, headers=_headers(), timeout=30)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.error("%s verify failed %s", LOG_PREFIX, exc)
        return False, {"error": str(exc)}
    status = (payload.get("status") or "").lower()
    return True, {
        "status": status,
        "success": status in {"success", "paid", "successful", "completed"},
        "raw": payload,
    }


def transfer(
    *,
    reference: str,
    amount: float,
    msisdn: str,
    disbursement: str = "",
) -> tuple[bool, dict[str, Any]]:
    """Reverse une partie d’une collecte vers un numéro Mobile Money."""
    if not is_configured():
        return False, {"error": "Identifiants SingPay manquants."}
    creds = credentials()
    dest = (disbursement or msisdn or "").strip()
    if not dest:
        return False, {"error": "Numéro Mobile Money manquant pour le reversement."}
    data = {
        "reference": reference,
        "disbursement": dest,
        "amount": float(amount),
        "msisdn": msisdn,
        "client_msisdn": msisdn,
    }
    url = f"{_base_url()}/v1/transfer"
    logger.info("%s transfer reference=%s amount=%s dest=%s", LOG_PREFIX, reference, amount, dest)
    try:
        response = requests.post(url, headers=_headers(), json=data, timeout=45)
        response.raise_for_status()
        payload = response.json() if response.content else {}
    except requests.RequestException as exc:
        details: dict[str, Any] = {"error": str(exc)}
        if getattr(exc, "response", None) is not None:
            try:
                details["api_error"] = exc.response.json()
            except Exception:
                details["response_text"] = (exc.response.text or "")[:400]
        logger.error("%s transfer failed %s", LOG_PREFIX, details)
        return False, details
    status = str(payload.get("status") or "").lower()
    ok = status in {"", "success", "pending", "successful"} or bool(payload.get("isFinish"))
    if payload.get("status") == "Failed":
        ok = False
    return ok, {
        "status": status or "success",
        "reference": payload.get("reference") or reference,
        "raw": payload,
    }
