from django.db import migrations, models


CATEGORY_COVERS = {
    "ceremony": "img/ceremony-bg.jpg",
    "wedding": "img/gallery-centre-table.jpg",
    "graduation": "img/ceremony-bg.jpg",
    "conference": "img/gallery-salle.jpg",
    "gala": "img/gallery-centre-table.jpg",
    "birthday": "img/gallery-soiree.jpg",
    "reception": "img/gallery-salle.jpg",
    "professional": "img/gallery-banquet.jpg",
    "other": "img/ceremony-bg.jpg",
}


def seed_category_covers(apps, schema_editor):
    EventCategory = apps.get_model("validation", "EventCategory")
    for slug, path in CATEGORY_COVERS.items():
        EventCategory.objects.filter(slug=slug, default_image_static="").update(
            default_image_static=path
        )


def unseed_category_covers(apps, schema_editor):
    EventCategory = apps.get_model("validation", "EventCategory")
    EventCategory.objects.filter(slug__in=CATEGORY_COVERS).update(default_image_static="")


class Migration(migrations.Migration):
    dependencies = [
        ("validation", "0019_faq_items"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventcategory",
            name="default_image",
            field=models.ImageField(
                blank=True,
                help_text="Utilisée automatiquement si l’organisateur n’ajoute pas de visuel.",
                null=True,
                upload_to="categories/%Y/%m/",
                verbose_name="Photo par défaut",
            ),
        ),
        migrations.AddField(
            model_name="eventcategory",
            name="default_image_static",
            field=models.CharField(
                blank=True,
                default="",
                max_length=200,
                verbose_name="Fichier statique (interne)",
            ),
        ),
        migrations.RunPython(seed_category_covers, unseed_category_covers),
    ]
