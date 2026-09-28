from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def seed_lifetime_and_windows(apps, schema_editor):
    Event = apps.get_model("validation", "Event")
    Invitation = apps.get_model("validation", "Invitation")
    SiteSettings = apps.get_model("validation", "SiteSettings")
    User = apps.get_model(settings.AUTH_USER_MODEL)

    site = SiteSettings.objects.first()
    if site is None:
        site = SiteSettings.objects.create()
    live_events = Event.objects.count()
    live_invitations = Invitation.objects.count()
    live_organizers = (
        User.objects.filter(is_active=True, events__isnull=False).distinct().count()
    )
    SiteSettings.objects.filter(pk=site.pk).update(
        lifetime_events=max(int(site.lifetime_events or 0), live_events),
        lifetime_invitations=max(int(site.lifetime_invitations or 0), live_invitations),
        lifetime_organizers=max(int(site.lifetime_organizers or 0), live_organizers),
    )

    slug_days = {"gratuit": 14, "petit": 21, "moyen": 30, "grand": 60}
    tz = timezone.get_current_timezone()
    for event in Event.objects.select_related("plan").iterator():
        if event.is_legacy:
            continue
        plan = event.plan
        created = event.created_at or timezone.now()
        created_day = timezone.localtime(created).date() if timezone.is_aware(created) else created.date()
        event_day = event.date or created_day
        if plan and plan.is_custom:
            start = event.validity_starts_on or created_day
            end = event.validity_ends_on or (event_day + timedelta(days=30))
        else:
            days = None
            if plan and plan.lifetime_days:
                days = int(plan.lifetime_days)
            elif plan:
                days = slug_days.get(plan.slug)
            days = days or 14
            start = created_day
            end = event_day + timedelta(days=days)
        end_dt = timezone.make_aware(datetime.combine(end, time(23, 59, 59)), tz)
        Event.objects.filter(pk=event.pk).update(
            validity_starts_on=start,
            validity_ends_on=end,
            expires_at=end_dt,
        )


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("validation", "0024_alter_adminauditlog_action"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="lifetime_events",
            field=models.PositiveIntegerField(
                default=0, verbose_name="Compteur cumulatif — événements"
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="lifetime_invitations",
            field=models.PositiveIntegerField(
                default=0, verbose_name="Compteur cumulatif — invitations"
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="lifetime_organizers",
            field=models.PositiveIntegerField(
                default=0, verbose_name="Compteur cumulatif — organisateurs"
            ),
        ),
        migrations.CreateModel(
            name="RecoveryOtp",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("phone", models.CharField(max_length=40, verbose_name="Téléphone")),
                ("code_hash", models.CharField(max_length=64)),
                (
                    "channel",
                    models.CharField(
                        choices=[
                            ("whatsapp", "WhatsApp"),
                            ("sms", "SMS"),
                            ("console", "Console / test"),
                        ],
                        default="console",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recovery_otps",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Code de récupération",
                "verbose_name_plural": "Codes de récupération",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="recoveryotp",
            index=models.Index(
                fields=["user", "consumed_at"],
                name="validation__user_id_recov_idx",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="expires_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="Archivage automatique le",
            ),
        ),
        migrations.AlterField(
            model_name="eventplan",
            name="lifetime_days",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Archivage automatique N jours après la date de l’événement (J+N). Vide pour une fenêtre définie à la création (Personnalisé).",
                null=True,
                verbose_name="Durée de vie (jours)",
            ),
        ),
        migrations.RunPython(seed_lifetime_and_windows, noop),
    ]
