from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("validation", "0022_site_runtime_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="allow_mock_payments",
            field=models.BooleanField(
                default=True,
                help_text="Uniquement en DEBUG. Décochez pour forcer SingPay.",
                verbose_name="Autoriser les paiements de test",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="default_from_email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Expéditeur des e-mails (mot de passe oublié…). Vide = e-mail support.",
                max_length=254,
                verbose_name="E-mail d’expédition",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="meta_description",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Balise meta des pages publiques. Vide = accroche.",
                max_length=220,
                verbose_name="Description SEO",
            ),
        ),
    ]
