from decimal import Decimal

from django.db import migrations, models


def refresh_ticketing_plan(apps, schema_editor):
    EventPlan = apps.get_model("validation", "EventPlan")
    Event = apps.get_model("validation", "Event")
    SiteSettings = apps.get_model("validation", "SiteSettings")
    EventCategory = apps.get_model("validation", "EventCategory")

    EventPlan.objects.filter(slug="personnalise").update(
        name="Vendre vos billets",
        description="Billetterie publique. Commission 7 % par billet, frais de transfert à la charge de l’organisateur.",
        is_custom=True,
        is_active=True,
        is_free=False,
        extra_ticket_price=Decimal("0"),
        display_order=5,
    )
    Event.objects.filter(plan__slug="personnalise", is_ticketing=False).update(is_ticketing=True)
    SiteSettings.objects.all().update(
        commission_fixed=Decimal("0"),
        singpay_fees_on_platform=False,
    )
    EventCategory.objects.update_or_create(
        slug="concert",
        defaults={"name": "Concert", "is_active": True, "display_order": 15},
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("validation", "0028_plan_catalog_extras"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="invite_access_code",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optionnel. Les invités doivent le saisir pour ouvrir le formulaire.",
                max_length=40,
                verbose_name="Code de validation du lien",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="is_public",
            field=models.BooleanField(
                default=False,
                help_text="Affiché sur la page Événements publics (indépendamment du carrousel).",
                verbose_name="Événement public",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="is_ticketing",
            field=models.BooleanField(
                default=False,
                help_text="Événement vendu via la billetterie (concerts, festivals, etc.).",
                verbose_name="Billetterie",
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
                    ("concert", "Concert"),
                    ("birthday", "Anniversaire"),
                    ("reception", "Réception"),
                    ("professional", "Événement professionnel"),
                    ("other", "Autre"),
                ],
                default="other",
                max_length=40,
                verbose_name="Type",
            ),
        ),
        migrations.AlterField(
            model_name="sitesettings",
            name="singpay_fees_on_platform",
            field=models.BooleanField(
                default=False,
                help_text="Si coché, les frais SingPay ne sont pas déduits du reversement organisateur.",
                verbose_name="Gab Event prend en charge les frais SingPay",
            ),
        ),
        migrations.CreateModel(
            name="TicketTier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, verbose_name="Nom")),
                ("description", models.CharField(blank=True, default="", max_length=200, verbose_name="Description")),
                ("price", models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="Prix")),
                (
                    "quantity",
                    models.PositiveIntegerField(default=0, help_text="0 = illimité.", verbose_name="Quantité"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
                ("display_order", models.PositiveIntegerField(default=0, verbose_name="Ordre")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="ticket_tiers",
                        to="validation.event",
                    ),
                ),
            ],
            options={
                "verbose_name": "Catégorie de billet",
                "verbose_name_plural": "Catégories de billets",
                "ordering": ["display_order", "price", "id"],
            },
        ),
        migrations.CreateModel(
            name="EventController",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(default="Contrôleur", max_length=120, verbose_name="Nom du contrôleur")),
                ("token", models.CharField(db_index=True, max_length=40, unique=True, verbose_name="Jeton")),
                ("access_code", models.CharField(max_length=40, verbose_name="Code de vérification")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="controllers",
                        to="validation.event",
                    ),
                ),
            ],
            options={
                "verbose_name": "Contrôleur",
                "verbose_name_plural": "Contrôleurs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="invitation",
            name="ticket_tier",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="invitations",
                to="validation.tickettier",
            ),
        ),
        migrations.RunPython(refresh_ticketing_plan, noop),
    ]
