from django.db import migrations


def forwards(apps, schema_editor):
    Invitation = apps.get_model("validation", "Invitation")
    for inv in Invitation.objects.all():
        code = (inv.code or "").upper()
        if code.startswith("VIP-"):
            inv.participant_type = "VIP"
        else:
            inv.participant_type = "RECIPIENT"
        if inv.is_validated and inv.places_used == 0:
            inv.places_used = inv.places
        inv.save(update_fields=["participant_type", "places_used"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("validation", "0002_phase2_types_places"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
