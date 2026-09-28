from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("validation", "0025_lifetime_otp_archive"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="animated_card",
            field=models.BooleanField(
                default=False,
                help_text="Option prestige : animation, musique et nom de l'invité (quelques secondes).",
                verbose_name="Carte d'invitation animée",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="commission_pct",
            field=models.DecimalField(
                decimal_places=2,
                default=7,
                help_text="Taux unique entre 6 et 8 %, appliqué à chaque billet payant.",
                max_digits=5,
                verbose_name="Commission unique (%)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="commission_fixed",
            field=models.DecimalField(
                decimal_places=2,
                default=150,
                max_digits=10,
                verbose_name="Frais fixe par billet (F CFA)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="payout_sla_hours",
            field=models.PositiveIntegerField(
                default=72,
                verbose_name="Délai de reversement (heures ouvrées)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="singpay_fees_on_platform",
            field=models.BooleanField(
                default=True,
                help_text="Si coché, les frais SingPay ne sont pas déduits du reversement organisateur.",
                verbose_name="Gab Event prend en charge les frais SingPay",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="animated_card_price",
            field=models.DecimalField(
                decimal_places=2,
                default=25000,
                max_digits=10,
                verbose_name="Prix carte animée (F CFA)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="legal_company_name",
            field=models.CharField(
                blank=True,
                default="Gab Event",
                max_length=160,
                verbose_name="Raison sociale (facture)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="legal_nif",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Obligatoire pour qu’une entreprise gabonaise puisse payer.",
                max_length=40,
                verbose_name="NIF",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="legal_rccm",
            field=models.CharField(
                blank=True,
                default="",
                max_length=40,
                verbose_name="RCCM",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="legal_address",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Adresse (facture)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="legal_city",
            field=models.CharField(
                blank=True,
                default="Libreville",
                max_length=120,
                verbose_name="Ville (facture)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="legal_phone",
            field=models.CharField(
                blank=True,
                default="",
                max_length=40,
                verbose_name="Téléphone (facture)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="legal_email",
            field=models.EmailField(
                blank=True,
                default="",
                max_length=254,
                verbose_name="E-mail (facture)",
            ),
        ),
    ]
