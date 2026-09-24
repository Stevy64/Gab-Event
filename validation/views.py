"""
Vues HTTP — landing, auth, événements, API scan, espace utilisateur.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal

from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Q, Sum
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import (
    event_workspace_required,
    get_owned_invitation,
    get_user_event,
    is_platform_admin,
    user_events_qs,
)
from .event_lifecycle import (
    EventLifecycleError,
    apply_event_action,
    dismiss_delete_prompt,
    events_needing_delete_prompt,
    expire_due_events,
)
from .card_service import (
    build_invitations_zip,
    generate_invitation_card,
    invitation_filename,
)
from .constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP, ceremony_settings
from .flyer_service import process_flyer_image
from .forms import (
    CancelValidationForm,
    EventAppearanceForm,
    EventPlanSelectForm,
    EventSettingsForm,
    EventWizardStep1Form,
    EventWizardStep2Form,
    GabPasswordResetForm,
    GabSetPasswordForm,
    InvitationSearchForm,
    LoginForm,
    ProfileForm,
    SignUpForm,
)
from .models import Event, EventPlan, Invitation, Payment, UserProfile
from .payment_service import (
    activate_free_event,
    create_pending_payment,
    handle_provider_webhook,
    start_checkout,
    confirm_payment_success,
)
from . import singpay as singpay_api
from .qr_service import generate_invitation_qr, qr_png_bytes
from .quota_service import can_add_invitations, quota_status
from .list_pdf import export_guest_list_pdf_response
from .services import (
    admit_persons,
    cancel_validation,
    event_dashboard_stats,
    export_attendance_response,
    lookup_invitation,
    mark_invitation_sent,
    search_invitations,
)


@require_GET
def health(request):
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False
    return JsonResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "error",
            "service": "gabevent",
        },
        status=200 if db_ok else 503,
    )


def _parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


def _agent(request) -> str:
    if request.user.is_authenticated:
        return request.user.get_username()
    return ""


def _require_scanner_user(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "status": "error",
                "message": "Connectez-vous pour scanner les invitations.",
            },
            status=401,
        )
    return None


def _session_event(request) -> Event | None:
    eid = request.session.get("current_event_id")
    if not eid or not request.user.is_authenticated:
        return None
    event = user_events_qs(request.user).filter(pk=eid).first()
    if event and event.needs_payment:
        request.session.pop("current_event_id", None)
        return None
    return event


def _resolve_event_for_user(request, event_id=None) -> Event | None:
    if event_id:
        return get_user_event(request.user, event_id)
    event = _session_event(request)
    if event:
        return event
    return (
        user_events_qs(request.user)
        .filter(status=Event.STATUS_ACTIVE)
        .order_by("-created_at")
        .first()
    )


# ---------------------------------------------------------------------------
# Public / scan
# ---------------------------------------------------------------------------


def _landing_search_q(q: str) -> Q:
    query = (
        Q(name__icontains=q)
        | Q(city__icontains=q)
        | Q(venue__icontains=q)
        | Q(address__icontains=q)
        | Q(organizer_name__icontains=q)
        | Q(event_type_custom__icontains=q)
        | Q(description__icontains=q)
    )
    needle = q.casefold()
    for key, label in Event.TYPE_CHOICES:
        if needle in label.casefold() or needle in key:
            query |= Q(event_type=key)
    return query


def _public_search_card(event: Event, request) -> dict:
    own = bool(
        getattr(request, "user", None)
        and request.user.is_authenticated
        and event.owner_id == request.user.id
    )
    flyer = ""
    logo = ""
    try:
        if event.flyer:
            flyer = event.flyer.url
    except ValueError:
        flyer = ""
    try:
        if event.logo:
            logo = event.logo.url
    except ValueError:
        logo = ""
    return {
        "id": event.id,
        "name": event.name,
        "type": event.type_label,
        "type_key": event.event_type,
        "date": event.display_date() or "Date à confirmer",
        "time": event.display_time(),
        "venue": event.venue or "",
        "address": event.address or "",
        "city": event.city or "",
        "organizer": event.organizer_name or "",
        "description": (event.description or event.welcome_text or "").strip(),
        "color": event.display_primary_color,
        "flyer": flyer or event.cover_url,
        "logo": logo or event.logo_display_url,
        "own": own,
        "href": (
            reverse("event_payment", args=[event.id])
            if own and event.needs_payment
            else reverse("event_dashboard", args=[event.id])
            if own
            else ""
        ),
    }


def landing(request):
    from django.contrib.auth.models import User

    plans = EventPlan.objects.filter(is_active=True)
    q = (request.GET.get("q") or "").strip()
    search_results = []
    if q:
        qs = Event.objects.filter(status=Event.STATUS_ACTIVE).filter(
            _landing_search_q(q)
        )
        if request.user.is_authenticated:
            own = qs.filter(owner=request.user).select_related("owner")[:20]
            others = qs.exclude(owner=request.user).select_related("owner")[:10]
            search_results = list(own) + list(others)
        else:
            search_results = list(qs.select_related("owner")[:20])

    hero_stats = {
        "events": Event.objects.filter(status=Event.STATUS_ACTIVE).count(),
        "invitations": Invitation.objects.count(),
        "organizers": User.objects.filter(
            is_active=True, events__isnull=False
        )
        .distinct()
        .count(),
    }

    from .branding import gallery_slides

    # Carrousel : visuels Gab Event + flyers des événements opt-in
    carousel = gallery_slides()
    featured = (
        Event.objects.filter(
            status=Event.STATUS_ACTIVE,
            show_on_homepage=True,
        )
        .exclude(flyer="")
        .exclude(flyer__isnull=True)
        .order_by("-updated_at")[:12]
    )
    for ev in featured:
        try:
            carousel.append(
                {
                    "url": ev.flyer.url,
                    "label": ev.name,
                    "caption": ev.city or ev.venue or ev.type_label,
                }
            )
        except ValueError:
            continue

    carousel_json = json.dumps(
        [{"label": s["label"], "caption": s["caption"]} for s in carousel],
        ensure_ascii=False,
    )

    return render(
        request,
        "landing.html",
        {
            "plans": plans,
            "q": q,
            "search_results": search_results,
            "search_payload": [
                _public_search_card(ev, request) for ev in search_results
            ],
            "hero_stats": hero_stats,
            "carousel": carousel,
            "carousel_json": carousel_json,
        },
    )


@require_GET
def terms(request):
    return render(request, "public/terms.html")


@require_GET
def faq(request):
    from collections import OrderedDict

    from .models import FaqItem

    grouped = OrderedDict((label, []) for _key, label in FaqItem.SECTION_CHOICES)
    for item in FaqItem.objects.filter(is_active=True):
        grouped[item.get_section_display()].append(item)
    return render(
        request,
        "public/faq.html",
        {"faq_sections": [(label, items) for label, items in grouped.items() if items]},
    )


@ensure_csrf_cookie
def home(request):
    """Scanner / flyer — événement courant en session si défini."""
    can_scan = request.user.is_authenticated
    open_scanner = can_scan and request.GET.get("scan") == "1"
    event = None
    if can_scan:
        eid = request.GET.get("event")
        if eid:
            try:
                event = get_user_event(request.user, int(eid))
                if event.needs_payment:
                    return redirect("event_payment", event_id=event.pk)
                request.session["current_event_id"] = event.pk
            except Exception:  # noqa: BLE001
                event = _session_event(request)
        else:
            event = _session_event(request)
    ceremony = ceremony_settings(event)
    welcome = ceremony.get("welcome") or ""
    title = ceremony.get("title") or ""
    if re.sub(r"[^a-z0-9]+", "", welcome.casefold().replace("&", "et")) == re.sub(
        r"[^a-z0-9]+", "", title.casefold().replace("&", "et")
    ):
        ceremony["welcome"] = ""
    return render(
        request,
        "home.html",
        {
            "open_scanner": open_scanner,
            "can_scan": can_scan,
            "ceremony": ceremony,
            "event": event,
        },
    )


@require_GET
def service_worker(request):
    path = settings.BASE_DIR / "static" / "sw.js"
    response = FileResponse(path.open("rb"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


@require_GET
def brand_icon(request):
    """Favicon / pastille de marque : logo console, sinon pictogramme officiel."""
    from io import BytesIO

    from PIL import Image, ImageOps

    from .branding import render_default_mark
    from .models import SiteSettings

    try:
        size = int(request.GET.get("s", "192"))
    except (TypeError, ValueError):
        size = 192
    size = min(max(size, 16), 512)

    try:
        site = SiteSettings.objects.first()
        if site and site.logo:
            try:
                src = Image.open(site.logo.path).convert("RGBA")
                fitted = ImageOps.fit(src, (size, size), Image.Resampling.LANCZOS)
                buf = BytesIO()
                fitted.save(buf, format="PNG")
                response = HttpResponse(buf.getvalue(), content_type="image/png")
                response["Cache-Control"] = "public, max-age=3600"
                return response
            except Exception:
                try:
                    return redirect(site.logo.url)
                except ValueError:
                    pass
    except Exception:
        pass

    buf = BytesIO()
    render_default_mark(size).save(buf, format="PNG")
    response = HttpResponse(buf.getvalue(), content_type="image/png")
    response["Cache-Control"] = "public, max-age=86400"
    return response


@require_GET
def offline(request):
    return render(request, "offline.html", status=200)


@login_required
@ensure_csrf_cookie
def scanner(request):
    event_id = request.GET.get("event")
    if event_id:
        return redirect(f"{reverse('home')}?scan=1&event={event_id}")
    return redirect(f"{reverse('home')}?scan=1")


def _redirect_locked_event(event: Event | None):
    if event and event.needs_payment:
        return redirect("event_payment", event_id=event.pk)
    return None


def _resolve_scan_event(request, event_id=None) -> Event | None:
    """Événement obligatoire pour un scan contextualisé (payload puis session)."""
    if event_id not in (None, ""):
        try:
            return get_user_event(request.user, int(event_id))
        except Exception:  # noqa: BLE001
            return None
    return _session_event(request)


@require_POST
def api_validate(request):
    denied = _require_scanner_user(request)
    if denied:
        return denied
    content_type = request.content_type or ""
    if "application/json" in content_type:
        payload = _parse_json(request)
        if payload is None:
            return JsonResponse({"status": "error", "message": "JSON invalide."}, status=400)
        code = payload.get("code", "")
        event_id = payload.get("event_id")
    else:
        code = request.POST.get("code", "")
        event_id = request.POST.get("event_id")

    event = _resolve_scan_event(request, event_id)
    if event is None:
        return JsonResponse(
            {
                "status": "error",
                "message": "Ouvrez le scan depuis un événement pour valider ses invitations.",
            },
            status=400,
        )
    if event.needs_payment:
        return JsonResponse(
            {
                "status": "error",
                "message": "Paiement non finalisé : le scan est indisponible.",
            },
            status=403,
        )
    request.session["current_event_id"] = event.pk
    result = lookup_invitation(code, agent=_agent(request), event=event)
    status_code = 200
    if result.status == "invalid":
        status_code = 404
    elif result.status == "wrong_event":
        status_code = 409
    return JsonResponse(result.to_dict(), status=status_code)


@require_POST
def api_admit(request):
    denied = _require_scanner_user(request)
    if denied:
        return denied
    payload = _parse_json(request) if "application/json" in (request.content_type or "") else None
    if payload is None and "application/json" in (request.content_type or ""):
        return JsonResponse({"status": "error", "message": "JSON invalide."}, status=400)
    if payload is None:
        payload = {
            "code": request.POST.get("code", ""),
            "persons": request.POST.get("persons", 1),
            "event_id": request.POST.get("event_id"),
        }
    event = _resolve_scan_event(request, payload.get("event_id"))
    if event is None:
        return JsonResponse(
            {
                "status": "error",
                "message": "Ouvrez le scan depuis un événement pour valider ses invitations.",
            },
            status=400,
        )
    if event.needs_payment:
        return JsonResponse(
            {
                "status": "error",
                "message": "Paiement non finalisé : aucune entrée n’est possible.",
            },
            status=403,
        )
    request.session["current_event_id"] = event.pk
    result = admit_persons(payload.get("code", ""), 1, agent=_agent(request), event=event)
    http = 200
    if result.status == "invalid":
        http = 404
    elif result.status == "error":
        http = 400
    elif result.status in ("already_used", "wrong_event"):
        http = 409
    return JsonResponse(result.to_dict(), status=http)


# ---------------------------------------------------------------------------
# Auth / profil
# ---------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("my_events")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="validation.auth_backends.EmailPhoneUsernameBackend")
        messages.success(request, "Compte créé. Créez votre premier événement !")
        return redirect("event_create")
    return render(request, "registration/signup.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("my_events")
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(
            request,
            form.get_user(),
            backend="validation.auth_backends.EmailPhoneUsernameBackend",
        )
        next_url = request.GET.get("next") or request.POST.get("next") or ""
        if next_url.startswith("/"):
            return redirect(next_url)
        return redirect("my_events")
    return render(
        request,
        "registration/login.html",
        {"form": form, "next": request.GET.get("next", "")},
    )


def _reset_email_context():
    extra = {"site_name": "Gab Event"}
    base = getattr(settings, "PUBLIC_BASE_URL", "") or ""
    parsed = urlparse(base)
    if parsed.netloc:
        extra["domain"] = parsed.netloc
        extra["protocol"] = parsed.scheme or "https"
    return extra


class GabPasswordResetView(PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.txt"
    html_email_template_name = "registration/password_reset_email.html"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")
    form_class = GabPasswordResetForm
    extra_email_context = None

    def form_valid(self, form):
        self.extra_email_context = _reset_email_context()
        return super().form_valid(form)


class GabPasswordResetDoneView(PasswordResetDoneView):
    template_name = "registration/password_reset_done.html"


class GabPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")
    form_class = GabSetPasswordForm


class GabPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "registration/password_reset_complete.html"


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    profile_obj, _ = UserProfile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST or None, request.FILES or None, instance=profile_obj, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profil mis à jour.")
        return redirect("profile")
    events_qs = user_events_qs(request.user)
    return render(
        request,
        "profile.html",
        {
            "form": form,
            "profile": profile_obj,
            "events_count": events_qs.count(),
            "active_events": events_qs.filter(status=Event.STATUS_ACTIVE).count(),
        },
    )


# ---------------------------------------------------------------------------
# Mes événements + wizard
# ---------------------------------------------------------------------------


@login_required
@require_GET
def my_events(request):
    expire_due_events()
    q = (request.GET.get("q") or "").strip()
    events = (
        user_events_qs(request.user)
        .select_related("plan")
        .annotate(
            inv_total=Count("invitations"),
            inv_regular=Count(
                "invitations",
                filter=Q(invitations__participant_type=PARTICIPANT_RECIPIENT),
            ),
            inv_vip=Count(
                "invitations",
                filter=Q(invitations__participant_type=PARTICIPANT_VIP),
            ),
            present=Count(
                "invitations",
                filter=Q(invitations__places_used__gt=0),
            ),
        )
    )
    if q:
        events = events.filter(
            Q(name__icontains=q)
            | Q(city__icontains=q)
            | Q(venue__icontains=q)
            | Q(organizer_name__icontains=q)
            | Q(event_type_custom__icontains=q)
        )
    events = list(events)
    hour = timezone.localtime().hour
    raw_name = (request.user.first_name or "").strip()
    username = request.user.get_username()
    first_name = raw_name or ("" if "@" in username else username)
    scan_event = next((e for e in events if e.status == Event.STATUS_ACTIVE), None)
    delete_prompt = events_needing_delete_prompt(request.user).first()
    return render(
        request,
        "events/my_events.html",
        {
            "events": events,
            "q": q,
            "hello": "Bonsoir" if hour >= 18 or hour < 5 else "Bonjour",
            "first_name": first_name,
            "scan_event": scan_event,
            "delete_prompt": delete_prompt,
            "hub": {
                "events": len(events),
                "invitations": sum(getattr(e, "inv_total", 0) for e in events),
                "present": sum(getattr(e, "present", 0) for e in events),
            },
        },
    )


@login_required
@require_GET
def dashboard(request):
    """Compat : redirige vers le dashboard événement ou Mes événements."""
    event = _resolve_event_for_user(request)
    if event:
        return redirect("event_dashboard", event_id=event.pk)
    return redirect("my_events")


@login_required
@require_http_methods(["GET", "POST"])
def event_create(request):
    step = int(request.GET.get("step") or request.POST.get("step") or 1)
    wizard = request.session.get("event_wizard", {})

    if step == 1:
        pick = (request.GET.get("type") or "").strip()
        valid_types = {key for key, _label in Event.TYPE_CHOICES}
        if request.method == "GET" and pick in valid_types and pick != Event.TYPE_OTHER:
            wizard["event_type"] = pick
            wizard["event_type_custom"] = ""
            request.session["event_wizard"] = wizard
            return redirect(f"{reverse('event_create')}?step=2")

        initial = dict(wizard)
        if request.method == "GET":
            if pick == Event.TYPE_OTHER:
                initial["event_type"] = Event.TYPE_OTHER
            elif initial.get("event_type") == Event.TYPE_OTHER:
                initial.pop("event_type", None)
                initial.pop("event_type_custom", None)

        form = EventWizardStep1Form(
            request.POST or None,
            initial=initial if request.method == "GET" else None,
        )
        if request.method == "POST" and form.is_valid():
            wizard["event_type"] = form.cleaned_data["event_type"]
            wizard["event_type_custom"] = form.cleaned_data.get("event_type_custom") or ""
            request.session["event_wizard"] = wizard
            return redirect(f"{reverse('event_create')}?step=2")
        return render(request, "events/wizard_type.html", {"form": form, "step": 1})

    if step == 2:
        if "event_type" not in wizard:
            return redirect("event_create")
        form = EventWizardStep2Form(request.POST or None, initial=wizard)
        if request.method == "POST" and form.is_valid():
            wizard.update({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in form.cleaned_data.items()})
            request.session["event_wizard"] = wizard
            return redirect("event_plans")
        return render(request, "events/wizard_info.html", {"form": form, "step": 2})

    return redirect("event_create")


@login_required
@require_http_methods(["GET", "POST"])
def event_plans(request):
    wizard = request.session.get("event_wizard") or {}
    if "name" not in wizard:
        return redirect("event_create")
    expected = int(wizard.get("expected_guests") or 50)
    plans = EventPlan.objects.filter(is_active=True)
    # Mettre en avant les plans capables d'accueillir expected
    form = EventPlanSelectForm(request.POST or None)
    form.fields["plan"].queryset = plans
    if request.method == "POST" and form.is_valid():
        plan = form.cleaned_data["plan"]
        if not plan.covers_guest_count(expected):
            messages.error(
                request,
                f"« {plan.name} » accepte jusqu’à {plan.potential_total} personnes, "
                f"alors que vous avez indiqué ≈ {expected} invités. "
                "Choisissez une formule supérieure ou modifiez le nombre à l’étape Infos.",
            )
            return redirect("event_plans")
        from datetime import date as date_cls, time as time_cls

        def _parse_date(v):
            if not v:
                return None
            if hasattr(v, "year"):
                return v
            return date_cls.fromisoformat(str(v))

        def _parse_time(v):
            if not v:
                return None
            if hasattr(v, "hour"):
                return v
            return time_cls.fromisoformat(str(v))

        from .branding import DEFAULT_PRIMARY_COLOR

        event = Event(
            owner=request.user,
            plan=plan,
            name=wizard["name"],
            event_type=wizard.get("event_type") or Event.TYPE_OTHER,
            event_type_custom=wizard.get("event_type_custom") or "",
            description=wizard.get("description") or "",
            date=_parse_date(wizard.get("date")),
            start_time=_parse_time(wizard.get("start_time")),
            venue=wizard.get("venue") or "",
            organizer_name=request.user.get_full_name() or request.user.username,
            primary_color=DEFAULT_PRIMARY_COLOR,
        )
        if plan.is_custom:
            event.validity_starts_on = form.cleaned_data.get("validity_starts_on")
            event.validity_ends_on = form.cleaned_data.get("validity_ends_on")
        # Préfixe legacy réservé
        event.save()
        event.apply_lifetime(
            starts=event.validity_starts_on,
            ends=event.validity_ends_on,
        )
        event.save(
            update_fields=[
                "validity_starts_on",
                "validity_ends_on",
                "expires_at",
                "invite_valid_from",
                "invite_valid_until",
                "updated_at",
            ]
        )
        if event.code_prefix == "ATC24" and Event.objects.filter(code_prefix="ATC24").exclude(pk=event.pk).exists():
            event.code_prefix = ""
            event.save()

        request.session.pop("event_wizard", None)

        if plan.is_free or plan.is_custom or Decimal(plan.price) <= 0:
            activate_free_event(event, plan)
            if plan.is_custom:
                messages.success(
                    request,
                    "Événement créé. Définissez les tarifs invités puis mettez le lien en ligne.",
                )
            else:
                messages.success(request, "Événement créé et activé (formule gratuite).")
            return redirect("event_invite_link", event_id=event.pk)

        event.apply_plan_snapshot(plan)
        event.status = Event.STATUS_PENDING_PAYMENT
        event.save()
        payment = create_pending_payment(user=request.user, event=event, plan=plan)
        try:
            intent = start_checkout(payment)
        except RuntimeError as exc:
            messages.error(request, str(exc))
            return redirect("event_payment", event_id=event.pk)
        return redirect(intent.checkout_url)

    return render(
        request,
        "events/plans.html",
        {"plans": plans, "form": form, "expected": expected, "wizard": wizard},
    )


# ---------------------------------------------------------------------------
# Paiement
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def mock_payment_checkout(request, payment_id):
    if not (settings.DEBUG and getattr(settings, "ALLOW_MOCK_PAYMENTS", False)):
        return HttpResponseForbidden("Paiement mock indisponible.")
    payment = get_object_or_404(
        Payment.objects.select_related("event", "plan"),
        pk=payment_id,
        user=request.user,
    )
    if request.method == "POST":
        confirm_payment_success(payment, provider_payload={"mock": True}, actor=request.user)
        messages.success(request, "Paiement confirmé. Événement activé.")
        return redirect("event_settings", event_id=payment.event_id)
    return render(request, "payments/mock_checkout.html", {"payment": payment})


@login_required
@require_GET
def singpay_return(request, payment_id):
    payment = get_object_or_404(
        Payment.objects.select_related("event"),
        pk=payment_id,
        user=request.user,
    )
    if payment.status == Payment.STATUS_SUCCESS:
        messages.success(request, "Paiement confirmé. Événement activé.")
        return redirect("event_dashboard", event_id=payment.event_id)

    meta = (payment.metadata or {}).get("singpay") or {}
    txn_id = meta.get("transaction_id") or payment.provider_reference
    failed = (request.GET.get("status") or "").lower() == "error"
    ok, payload = singpay_api.verify_transaction(txn_id)
    if ok and payload.get("success"):
        confirm_payment_success(payment, provider_payload=payload, actor=request.user)
        messages.success(request, "Paiement SingPay confirmé. Événement activé.")
        return redirect("event_dashboard", event_id=payment.event_id)
    if failed or (ok and not payload.get("success")):
        messages.error(request, "Le paiement n’a pas abouti. Vous pouvez réessayer ou supprimer l’événement.")
    else:
        messages.info(request, "Paiement en cours de confirmation. Actualisez dans un instant.")
    return redirect("event_payment", event_id=payment.event_id)


@csrf_exempt
@require_POST
def payment_webhook(request, provider: str = "mock"):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "json"}, status=400)
    try:
        payment = handle_provider_webhook(provider, payload)
    except RuntimeError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=403)
    if payment is None:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)
    return JsonResponse({"ok": True, "status": payment.status, "payment_id": payment.pk})


# ---------------------------------------------------------------------------
# Dashboard événement
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def event_payment(request, event_id):
    """Seul point d'entrée d'un événement payant en attente de paiement."""
    event = get_user_event(request.user, event_id)
    if not event.needs_payment:
        return redirect("event_dashboard", event_id=event.pk)

    payment = (
        Payment.objects.filter(event=event, user=request.user)
        .select_related("plan")
        .order_by("-created_at")
        .first()
    )
    if request.method == "POST" and request.POST.get("action") == "pay":
        plan = event.plan
        if plan is None:
            messages.error(request, "Aucune formule n’est associée à cet événement.")
            return redirect("event_payment", event_id=event.pk)
        if (
            payment is None
            or payment.status == Payment.STATUS_SUCCESS
            or payment.status == Payment.STATUS_FAILED
        ):
            payment = create_pending_payment(user=request.user, event=event, plan=plan)
        try:
            intent = start_checkout(payment)
        except RuntimeError as exc:
            messages.error(request, str(exc))
            return redirect("event_payment", event_id=event.pk)
        return redirect(intent.checkout_url)

    return render(
        request,
        "events/payment_required.html",
        {
            "event": event,
            "payment": payment,
            "plan": event.plan,
        },
    )


@login_required
@require_GET
@event_workspace_required
def event_dashboard(request, event_id):
    expire_due_events()
    event = get_user_event(request.user, event_id)
    request.session["current_event_id"] = event.pk
    stats = event_dashboard_stats(event)
    return render(
        request,
        "events/dashboard.html",
        {
            "event": event,
            "stats": stats,
            "nav_active": "overview",
            "quotas": stats["quotas"],
        },
    )


@login_required
@require_GET
@event_workspace_required
def event_guests(request, event_id):
    event = get_user_event(request.user, event_id)
    form = InvitationSearchForm(request.GET or None)
    type_filter = request.GET.get("type", "all")
    status_filter = request.GET.get("status", "all")
    qs = Invitation.objects.filter(event=event)
    if type_filter == "RECIPIENT":
        qs = qs.filter(participant_type=PARTICIPANT_RECIPIENT)
    elif type_filter == "VIP":
        qs = qs.filter(participant_type=PARTICIPANT_VIP)
    if status_filter == "present":
        qs = qs.filter(places_used__gt=0)
    elif status_filter == "pending":
        qs = qs.filter(places_used=0)
    query = ""
    if form.is_valid():
        query = form.cleaned_data.get("q", "")
        if query:
            qs = search_invitations(query, event=event)
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "events/guests.html",
        {
            "event": event,
            "guests": page,
            "form": form,
            "query": query,
            "type_filter": type_filter,
            "status_filter": status_filter,
            "nav_active": "guests",
            "quotas": quota_status(event),
        },
    )


@login_required
@require_GET
@event_workspace_required
def event_invitations(request, event_id):
    event = get_user_event(request.user, event_id)
    form = InvitationSearchForm(request.GET or None)
    type_filter = request.GET.get("type", "all")
    qs = Invitation.objects.filter(event=event).order_by("last_name", "first_name", "id")
    if type_filter == "RECIPIENT":
        qs = qs.filter(participant_type=PARTICIPANT_RECIPIENT)
    elif type_filter == "VIP":
        qs = qs.filter(participant_type=PARTICIPANT_VIP)
    query = ""
    if form.is_valid():
        query = form.cleaned_data.get("q", "")
        if query:
            qs = qs.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(code__icontains=query)
                | Q(category__icontains=query)
            )
    total = qs.count()
    paginator = Paginator(qs, 40)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "events/invitations.html",
        {
            "event": event,
            "invitations": page,
            "total_count": total,
            "query": query,
            "type_filter": type_filter,
            "nav_active": "invitations",
            "quotas": quota_status(event),
        },
    )


@login_required
@require_GET
@event_workspace_required
def event_presence(request, event_id):
    event = get_user_event(request.user, event_id)
    stats = event_dashboard_stats(event)
    return render(
        request,
        "events/presence.html",
        {"event": event, "stats": stats, "nav_active": "presence"},
    )


@login_required
@require_http_methods(["GET", "POST"])
@event_workspace_required
def event_appearance(request, event_id):
    event = get_user_event(request.user, event_id)
    form = EventAppearanceForm(request.POST or None, request.FILES or None, instance=event)
    if request.method == "POST":
        if form.is_valid():
            obj = form.save(commit=False)
            uploaded = request.FILES.get("flyer")
            if uploaded:
                try:
                    content = process_flyer_image(uploaded)
                    obj.flyer.save(content.name, content, save=False)
                except Exception as exc:  # noqa: BLE001
                    messages.error(request, str(exc))
                    return render(
                        request,
                        "events/appearance.html",
                        {"event": event, "form": form, "nav_active": "appearance"},
                    )
            obj.save()
            form.save_m2m()
            messages.success(request, "Apparence enregistrée.")
            return redirect("event_appearance", event_id=event.pk)
        messages.error(request, "Impossible d’enregistrer l’apparence. Vérifiez les champs.")
    return render(
        request,
        "events/appearance.html",
        {"event": event, "form": form, "nav_active": "appearance"},
    )


@login_required
@require_http_methods(["GET", "POST"])
@event_workspace_required
def event_settings(request, event_id):
    event = get_user_event(request.user, event_id)
    form = EventSettingsForm(request.POST or None, instance=event)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Paramètres enregistrés.")
            return redirect("event_settings", event_id=event.pk)
        messages.error(request, "Certains champs sont invalides. Vérifiez la date et les horaires.")
    return render(
        request,
        "events/settings.html",
        {
            "event": event,
            "form": form,
            "nav_active": "settings",
            "quotas": quota_status(event),
        },
    )


@login_required
@require_POST
def event_status(request, event_id):
    event = get_user_event(request.user, event_id)
    action = (request.POST.get("action") or "").strip()
    nxt = request.POST.get("next") or ""
    if not (nxt.startswith("/") and not nxt.startswith("//")):
        nxt = "my_events"
    try:
        message = apply_event_action(event, action)
    except EventLifecycleError as exc:
        messages.error(request, str(exc))
        return redirect(nxt)
    messages.success(request, message)
    if action == "delete":
        request.session.pop("current_event_id", None)
        return redirect("my_events")
    return redirect(nxt)


@login_required
@require_POST
def event_delete(request, event_id):
    event = get_user_event(request.user, event_id)
    try:
        message = apply_event_action(event, "delete")
    except EventLifecycleError as exc:
        messages.error(request, str(exc))
        return redirect("my_events")
    request.session.pop("current_event_id", None)
    messages.success(request, message)
    return redirect("my_events")


@login_required
@require_POST
def event_keep(request, event_id):
    event = get_user_event(request.user, event_id)
    dismiss_delete_prompt(event)
    messages.info(
        request,
        "L’événement est conservé. Vous pourrez le supprimer depuis les paramètres.",
    )
    return redirect("my_events")


@login_required
@require_http_methods(["GET", "POST"])
@event_workspace_required
def event_import(request, event_id):
    """L’import Excel est retiré : les quotas ne doivent pas être contournés."""
    event = get_user_event(request.user, event_id)
    messages.info(
        request,
        "L’ajout d’invités par fichier n’est plus possible. "
        "Partagez le lien d’invitation. Vous pouvez toujours télécharger la liste (Excel ou PDF).",
    )
    return redirect("event_guests", event_id=event.pk)


@login_required
@require_GET
@event_workspace_required
def event_export(request, event_id):
    event = get_user_event(request.user, event_id)
    fmt = (request.GET.get("fmt") or "xlsx").lower()
    if fmt == "pdf":
        return export_guest_list_pdf_response(event)
    return export_attendance_response(
        filename=f"liste_{event.slug}.xlsx",
        event=event,
    )


@login_required
@require_POST
@event_workspace_required
def event_generate_all(request, event_id):
    event = get_user_event(request.user, event_id)
    ids = [pk for pk in request.POST.getlist("ids") if str(pk).isdigit()]
    select_all = request.POST.get("select_all") == "1"
    type_filter = request.POST.get("type") or None
    query = (request.POST.get("q") or "").strip()
    qs = Invitation.objects.filter(event=event)
    if type_filter in (PARTICIPANT_RECIPIENT, PARTICIPANT_VIP):
        qs = qs.filter(participant_type=type_filter)
    if query:
        qs = qs.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(code__icontains=query)
            | Q(category__icontains=query)
        )
    if not select_all:
        qs = qs.filter(pk__in=ids)
    if not qs.exists():
        messages.error(request, "Sélectionnez au moins une carte à télécharger.")
        return redirect("event_invitations", event_id=event.pk)
    data, _summary = build_invitations_zip(qs)
    for inv in qs.iterator():
        generate_invitation_qr(inv)
    response = HttpResponse(data, content_type="application/zip")
    response["Content-Disposition"] = (
        f'attachment; filename="cartes_{event.slug}_{qs.count()}.zip"'
    )
    return response


# ---------------------------------------------------------------------------
# Compat routes globales (scopées à l'événement courant)
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def import_excel(request):
    event = _resolve_event_for_user(request)
    if not event:
        return redirect("my_events")
    return event_import(request, event.pk)


@login_required
@require_GET
def export_report(request):
    event = _resolve_event_for_user(request)
    if not event:
        return redirect("my_events")
    return event_export(request, event.pk)


@login_required
@require_http_methods(["GET", "POST"])
def invitation_detail(request, pk):
    invitation = get_owned_invitation(request.user, pk)
    locked = _redirect_locked_event(invitation.event)
    if locked:
        return locked
    form = CancelValidationForm()
    if request.method == "POST":
        action = request.POST.get("action", "cancel")
        if action == "mark_sent":
            mark_invitation_sent(invitation, True)
            messages.success(request, "Invitation marquée comme envoyée.")
            return redirect("invitation_detail", pk=invitation.pk)
        if action == "unmark_sent":
            mark_invitation_sent(invitation, False)
            messages.success(request, "Statut « envoyée » annulé.")
            return redirect("invitation_detail", pk=invitation.pk)
        form = CancelValidationForm(request.POST)
        if form.is_valid() and invitation.places_used > 0:
            cancel_validation(invitation)
            messages.success(request, f"Entrées annulées pour {invitation.full_name}.")
            return redirect("invitation_detail", pk=invitation.pk)
    logs = invitation.scan_logs.all()[:20]
    admissions = invitation.admissions.filter(is_cancelled=False)[:20]
    return render(
        request,
        "invitation_detail.html",
        {
            "invitation": invitation,
            "form": form,
            "logs": logs,
            "admissions": admissions,
            "ceremony": ceremony_settings(invitation.event),
            "event": invitation.event,
        },
    )


@login_required
@require_GET
def invitation_preview(request, pk):
    invitation = get_owned_invitation(request.user, pk)
    locked = _redirect_locked_event(invitation.event)
    if locked:
        return locked
    return render(
        request,
        "invitation_preview.html",
        {
            "invitation": invitation,
            "ceremony": ceremony_settings(invitation.event),
            "event": invitation.event,
        },
    )


@login_required
@require_GET
def invitation_download(request, pk):
    invitation = get_owned_invitation(request.user, pk)
    locked = _redirect_locked_event(invitation.event)
    if locked:
        return locked
    generate_invitation_qr(invitation)
    data, _ = generate_invitation_card(invitation, save=True)
    fmt = (request.GET.get("fmt") or "png").lower()
    if fmt == "pdf":
        from .card_service import invitation_pdf_bytes, invitation_pdf_filename

        response = HttpResponse(invitation_pdf_bytes(data), content_type="application/pdf")
        if request.GET.get("inline") != "1":
            response["Content-Disposition"] = (
                f'attachment; filename="{invitation_pdf_filename(invitation)}"'
            )
        return response
    response = HttpResponse(data, content_type="image/png")
    if request.GET.get("inline") != "1":
        response["Content-Disposition"] = (
            f'attachment; filename="{invitation_filename(invitation)}"'
        )
    return response


@login_required
@require_GET
def invitation_qr_download(request, pk):
    invitation = get_owned_invitation(request.user, pk)
    locked = _redirect_locked_event(invitation.event)
    if locked:
        return locked
    data = qr_png_bytes(invitation.code)
    response = HttpResponse(data, content_type="image/png")
    response["Content-Disposition"] = f'attachment; filename="{invitation.code}.png"'
    return response


@login_required
@require_POST
def generate_all_invitations(request):
    event = _resolve_event_for_user(request)
    if not event:
        return redirect("my_events")
    return event_generate_all(request, event.pk)


@login_required
@require_GET
def search_page(request):
    event = _resolve_event_for_user(request)
    form = InvitationSearchForm(request.GET or None)
    results = []
    query = ""
    if form.is_valid():
        query = form.cleaned_data.get("q", "")
        if query:
            results = list(search_invitations(query, event=event)[:50])
    return render(
        request,
        "search.html",
        {"form": form, "results": results, "query": query, "event": event},
    )
