"""
Billetterie publique, contrôleurs et page Événements.

Ce module isole le parcours « ventes de billets » (hub, configuration, tableau de bord)
du parcours invitations classiques. Les simulations de paiement ne sont disponibles
que lorsque ``mock_payments_allowed()`` est vrai (DEBUG + config site).
"""
from __future__ import annotations

import secrets
from datetime import date, time
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .access import (
    event_workspace_required,
    get_user_event,
    grant_controller_session,
)
from .forms import _clean_momo
from .invite_form import ensure_invite_token
from .models import (
    Event,
    EventCategory,
    EventController,
    EventPlan,
    GuestPayment,
    Invitation,
    TicketTier,
    UserProfile,
    public_tier_name,
)
from .payment_service import (
    activate_free_event,
    confirm_guest_payment_success,
    create_guest_payment,
)
from .quota_service import quota_status
from .siteconfig import mock_payments_allowed


PUBLIC_GROUPS = (
    ("all", "Tous"),
    ("concert", "Concert"),
    ("mariage", "Mariage"),
    ("autres", "Autres"),
)


def _public_events_qs():
    """Événements visibles sur l’agenda : publics, homepage, ou billetterie (ouverte ou déjà publiée puis fermée)."""
    return (
        Event.objects.filter(status=Event.STATUS_ACTIVE)
        .filter(
            Q(is_ticketing=True, invite_link_enabled=True)
            | Q(is_ticketing=True, invite_published_at__isnull=False)
            | Q(is_public=True)
            | Q(show_on_homepage=True)
        )
        .select_related("owner", "plan")
        .prefetch_related("ticket_tiers")
    )


def _agenda_sale_state(event: Event) -> dict:
    """État vente / échéance pour la bottom sheet agenda."""
    from django.utils import timezone as dj_tz

    ended = False
    iso = event.starts_at_iso()
    if iso:
        try:
            from datetime import datetime

            start = datetime.fromisoformat(iso)
            if dj_tz.is_naive(start):
                start = dj_tz.make_aware(start, dj_tz.get_current_timezone())
            ended = start <= dj_tz.now()
        except ValueError:
            ended = False
    closed = bool(
        event.is_ticketing
        and not event.invite_link_enabled
        and event.invite_published_at is not None
    )
    if ended:
        status = "ended"
        status_label = "Événement terminé"
    elif closed:
        status = "closed"
        status_label = "Billetterie fermée"
    else:
        status = "open"
        status_label = ""
    return {
        "sale_status": status,
        "sale_status_label": status_label,
        "tickets_open": bool(event.is_ticketing and event.invite_link_enabled and not ended),
    }


def _agenda_card(event: Event, request) -> dict:
    ensure_invite_token(event)
    flyer = event.cover_url
    logo = event.logo_display_url
    try:
        if event.flyer:
            flyer = event.flyer.url
    except ValueError:
        pass
    try:
        if event.logo:
            logo = event.logo.url
    except ValueError:
        pass
    sale = _agenda_sale_state(event)
    buy = ""
    if sale["tickets_open"] and event.invite_token:
        buy = request.build_absolute_uri(reverse("public_invite", args=[event.invite_token]))
    tiers = []
    for tier in event.ticket_tiers.all():
        if not tier.is_active:
            continue
        tiers.append(
            {
                "name": tier.public_name,
                "price": f"{tier.price:.0f}",
                "sold_out": tier.sold_out,
                "remaining": tier.remaining,
                "description": tier.description or "",
            }
        )
    cheapest = event.cheapest_ticket_price
    own = bool(
        getattr(request, "user", None)
        and request.user.is_authenticated
        and event.owner_id == request.user.id
    )
    return {
        "id": event.id,
        "name": event.name,
        "type": event.type_label,
        "type_key": event.event_type or "other",
        "date": event.display_date() or "Date à confirmer",
        "date_long": event.display_date_long() or "Date à confirmer",
        "time": event.display_time(),
        "starts_at": event.starts_at_iso(),
        "venue": event.venue or "",
        "address": event.address or "",
        "city": event.city or "",
        "organizer": event.organizer_name or "",
        "description": (event.description or event.welcome_text or "").strip(),
        "color": event.display_primary_color,
        "flyer": flyer,
        "logo": logo,
        "own": own,
        "href": reverse("event_dashboard", args=[event.id]) if own else "",
        "slug": event.slug,
        "buy": buy,
        "recover": request.build_absolute_uri(
            reverse("public_ticket_recover", args=[event.invite_token])
        )
        if event.invite_token
        else "",
        "is_ticketing": bool(event.is_ticketing),
        "price": f"{cheapest:.0f}" if cheapest is not None else "",
        "tiers": tiers,
        "cta": "Acheter un billet" if event.is_ticketing else "S’inscrire",
        "sale_status": sale["sale_status"],
        "sale_status_label": sale["sale_status_label"],
        "tickets_open": sale["tickets_open"],
    }


def public_events(request):
    q = (request.GET.get("q") or "").strip()
    group = (request.GET.get("cat") or "all").strip() or "all"
    qs = _public_events_qs()
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(venue__icontains=q)
            | Q(city__icontains=q)
            | Q(description__icontains=q)
            | Q(organizer_name__icontains=q)
        )
    grouped = {"concert": [], "mariage": [], "autres": []}
    for event in qs.order_by("date", "name"):
        grouped[event.public_category_group()].append(event)
    if group in grouped:
        visible = grouped[group]
    else:
        visible = grouped["concert"] + grouped["mariage"] + grouped["autres"]
        group = "all"
    groups = [
        ("all", "Tous", sum(len(items) for items in grouped.values())),
        ("concert", "Concert", len(grouped["concert"])),
        ("mariage", "Mariage", len(grouped["mariage"])),
        ("autres", "Autres", len(grouped["autres"])),
    ]
    return render(
        request,
        "public/events.html",
        {
            "q": q,
            "cat": group,
            "groups": groups,
            "events": visible,
            "grouped": grouped,
            "agenda_payload": [_agenda_card(event, request) for event in visible],
        },
    )


def public_event_detail(request, slug):
    event = get_object_or_404(_public_events_qs(), slug=slug)
    ensure_invite_token(event)
    tiers = list(event.ticket_tiers.filter(is_active=True))
    public_url = ""
    if event.invite_token:
        public_url = request.build_absolute_uri(reverse("public_invite", args=[event.invite_token]))
    return render(
        request,
        "public/event_detail.html",
        {
            "event": event,
            "tiers": tiers,
            "buy_url": public_url,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def ticketing_hub(request):
    """Liste des événements billetterie de l’organisateur connecté."""
    collected_sq = (
        GuestPayment.objects.filter(
            event_id=OuterRef("pk"),
            status=GuestPayment.STATUS_SUCCESS,
        )
        .values("event_id")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )
    events = (
        Event.objects.filter(owner=request.user, is_ticketing=True)
        .exclude(status__in=[Event.STATUS_ARCHIVED, Event.STATUS_CANCELLED])
        .prefetch_related("ticket_tiers")
        .annotate(
            sold=Count(
                "invitations",
                filter=Q(invitations__status=Invitation.STATUS_VALID),
                distinct=True,
            ),
            collected=Coalesce(
                Subquery(
                    collected_sq,
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Value(Decimal("0"), output_field=DecimalField(max_digits=12, decimal_places=2)),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )
    )
    return render(
        request,
        "ticketing/hub.html",
        {"events": events, "nav_active": "hub"},
    )


def _ticketing_plan() -> EventPlan:
    plan, _ = EventPlan.objects.get_or_create(
        slug="personnalise",
        defaults={
            "name": "Vendre vos billets",
            "description": "Billetterie publique. Commission 7 % par billet.",
            "is_custom": True,
            "is_active": True,
            "is_free": False,
            "currency": "XOF",
            "display_order": 5,
        },
    )
    if plan.name != "Vendre vos billets":
        plan.name = "Vendre vos billets"
        plan.is_custom = True
        plan.is_active = True
        plan.save(update_fields=["name", "is_custom", "is_active", "updated_at"])
    return plan


def _parse_date(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _parse_time(raw):
    if not raw:
        return None
    try:
        return time.fromisoformat(str(raw))
    except ValueError:
        return None


def _parse_money(raw) -> Decimal:
    try:
        return Decimal(str(raw or "0").replace(" ", "").replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _ticketing_setup_errors(post, files, event=None) -> list[str]:
    errors = []
    if not (post.get("name") or "").strip():
        errors.append("Indiquez le nom de l’événement.")
    if not (post.get("organizer_name") or "").strip():
        errors.append("Indiquez qui organise l’événement (Organisé par).")
    if not (post.get("description") or "").strip():
        errors.append("Ajoutez les détails / la description de l’événement.")
    if not (post.get("venue") or "").strip():
        errors.append("Indiquez le lieu.")
    if not _parse_date(post.get("date")):
        errors.append("Indiquez la date.")
    if not _parse_time(post.get("start_time")):
        errors.append("Indiquez l’heure.")
    has_flyer = bool(files.get("flyer"))
    if event is not None:
        try:
            has_flyer = has_flyer or bool(event.flyer)
        except ValueError:
            pass
    if not has_flyer:
        errors.append("Ajoutez une affiche ou une image.")
    return errors


def _ticketing_publish_errors(event: Event) -> list[str]:
    missing = []
    if not event.name:
        missing.append("nom")
    if not (event.organizer_name or "").strip():
        missing.append("organisé par")
    if not (event.description or "").strip():
        missing.append("description")
    if not (event.venue or "").strip():
        missing.append("lieu")
    if not event.date:
        missing.append("date")
    if not event.start_time:
        missing.append("heure")
    has_flyer = False
    try:
        has_flyer = bool(event.flyer)
    except ValueError:
        has_flyer = False
    if not has_flyer:
        missing.append("affiche")
    if missing:
        return [f"Complétez la fiche avant publication : {', '.join(missing)}."]
    return []


def _save_tiers(event: Event, post) -> int:
    names = post.getlist("tier_name")
    prices = post.getlist("tier_price")
    qtys = post.getlist("tier_qty")
    descs = post.getlist("tier_desc")
    kept = 0
    existing = list(event.ticket_tiers.all())
    for i, name in enumerate(names):
        label = (name or "").strip()
        if not label:
            continue
        price = _parse_money(prices[i] if i < len(prices) else 0)
        qty = 0
        try:
            qty = max(0, int(qtys[i] if i < len(qtys) else 0 or 0))
        except (TypeError, ValueError):
            qty = 0
        desc = (descs[i] if i < len(descs) else "") or ""
        if i < len(existing):
            tier = existing[i]
            tier.name = label
            tier.price = price
            tier.quantity = qty
            tier.description = desc[:200]
            tier.display_order = i
            tier.is_active = True
            tier.save()
        else:
            TicketTier.objects.create(
                event=event,
                name=label,
                price=price,
                quantity=qty,
                description=desc[:200],
                display_order=i,
            )
        kept += 1
    for extra in existing[kept:]:
        extra.is_active = False
        extra.save(update_fields=["is_active", "updated_at"])
    return kept


@login_required
@require_http_methods(["GET", "POST"])
def ticketing_setup(request, event_id=None):
    event = None
    if event_id:
        event = get_user_event(request.user, event_id)
        if not event.is_ticketing:
            event.is_ticketing = True
            event.save(update_fields=["is_ticketing", "updated_at"])
    wizard = request.session.get("event_wizard") or {}
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        errors = _ticketing_setup_errors(request.POST, request.FILES, event=event)
        if errors:
            for err in errors:
                messages.error(request, err)
            initial = {
                "name": name,
                "organizer_name": (request.POST.get("organizer_name") or "").strip(),
                "event_type": request.POST.get("event_type") or Event.TYPE_CONCERT,
                "event_type_custom": (request.POST.get("event_type_custom") or "").strip(),
                "description": (request.POST.get("description") or "").strip(),
                "date": request.POST.get("date") or "",
                "start_time": request.POST.get("start_time") or "",
                "end_time": request.POST.get("end_time") or "",
                "venue": (request.POST.get("venue") or "").strip(),
                "city": (request.POST.get("city") or "").strip(),
                "address": (request.POST.get("address") or "").strip(),
            }
            posted_names = request.POST.getlist("tier_name")
            if posted_names:
                tiers = []
                prices = request.POST.getlist("tier_price")
                qtys = request.POST.getlist("tier_qty")
                descs = request.POST.getlist("tier_desc")
                for i, label in enumerate(posted_names):
                    tiers.append(
                        TicketTier(
                            name=label or "Standard",
                            price=_parse_money(prices[i] if i < len(prices) else 0),
                            quantity=int(qtys[i] or 0) if i < len(qtys) and str(qtys[i]).isdigit() else 0,
                            description=(descs[i] if i < len(descs) else "") or "",
                        )
                    )
            else:
                tiers = [
                    TicketTier(name="Standard", price=Decimal("5000"), quantity=0),
                    TicketTier(name="VIP", price=Decimal("10000"), quantity=0),
                ]
            return render(
                request,
                "ticketing/setup.html",
                {
                    "event": event,
                    "initial": initial,
                    "tiers": tiers,
                    "categories": EventCategory.objects.filter(is_active=True),
                    "nav_active": "create",
                },
            )
        plan = _ticketing_plan()
        organizer = (request.POST.get("organizer_name") or "").strip()
        if event is None:
            event = Event(
                owner=request.user,
                plan=plan,
                name=name,
                is_ticketing=True,
                organizer_name=organizer,
            )
        event.plan = plan
        event.name = name
        event.organizer_name = organizer
        event.event_type = request.POST.get("event_type") or Event.TYPE_CONCERT
        event.event_type_custom = (request.POST.get("event_type_custom") or "").strip()
        event.description = (request.POST.get("description") or "").strip()
        event.date = _parse_date(request.POST.get("date"))
        event.start_time = _parse_time(request.POST.get("start_time"))
        event.end_time = _parse_time(request.POST.get("end_time"))
        event.venue = (request.POST.get("venue") or "").strip()
        event.city = (request.POST.get("city") or "").strip()
        event.address = (request.POST.get("address") or "").strip()
        event.is_ticketing = True
        event.save()
        activate_free_event(event, plan)
        event.is_ticketing = True
        event.save(update_fields=["is_ticketing", "updated_at"])
        if not event.ticket_tiers.exists() and not request.POST.getlist("tier_name"):
            TicketTier.objects.create(event=event, name="Standard", price=Decimal("5000"), quantity=0, display_order=0)
            TicketTier.objects.create(event=event, name="VIP", price=Decimal("10000"), quantity=0, display_order=1)
        else:
            _save_tiers(event, request.POST)
        flyer = request.FILES.get("flyer")
        if flyer:
            from .flyer_service import process_flyer_image

            try:
                content = process_flyer_image(flyer)
                event.flyer.save(content.name, content, save=True)
            except Exception as exc:  # noqa: BLE001
                messages.error(request, str(exc))
                return redirect("ticketing_edit", event_id=event.pk)
        request.session.pop("event_wizard", None)
        messages.success(request, "Billetterie enregistrée. Vérifiez les tarifs puis publiez.")
        return redirect("ticketing_dashboard", event_id=event.pk)

    default_org = request.user.get_full_name() or request.user.username
    initial = {
        "name": event.name if event else wizard.get("name") or "",
        "organizer_name": event.organizer_name if event else wizard.get("organizer_name") or default_org,
        "event_type": event.event_type if event else wizard.get("event_type") or Event.TYPE_CONCERT,
        "event_type_custom": event.event_type_custom if event else wizard.get("event_type_custom") or "",
        "description": event.description if event else wizard.get("description") or "",
        "date": event.date if event else wizard.get("date") or "",
        "start_time": (
            event.start_time.strftime("%H:%M")
            if event and event.start_time
            else wizard.get("start_time") or ""
        ),
        "end_time": event.end_time.strftime("%H:%M") if event and event.end_time else "",
        "venue": event.venue if event else wizard.get("venue") or "",
        "city": event.city if event else "",
        "address": event.address if event else "",
    }
    if event:
        for tier in event.ticket_tiers.all():
            localized = public_tier_name(tier.name)
            if localized != tier.name:
                tier.name = localized
                tier.save(update_fields=["name", "updated_at"])
        tiers = list(event.ticket_tiers.all())
    else:
        tiers = [
            TicketTier(name="Standard", price=Decimal("5000"), quantity=0),
            TicketTier(name="VIP", price=Decimal("10000"), quantity=0),
        ]
    categories = EventCategory.objects.filter(is_active=True)
    return render(
        request,
        "ticketing/setup.html",
        {
            "event": event,
            "initial": initial,
            "tiers": tiers,
            "categories": categories,
            "nav_active": "create",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
@event_workspace_required
def ticketing_dashboard(request, event_id):
    event = get_user_event(request.user, event_id)
    if not event.is_ticketing:
        event.is_ticketing = True
        event.save(update_fields=["is_ticketing", "updated_at"])
    ensure_invite_token(event)
    if request.method == "POST":
        action = request.POST.get("action") or ""
        if action == "save_tiers":
            count = _save_tiers(event, request.POST)
            if count == 0:
                messages.error(request, "Ajoutez au moins une catégorie de billet.")
            else:
                messages.success(request, "Tarifs mis à jour.")
        elif action == "publish":
            profile, _ = UserProfile.objects.get_or_create(user=event.owner)
            publish_errors = _ticketing_publish_errors(event)
            if publish_errors:
                for err in publish_errors:
                    messages.error(request, err)
                return redirect("ticketing_edit", event_id=event.pk)
            if not profile.momo_ready and not mock_payments_allowed():
                messages.error(
                    request,
                    "Confirmez votre numéro Mobile Money dans le profil avant de publier la billetterie.",
                )
                return redirect("profile")
            if not event.ticket_tiers.filter(is_active=True, price__gt=0).exists():
                messages.error(request, "Définissez au moins un tarif avant de publier.")
                return redirect("ticketing_dashboard", event_id=event.pk)
            event.invite_published_at = event.invite_published_at or timezone.now()
            event.invite_link_enabled = True
            event.is_public = True
            event.is_ticketing = True
            event.status = Event.STATUS_ACTIVE
            event.apply_default_invite_window()
            event.save()
            if not profile.momo_ready:
                messages.info(
                    request,
                    "Mode démonstration : publié sans Mobile Money. En production, un numéro confirmé sera demandé.",
                )
            messages.success(request, "Billetterie publiée. L’événement apparaît dans Événements du moment.")
        elif action == "unpublish":
            event.invite_link_enabled = False
            event.is_public = False
            event.save(update_fields=["invite_link_enabled", "is_public", "updated_at"])
            messages.info(request, "Billetterie retirée des événements publics.")
        elif action == "simulate_sale":
            if not mock_payments_allowed():
                messages.error(request, "La simulation n’est disponible qu’en environnement de test.")
            else:
                tier = (
                    event.ticket_tiers.filter(is_active=True, price__gt=0)
                    .order_by("display_order", "price", "id")
                    .first()
                )
                if tier is None:
                    messages.error(request, "Ajoutez un tarif avant de simuler un achat.")
                else:
                    n = Invitation.objects.filter(event=event).count() + 1
                    ptype = (
                        Invitation.TYPE_VIP
                        if "vip" in (tier.name or "").casefold()
                        else Invitation.TYPE_RECIPIENT
                    )
                    payment = create_guest_payment(
                        event=event,
                        payload={
                            "first_name": "Spectateur",
                            "last_name": f"Test {n}",
                            "email": "",
                            "phone": "",
                            "participant_type": ptype,
                            "amount": tier.price,
                            "extra_data": {
                                "ticket_tier": tier.name,
                                "ticket_tier_id": tier.pk,
                                "simulated": True,
                            },
                        },
                    )
                    confirm_guest_payment_success(
                        payment, provider_payload={"mock": True, "simulated": True}
                    )
                    messages.success(
                        request,
                        f"Achat simulé : {tier.name} à {tier.price:.0f} F CFA. Parcourez aussi le paiement test public.",
                    )
        tab = (request.POST.get("tab") or "").strip()
        if tab not in {"publish", "tiers", "sales"}:
            if action in {"save_tiers"}:
                tab = "tiers"
            elif action == "simulate_sale":
                tab = "sales"
            else:
                tab = "publish"
        url = reverse("ticketing_dashboard", args=[event.pk])
        return redirect(f"{url}?tab={tab}")

    success = GuestPayment.objects.filter(event=event, status=GuestPayment.STATUS_SUCCESS)
    sold = Invitation.objects.filter(event=event, status=Invitation.STATUS_VALID).count()
    present = Invitation.objects.filter(event=event, is_validated=True).count()
    tiers = list(event.ticket_tiers.filter(is_active=True))
    public_url = request.build_absolute_uri(reverse("public_invite", args=[event.invite_token]))
    listing_url = request.build_absolute_uri(reverse("public_event_detail", args=[event.slug]))
    sales_count = success.count()
    return render(
        request,
        "ticketing/dashboard.html",
        {
            "event": event,
            "nav_active": "ticketing",
            "tiers": tiers,
            "sold": sold,
            "present": present,
            "quotas": quota_status(event),
            "gross": success.aggregate(t=Sum("amount"))["t"] or 0,
            "commission": success.aggregate(t=Sum("commission_amount"))["t"] or 0,
            "net": success.aggregate(t=Sum("net_amount"))["t"] or 0,
            "pending": GuestPayment.objects.filter(event=event, status=GuestPayment.STATUS_PENDING).count(),
            "payments": success.order_by("-paid_at", "-created_at")[:80],
            "sales_count": sales_count,
            "public_url": public_url,
            "listing_url": listing_url,
            "can_simulate": mock_payments_allowed(),
            "daily": list(
                success.annotate(d=TruncDate("paid_at"))
                .values("d")
                .annotate(n=Count("id"), t=Sum("amount"))
                .order_by("d")[:14]
            ),
        },
    )


@require_http_methods(["GET", "POST"])
def controller_access(request, token):
    controller = get_object_or_404(
        EventController.objects.select_related("event"),
        token=token,
        is_active=True,
    )
    event = controller.event
    if event.needs_payment or event.status != Event.STATUS_ACTIVE:
        messages.error(request, "Cet événement n’est pas disponible pour le contrôle.")
        return redirect("landing")
    error = ""
    if request.method == "POST":
        submitted = (request.POST.get("access_code") or "").strip()
        if submitted == (controller.access_code or "").strip():
            grant_controller_session(request, controller)
            controller.last_used_at = timezone.now()
            controller.save(update_fields=["last_used_at"])
            return redirect(f"{reverse('home')}?scan=1&event={event.pk}")
        error = "Code de vérification incorrect."
    return render(
        request,
        "public/controller_gate.html",
        {"event": event, "controller": controller, "error": error},
    )


@login_required
@require_http_methods(["GET", "POST"])
@event_workspace_required
def event_control(request, event_id):
    """Scanner + gestion des accès contrôleurs."""
    event = get_user_event(request.user, event_id)
    if request.method == "POST":
        action = request.POST.get("action") or "add_controller"
        if action == "add_controller":
            label = (request.POST.get("controller_label") or "Contrôleur").strip() or "Contrôleur"
            code = (request.POST.get("controller_code") or "").strip()
            if not code:
                messages.error(request, "Définissez un code de vérification.")
            else:
                EventController.objects.create(
                    event=event,
                    label=label[:120],
                    token=secrets.token_urlsafe(12).replace("_", "x").replace("-", "x")[:22],
                    access_code=code[:40],
                )
                messages.success(request, "Accès contrôleur créé.")
        elif action == "revoke_controller":
            EventController.objects.filter(
                event=event, pk=request.POST.get("controller_id")
            ).update(is_active=False)
            messages.info(request, "Accès contrôleur révoqué.")
        return redirect("event_control", event_id=event.pk)

    controllers = list(event.controllers.filter(is_active=True))
    for ctrl in controllers:
        ctrl.public_url = request.build_absolute_uri(
            reverse("controller_access", args=[ctrl.token])
        )
    return render(
        request,
        "events/control.html",
        {
            "event": event,
            "nav_active": "control",
            "controllers": controllers,
        },
    )


# Compat alias historically used from invite flows.
event_controllers = event_control
