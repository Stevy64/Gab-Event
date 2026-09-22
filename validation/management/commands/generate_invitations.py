from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from validation.card_service import build_invitations_zip, generate_invitation_card
from validation.constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP
from validation.models import Invitation
from validation.qr_service import generate_invitation_qr


class Command(BaseCommand):
    help = "Génère les QR et cartes d'invitation (ATC24 / VIP)."

    def add_arguments(self, parser):
        parser.add_argument("--only-missing", action="store_true")
        parser.add_argument(
            "--type",
            choices=[PARTICIPANT_RECIPIENT, PARTICIPANT_VIP],
            default=None,
        )

    def handle(self, *args, **options):
        qs = Invitation.objects.all()
        if options["type"]:
            qs = qs.filter(participant_type=options["type"])

        recipient_total = Invitation.objects.filter(
            participant_type=PARTICIPANT_RECIPIENT
        ).count()
        vip_total = Invitation.objects.filter(participant_type=PARTICIPANT_VIP).count()

        data, summary = build_invitations_zip(
            invitations=qs,
            only_missing=options["only_missing"],
        )
        # Also ensure QR PNGs exist
        for inv in qs.iterator():
            generate_invitation_qr(inv)

        out = Path(settings.BASE_DIR) / "invitations_ceremonie.zip"
        out.write_bytes(data)

        self.stdout.write("")
        self.stdout.write(f"Récipiendaires : {recipient_total}")
        self.stdout.write(f"VIP : {vip_total}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Invitations générées : {summary['generated']}"))
        self.stdout.write(f"Déjà existantes : {summary['skipped']}")
        self.stdout.write(f"Erreurs : {summary['errors']}")
        self.stdout.write(f"Archive : {out}")
