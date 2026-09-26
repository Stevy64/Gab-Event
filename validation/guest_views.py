"""Lien public d’invitation et paiements invités."""
from __future__ import annotations

from collections import OrderedDict
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from . import singpay as singpay_api
from .access import event_workspace_required, get_user_event
from .invite_form import (
    catalog,
    create_free_guest_invitation,
    ensure_invite_token,
    event_fields,
    field_specs,
    guest_price_for,
    normalize_fields,
    payload_from_post,
    validate_payload,
)
from .card_service import (
    generate_invitation_card,
    invitation_filename,
    invitation_pdf_bytes,
    invitation_pdf_filename,
)
from .models import Event, FaqItem, GuestPayment, Invitation, UserProfile
from .qr_service import generate_invitation_qr
from .payment_service import (
    confirm_guest_payment_success,
    create_guest_payment,
    start_guest_checkout,
)
from .quota_service import guest_registration_open, quota_status


def _legal_sheet_context():
    grouped = OrderedDict((label, []) for _key, label in FaqItem.SECTION_CHOICES)
    for item in FaqItem.objects.filter(is_active=True):
        grouped[item.get_section_display()].append(item)
    return {
        "faq_sections": [(label, items) for label, items in grouped.items() if items],
    }


def _parse_iso_date(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _apply_invite_window(event, post) -> str:
    starts = _parse_iso_date(post.get("invite_valid_from"))
    ends = _parse_iso_date(post.get("invite_valid_until"))
    if starts or ends:
        event.set_invite_window(
            starts or event.invite_valid_from,
            ends or event.invite_valid_until,
        )
    else:
        event.apply_default_invite_window()
    if event.invite_valid_from and event.invite_valid_until:
        if event.invite_valid_until < event.invite_valid_from:
            return "La fin du lien doit être postérieure à son début."
    if event.validity_starts_on and event.invite_valid_from:
        if event.invite_valid_from < event.validity_starts_on:
            return "Le lien ne peut pas commencer avant la validité de l’événement."
    if event.validity_ends_on and event.invite_valid_until:
        if event.invite_valid_until > event.validity_ends_on:
            return "Le lien ne peut pas dépasser la fin de validité de l’événement."
    return ""


@login_required
@require_http_methods(["GET", "POST"])
@event_workspace_required
def event_invite_link(request, event_id):
    event = get_user_event(request.user, event_id)
    ensure_invite_token(event)
    locked = event.invite_form_locked
    if request.method == "POST":
        action = request.POST.get("action") or "save"
        window_error = _apply_invite_window(event, request.POST)
        if window_error:
            messages.error(request, window_error)
            return redirect("event_invite_link", event_id=event.pk)
        if action == "save" and not locked:
            event.invite_form_fields = normalize_fields(request.POST.getlist("fields"))
            if event.uses_paid_guest_link:
                event.guest_price_regular = Decimal(request.POST.get("guest_price_regular") or 0)
                event.guest_price_vip = Decimal(request.POST.get("guest_price_vip") or 0)
            event.save()
            messages.success(request, "Formulaire enregistré.")
        elif action == "save":
            event.save(
                update_fields=[
                    "invite_valid_from",
                    "invite_valid_until",
                    "updated_at",
                ]
            )
            messages.success(request, "Fenêtre du lien enregistrée.")
        elif action in {"publish", "resume"} and event.status != event.STATUS_ACTIVE:
            messages.error(
                request,
                "Réactivez l’événement pour publier ou rouvrir le lien d’invitation.",
            )
            return redirect("event_invite_link", event_id=event.pk)
        elif action == "publish":
            if event.uses_paid_guest_link:
                profile = UserProfile.objects.filter(user=event.owner).first()
                if profile is None or not profile.momo_ready:
                    messages.error(
                        request,
                        "Confirmez votre numéro Airtel Money ou Moov Money dans le profil pour recevoir les reversements.",
                    )
                    return redirect("profile")
            if not locked:
                event.invite_form_fields = normalize_fields(
                    request.POST.getlist("fields") or event_fields(event)
                )
                if event.uses_paid_guest_link:
                    event.guest_price_regular = Decimal(
                        request.POST.get("guest_price_regular") or event.guest_price_regular or 0
                    )
                    event.guest_price_vip = Decimal(
                        request.POST.get("guest_price_vip") or event.guest_price_vip or 0
                    )
            event.invite_published_at = event.invite_published_at or timezone.now()
            event.invite_link_enabled = True
            event.apply_default_invite_window()
            event.save()
            messages.success(request, "Lien d’invitation mis en ligne.")
        elif action == "pause":
            event.invite_link_enabled = False
            event.save(update_fields=["invite_link_enabled", "invite_valid_from", "invite_valid_until", "updated_at"])
            messages.info(request, "Le lien est temporairement désactivé.")
        elif action == "resume" and event.invite_published_at:
            event.invite_link_enabled = True
            event.apply_default_invite_window()
            event.save(update_fields=["invite_link_enabled", "invite_valid_from", "invite_valid_until", "updated_at"])
            messages.success(request, "Le lien est de nouveau actif.")
        return redirect("event_invite_link", event_id=event.pk)

    public_path = reverse("public_invite", args=[event.invite_token])
    public_url = request.build_absolute_uri(public_path)
    profile = UserProfile.objects.filter(user=event.owner).first()
    return render(
        request,
        "events/invite_link.html",
        {
            "event": event,
            "nav_active": "invite",
            "fields": field_specs(event),
            "locked": locked,
            "public_url": public_url,
            "quotas": quota_status(event),
            "momo_ready": bool(profile and profile.momo_ready),
            "momo_label": profile.momo_label if profile else "Non renseigné",
        },
    )


@login_required
@require_GET
@event_workspace_required
def event_guest_payments(request, event_id):
    event = get_user_event(request.user, event_id)
    payments = event.guest_payments.select_related("invitation").all()
    success = payments.filter(status=GuestPayment.STATUS_SUCCESS)
    profile = UserProfile.objects.filter(user=event.owner).first()
    return render(
        request,
        "events/guest_payments.html",
        {
            "event": event,
            "nav_active": "invite",
            "payments": payments,
            "gross": success.aggregate(t=Sum("amount"))["t"] or 0,
            "commission": success.aggregate(t=Sum("commission_amount"))["t"] or 0,
            "net": success.aggregate(t=Sum("net_amount"))["t"] or 0,
            "momo_ready": bool(profile and profile.momo_ready),
            "momo_label": profile.momo_label if profile else "Non renseigné",
        },
    )


@require_http_methods(["GET", "POST"])
def public_invite(request, token):
    event = get_object_or_404(Event, invite_token=token)
    if event.needs_payment or event.status != Event.STATUS_ACTIVE:
        raise Http404()
    if not event.invite_window_open:
        return render(
            request,
            "public/invite_closed.html",
            {
                "event": event,
                "window_state": event.invite_window_state,
                **_legal_sheet_context(),
            },
        )
    slots = guest_registration_open(event)
    if not slots.allowed:
        return render(
            request,
            "public/invite_closed.html",
            {
                "event": event,
                "window_state": "full",
                "quota_message": slots.message,
                **_legal_sheet_context(),
            },
        )
    errors = []
    payload = {}
    if request.method == "POST":
        payload = payload_from_post(event, request.POST)
        errors = validate_payload(event, payload)
        accepted = (request.POST.get("accept_terms") or "").lower()
        if accepted not in {"on", "1", "true", "yes"}:
            errors.append("Veuillez accepter les CGU.")
        if not errors:
            if event.uses_paid_guest_link:
                payload["amount"] = guest_price_for(event, payload["participant_type"])
                payment = create_guest_payment(event=event, payload=payload)
                try:
                    intent = start_guest_checkout(payment)
                except RuntimeError as exc:
                    errors.append(str(exc))
                else:
                    return redirect(intent.checkout_url)
            else:
                invitation = create_free_guest_invitation(event, payload)
                request.session["guest_invite_code"] = invitation.code
                return redirect("public_invite_thanks", token=token)
    return render(
        request,
        "public/invite_form.html",
        {
            "event": event,
            "fields": event_fields(event),
            "catalog": {item["key"]: item for item in catalog()},
            "errors": errors,
            "payload": payload,
            "paid": event.uses_paid_guest_link,
            "price_regular": guest_price_for(event, "RECIPIENT"),
            "price_vip": guest_price_for(event, "VIP"),
            **_legal_sheet_context(),
        },
    )


def _guest_invitation_from_session(request, event):
    code = (request.session.get("guest_invite_code") or "").strip()
    if not code:
        return None
    return Invitation.objects.filter(event=event, code=code).first()


@require_GET
def public_invite_thanks(request, token):
    event = get_object_or_404(Event, invite_token=token)
    invitation = _guest_invitation_from_session(request, event)
    return render(
        request,
        "public/invite_thanks.html",
        {
            "event": event,
            "code": invitation.code if invitation else "",
            "invitation": invitation,
            **_legal_sheet_context(),
        },
    )


@require_GET
def public_invite_card(request, token):
    event = get_object_or_404(Event, invite_token=token)
    invitation = _guest_invitation_from_session(request, event)
    if not invitation:
        raise Http404()
    generate_invitation_qr(invitation)
    data, _ = generate_invitation_card(invitation, save=True)
    fmt = (request.GET.get("fmt") or "png").lower()
    if fmt == "pdf":
        payload = invitation_pdf_bytes(data)
        response = HttpResponse(payload, content_type="application/pdf")
        response["Content-Length"] = str(len(payload))
        response["Content-Disposition"] = (
            f'attachment; filename="{invitation_pdf_filename(invitation)}"'
        )
        return response
    response = HttpResponse(data, content_type="image/png")
    response["Content-Length"] = str(len(data))
    response["Content-Disposition"] = (
        f'attachment; filename="{invitation_filename(invitation)}"'
    )
    return response


@require_http_methods(["GET", "POST"])
def guest_mock_checkout(request, payment_id):
    if not (settings.DEBUG and getattr(settings, "ALLOW_MOCK_PAYMENTS", False)):
        return HttpResponseForbidden("Paiement mock indisponible.")
    payment = get_object_or_404(GuestPayment.objects.select_related("event"), pk=payment_id)
    if request.method == "POST":
        payment = confirm_guest_payment_success(payment, provider_payload={"mock": True})
        request.session["guest_invite_code"] = (
            payment.invitation.code if payment.invitation_id else ""
        )
        return redirect("public_invite_thanks", token=payment.event.invite_token)
    return render(request, "payments/guest_mock_checkout.html", {"payment": payment})


@require_GET
def guest_singpay_return(request, payment_id):
    payment = get_object_or_404(GuestPayment.objects.select_related("event"), pk=payment_id)
    event = payment.event
    if payment.status == GuestPayment.STATUS_SUCCESS:
        request.session["guest_invite_code"] = (
            payment.invitation.code if payment.invitation_id else ""
        )
        return redirect("public_invite_thanks", token=event.invite_token)
    meta = (payment.metadata or {}).get("singpay") or {}
    txn_id = meta.get("transaction_id") or payment.provider_reference
    failed = (request.GET.get("status") or "").lower() == "error"
    ok, payload = singpay_api.verify_transaction(txn_id)
    if ok and payload.get("success"):
        payment = confirm_guest_payment_success(payment, provider_payload=payload)
        request.session["guest_invite_code"] = (
            payment.invitation.code if payment.invitation_id else ""
        )
        return redirect("public_invite_thanks", token=event.invite_token)
    if failed or (ok and not payload.get("success")):
        payment.status = GuestPayment.STATUS_FAILED
        payment.save(update_fields=["status", "updated_at"])
    return render(
        request,
        "public/invite_thanks.html",
        {
            "event": event,
            "code": "",
            "failed": True,
            **_legal_sheet_context(),
        },
    )
