"""Seed EventPlan + migrate legacy invitations vers l'événement historique ATC."""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import migrations


PLANS = [
    {
        "slug": "gratuit",
        "name": "Événement Gratuit",
        "description": "Jusqu'à 30 personnes — idéal pour démarrer.",
        "regular_invitation_limit": 30,
        "vip_invitation_limit": 30,
        "total_invitation_limit": 30,
        "price": Decimal("0"),
        "currency": "XOF",
        "is_free": True,
        "is_active": True,
        "is_recommended": False,
        "display_order": 1,
    },
    {
        "slug": "petit",
        "name": "Petit événement",
        "description": "100 invitations standard + 10 VIP.",
        "regular_invitation_limit": 100,
        "vip_invitation_limit": 10,
        "total_invitation_limit": 0,
        "price": Decimal("25000"),
        "currency": "XOF",
        "is_free": False,
        "is_active": True,
        "is_recommended": True,
        "display_order": 2,
    },
    {
        "slug": "moyen",
        "name": "Événement moyen",
        "description": "250 invitations standard + 25 VIP.",
        "regular_invitation_limit": 250,
        "vip_invitation_limit": 25,
        "total_invitation_limit": 0,
        "price": Decimal("50000"),
        "currency": "XOF",
        "is_free": False,
        "is_active": True,
        "is_recommended": False,
        "display_order": 3,
    },
    {
        "slug": "mariage",
        "name": "Mariage",
        "description": "350 invitations standard + 50 VIP.",
        "regular_invitation_limit": 350,
        "vip_invitation_limit": 50,
        "total_invitation_limit": 0,
        "price": Decimal("75000"),
        "currency": "XOF",
        "is_free": False,
        "is_active": True,
        "is_recommended": False,
        "display_order": 4,
    },
    {
        "slug": "grand",
        "name": "Grand événement",
        "description": "500 invitations standard + 200 VIP.",
        "regular_invitation_limit": 500,
        "vip_invitation_limit": 200,
        "total_invitation_limit": 0,
        "price": Decimal("120000"),
        "currency": "XOF",
        "is_free": False,
        "is_active": True,
        "is_recommended": False,
        "display_order": 5,
    },
]


def seed_and_migrate(apps, schema_editor):
    EventPlan = apps.get_model("validation", "EventPlan")
    Event = apps.get_model("validation", "Event")
    Invitation = apps.get_model("validation", "Invitation")
    Admission = apps.get_model("validation", "Admission")
    ScanLog = apps.get_model("validation", "ScanLog")
    UserProfile = apps.get_model("validation", "UserProfile")
    User = get_user_model()

    for data in PLANS:
        EventPlan.objects.update_or_create(slug=data["slug"], defaults=data)

    owner = User.objects.filter(is_superuser=True).order_by("id").first()
    if owner is None:
        owner = User.objects.order_by("id").first()
    if owner is None:
        owner = User.objects.create_user(
            username="legacy_owner",
            email="legacy@gabevent.local",
            password=None,
        )
        owner.set_unusable_password()
        owner.save()

    UserProfile.objects.get_or_create(user_id=owner.pk)

    grand = EventPlan.objects.filter(slug="grand").first()
    ceremony = getattr(settings, "CEREMONY", {}) or {}

    event, created = Event.objects.get_or_create(
        code_prefix="ATC24",
        defaults={
            "owner_id": owner.pk,
            "plan_id": grand.pk if grand else None,
            "name": "Ancienne cérémonie ATC",
            "slug": "ancienne-ceremonie-atc",
            "event_type": "graduation",
            "description": ceremony.get("subtitle")
            or "Cérémonie historique migrée (codes ATC24 / VIP conservés)",
            "date": date(2024, 12, 20),
            "start_time": time(18, 0),
            "venue": ceremony.get("venue") or "Grande salle de cérémonie",
            "organizer_name": ceremony.get("organizer") or "ATC",
            "status": "active",
            "is_legacy": True,
            "plan_name_snapshot": grand.name if grand else "Grand événement",
            "regular_limit_snapshot": grand.regular_invitation_limit if grand else 500,
            "vip_limit_snapshot": grand.vip_invitation_limit if grand else 200,
            "total_limit_snapshot": None,
            "price_snapshot": Decimal("0"),
            "currency_snapshot": "XOF",
        },
    )
    if not created and event.owner_id is None:
        event.owner_id = owner.pk
        event.save(update_fields=["owner_id"])

    Invitation.objects.filter(event__isnull=True).update(event_id=event.pk)

    for adm in Admission.objects.filter(event__isnull=True).select_related("invitation"):
        if adm.invitation_id and adm.invitation.event_id:
            Admission.objects.filter(pk=adm.pk).update(event_id=adm.invitation.event_id)
        else:
            Admission.objects.filter(pk=adm.pk).update(event_id=event.pk)

    for log in ScanLog.objects.filter(event__isnull=True).select_related("invitation"):
        if log.invitation_id and log.invitation.event_id:
            ScanLog.objects.filter(pk=log.pk).update(event_id=log.invitation.event_id)
        else:
            ScanLog.objects.filter(pk=log.pk).update(event_id=event.pk)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("validation", "0005_multi_event_platform"),
    ]

    operations = [
        migrations.RunPython(seed_and_migrate, noop_reverse),
    ]
