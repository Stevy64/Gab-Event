"""Dashboard administrateur plateforme — /platform-admin/."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from .access import require_platform_admin
from . import singpay as singpay_api
from .branding import site_brand
from .siteconfig import display_name
from .forms import (
    EventCategoryForm,
    EventLimitAdjustForm,
    EventPlanAdminForm,
    FaqItemForm,
    GalleryImageForm,
    SiteSettingsForm,
)
from .models import (
    AdminAuditLog,
    Event,
    EventCategory,
    EventLimitAdjustment,
    EventPlan,
    FaqItem,
    GalleryImage,
    Invitation,
    GuestPayment,
    OrganizerPayout,
    Payment,
    SiteSettings,
    UserProfile,
)
from .payment_service import payout_organizer
from .constants import PARTICIPANT_VIP


def _admin_required(view):
    @login_required
    def wrapped(request, *args, **kwargs):
        require_platform_admin(request.user)
        return view(request, *args, **kwargs)

    return wrapped


def _ctx(extra: dict | None = None) -> dict:
    brand = site_brand()
    data = {
        "site_logo": brand["logo_url"],
        "site_logo_version": brand["version"],
        "site_name": display_name(),
    }
    if extra:
        data.update(extra)
    return data


def _daily_series(qs, date_field: str, days: int = 14, amount_field: str | None = None):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    filt = {f"{date_field}__date__gte": start}
    mapped: dict = {}
    annotated = qs.filter(**filt).annotate(d=TruncDate(date_field))
    if amount_field:
        rows = annotated.values("d").annotate(n=Count("id"), t=Sum(amount_field))
        for row in rows:
            mapped[row["d"]] = {"n": row["n"] or 0, "t": row["t"] or 0}
    else:
        rows = annotated.values("d").annotate(n=Count("id"))
        for row in rows:
            mapped[row["d"]] = {"n": row["n"] or 0, "t": 0}
    series = []
    peak = 1
    for i in range(days):
        day = start + timedelta(days=i)
        rec = mapped.get(day, {"n": 0, "t": 0})
        val = float(rec["t"] or 0) if amount_field else rec["n"]
        peak = max(peak, val)
        series.append(
            {
                "label": day.strftime("%d/%m"),
                "n": rec["n"],
                "t": rec["t"],
                "val": val,
            }
        )
    for item in series:
        item["pct"] = max(4, int(round((item["val"] / peak) * 100))) if item["val"] else 4
    return series


def _audit(actor, action, summary, target_type="", target_id=""):
    AdminAuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=str(target_id or ""),
        summary=summary,
    )


@_admin_required
@require_GET
def overview(request):
    now = timezone.now()
    month_ago = now - timedelta(days=30)
    users_total = User.objects.count()
    users_new = User.objects.filter(date_joined__gte=month_ago).count()
    users_active = User.objects.filter(last_login__gte=month_ago).count()
    events = Event.objects.all()
    payments = Payment.objects.all()
    ctx = {
        "nav_active": "overview",
        "users_total": users_total,
        "users_new": users_new,
        "users_active": users_active,
        "events_total": events.count(),
        "events_active": events.filter(status=Event.STATUS_ACTIVE).count(),
        "events_pending": events.filter(status=Event.STATUS_PENDING_PAYMENT).count(),
        "events_completed": events.filter(status=Event.STATUS_COMPLETED).count(),
        "invitations_total": Invitation.objects.count(),
        "invitations_vip": Invitation.objects.filter(
            participant_type=PARTICIPANT_VIP
        ).count(),
        "payments_success": payments.filter(status=Payment.STATUS_SUCCESS).count(),
        "payments_pending": payments.filter(status=Payment.STATUS_PENDING).count(),
        "revenue": payments.filter(status=Payment.STATUS_SUCCESS).aggregate(
            t=Sum("amount")
        )["t"]
        or 0,
        "recent_events": Event.objects.select_related("owner", "plan").order_by(
            "-created_at"
        )[:6],
        "recent_payments": Payment.objects.select_related("user", "event", "plan")[:6],
        "recent_logs": AdminAuditLog.objects.select_related("actor")[:6],
        "chart_events": _daily_series(Event.objects.all(), "created_at"),
        "chart_payments": _daily_series(
            Payment.objects.filter(status=Payment.STATUS_SUCCESS),
            "created_at",
            amount_field="amount",
        ),
        "users_today": User.objects.filter(date_joined__date=timezone.localdate()).count(),
        "events_today": events.filter(created_at__date=timezone.localdate()).count(),
    }
    return render(request, "platform_admin/overview.html", _ctx(ctx))


@_admin_required
@require_GET
def users_list(request):
    q = (request.GET.get("q") or "").strip()
    qs = User.objects.annotate(
        events_count=Count("events"),
        invitations_count=Count("events__invitations"),
    ).select_related("profile")
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(profile__organization_name__icontains=q)
        )
    page = Paginator(qs.order_by("-date_joined"), 40).get_page(request.GET.get("page"))
    return render(
        request,
        "platform_admin/users.html",
        _ctx({"nav_active": "users", "users": page, "q": q}),
    )


@_admin_required
@require_GET
def user_detail(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    events = Event.objects.filter(owner=user).select_related("plan")
    payments = Payment.objects.filter(user=user).select_related("event", "plan")
    guest_payments = GuestPayment.objects.filter(organizer=user).select_related(
        "event", "invitation"
    )
    guest_success = guest_payments.filter(status=GuestPayment.STATUS_SUCCESS)
    pending_net = (
        guest_success.filter(
            payout_status__in=[GuestPayment.PAYOUT_PENDING, GuestPayment.PAYOUT_FAILED]
        ).aggregate(t=Sum("net_amount"))["t"]
        or 0
    )
    return render(
        request,
        "platform_admin/user_detail.html",
        _ctx(
            {
                "nav_active": "users",
                "u": user,
                "profile": profile,
                "events": events,
                "payments": payments,
                "guest_payments": guest_payments[:80],
                "guest_gross": guest_success.aggregate(t=Sum("amount"))["t"] or 0,
                "guest_commission": guest_success.aggregate(t=Sum("commission_amount"))["t"] or 0,
                "guest_net": guest_success.aggregate(t=Sum("net_amount"))["t"] or 0,
                "pending_net": pending_net,
            }
        ),
    )


@_admin_required
@require_GET
def events_list(request):
    qs = Event.objects.select_related("owner", "plan")
    q = (request.GET.get("q") or "").strip()
    status = request.GET.get("status")
    plan = request.GET.get("plan")
    etype = request.GET.get("type")
    free = request.GET.get("free")
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(owner__username__icontains=q)
            | Q(owner__email__icontains=q)
            | Q(owner__first_name__icontains=q)
            | Q(owner__last_name__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    if plan:
        qs = qs.filter(plan__slug=plan)
    if etype:
        qs = qs.filter(event_type=etype)
    if free == "1":
        qs = qs.filter(Q(plan__is_free=True) | Q(price_snapshot=0))
    elif free == "0":
        qs = qs.filter(plan__is_free=False).exclude(price_snapshot=0)
    qs = qs.annotate(inv_count=Count("invitations"))
    page = Paginator(qs, 40).get_page(request.GET.get("page"))
    return render(
        request,
        "platform_admin/events.html",
        _ctx(
            {
                "nav_active": "events",
                "events": page,
                "plans": EventPlan.objects.all(),
                "filters": {
                    "q": q,
                    "status": status or "",
                    "plan": plan or "",
                    "type": etype or "",
                    "free": free or "",
                },
            }
        ),
    )


@_admin_required
@require_http_methods(["GET", "POST"])
def event_detail(request, event_id):
    event = get_object_or_404(
        Event.objects.select_related("owner", "plan"), pk=event_id
    )
    if request.method == "POST" and request.POST.get("action") == "activate":
        event.status = Event.STATUS_ACTIVE
        if event.plan_id and not event.plan_name_snapshot:
            event.apply_plan_snapshot(event.plan)
        event.save()
        AdminAuditLog.objects.create(
            actor=request.user,
            action=AdminAuditLog.ACTION_EVENT_ACTIVATE,
            target_type="event",
            target_id=str(event.pk),
            summary=f"Activation manuelle {event.name}",
        )
        messages.success(request, "Événement activé.")
        return redirect("platform_admin_event", event_id=event.pk)

    form = EventLimitAdjustForm(
        request.POST or None,
        initial={
            "custom_regular_limit": event.custom_regular_limit,
            "custom_vip_limit": event.custom_vip_limit,
            "custom_total_limit": event.custom_total_limit,
        },
    )
    if request.method == "POST" and form.is_valid():
        adj = EventLimitAdjustment.objects.create(
            event=event,
            admin_user=request.user,
            previous_regular=event.regular_limit,
            previous_vip=event.vip_limit,
            previous_total=event.total_limit,
            new_regular=form.cleaned_data.get("custom_regular_limit"),
            new_vip=form.cleaned_data.get("custom_vip_limit"),
            new_total=form.cleaned_data.get("custom_total_limit"),
            reason=form.cleaned_data.get("reason") or "",
        )
        event.custom_regular_limit = form.cleaned_data.get("custom_regular_limit")
        event.custom_vip_limit = form.cleaned_data.get("custom_vip_limit")
        event.custom_total_limit = form.cleaned_data.get("custom_total_limit")
        event.save(
            update_fields=[
                "custom_regular_limit",
                "custom_vip_limit",
                "custom_total_limit",
                "updated_at",
            ]
        )
        AdminAuditLog.objects.create(
            actor=request.user,
            action=AdminAuditLog.ACTION_LIMIT_ADJUST,
            target_type="event",
            target_id=str(event.pk),
            summary=f"Ajustement limites événement {event.name}",
            details={"adjustment_id": adj.pk},
        )
        messages.success(request, "Limites ajustées.")
        return redirect("platform_admin_event", event_id=event.pk)

    return render(
        request,
        "platform_admin/event_detail.html",
        _ctx(
            {
                "nav_active": "events",
                "event": event,
                "form": form,
                "invitations_count": event.invitations.count(),
                "adjustments": event.limit_adjustments.select_related("admin_user")[:20],
            }
        ),
    )


@_admin_required
@require_http_methods(["GET", "POST"])
def plans_list(request):
    plans = EventPlan.objects.all()
    return render(
        request, "platform_admin/plans.html", _ctx({"nav_active": "plans", "plans": plans})
    )


@_admin_required
@require_http_methods(["GET", "POST"])
def plan_edit(request, plan_id):
    plan = get_object_or_404(EventPlan, pk=plan_id)
    form = EventPlanAdminForm(request.POST or None, instance=plan)
    if request.method == "POST" and form.is_valid():
        before = {
            "price": str(plan.price),
            "regular": plan.regular_invitation_limit,
            "vip": plan.vip_invitation_limit,
        }
        form.save()
        AdminAuditLog.objects.create(
            actor=request.user,
            action=AdminAuditLog.ACTION_PLAN_UPDATE,
            target_type="eventplan",
            target_id=str(plan.pk),
            summary=f"Modification formule {plan.name}",
            details={"before": before},
        )
        messages.success(request, "Formule enregistrée (nouveaux événements).")
        return redirect("platform_admin_plans")
    return render(
        request,
        "platform_admin/plan_edit.html",
        _ctx({"nav_active": "plans", "form": form, "plan": plan}),
    )


def _empty_event_ledger(event):
    zero = Decimal("0")
    return {
        "event": event,
        "in_guest": zero,
        "commission": zero,
        "net": zero,
        "due": zero,
        "paid_out": zero,
        "plan_in": zero,
        "due_ids": [],
        "due_count": 0,
        "movements": [],
    }


def _accounting_ledger():
    groups: dict[int, dict] = {}

    def group_for(user):
        row = groups.get(user.pk)
        if row:
            return row
        row = {
            "organizer": user,
            "profile": getattr(user, "profile", None),
            "events": {},
            "in_guest": Decimal("0"),
            "commission": Decimal("0"),
            "net": Decimal("0"),
            "due": Decimal("0"),
            "paid_out": Decimal("0"),
            "plan_in": Decimal("0"),
            "due_ids": [],
        }
        groups[user.pk] = row
        return row

    guests = GuestPayment.objects.filter(status=GuestPayment.STATUS_SUCCESS).select_related(
        "organizer", "organizer__profile", "event"
    )
    for pay in guests:
        group = group_for(pay.organizer)
        ev = group["events"].setdefault(pay.event_id, _empty_event_ledger(pay.event))
        ev["in_guest"] += pay.amount
        ev["commission"] += pay.commission_amount
        ev["net"] += pay.net_amount
        group["in_guest"] += pay.amount
        group["commission"] += pay.commission_amount
        group["net"] += pay.net_amount
        if pay.payout_status in (GuestPayment.PAYOUT_PENDING, GuestPayment.PAYOUT_FAILED):
            ev["due"] += pay.net_amount
            ev["due_ids"].append(pay.pk)
            ev["due_count"] += 1
            group["due"] += pay.net_amount
            group["due_ids"].append(pay.pk)
        elif pay.payout_status == GuestPayment.PAYOUT_RECORDED:
            ev["paid_out"] += pay.net_amount
            group["paid_out"] += pay.net_amount
        ev["movements"].append(
            {
                "kind": "in",
                "label": f"Invité {pay.full_name}",
                "amount": pay.amount,
                "when": pay.paid_at or pay.created_at,
                "status": pay.get_payout_status_display(),
            }
        )

    plans = Payment.objects.filter(
        status__in=[Payment.STATUS_SUCCESS, Payment.STATUS_PENDING]
    ).select_related("user", "user__profile", "event", "plan")
    for pay in plans:
        group = group_for(pay.user)
        ev = group["events"].setdefault(pay.event_id, _empty_event_ledger(pay.event))
        if pay.status == Payment.STATUS_SUCCESS:
            ev["plan_in"] += pay.amount
            group["plan_in"] += pay.amount
        ev["movements"].append(
            {
                "kind": "plan" if pay.status == Payment.STATUS_SUCCESS else "pending",
                "label": f"Formule {pay.plan.name if pay.plan_id else ''}".strip(),
                "amount": pay.amount,
                "when": pay.paid_at or pay.created_at,
                "status": pay.get_status_display(),
            }
        )

    batches = OrganizerPayout.objects.select_related("organizer", "organizer__profile").prefetch_related(
        "guest_payments__event"
    )[:80]
    journal = []
    for pay in guests:
        journal.append(
            {
                "kind": "in",
                "when": pay.paid_at or pay.created_at,
                "label": f"Invité · {pay.full_name}",
                "party": pay.organizer,
                "event": pay.event,
                "amount": pay.amount,
                "status": pay.get_payout_status_display(),
            }
        )
    for pay in plans:
        journal.append(
            {
                "kind": "plan" if pay.status == Payment.STATUS_SUCCESS else "pending",
                "when": pay.paid_at or pay.created_at,
                "label": f"Formule · {pay.plan.name if pay.plan_id else 'événement'}",
                "party": pay.user,
                "event": pay.event,
                "amount": pay.amount,
                "status": pay.get_status_display(),
            }
        )
    for batch in batches:
        journal.append(
            {
                "kind": "out",
                "when": batch.paid_at or batch.created_at,
                "label": f"Reversement · {batch.momo_phone}",
                "party": batch.organizer,
                "event": None,
                "amount": batch.amount,
                "status": batch.get_status_display(),
            }
        )
        group = groups.get(batch.organizer_id)
        if not group:
            continue
        by_event = defaultdict(lambda: Decimal("0"))
        for gp in batch.guest_payments.all():
            if gp.payout_status == GuestPayment.PAYOUT_RECORDED:
                by_event[gp.event_id] += gp.net_amount
        for event_id, amount in by_event.items():
            ev = group["events"].get(event_id)
            if not ev:
                continue
            ev["movements"].append(
                {
                    "kind": "out",
                    "label": f"Reversé vers {batch.momo_phone}",
                    "amount": amount,
                    "when": batch.paid_at or batch.created_at,
                    "status": batch.get_status_display(),
                }
            )

    for group in groups.values():
        group["event_rows"] = sorted(
            group["events"].values(),
            key=lambda row: (row["event"].name or "").lower(),
        )
        for ev in group["event_rows"]:
            ev["movements"].sort(key=lambda item: item["when"] or timezone.now(), reverse=True)

    journal.sort(key=lambda item: item["when"] or timezone.now(), reverse=True)
    return {
        "groups": sorted(groups.values(), key=lambda row: row["organizer"].username),
        "journal": journal[:60],
    }


@_admin_required
@require_http_methods(["GET", "POST"])
def payments_list(request):
    if request.method == "POST" and request.POST.get("action") == "payout":
        organizer = get_object_or_404(User, pk=request.POST.get("organizer_id"))
        raw_ids = request.POST.getlist("payment_ids")
        payment_ids = [int(x) for x in raw_ids if str(x).isdigit()] or None
        raw_event = request.POST.get("event_id")
        event_id = int(raw_event) if str(raw_event or "").isdigit() else None
        try:
            batch = payout_organizer(
                actor=request.user,
                organizer=organizer,
                payment_ids=payment_ids,
                event_id=event_id,
            )
        except RuntimeError as exc:
            messages.error(request, str(exc))
        else:
            if batch.status == OrganizerPayout.STATUS_SUCCESS:
                messages.success(
                    request,
                    f"Reversé {batch.amount} {batch.currency} vers {batch.momo_phone}.",
                )
            elif batch.status == OrganizerPayout.STATUS_PARTIAL:
                messages.warning(request, "Reversement partiel — vérifiez les lignes en échec.")
            else:
                messages.error(request, "Le reversement n’a pas abouti.")
        return redirect("platform_admin_payments")

    qs = Payment.objects.select_related("user", "event", "plan")
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs, 40).get_page(request.GET.get("page"))
    success = Payment.objects.filter(status=Payment.STATUS_SUCCESS)
    revenue = success.aggregate(t=Sum("amount"))["t"] or 0
    pending_amount = (
        Payment.objects.filter(status=Payment.STATUS_PENDING).aggregate(t=Sum("amount"))["t"]
        or 0
    )
    guest_qs = GuestPayment.objects.select_related(
        "organizer", "organizer__profile", "event", "invitation"
    )
    if status:
        guest_qs = guest_qs.filter(status=status)
    guest_success = GuestPayment.objects.filter(status=GuestPayment.STATUS_SUCCESS)
    payout_due = guest_success.filter(
        payout_status__in=[GuestPayment.PAYOUT_PENDING, GuestPayment.PAYOUT_FAILED]
    ).select_related("organizer", "organizer__profile")
    buckets: dict[int, dict] = {}
    for pay in payout_due:
        row = buckets.setdefault(
            pay.organizer_id,
            {
                "organizer": pay.organizer,
                "profile": getattr(pay.organizer, "profile", None),
                "net": 0,
                "count": 0,
                "ids": [],
            },
        )
        row["net"] += pay.net_amount
        row["count"] += 1
        row["ids"].append(pay.pk)
    ledger = _accounting_ledger()
    return render(
        request,
        "platform_admin/payments.html",
        _ctx(
            {
                "nav_active": "payments",
                "payments": page,
                "status": status or "",
                "revenue": revenue,
                "pending_amount": pending_amount,
                "success_count": success.count(),
                "guest_payments": guest_qs[:80],
                "guest_gross": guest_success.aggregate(t=Sum("amount"))["t"] or 0,
                "guest_commission": guest_success.aggregate(t=Sum("commission_amount"))["t"] or 0,
                "guest_net": guest_success.aggregate(t=Sum("net_amount"))["t"] or 0,
                "payout_due": guest_success.filter(
                    payout_status__in=[GuestPayment.PAYOUT_PENDING, GuestPayment.PAYOUT_FAILED]
                ).aggregate(t=Sum("net_amount"))["t"]
                or 0,
                "payout_rows": sorted(buckets.values(), key=lambda r: r["organizer"].username),
                "recent_payouts": OrganizerPayout.objects.select_related("organizer", "actor")[:20],
                "ledger_groups": ledger["groups"],
                "ledger_journal": ledger["journal"],
                "singpay_ready": singpay_api.is_configured(),
            }
        ),
    )


@_admin_required
@require_GET
def activity(request):
    logs = AdminAuditLog.objects.select_related("actor")[:100]
    return render(
        request, "platform_admin/activity.html", _ctx({"nav_active": "activity", "logs": logs})
    )


@_admin_required
@require_http_methods(["GET", "POST"])
def settings_page(request):
    site = SiteSettings.load()
    form = SiteSettingsForm(request.POST or None, request.FILES or None, instance=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        _audit(request.user, AdminAuditLog.ACTION_OTHER, "Mise à jour configuration du site", "site")
        messages.success(request, "Configuration enregistrée.")
        return redirect("platform_admin_settings")
    return render(
        request,
        "platform_admin/settings.html",
        _ctx(
            {
                "nav_active": "settings",
                "form": form,
                "site": site,
                "singpay_ready": singpay_api.is_configured(),
                "singpay_from_console": site.has_singpay_keys(),
            }
        ),
    )


@_admin_required
@require_http_methods(["GET", "POST"])
def plan_create(request):
    form = EventPlanAdminForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        plan = form.save()
        _audit(
            request.user,
            AdminAuditLog.ACTION_PLAN_UPDATE,
            f"Création formule {plan.name}",
            "eventplan",
            plan.pk,
        )
        messages.success(request, "Formule créée.")
        return redirect("platform_admin_plans")
    return render(
        request,
        "platform_admin/plan_edit.html",
        _ctx({"nav_active": "plans", "form": form, "plan": None}),
    )


@_admin_required
@require_http_methods(["POST"])
def plan_delete(request, plan_id):
    plan = get_object_or_404(EventPlan, pk=plan_id)
    if plan.events.exists():
        messages.error(request, "Impossible de supprimer une formule déjà utilisée.")
        return redirect("platform_admin_plan_edit", plan_id=plan.pk)
    name = plan.name
    plan.delete()
    _audit(request.user, AdminAuditLog.ACTION_OTHER, f"Suppression formule {name}", "eventplan")
    messages.success(request, "Formule supprimée.")
    return redirect("platform_admin_plans")


@_admin_required
@require_http_methods(["GET", "POST"])
def media_list(request):
    edit_id = request.GET.get("edit") or request.POST.get("image_id")
    instance = get_object_or_404(GalleryImage, pk=edit_id) if edit_id else None
    form = GalleryImageForm(
        request.POST or None, request.FILES or None, instance=instance
    )
    if request.method == "POST" and form.is_valid():
        image = form.save()
        _audit(
            request.user,
            AdminAuditLog.ACTION_OTHER,
            f"{'Mise à jour' if instance else 'Ajout'} image {image.label}",
            "gallery",
            image.pk,
        )
        messages.success(
            request, "Image enregistrée." if instance else "Image ajoutée au carrousel."
        )
        return redirect("platform_admin_media")
    images = GalleryImage.objects.all()
    return render(
        request,
        "platform_admin/media.html",
        _ctx(
            {
                "nav_active": "media",
                "images": images,
                "form": form,
                "editing": instance,
            }
        ),
    )


@_admin_required
@require_http_methods(["POST"])
def media_delete(request, image_id):
    image = get_object_or_404(GalleryImage, pk=image_id)
    label = image.label
    image.delete()
    _audit(request.user, AdminAuditLog.ACTION_OTHER, f"Suppression image {label}", "gallery")
    messages.success(request, "Image retirée.")
    return redirect("platform_admin_media")


@_admin_required
@require_http_methods(["GET", "POST"])
def categories_list(request):
    edit_id = request.GET.get("edit") or request.POST.get("category_id")
    instance = get_object_or_404(EventCategory, pk=edit_id) if edit_id else None
    form = EventCategoryForm(
        request.POST or None, request.FILES or None, instance=instance
    )
    if request.method == "POST" and form.is_valid():
        cat = form.save()
        if not cat.default_image and not cat.default_image_static:
            cat.default_image_static = "img/ceremony-bg.jpg"
            cat.save(update_fields=["default_image_static"])
        _audit(
            request.user,
            AdminAuditLog.ACTION_OTHER,
            f"{'Mise à jour' if instance else 'Ajout'} catégorie {cat.name}",
            "category",
            cat.pk,
        )
        messages.success(
            request, "Catégorie enregistrée." if instance else "Catégorie ajoutée."
        )
        return redirect("platform_admin_categories")
    categories = EventCategory.objects.all()
    return render(
        request,
        "platform_admin/categories.html",
        _ctx(
            {
                "nav_active": "categories",
                "categories": categories,
                "form": form,
                "editing": instance,
            }
        ),
    )


@_admin_required
@require_http_methods(["POST"])
def category_delete(request, category_id):
    cat = get_object_or_404(EventCategory, pk=category_id)
    if Event.objects.filter(event_type=cat.slug).exists():
        messages.error(request, "Cette catégorie est encore utilisée par des événements.")
        return redirect("platform_admin_categories")
    name = cat.name
    cat.delete()
    _audit(request.user, AdminAuditLog.ACTION_OTHER, f"Suppression catégorie {name}", "category")
    messages.success(request, "Catégorie supprimée.")
    return redirect("platform_admin_categories")


@_admin_required
@require_http_methods(["GET", "POST"])
def faq_list(request):
    edit_id = request.GET.get("edit") or request.POST.get("item_id")
    instance = get_object_or_404(FaqItem, pk=edit_id) if edit_id else None
    form = FaqItemForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        _audit(
            request.user,
            AdminAuditLog.ACTION_OTHER,
            f"{'Mise à jour' if instance else 'Ajout'} FAQ {item.question}",
            "faq",
            item.pk,
        )
        messages.success(
            request, "Question enregistrée." if instance else "Question ajoutée."
        )
        return redirect("platform_admin_faq")
    items = FaqItem.objects.all()
    return render(
        request,
        "platform_admin/faq.html",
        _ctx(
            {
                "nav_active": "faq",
                "items": items,
                "form": form,
                "editing": instance,
            }
        ),
    )


@_admin_required
@require_http_methods(["POST"])
def faq_delete(request, item_id):
    item = get_object_or_404(FaqItem, pk=item_id)
    title = item.question
    item.delete()
    _audit(request.user, AdminAuditLog.ACTION_OTHER, f"Suppression FAQ {title}", "faq")
    messages.success(request, "Question supprimée.")
    return redirect("platform_admin_faq")
