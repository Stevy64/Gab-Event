from datetime import datetime, time, timedelta

from django.db import migrations, models
from django.utils import timezone


LIFETIME = {
    "gratuit": 14,
    "petit": 21,
    "moyen": 30,
    "grand": 60,
}


def seed_lifetimes(apps, schema_editor):
    EventPlan = apps.get_model("validation", "EventPlan")
    Event = apps.get_model("validation", "Event")
    for slug, days in LIFETIME.items():
        EventPlan.objects.filter(slug=slug).update(lifetime_days=days)
    EventPlan.objects.filter(is_custom=True).update(lifetime_days=None)

    for event in Event.objects.select_related("plan").all():
        if event.is_legacy or event.expires_at:
            continue
        plan = event.plan
        created = event.created_at or timezone.now()
        if plan and plan.is_custom:
            start = event.validity_starts_on or created.date()
            end = event.validity_ends_on or (start + timedelta(days=30))
            expires = timezone.make_aware(datetime.combine(end, time(23, 59, 59)))
        else:
            days = (plan.lifetime_days if plan and plan.lifetime_days else None)
            if days is None and plan:
                days = LIFETIME.get(plan.slug, 14)
            days = days or 14
            start = created.date()
            expires = created + timedelta(days=days)
            end = timezone.localtime(expires).date() if timezone.is_aware(expires) else expires.date()
        Event.objects.filter(pk=event.pk).update(
            validity_starts_on=start,
            validity_ends_on=end,
            expires_at=expires,
            invite_valid_from=event.invite_valid_from or start,
            invite_valid_until=event.invite_valid_until or end,
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("validation", "0017_momo_payouts"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventplan",
            name="lifetime_days",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Suppression automatique N jours après la création. Vide pour une fenêtre définie à la création (Personnalisé).",
                null=True,
                verbose_name="Durée de vie (jours)",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="validity_starts_on",
            field=models.DateField(blank=True, null=True, verbose_name="Début de validité"),
        ),
        migrations.AddField(
            model_name="event",
            name="validity_ends_on",
            field=models.DateField(blank=True, null=True, verbose_name="Fin de validité"),
        ),
        migrations.AddField(
            model_name="event",
            name="expires_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="Suppression automatique le",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="invite_valid_from",
            field=models.DateField(blank=True, null=True, verbose_name="Lien invité — début"),
        ),
        migrations.AddField(
            model_name="event",
            name="invite_valid_until",
            field=models.DateField(blank=True, null=True, verbose_name="Lien invité — fin"),
        ),
        migrations.RunPython(seed_lifetimes, noop),
    ]
