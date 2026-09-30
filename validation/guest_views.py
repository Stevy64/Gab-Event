"""Lien public d’invitation et paiements invités."""
from __future__ import annotations

import secrets
from collections import OrderedDict
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from . import singpay as singpay_api
from .access import event_workspace_required, get_user_event
from .forms import _clean_momo
from .invite_form import (
    catalog,
    create_free_guest_invitation,
    ensure_invite_token,
    event_fields,
    field_specs,
    guest_price_for,
    invite_code_unlocked,
    merge_locked_fields,
    normalize_fields,
    payload_from_post,
    try_unlock_invite,
    validate_payload,
)
from .invoice_service import guest_payment_invoice_bytes, invoice_response
from .share import guest_invite_href, organizer_invite_href
from .card_service import (
    generate_invitation_card,
    invitation_filename,
    invitation_pdf_bytes,
    invitation_pdf_filename,
)
from .models import AdminAuditLog, Event, EventController, FaqItem, GuestPayment, Invitation, SiteSettings, UserProfile
from .identity import phones_match
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

    def _redirect_invite(tab=None):
        tab = (tab or request.POST.get("tab") or request.GET.get("tab") or "link").strip()
        url = reverse("event_invite_link", args=[event.pk])
        if tab and tab != "link":
            return redirect(f"{url}?tab={tab}")
        return redirect(url)

    if request.method == "POST":
        action = request.POST.get("action") or "save"
        window_error = _apply_invite_window(event, request.POST)
        if window_error:
            messages.error(request, window_error)
            return _redirect_invite()
        if action == "save":
            incoming = request.POST.getlist("fields")
            if locked:
                event.invite_form_fields = merge_locked_fields(event_fields(event), incoming)
            else:
                event.invite_form_fields = normalize_fields(incoming)
            event.invite_access_code = (request.POST.get("invite_access_code") or "").strip()[:40]
            if event.uses_paid_guest_link and not locked:
                event.guest_price_regular = Decimal(request.POST.get("guest_price_regular") or 0)
                event.guest_price_vip = Decimal(request.POST.get("guest_price_vip") or 0)
            event.save()
            messages.success(
                request,
                "Formulaire enregistré." if not locked else "Champs ajoutés et dates enregistrées.",
            )
        elif action in {"publish", "resume"} and event.status != event.STATUS_ACTIVE:
            messages.error(
                request,
                "Réactivez l’événement pour publier ou rouvrir le lien d’invitation.",
            )
            return _redirect_invite()
        elif action == "publish":
            if event.uses_paid_guest_link:
                profile, _ = UserProfile.objects.get_or_create(user=event.owner)
                if not profile.momo_ready:
                    try:
                        cleaned = _clean_momo(
                            {
                                "momo_operator": request.POST.get("momo_operator"),
                                "momo_phone": request.POST.get("momo_phone"),
                                "momo_phone_confirm": request.POST.get("momo_phone_confirm"),
                            },
                            required=True,
                        )
                    except ValidationError:
                        messages.error(
                            request,
                            "Indiquez votre numéro Airtel Money ou Moov Money pour publier un lien payant.",
                        )
                        return _redirect_invite("prices")
                    profile.momo_operator = cleaned["momo_operator"]
                    profile.momo_phone = cleaned["momo_phone"]
                    profile.momo_confirmed_at = timezone.now()
                    profile.save()
            incoming = request.POST.getlist("fields") or event_fields(event)
            if locked:
                event.invite_form_fields = merge_locked_fields(event_fields(event), incoming)
            else:
                event.invite_form_fields = normalize_fields(incoming)
                if event.uses_paid_guest_link:
                    event.guest_price_regular = Decimal(
                        request.POST.get("guest_price_regular") or event.guest_price_regular or 0
                    )
                    event.guest_price_vip = Decimal(
                        request.POST.get("guest_price_vip") or event.guest_price_vip or 0
                    )
            event.invite_published_at = event.invite_published_at or timezone.now()
            event.invite_link_enabled = True
            event.invite_access_code = (request.POST.get("invite_access_code") or event.invite_access_code or "").strip()[:40]
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
        elif action == "add_controller":
            label = (request.POST.get("controller_label") or "Contrôleur").strip() or "Contrôleur"
            code = (request.POST.get("controller_code") or "").strip()
            if not code:
                messages.error(request, "Définissez un code de vérification pour le contrôleur.")
            else:
                EventController.objects.create(
                    event=event,
                    label=label[:120],
                    token=secrets.token_urlsafe(12).replace("_", "x").replace("-", "x")[:22],
                    access_code=code[:40],
                )
                messages.success(request, "Accès contrôleur créé.")
            return _redirect_invite("control")
        elif action == "revoke_controller":
            EventController.objects.filter(
                event=event, pk=request.POST.get("controller_id")
            ).update(is_active=False)
            messages.info(request, "Accès contrôleur révoqué.")
            return _redirect_invite("control")
        return _redirect_invite()

    public_path = reverse("public_invite", args=[event.invite_token])
    public_url = request.build_absolute_uri(public_path)
    profile = UserProfile.objects.filter(user=event.owner).first()
    controllers = []
    for ctrl in event.controllers.filter(is_active=True):
        ctrl.public_url = request.build_absolute_uri(reverse("controller_access", args=[ctrl.token]))
        controllers.append(ctrl)
    return render(
        request,
        "events/invite_link.html",
        {
            "event": event,
            "nav_active": "invite",
            "fields": field_specs(event),
            "locked": locked,
            "public_url": public_url,
            "wa_share_href": organizer_invite_href(event, public_url),
            "quotas": quota_status(event),
            "momo_ready": bool(profile and profile.momo_ready),
            "momo_label": profile.momo_label if profile else "Non renseigné",
            "controllers": controllers,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
@event_workspace_required
def event_guest_payments(request, event_id):
    from django.core.paginator import Paginator
    from django.db.models import Q

    event = get_user_event(request.user, event_id)
    profile = UserProfile.objects.filter(user=event.owner).first()
    success_qs = event.guest_payments.filter(status=GuestPayment.STATUS_SUCCESS)
    due_qs = success_qs.filter(
        payout_status__in=[GuestPayment.PAYOUT_PENDING, GuestPayment.PAYOUT_FAILED]
    )
    net_due = due_qs.aggregate(t=Sum("net_amount"))["t"] or 0

    if request.method == "POST" and request.POST.get("action") == "request_payout":
        if not profile or not profile.momo_ready:
            messages.error(
                request,
                "Confirmez d’abord votre numéro Mobile Money dans le profil.",
            )
            return redirect("event_guest_payments", event_id=event.pk)
        confirm = (request.POST.get("momo_confirm") or "").strip()
        if not phones_match(confirm, profile.momo_phone):
            messages.error(
                request,
                "Le numéro saisi ne correspond pas à votre numéro de remboursement confirmé.",
            )
            return redirect("event_guest_payments", event_id=event.pk)
        if not due_qs.exists():
            messages.info(request, "Aucun montant à reverser pour le moment.")
            return redirect("event_guest_payments", event_id=event.pk)
        now = timezone.now()
        updated = 0
        for payment in due_qs.iterator():
            meta = dict(payment.metadata or {})
            if meta.get("payout_requested_at"):
                continue
            meta["payout_requested_at"] = now.isoformat()
            meta["payout_request_phone"] = profile.momo_phone
            meta["payout_request_operator"] = profile.momo_operator
            payment.metadata = meta
            payment.save(update_fields=["metadata", "updated_at"])
            updated += 1
        if updated == 0:
            messages.info(request, "Une demande de reversement est déjà en cours.")
        else:
            AdminAuditLog.objects.create(
                actor=request.user,
                action=AdminAuditLog.ACTION_OTHER,
                target_type="event",
                target_id=str(event.pk),
                summary=f"Demande de reversement — {event.name}",
                details={
                    "net": str(net_due),
                    "payments": updated,
                    "momo": profile.momo_label,
                },
            )
            messages.success(
                request,
                f"Demande envoyée pour {net_due:.0f} F CFA vers {profile.momo_label}. "
                f"Reversement sous {SiteSettings.load().payout_sla_hours or 72}h ouvrées maximum.",
            )
        return redirect("event_guest_payments", event_id=event.pk)

    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "all").strip() or "all"
    payments = event.guest_payments.select_related("invitation").all()
    if status_filter in {
        GuestPayment.STATUS_SUCCESS,
        GuestPayment.STATUS_PENDING,
        GuestPayment.STATUS_FAILED,
    }:
        payments = payments.filter(status=status_filter)
    if q:
        payments = payments.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
            | Q(phone__icontains=q)
        )
    paginator = Paginator(payments.order_by("-created_at"), 40)
    page_obj = paginator.get_page(request.GET.get("page") or 1)
    due_list = list(due_qs.only("id", "metadata", "net_amount"))
    pending_unrequested = [
        p for p in due_list if not (p.metadata or {}).get("payout_requested_at")
    ]
    payout_requested = bool(due_list) and not pending_unrequested
    payout_partial = bool(pending_unrequested) and any(
        (p.metadata or {}).get("payout_requested_at") for p in due_list
    )
    site = SiteSettings.load()
    hours = site.payout_sla_hours or 72
    op_label = (
        profile.get_momo_operator_display()
        if profile and profile.momo_operator
        else "Mobile Money"
    )
    return render(
        request,
        "events/guest_payments.html",
        {
            "event": event,
            "nav_active": "ticketing" if event.is_ticketing else "invite",
            "payments": page_obj.object_list,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "q": q,
            "status_filter": status_filter,
            "gross": success_qs.aggregate(t=Sum("amount"))["t"] or 0,
            "commission": success_qs.aggregate(t=Sum("commission_amount"))["t"] or 0,
            "net": success_qs.aggregate(t=Sum("net_amount"))["t"] or 0,
            "net_due": net_due,
            "momo_ready": bool(profile and profile.momo_ready),
            "momo_label": profile.momo_label if profile else "Non renseigné",
            "momo_phone": profile.momo_phone if profile else "",
            "momo_operator_label": op_label,
            "payout_hours": hours,
            "commission_label": f"{(site.commission_pct or site.commission_regular_pct or 7):.0f}",
            "payout_requested": payout_requested,
            "payout_partial": payout_partial,
            "can_request_payout": bool(
                profile and profile.momo_ready and pending_unrequested
            ),
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
    if request.method == "POST" and request.POST.get("action") == "unlock":
        if try_unlock_invite(request, event, request.POST.get("invite_code") or ""):
            return redirect("public_invite", token=token)
        errors_gate = ["Code de validation incorrect."]
        return render(
            request,
            "public/invite_gate.html",
            {"event": event, "errors": errors_gate, **_legal_sheet_context()},
        )
    if not invite_code_unlocked(request, event):
        return render(
            request,
            "public/invite_gate.html",
            {"event": event, "errors": [], **_legal_sheet_context()},
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
                payload["amount"] = guest_price_for(
                    event, payload["participant_type"], payload.get("ticket_tier")
                )
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
            "tiers": list(event.ticket_tiers.filter(is_active=True)) if event.is_ticketing else [],
            **_legal_sheet_context(),
        },
    )


def _guest_invitation_from_session(request, event):
    code = (request.session.get("guest_invite_code") or "").strip()
    if not code:
        return None
    return Invitation.objects.filter(event=event, code=code).first()


def _norm_name(value: str) -> str:
    return " ".join((value or "").strip().casefold().split())


def _find_invitation_by_phone(
    event,
    phone: str,
    last_name: str = "",
    first_name: str = "",
):
    """Retrouve une invitation valide via téléphone + identité (nom/prénom obligatoires)."""
    from .identity import phone_digits_key

    key = phone_digits_key(phone)
    last = _norm_name(last_name)
    first = _norm_name(first_name)
    if not key or not last or not first:
        return None
    matches = []
    qs = (
        Invitation.objects.filter(event=event, status=Invitation.STATUS_VALID)
        .exclude(phone="")
        .order_by("-imported_at", "-id")
    )
    for inv in qs[:250]:
        if phone_digits_key(inv.phone) != key:
            continue
        if _norm_name(inv.last_name) != last:
            continue
        if _norm_name(inv.first_name) != first:
            continue
        matches.append(inv)
    if not matches:
        pays = (
            GuestPayment.objects.filter(
                event=event,
                status=GuestPayment.STATUS_SUCCESS,
                invitation__isnull=False,
            )
            .exclude(phone="")
            .select_related("invitation")
            .order_by("-paid_at", "-id")[:100]
        )
        for pay in pays:
            if phone_digits_key(pay.phone) != key:
                continue
            inv = pay.invitation
            if not inv or inv.status != Invitation.STATUS_VALID:
                continue
            pay_last = _norm_name(pay.last_name) or _norm_name(inv.last_name)
            pay_first = _norm_name(pay.first_name) or _norm_name(inv.first_name)
            if pay_last != last or pay_first != first:
                continue
            if inv not in matches:
                matches.append(inv)
    if not matches:
        return None
    if len(matches) > 1:
        return "ambiguous"
    return matches[0]


@require_http_methods(["GET", "POST"])
def public_ticket_recover(request, token):
    event = get_object_or_404(Event, invite_token=token)
    if event.needs_payment or event.status != Event.STATUS_ACTIVE:
        raise Http404()
    error = ""
    phone = ""
    last_name = ""
    first_name = ""
    if request.method == "POST":
        phone = (request.POST.get("phone") or "").strip()
        last_name = (request.POST.get("last_name") or "").strip()
        first_name = (request.POST.get("first_name") or "").strip()
        if not phone or not last_name or not first_name:
            error = "Téléphone, prénom et nom sont obligatoires pour vérifier que le billet vous appartient."
        else:
            found = _find_invitation_by_phone(event, phone, last_name, first_name)
            if found == "ambiguous":
                error = (
                    "Plusieurs billets correspondent à ces informations. "
                    "Contactez l’organisateur avec votre preuve d’achat."
                )
            elif not found:
                error = (
                    "Aucun billet trouvé. Vérifiez le téléphone, le prénom et le nom "
                    "exactement tels qu’à l’achat."
                )
            else:
                request.session["guest_invite_code"] = found.code
                messages.success(request, "Billet retrouvé. Vous pouvez le télécharger.")
                return redirect("public_invite_thanks", token=token)
    return render(
        request,
        "public/ticket_recover.html",
        {
            "event": event,
            "error": error,
            "phone": phone,
            "last_name": last_name,
            "first_name": first_name,
            **_legal_sheet_context(),
        },
    )


@require_GET
def public_invite_thanks(request, token):
    event = get_object_or_404(Event, invite_token=token)
    invitation = _guest_invitation_from_session(request, event)
    card_url = request.build_absolute_uri(reverse("public_invite_card", args=[token]))
    return render(
        request,
        "public/invite_thanks.html",
        {
            "event": event,
            "code": invitation.display_code if invitation else "",
            "invitation": invitation,
            "wa_share_href": guest_invite_href(invitation, card_url) if invitation else "",
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


@require_GET
def public_invite_reveal(request, token):
    event = get_object_or_404(Event, invite_token=token)
    invitation = _guest_invitation_from_session(request, event)
    if not invitation or not event.animated_card:
        raise Http404()
    from .constants import ceremony_settings

    return render(
        request,
        "invitation_reveal.html",
        {
            "invitation": invitation,
            "event": event,
            "ceremony": ceremony_settings(event),
            "reveal_continue": reverse("public_invite_thanks", args=[token]),
        },
    )


@login_required
@require_GET
@event_workspace_required
def guest_payment_invoice(request, event_id, payment_id):
    event = get_user_event(request.user, event_id)
    payment = get_object_or_404(GuestPayment, pk=payment_id, event=event)
    data = guest_payment_invoice_bytes(payment)
    return invoice_response(data, f"facture-invitation-{payment.pk:06d}.pdf")


@require_http_methods(["GET", "POST"])
def guest_mock_checkout(request, payment_id):
    from .siteconfig import mock_payments_allowed

    if not mock_payments_allowed():
        return HttpResponseForbidden("Paiement mock indisponible.")
    payment = get_object_or_404(GuestPayment.objects.select_related("event"), pk=payment_id)
    if request.method == "POST":
        payment = confirm_guest_payment_success(payment, provider_payload={"mock": True})
        request.session["guest_invite_code"] = (
            payment.invitation.code if payment.invitation_id else ""
        )
        return redirect("public_invite_thanks", token=payment.event.invite_token)
    extra = payment.extra_data or {}
    return render(
        request,
        "payments/guest_mock_checkout.html",
        {
            "payment": payment,
            "event": payment.event,
            "tier_name": extra.get("ticket_tier") or payment.get_participant_type_display(),
        },
    )


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
