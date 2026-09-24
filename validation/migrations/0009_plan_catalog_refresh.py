from decimal import Decimal

from django.db import migrations, models


def refresh_plans(apps, schema_editor):
    EventPlan = apps.get_model("validation", "EventPlan")
    updates = {
        "petit": {
            "name": "Petit événement",
            "description": "100 invitations standard + 20 VIP.",
            "regular_invitation_limit": 100,
            "vip_invitation_limit": 20,
            "total_invitation_limit": 0,
            "price": Decimal("10499"),
            "currency": "FCFA",
            "is_free": False,
            "is_custom": False,
            "is_recommended": False,
            "is_active": True,
            "display_order": 2,
        },
        "moyen": {
            "name": "Événement moyen",
            "description": "250 invitations standard + 50 VIP.",
            "regular_invitation_limit": 250,
            "vip_invitation_limit": 50,
            "total_invitation_limit": 0,
            "price": Decimal("25900"),
            "currency": "FCFA",
            "is_free": False,
            "is_custom": False,
            "is_recommended": True,
            "is_active": True,
            "display_order": 3,
        },
        "grand": {
            "name": "Grand événement",
            "description": "500 invitations standard + 90 VIP.",
            "regular_invitation_limit": 500,
            "vip_invitation_limit": 90,
            "total_invitation_limit": 0,
            "price": Decimal("50999"),
            "currency": "FCFA",
            "is_free": False,
            "is_custom": False,
            "is_recommended": False,
            "is_active": True,
            "display_order": 4,
        },
        "gratuit": {
            "currency": "FCFA",
            "is_custom": False,
            "is_recommended": False,
            "display_order": 1,
        },
    }
    for slug, data in updates.items():
        EventPlan.objects.filter(slug=slug).update(**data)

    EventPlan.objects.filter(slug="mariage").update(is_active=False, display_order=90)
    EventPlan.objects.update_or_create(
        slug="personnalise",
        defaults={
            "name": "Personnalisé",
            "description": "100 FCFA / invitation standard · 130 FCFA / VIP.",
            "regular_invitation_limit": 0,
            "vip_invitation_limit": 0,
            "total_invitation_limit": 0,
            "price": Decimal("100"),
            "currency": "FCFA",
            "is_free": False,
            "is_custom": True,
            "price_per_regular": Decimal("100"),
            "price_per_vip": Decimal("130"),
            "is_recommended": False,
            "is_active": True,
            "display_order": 5,
        },
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("validation", "0008_unique_profile_phone"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventplan",
            name="is_custom",
            field=models.BooleanField(
                default=False,
                help_text="Tarif à l'invitation, sans quota fixe.",
                verbose_name="Formule à la carte",
            ),
        ),
        migrations.AddField(
            model_name="eventplan",
            name="price_per_regular",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name="Prix / invitation standard",
            ),
        ),
        migrations.AddField(
            model_name="eventplan",
            name="price_per_vip",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name="Prix / invitation VIP",
            ),
        ),
        migrations.RunPython(refresh_plans, noop),
    ]
