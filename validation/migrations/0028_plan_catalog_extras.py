from decimal import Decimal

from django.db import migrations, models


def refresh_catalog(apps, schema_editor):
    EventPlan = apps.get_model("validation", "EventPlan")
    EventPlan.objects.filter(slug="gratuit").update(
        extra_ticket_price=Decimal("200"),
        description="Jusqu'à 30 personnes — idéal pour démarrer.",
    )
    EventPlan.objects.filter(slug="petit").update(
        name="Petit événement",
        description="50 invitations VIP.",
        regular_invitation_limit=0,
        vip_invitation_limit=50,
        total_invitation_limit=0,
        price=Decimal("5999"),
        extra_ticket_price=Decimal("150"),
        is_custom=False,
        is_active=True,
    )
    EventPlan.objects.filter(slug="moyen").update(
        name="Événement moyen",
        description="300 invitations standard + 100 VIP.",
        regular_invitation_limit=300,
        vip_invitation_limit=100,
        total_invitation_limit=0,
        price=Decimal("17999"),
        extra_ticket_price=Decimal("100"),
        is_custom=False,
        is_active=True,
    )
    EventPlan.objects.filter(slug="grand").update(
        name="Grand événement",
        description="500 invitations standard + 150 VIP.",
        regular_invitation_limit=500,
        vip_invitation_limit=150,
        total_invitation_limit=0,
        price=Decimal("33999"),
        extra_ticket_price=Decimal("200"),
        is_custom=False,
        is_active=True,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("validation", "0027_faq_unique_commission"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventplan",
            name="extra_ticket_price",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Tarif d’un billet au-delà du forfait inclus. 0 = non proposé.",
                max_digits=10,
                verbose_name="Prix / billet supplémentaire",
            ),
        ),
        migrations.RunPython(refresh_catalog, noop),
    ]
