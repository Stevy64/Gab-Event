from django.db import migrations, models
from django.db.models import Q


def apply_uncustomized_navy(apps, schema_editor):
    Event = apps.get_model("validation", "Event")
    uncustomized = (
        Q(flyer="") | Q(flyer__isnull=True)
    ) & (Q(logo="") | Q(logo__isnull=True))
    Event.objects.filter(
        uncustomized,
        primary_color__in=["", "#F26522", "#f26522"],
    ).update(primary_color="#1A2744")
    Event.objects.filter(primary_color="").update(primary_color="#1A2744")


class Migration(migrations.Migration):

    dependencies = [
        ("validation", "0013_event_archive_lifecycle"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="primary_color",
            field=models.CharField(
                blank=True,
                default="#1A2744",
                max_length=16,
                verbose_name="Couleur principale",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="code_prefix",
            field=models.CharField(
                help_text="Préfixe des codes d'invitation (ex. GAE26).",
                max_length=24,
                unique=True,
                verbose_name="Préfixe QR",
            ),
        ),
        migrations.RunPython(apply_uncustomized_navy, migrations.RunPython.noop),
    ]
