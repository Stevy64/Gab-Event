from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("validation", "0010_petit_plan_popular"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="event_type_custom",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Ex. Noël, Nouvel an, Baptême…",
                max_length=80,
                verbose_name="Type personnalisé",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("ceremony", "Cérémonie"),
                    ("wedding", "Mariage"),
                    ("graduation", "Remise de diplômes"),
                    ("conference", "Conférence"),
                    ("gala", "Gala"),
                    ("birthday", "Anniversaire"),
                    ("reception", "Réception"),
                    ("professional", "Événement professionnel"),
                    ("other", "Personnalisé"),
                ],
                default="other",
                max_length=40,
                verbose_name="Type",
            ),
        ),
    ]
