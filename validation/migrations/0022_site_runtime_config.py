from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("validation", "0021_event_status_disabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="app_store_url",
            field=models.URLField(blank=True, default="", verbose_name="Lien App Store"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="banner_enabled",
            field=models.BooleanField(default=False, verbose_name="Afficher la bannière promo"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="banner_link",
            field=models.URLField(blank=True, default="", verbose_name="Lien de la bannière"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="banner_link_label",
            field=models.CharField(
                blank=True, default="Voir", max_length=40, verbose_name="Libellé du lien bannière"
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="banner_text",
            field=models.CharField(
                blank=True, default="", max_length=200, verbose_name="Texte de la bannière"
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="extra_link_label",
            field=models.CharField(
                blank=True, default="", max_length=40, verbose_name="Lien personnalisé — libellé"
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="extra_link_url",
            field=models.URLField(blank=True, default="", verbose_name="Lien personnalisé — URL"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="facebook_url",
            field=models.URLField(blank=True, default="", verbose_name="Facebook"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="hero_cta_guest",
            field=models.CharField(
                blank=True,
                default="Commencer gratuitement",
                max_length=80,
                verbose_name="Bouton hero (visiteur)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="hero_cta_user",
            field=models.CharField(
                blank=True,
                default="Créer un événement",
                max_length=80,
                verbose_name="Bouton hero (connecté)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="hero_image",
            field=models.ImageField(
                blank=True, null=True, upload_to="site/", verbose_name="Image hero (accueil)"
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="hero_lead",
            field=models.TextField(
                blank=True,
                default="Créez votre événement, envoyez vos billets électroniques et gérez vos invités depuis votre smartphone.",
                verbose_name="Sous-titre hero",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="hero_line1",
            field=models.CharField(
                blank=True,
                default="Vos invitations électroniques",
                max_length=120,
                verbose_name="Titre hero — ligne 1",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="hero_line2",
            field=models.CharField(
                blank=True,
                default="en une minute",
                max_length=120,
                verbose_name="Titre hero — ligne 2",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="instagram_url",
            field=models.URLField(blank=True, default="", verbose_name="Instagram"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="linkedin_url",
            field=models.URLField(blank=True, default="", verbose_name="LinkedIn"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="play_store_url",
            field=models.URLField(blank=True, default="", verbose_name="Lien Google Play"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="public_base_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Retours de paiement SingPay. Ex. https://gabevent.com",
                verbose_name="URL publique du site",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="singpay_api_key",
            field=models.CharField(
                blank=True, default="", max_length=200, verbose_name="SingPay — clé API"
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="singpay_api_secret",
            field=models.CharField(
                blank=True, default="", max_length=300, verbose_name="SingPay — secret API"
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="singpay_disbursement_id",
            field=models.CharField(
                blank=True, default="", max_length=120, verbose_name="SingPay — disbursement"
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="singpay_environment",
            field=models.CharField(
                choices=[("sandbox", "Sandbox (tests)"), ("production", "Production")],
                default="sandbox",
                max_length=20,
                verbose_name="Environnement SingPay",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="singpay_merchant_id",
            field=models.CharField(
                blank=True, default="", max_length=120, verbose_name="SingPay — portefeuille"
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="support_email",
            field=models.EmailField(blank=True, default="", max_length=254, verbose_name="E-mail support"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="support_phone",
            field=models.CharField(
                blank=True, default="", max_length=32, verbose_name="Téléphone support"
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="tiktok_url",
            field=models.URLField(blank=True, default="", verbose_name="TikTok"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="whatsapp_message",
            field=models.CharField(
                blank=True,
                default="Bonjour, j’ai une question sur Gab Event.",
                max_length=180,
                verbose_name="Message WhatsApp prérempli",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="whatsapp_number",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Ex. 077012345 ou +24177012345",
                max_length=32,
                verbose_name="Numéro WhatsApp",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="x_url",
            field=models.URLField(blank=True, default="", verbose_name="X (Twitter)"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="youtube_url",
            field=models.URLField(blank=True, default="", verbose_name="YouTube"),
        ),
        migrations.AlterField(
            model_name="sitesettings",
            name="default_cover",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="site/",
                verbose_name="Image par défaut / bannière",
            ),
        ),
    ]
