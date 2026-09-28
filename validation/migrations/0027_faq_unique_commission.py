from django.db import migrations


def update_commission_faq(apps, schema_editor):
    FaqItem = apps.get_model("validation", "FaqItem")
    FaqItem.objects.filter(question="Qu’est-ce que la commission Gab Event ?").update(
        answer=(
            "Taux unique : 7 % + 150 F CFA par billet (réglable par l’équipe, dans une fourchette "
            "de 6 à 8 % plus un frais fixe). Gab Event prend en charge les frais SingPay. "
            "Le reversement se fait sous 72h ouvrées. Vous voyez le brut, la commission et le net "
            "dans Paiements invités."
        )
    )
    FaqItem.objects.filter(question="Comment fonctionne le paiement des invitations ?").update(
        answer=(
            "Pour vos invitations payantes, les invités paient par Airtel/Moov Money. "
            "Le montant arrive d’abord dans le portefeuille Gab Event. Après la commission unique, "
            "le net vous est reversé sous 72h ouvrées sur le numéro Airtel ou Moov confirmé dans votre profil."
        )
    )
    FaqItem.objects.filter(question="Comment recevoir mon argent (Airtel / Moov) ?").update(
        answer=(
            "Renseignez et confirmez votre numéro Mobile Money dans le profil. Sans ce numéro confirmé, "
            "la publication d’un lien payant est bloquée. Gab Event prend en charge les frais SingPay. "
            "Les reversements partent sous 72h ouvrées vers votre numéro."
        )
    )


def revert_commission_faq(apps, schema_editor):
    FaqItem = apps.get_model("validation", "FaqItem")
    FaqItem.objects.filter(question="Qu’est-ce que la commission Gab Event ?").update(
        answer=(
            "Par défaut 10 % sur une invitation Standard et 20 % sur une VIP. Ces taux sont définis par "
            "l’équipe Gab Event. Vous voyez le brut, la commission et le net dans Paiements invités."
        )
    )


class Migration(migrations.Migration):

    dependencies = [
        ("validation", "0026_offline_invoice_fees"),
    ]

    operations = [
        migrations.RunPython(update_commission_faq, revert_commission_faq),
    ]
