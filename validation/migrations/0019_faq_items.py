from django.db import migrations, models


FAQ_SEED = [
    (
        "start",
        10,
        "Qu’est-ce que Gab Event ?",
        "Gab Event est une plateforme pour créer, envoyer et contrôler des invitations électroniques. "
        "Vous créez un événement, partagez un lien (gratuit ou payant), collectez les inscriptions, "
        "puis scannez les QR codes à l’entrée.",
    ),
    (
        "start",
        20,
        "Comment créer un compte ?",
        "Ouvrez Créer un compte, renseignez prénom, nom, e-mail, téléphone et un mot de passe d’au moins "
        "6 caractères. Le téléphone est obligatoire : il sert aussi à récupérer le compte. Indiquez "
        "également votre opérateur Mobile Money (Airtel ou Moov) et confirmez le numéro pour les reversements.",
    ),
    (
        "start",
        30,
        "Comment me connecter ?",
        "Sur la page Connexion, choisissez E-mail ou Téléphone, saisissez votre identifiant et votre mot "
        "de passe. L’œil à droite du champ affiche le mot de passe.",
    ),
    (
        "start",
        40,
        "J’ai oublié mon mot de passe",
        "Cliquez sur Mot de passe oublié. Indiquez l’e-mail ou le numéro renseigné à la création. Un lien "
        "de réinitialisation est envoyé à l’e-mail du compte. Pensez à regarder les indésirables.",
    ),
    (
        "events",
        10,
        "Comment créer un événement ?",
        "Depuis Mon espace, cliquez sur Créer. Choisissez le type (gala, remise de diplômes, etc.), "
        "puis une formule. Renseignez le nom, la date et le lieu. Vous pourrez ensuite personnaliser "
        "l’apparence et le lien d’invitation.",
    ),
    (
        "events",
        20,
        "Quelles formules existent et combien de temps durent-elles ?",
        "Gratuit : 14 jours. Petit : 21 jours. Moyen : 30 jours. Grand : 60 jours. Personnalisé : "
        "vous définissez la fenêtre de validité à la création. Le décompte part de la date de création "
        "de l’événement, pas de la date de la soirée.",
    ),
    (
        "events",
        30,
        "Que se passe-t-il à la fin de la validité ?",
        "L’événement est retiré automatiquement à l’échéance. Les liens d’invitation se ferment aussi "
        "selon la fenêtre de dates que vous avez définie. Pensez à exporter votre liste Excel avant.",
    ),
    (
        "events",
        40,
        "Puis-je modifier l’apparence de mon événement ?",
        "Oui, dans Apparence : visuel de couverture, couleurs et textes. Cette page reste accessible "
        "tant que l’événement est actif.",
    ),
    (
        "invites",
        10,
        "Comment inviter mes convives ?",
        "Ouvrez Lien d’invitation. Choisissez les champs du formulaire (prénom, nom, e-mail…), puis "
        "publiez. Copiez le lien public et envoyez-le par WhatsApp, SMS ou e-mail. Chaque convive "
        "s’inscrit lui-même : plus besoin de saisir toute la liste à la main.",
    ),
    (
        "invites",
        20,
        "Quelle est la différence entre invitation gratuite et payante ?",
        "Sur les formules classiques, le lien est gratuit : le convive confirme sa présence. Sur la "
        "formule Personnalisé, vous pouvez fixer un tarif Standard et VIP. Le convive paie via SingPay "
        "(Airtel Money / Moov Money) avant d’être ajouté à la liste.",
    ),
    (
        "invites",
        30,
        "Les convives doivent-ils créer un compte ?",
        "Non. Ils ouvrent le lien, remplissent le formulaire et, le cas échéant, paient. Ils n’ont "
        "pas besoin d’espace organisateur.",
    ),
    (
        "invites",
        40,
        "Puis-je exporter la liste (Excel) ?",
        "Oui. L’export Excel reste disponible pour travailler hors ligne, imprimer ou partager la "
        "liste avec votre équipe. Les inscriptions du lien public y apparaissent automatiquement.",
    ),
    (
        "invites",
        50,
        "Puis-je changer les champs du formulaire après publication ?",
        "Non. Dès la première mise en ligne, les champs sont verrouillés pour que tous les invités "
        "voient le même formulaire. Préparez-le avant de publier.",
    ),
    (
        "payments",
        10,
        "Comment fonctionne le paiement des invitations ?",
        "Le convive choisit Standard ou VIP, est redirigé vers SingPay, et paie sur son Mobile Money. "
        "Le montant arrive d’abord dans le portefeuille Gab Event. Après commission, le net vous est "
        "reversé sur le numéro Airtel ou Moov confirmé dans votre profil.",
    ),
    (
        "payments",
        20,
        "Qu’est-ce que la commission Gab Event ?",
        "Par défaut 10 % sur une invitation Standard et 20 % sur une VIP. Ces taux sont définis par "
        "l’équipe Gab Event. Vous voyez le brut, la commission et le net dans Paiements invités.",
    ),
    (
        "payments",
        30,
        "Comment recevoir mon argent (Airtel / Moov) ?",
        "Renseignez et confirmez votre numéro Mobile Money dans le profil. Sans ce numéro confirmé, "
        "la publication d’un lien payant est bloquée. Les reversements sont lancés depuis la console "
        "Gab Event vers votre numéro.",
    ),
    (
        "payments",
        40,
        "Que faire si un paiement échoue ?",
        "Le convive peut rouvrir le même lien et réessayer. Tant que le paiement n’est pas confirmé, "
        "aucune place n’est créée. En cas de doute, contactez l’organisateur avec l’heure et le numéro utilisé.",
    ),
    (
        "scan",
        10,
        "Comment contrôler l’entrée le jour J ?",
        "Ouvrez Scanner depuis l’événement. Placez le QR code de l’invitation dans le cadre, ou saisissez "
        "le code à la main. Un billet = une personne. Le statut passe à Présent.",
    ),
    (
        "scan",
        20,
        "Un QR code peut-il être utilisé deux fois ?",
        "Non. Une fois scanné et validé, le code ne peut plus servir pour une autre entrée. C’est "
        "volontaire pour éviter les copies.",
    ),
    (
        "account",
        10,
        "Pourquoi mon numéro Mobile Money est-il demandé ?",
        "Il sert à vous reverser l’argent des invitations payantes. Il est distinct du téléphone de "
        "connexion, même s’il peut être identique. Vous devez le retaper pour confirmer.",
    ),
    (
        "account",
        20,
        "Comment modifier mon profil ?",
        "Allez dans Profil : nom, téléphone, mot de passe et numéro Mobile Money. Enregistrez en bas "
        "de page. Sur téléphone, le bouton d’enregistrement reste visible au-dessus du menu.",
    ),
    (
        "account",
        30,
        "Qui peut voir les données des invités ?",
        "L’organisateur de l’événement et l’équipe Gab Event (support, comptabilité, contrôle). Les "
        "convives ne voient pas la liste des autres invités. Consultez aussi les conditions d’utilisation.",
    ),
]


def seed_faq(apps, schema_editor):
    FaqItem = apps.get_model("validation", "FaqItem")
    if FaqItem.objects.exists():
        return
    FaqItem.objects.bulk_create(
        [
            FaqItem(
                section=section,
                display_order=order,
                question=question,
                answer=answer,
                is_active=True,
            )
            for section, order, question, answer in FAQ_SEED
        ]
    )


def unseed_faq(apps, schema_editor):
    FaqItem = apps.get_model("validation", "FaqItem")
    FaqItem.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("validation", "0018_event_lifetime_windows"),
    ]

    operations = [
        migrations.CreateModel(
            name="FaqItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("question", models.CharField(max_length=220, verbose_name="Question")),
                ("answer", models.TextField(verbose_name="Réponse")),
                (
                    "section",
                    models.CharField(
                        choices=[
                            ("start", "Démarrer"),
                            ("events", "Événements"),
                            ("invites", "Invitations"),
                            ("payments", "Paiements"),
                            ("scan", "Contrôle d’accès"),
                            ("account", "Compte"),
                        ],
                        default="start",
                        max_length=20,
                        verbose_name="Rubrique",
                    ),
                ),
                (
                    "display_order",
                    models.PositiveIntegerField(default=0, verbose_name="Ordre"),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="Visible"),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Question FAQ",
                "verbose_name_plural": "Questions FAQ",
                "ordering": ["section", "display_order", "id"],
            },
        ),
        migrations.RunPython(seed_faq, unseed_faq),
    ]
