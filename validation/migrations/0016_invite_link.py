from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("validation", "0015_console_cms"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="invite_token",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=40,
                null=True,
                unique=True,
                verbose_name="Jeton lien d’invitation",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="invite_form_fields",
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name="Champs du formulaire invité",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="invite_published_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Formulaire mis en ligne le",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="invite_link_enabled",
            field=models.BooleanField(default=False, verbose_name="Lien d’invitation actif"),
        ),
        migrations.AddField(
            model_name="event",
            name="guest_price_regular",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name="Tarif invité standard",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="guest_price_vip",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name="Tarif invité VIP",
            ),
        ),
        migrations.AddField(
            model_name="invitation",
            name="email",
            field=models.EmailField(blank=True, default="", max_length=254, verbose_name="E-mail"),
        ),
        migrations.AddField(
            model_name="invitation",
            name="phone",
            field=models.CharField(blank=True, default="", max_length=40, verbose_name="Téléphone"),
        ),
        migrations.AddField(
            model_name="invitation",
            name="extra_data",
            field=models.JSONField(blank=True, default=dict, verbose_name="Champs complémentaires"),
        ),
        migrations.AddField(
            model_name="invitation",
            name="source",
            field=models.CharField(
                choices=[("import", "Excel / import"), ("form", "Formulaire public")],
                db_index=True,
                default="import",
                max_length=16,
                verbose_name="Origine",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="commission_regular_pct",
            field=models.DecimalField(
                decimal_places=2,
                default=10,
                max_digits=5,
                verbose_name="Commission standard (%)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="commission_vip_pct",
            field=models.DecimalField(
                decimal_places=2,
                default=20,
                max_digits=5,
                verbose_name="Commission VIP (%)",
            ),
        ),
        migrations.CreateModel(
            name="GuestPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_name", models.CharField(max_length=120)),
                ("last_name", models.CharField(max_length=120)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("phone", models.CharField(blank=True, default="", max_length=40)),
                ("extra_data", models.JSONField(blank=True, default=dict)),
                (
                    "participant_type",
                    models.CharField(
                        choices=[("RECIPIENT", "Standard"), ("VIP", "VIP")],
                        default="RECIPIENT",
                        max_length=20,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(default="XOF", max_length=8)),
                ("commission_rate", models.DecimalField(decimal_places=2, default=10, max_digits=5)),
                ("commission_amount", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("net_amount", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("provider", models.CharField(default="mock", max_length=40)),
                ("provider_reference", models.CharField(blank=True, db_index=True, default="", max_length=120)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "En attente"),
                            ("success", "Réussi"),
                            ("failed", "Échoué"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "payout_status",
                    models.CharField(
                        choices=[("pending", "À reverser"), ("recorded", "Reversé")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guest_payments",
                        to="validation.event",
                    ),
                ),
                (
                    "invitation",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="guest_payment",
                        to="validation.invitation",
                    ),
                ),
                (
                    "organizer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guest_payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Paiement invité",
                "verbose_name_plural": "Paiements invités",
                "ordering": ["-created_at"],
            },
        ),
    ]
