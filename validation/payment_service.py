"""
Abstraction paiement — confirmation serveur obligatoire pour activer un événement payant.

MockPaymentProvider : développement uniquement (jamais en production).
"""
from __future__ import annotations

import logging
import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from . import singpay as singpay_api
from .code_service import create_invitation_with_unique_code
from .invite_form import split_amounts
from .identity import momo_msisdn
from .models import (
    AdminAuditLog,
    Event,
    EventPlan,
    GuestPayment,
    Invitation,
    OrganizerPayout,
    Payment,
    UserProfile,
)

logger = logging.getLogger(__name__)


@dataclass
class PaymentIntent:
    payment: Payment
    checkout_url: str
    provider_reference: str


class PaymentProvider(ABC):
    name: str = "base"

    @abstractmethod
    def create_intent(self, payment: Payment) -> PaymentIntent:
        raise NotImplementedError

    @abstractmethod
    def verify_callback(self, payload: dict) -> dict:
        """Retourne {reference, success, raw} après vérification prestataire."""
        raise NotImplementedError


class MockPaymentProvider(PaymentProvider):
    """Prestataire fictif — uniquement si DEBUG et ALLOW_MOCK_PAYMENTS."""

    name = "mock"

    def create_intent(self, payment: Payment) -> PaymentIntent:
        if not getattr(settings, "DEBUG", False) or not getattr(
            settings, "ALLOW_MOCK_PAYMENTS", False
        ):
            raise RuntimeError(
                "MockPaymentProvider interdit hors développement "
                "(DEBUG + ALLOW_MOCK_PAYMENTS requis)."
            )
        ref = payment.provider_reference or f"MOCK-{uuid.uuid4().hex[:16].upper()}"
        payment.provider = self.name
        payment.provider_reference = ref
        payment.save(update_fields=["provider", "provider_reference", "updated_at"])
        return PaymentIntent(
            payment=payment,
            checkout_url=f"/payments/mock/{payment.pk}/",
            provider_reference=ref,
        )

    def verify_callback(self, payload: dict) -> dict:
        if not getattr(settings, "DEBUG", False) or not getattr(
            settings, "ALLOW_MOCK_PAYMENTS", False
        ):
            raise RuntimeError("Callback mock refusé hors développement.")
        reference = (payload.get("reference") or "").strip()
        success = bool(payload.get("success", True))
        return {"reference": reference, "success": success, "raw": payload}


class SingPayProvider(PaymentProvider):
    name = "singpay"

    def create_intent(self, payment: Payment) -> PaymentIntent:
        if not singpay_api.is_configured():
            raise RuntimeError(
                "SingPay n’est pas configuré. Renseignez SINGPAY_API_KEY, "
                "SINGPAY_API_SECRET et SINGPAY_MERCHANT_ID."
            )
        base = (getattr(settings, "PUBLIC_BASE_URL", "") or "http://127.0.0.1:8000").rstrip("/")
        return_url = f"{base}{reverse('singpay_return', args=[payment.pk])}"
        reference = payment.provider_reference or f"GE-{payment.pk}"
        ok, payload = singpay_api.init_payment(
            amount=float(payment.amount),
            reference=reference,
            return_url=return_url,
            error_url=f"{return_url}?status=error",
        )
        if not ok:
            raise RuntimeError(payload.get("error") or "Impossible d’ouvrir SingPay.")
        meta = dict(payment.metadata or {})
        meta["singpay"] = {
            "transaction_id": payload.get("transaction_id") or "",
            "reference": payload.get("reference") or reference,
        }
        payment.provider = self.name
        payment.provider_reference = payload.get("reference") or reference
        payment.metadata = meta
        payment.save(update_fields=["provider", "provider_reference", "metadata", "updated_at"])
        return PaymentIntent(
            payment=payment,
            checkout_url=payload["payment_url"],
            provider_reference=payment.provider_reference,
        )

    def verify_callback(self, payload: dict) -> dict:
        reference = (
            payload.get("reference")
            or payload.get("order_id")
            or payload.get("provider_reference")
            or ""
        )
        status = str(payload.get("status") or "").lower()
        success = status in {"success", "paid", "successful", "completed"}
        return {"reference": str(reference).strip(), "success": success, "raw": payload}


def get_payment_provider(name: str | None = None) -> PaymentProvider:
    provider_name = (name or getattr(settings, "PAYMENT_PROVIDER", "mock")).lower()
    if provider_name == "mock":
        return MockPaymentProvider()
    if provider_name == "singpay":
        return SingPayProvider()
    raise ValueError(f"Prestataire de paiement inconnu : {provider_name}")


def create_pending_payment(
    *,
    user,
    event: Event,
    plan: EventPlan,
) -> Payment:
    amount = plan.price
    currency = plan.currency
    payment = Payment.objects.create(
        user=user,
        event=event,
        plan=plan,
        amount=amount,
        currency=currency,
        provider=getattr(settings, "PAYMENT_PROVIDER", "mock"),
        provider_reference=f"PAY-{secrets.token_hex(8).upper()}",
        status=Payment.STATUS_PENDING,
    )
    return payment


def start_checkout(payment: Payment) -> PaymentIntent:
    provider = get_payment_provider(payment.provider)
    return provider.create_intent(payment)


@transaction.atomic
def confirm_payment_success(
    payment: Payment,
    *,
    provider_payload: dict | None = None,
    actor=None,
) -> Payment:
    """
    Idempotent : si déjà SUCCESS, ne ré-active pas deux fois.
    Active l'événement et fige le snapshot du plan.
    """
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == Payment.STATUS_SUCCESS:
        return payment

    payment.status = Payment.STATUS_SUCCESS
    payment.paid_at = timezone.now()
    if provider_payload:
        meta = dict(payment.metadata or {})
        meta["callback"] = {
            k: v
            for k, v in provider_payload.items()
            if k not in ("card", "password", "token", "cvv")
        }
        payment.metadata = meta
    payment.save()

    event = Event.objects.select_for_update().get(pk=payment.event_id)
    event.apply_plan_snapshot(payment.plan)
    event.status = Event.STATUS_ACTIVE
    event.save()

    AdminAuditLog.objects.create(
        actor=actor,
        action=AdminAuditLog.ACTION_EVENT_ACTIVATE,
        target_type="event",
        target_id=str(event.pk),
        summary=f"Événement activé après paiement #{payment.pk}",
        details={"payment_id": payment.pk, "plan": payment.plan.slug},
    )
    logger.info("Payment %s confirmed — event %s active", payment.pk, event.pk)
    return payment


@transaction.atomic
def handle_provider_webhook(provider_name: str, payload: dict) -> Payment | None:
    provider = get_payment_provider(provider_name)
    verified = provider.verify_callback(payload)
    reference = verified.get("reference") or ""
    if not reference:
        logger.warning("Webhook %s sans référence", provider_name)
        return None

    payment = (
        Payment.objects.select_for_update()
        .filter(provider_reference=reference, provider=provider_name)
        .first()
    )
    if payment is None:
        guest = (
            GuestPayment.objects.select_for_update()
            .filter(provider_reference=reference, provider=provider_name)
            .first()
        )
        if guest is None:
            logger.warning("Paiement introuvable pour ref=%s", reference)
            return None
        if guest.status == GuestPayment.STATUS_SUCCESS:
            return guest
        if verified.get("success"):
            return confirm_guest_payment_success(guest, provider_payload=verified)
        guest.status = GuestPayment.STATUS_FAILED
        guest.save(update_fields=["status", "updated_at"])
        return guest

    if payment.status == Payment.STATUS_SUCCESS:
        return payment  # idempotence

    if verified.get("success"):
        return confirm_payment_success(payment, provider_payload=verified)
    payment.status = Payment.STATUS_FAILED
    payment.save(update_fields=["status", "updated_at"])
    return payment


def activate_free_event(event: Event, plan: EventPlan) -> Event:
    if not plan.is_free and not plan.is_custom and Decimal(plan.price) > 0:
        raise ValueError("Cette formule n'est pas gratuite.")
    event.plan = plan
    event.apply_plan_snapshot(plan)
    event.status = Event.STATUS_ACTIVE
    if plan.is_custom:
        if event.guest_price_regular is None:
            event.guest_price_regular = plan.price_per_regular or Decimal("0")
        if event.guest_price_vip is None:
            event.guest_price_vip = plan.price_per_vip or Decimal("0")
    event.save()
    return event


def create_guest_payment(*, event: Event, payload: dict) -> GuestPayment:
    participant_type = payload.get("participant_type") or Invitation.TYPE_RECIPIENT
    amount = Decimal(str(payload.get("amount") or 0))
    rate, commission, net = split_amounts(amount, participant_type)
    return GuestPayment.objects.create(
        organizer=event.owner,
        event=event,
        first_name=payload.get("first_name") or "",
        last_name=payload.get("last_name") or "",
        email=payload.get("email") or "",
        phone=payload.get("phone") or "",
        extra_data=payload.get("extra_data") or {},
        participant_type=participant_type,
        amount=amount,
        currency=event.currency_snapshot or (event.plan.currency if event.plan_id else "XOF"),
        commission_rate=rate,
        commission_amount=commission,
        net_amount=net,
        provider=getattr(settings, "PAYMENT_PROVIDER", "mock"),
        provider_reference=f"GINV-{secrets.token_hex(7).upper()}",
        status=GuestPayment.STATUS_PENDING,
    )


def start_guest_checkout(payment: GuestPayment) -> PaymentIntent:
    provider_name = (payment.provider or getattr(settings, "PAYMENT_PROVIDER", "mock")).lower()
    base = (getattr(settings, "PUBLIC_BASE_URL", "") or "http://127.0.0.1:8000").rstrip("/")
    if provider_name == "mock":
        if not getattr(settings, "DEBUG", False) or not getattr(
            settings, "ALLOW_MOCK_PAYMENTS", False
        ):
            raise RuntimeError("Paiement mock indisponible.")
        payment.provider = "mock"
        payment.save(update_fields=["provider", "updated_at"])
        return PaymentIntent(
            payment=payment,
            checkout_url=reverse("guest_mock_checkout", args=[payment.pk]),
            provider_reference=payment.provider_reference,
        )
    if not singpay_api.is_configured():
        raise RuntimeError("SingPay n’est pas configuré.")
    return_url = f"{base}{reverse('guest_singpay_return', args=[payment.pk])}"
    ok, payload = singpay_api.init_payment(
        amount=float(payment.amount),
        reference=payment.provider_reference,
        return_url=return_url,
        error_url=f"{return_url}?status=error",
        is_transfer=True,
    )
    if not ok:
        raise RuntimeError(payload.get("error") or "Impossible d’ouvrir SingPay.")
    meta = dict(payment.metadata or {})
    meta["singpay"] = {
        "transaction_id": payload.get("transaction_id") or "",
        "reference": payload.get("reference") or payment.provider_reference,
    }
    payment.provider = "singpay"
    payment.provider_reference = payload.get("reference") or payment.provider_reference
    payment.metadata = meta
    payment.save(update_fields=["provider", "provider_reference", "metadata", "updated_at"])
    return PaymentIntent(
        payment=payment,
        checkout_url=payload["payment_url"],
        provider_reference=payment.provider_reference,
    )


@transaction.atomic
def confirm_guest_payment_success(payment: GuestPayment, *, provider_payload: dict | None = None) -> GuestPayment:
    payment = GuestPayment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == GuestPayment.STATUS_SUCCESS:
        return payment
    payment.status = GuestPayment.STATUS_SUCCESS
    payment.paid_at = timezone.now()
    if provider_payload:
        meta = dict(payment.metadata or {})
        meta["callback"] = {
            k: v
            for k, v in provider_payload.items()
            if k not in ("card", "password", "token", "cvv")
        }
        payment.metadata = meta
    if payment.invitation_id is None:
        extra = dict(payment.extra_data or {})
        invitation = create_invitation_with_unique_code(
            event=payment.event,
            first_name=payment.first_name,
            last_name=payment.last_name,
            participant_type=payment.participant_type,
            category=extra.get("category") or "",
            email=payment.email,
            phone=payment.phone,
            extra_data=extra,
            source=Invitation.SOURCE_FORM,
            places=1,
            status=Invitation.STATUS_VALID,
        )
        payment.invitation = invitation
    payment.save()
    return payment


def _profile_for(user) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def send_guest_payout(payment: GuestPayment, profile: UserProfile) -> dict:
    msisdn = momo_msisdn(profile.momo_phone)
    provider = (payment.provider or "mock").lower()
    if provider != "singpay" or not singpay_api.is_configured():
        if not (getattr(settings, "DEBUG", False) and getattr(settings, "ALLOW_MOCK_PAYMENTS", False)):
            if provider == "singpay":
                raise RuntimeError("SingPay n’est pas configuré pour le reversement.")
        return {"provider": "mock", "reference": f"MOCK-PAYOUT-{payment.pk}"}
    reference = ""
    meta = (payment.metadata or {}).get("singpay") or {}
    reference = meta.get("reference") or payment.provider_reference
    ok, payload = singpay_api.transfer(
        reference=reference,
        amount=float(payment.net_amount),
        msisdn=msisdn,
    )
    if not ok:
        raise RuntimeError(
            (payload.get("api_error") or payload.get("error") or "Reversement SingPay refusé.")
            if isinstance(payload.get("api_error"), str)
            else (payload.get("error") or "Reversement SingPay refusé.")
        )
    return {
        "provider": "singpay",
        "reference": payload.get("reference") or reference,
        "raw": payload.get("raw") or payload,
    }


@transaction.atomic
def payout_organizer(*, actor, organizer, payment_ids: list[int] | None = None) -> OrganizerPayout:
    profile = _profile_for(organizer)
    if not profile.momo_ready:
        raise RuntimeError(
            "L’organisateur doit renseigner et confirmer son numéro Airtel Money ou Moov Money."
        )
    qs = (
        GuestPayment.objects.select_for_update()
        .filter(
            organizer=organizer,
            status=GuestPayment.STATUS_SUCCESS,
            payout_status__in=[GuestPayment.PAYOUT_PENDING, GuestPayment.PAYOUT_FAILED],
        )
        .order_by("created_at")
    )
    if payment_ids:
        qs = qs.filter(pk__in=payment_ids)
    payments = list(qs)
    if not payments:
        raise RuntimeError("Aucun montant à reverser pour cet organisateur.")

    total = sum((p.net_amount for p in payments), Decimal("0"))
    batch = OrganizerPayout.objects.create(
        organizer=organizer,
        actor=actor,
        amount=total,
        currency=payments[0].currency or "XOF",
        momo_operator=profile.momo_operator,
        momo_phone=profile.momo_phone,
        status=OrganizerPayout.STATUS_PENDING,
        provider="singpay" if singpay_api.is_configured() else "mock",
    )
    results = []
    ok_count = 0
    for payment in payments:
        payment.payout = batch
        payment.payout_status = GuestPayment.PAYOUT_PROCESSING
        payment.payout_error = ""
        payment.save(update_fields=["payout", "payout_status", "payout_error", "updated_at"])
        try:
            sent = send_guest_payout(payment, profile)
            payment.payout_status = GuestPayment.PAYOUT_RECORDED
            payment.payout_reference = sent.get("reference") or ""
            payment.save(update_fields=["payout_status", "payout_reference", "updated_at"])
            ok_count += 1
            results.append({"id": payment.pk, "ok": True, "reference": payment.payout_reference})
        except RuntimeError as exc:
            payment.payout_status = GuestPayment.PAYOUT_FAILED
            payment.payout_error = str(exc)[:255]
            payment.save(update_fields=["payout_status", "payout_error", "updated_at"])
            results.append({"id": payment.pk, "ok": False, "error": str(exc)})

    if ok_count == len(payments):
        batch.status = OrganizerPayout.STATUS_SUCCESS
        batch.paid_at = timezone.now()
    elif ok_count == 0:
        batch.status = OrganizerPayout.STATUS_FAILED
    else:
        batch.status = OrganizerPayout.STATUS_PARTIAL
        batch.paid_at = timezone.now()
    batch.metadata = {"results": results, "msisdn": momo_msisdn(profile.momo_phone)}
    if results and results[0].get("reference"):
        batch.provider_reference = results[0]["reference"]
    batch.save()
    AdminAuditLog.objects.create(
        actor=actor,
        action=AdminAuditLog.ACTION_PAYOUT,
        target_type="user",
        target_id=str(organizer.pk),
        summary=f"Reversement {batch.amount} {batch.currency} vers {profile.momo_label}",
        details={"payout_id": batch.pk, "status": batch.status, "count": len(payments)},
    )
    return batch
