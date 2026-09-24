from decimal import Decimal

from django.db import migrations


def update_petit(apps, schema_editor):
    EventPlan = apps.get_model("validation", "EventPlan")
    EventPlan.objects.filter(slug="petit").update(
        price=Decimal("9999"),
        currency="FCFA",
        is_recommended=True,
        description="100 invitations standard + 20 VIP.",
    )
    EventPlan.objects.filter(slug="moyen").update(is_recommended=False)


def revert_petit(apps, schema_editor):
    EventPlan = apps.get_model("validation", "EventPlan")
    EventPlan.objects.filter(slug="petit").update(
        price=Decimal("10499"),
        is_recommended=False,
    )
    EventPlan.objects.filter(slug="moyen").update(is_recommended=True)


class Migration(migrations.Migration):
    dependencies = [
        ("validation", "0009_plan_catalog_refresh"),
    ]

    operations = [
        migrations.RunPython(update_petit, revert_petit),
    ]
