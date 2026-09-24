from django.db import migrations, models


def seed_cms(apps, schema_editor):
    EventCategory = apps.get_model("validation", "EventCategory")
    GalleryImage = apps.get_model("validation", "GalleryImage")
    SiteSettings = apps.get_model("validation", "SiteSettings")

    categories = [
        ("ceremony", "Cérémonie", "ceremony", 10, False),
        ("wedding", "Mariage", "wedding", 20, False),
        ("graduation", "Remise de diplômes", "graduation", 30, False),
        ("conference", "Conférence", "conference", 40, False),
        ("gala", "Gala", "gala", 50, False),
        ("birthday", "Anniversaire", "birthday", 60, False),
        ("reception", "Réception", "reception", 70, False),
        ("professional", "Événement professionnel", "professional", 80, False),
        ("other", "Personnalisé", "other", 90, True),
    ]
    for slug, name, icon, order, custom in categories:
        EventCategory.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "icon_key": icon,
                "display_order": order,
                "is_custom_entry": custom,
                "is_active": True,
            },
        )

    gallery = [
        (0, "img/ceremony-bg.jpg", "Gab Event", "Votre plateforme d'invitations"),
        (10, "img/gallery-soiree.jpg", "Soirée", "Une table prête pour vos invités"),
        (20, "img/gallery-salle.jpg", "Réception", "La salle, avant l'arrivée des convives"),
        (30, "img/gallery-centre-table.jpg", "Gala", "Le détail qui donne le ton"),
        (40, "img/gallery-banquet.jpg", "Banquet", "Un service soigné, de bout en bout"),
    ]
    for order, path, label, caption in gallery:
        GalleryImage.objects.get_or_create(
            static_path=path,
            defaults={
                "label": label,
                "caption": caption,
                "display_order": order,
                "is_active": True,
            },
        )

    if not SiteSettings.objects.exists():
        SiteSettings.objects.create()


class Migration(migrations.Migration):

    dependencies = [
        ("validation", "0014_event_defaults_branding"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("site_name", models.CharField(default="Gab Event", max_length=80, verbose_name="Nom du site")),
                (
                    "tagline",
                    models.CharField(
                        blank=True,
                        default="Invitations électroniques, avec élégance.",
                        max_length=180,
                        verbose_name="Accroche",
                    ),
                ),
                ("logo", models.ImageField(blank=True, null=True, upload_to="site/", verbose_name="Logo du site")),
                (
                    "default_cover",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="site/",
                        verbose_name="Image par défaut des événements",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Réglages du site",
                "verbose_name_plural": "Réglages du site",
            },
        ),
        migrations.CreateModel(
            name="GalleryImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(blank=True, null=True, upload_to="gallery/%Y/%m/", verbose_name="Image")),
                (
                    "static_path",
                    models.CharField(blank=True, default="", max_length=200, verbose_name="Fichier statique (interne)"),
                ),
                ("label", models.CharField(max_length=120, verbose_name="Titre")),
                ("caption", models.CharField(blank=True, default="", max_length=200, verbose_name="Légende")),
                ("is_active", models.BooleanField(default=True, verbose_name="Visible")),
                ("display_order", models.PositiveIntegerField(default=0, verbose_name="Ordre")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Image de galerie",
                "verbose_name_plural": "Images de galerie",
                "ordering": ["display_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="EventCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=40, unique=True)),
                ("name", models.CharField(max_length=80, verbose_name="Nom")),
                ("icon_key", models.CharField(blank=True, default="", max_length=40, verbose_name="Icône")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
                (
                    "is_custom_entry",
                    models.BooleanField(
                        default=False,
                        help_text="Ex. Personnalisé — l'organisateur nomme son type.",
                        verbose_name="Permet un type libre",
                    ),
                ),
                ("display_order", models.PositiveIntegerField(default=0, verbose_name="Ordre")),
            ],
            options={
                "verbose_name": "Catégorie d'événement",
                "verbose_name_plural": "Catégories d'événements",
                "ordering": ["display_order", "name"],
            },
        ),
        migrations.RunPython(seed_cms, migrations.RunPython.noop),
    ]
