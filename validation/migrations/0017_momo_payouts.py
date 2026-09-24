from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("validation", "0016_invite_link"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="momo_operator",
            field=models.CharField(
                blank=True,
                choices=[("airtel", "Airtel Money"), ("moov", "Moov Money")],
                default="",
                max_length=16,
                verbose_name="Opérateur Mobile Money",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="momo_phone",
            field=models.CharField(
                blank=True,
                default="",
                max_length=40,
                verbose_name="Numéro Mobile Money",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="momo_confirmed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Mobile Money confirmé le",
            ),
        ),
        migrations.AlterField(
            model_name="guestpayment",
            name="payout_status",
            field=models.CharField(
                choices=[
                    ("pending", "À reverser"),
                    ("processing", "En cours"),
                    ("recorded", "Reversé"),
                    ("failed", "Échec"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="guestpayment",
            name="payout_reference",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="guestpayment",
            name="payout_error",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.CreateModel(
            name="OrganizerPayout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(default="XOF", max_length=8)),
                (
                    "momo_operator",
                    models.CharField(
                        blank=True,
                        choices=[("airtel", "Airtel Money"), ("moov", "Moov Money")],
                        default="",
                        max_length=16,
                    ),
                ),
                ("momo_phone", models.CharField(blank=True, default="", max_length=40)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "En cours"),
                            ("partial", "Partiel"),
                            ("success", "Réussi"),
                            ("failed", "Échoué"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("provider", models.CharField(default="mock", max_length=40)),
                ("provider_reference", models.CharField(blank=True, default="", max_length=120)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                (
                    "actor",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="issued_payouts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organizer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organizer_payouts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Reversement organisateur",
                "verbose_name_plural": "Reversements organisateurs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="guestpayment",
            name="payout",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="guest_payments",
                to="validation.organizerpayout",
            ),
        ),
    ]
