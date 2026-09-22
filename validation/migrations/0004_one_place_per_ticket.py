from django.db import migrations, models


def force_one_place(apps, schema_editor):
    Invitation = apps.get_model("validation", "Invitation")
    for inv in Invitation.objects.all():
        changed = False
        if inv.places != 1:
            inv.places = 1
            changed = True
        if inv.places_used > 1:
            inv.places_used = 1
            changed = True
        if changed:
            inv.save(update_fields=["places", "places_used"])


class Migration(migrations.Migration):
    dependencies = [
        ("validation", "0003_backfill_types_places"),
    ]

    operations = [
        migrations.RunPython(force_one_place, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="invitation",
            name="places",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Toujours 1 : une invitation = une personne.",
                verbose_name="Places autorisées",
            ),
        ),
    ]
