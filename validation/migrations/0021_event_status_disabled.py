from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("validation", "0020_category_default_image"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Brouillon"),
                    ("pending_payment", "En attente de paiement"),
                    ("active", "Actif"),
                    ("disabled", "Désactivé"),
                    ("completed", "Terminé"),
                    ("archived", "Archivé"),
                    ("cancelled", "Annulé"),
                ],
                db_index=True,
                default="draft",
                max_length=32,
                verbose_name="Statut",
            ),
        ),
    ]
