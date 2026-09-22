from django.core.management.base import BaseCommand
from pathlib import Path

from django.conf import settings

from validation.models import Invitation
from validation.qr_service import generate_invitation_qr


class Command(BaseCommand):
    help = "Génère un PNG QR Code par invitation (contenu = code unique)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--outdir",
            type=str,
            default=str(Path(settings.BASE_DIR) / "generated_qr"),
        )

    def handle(self, *args, **options):
        outdir = Path(options["outdir"])
        count = 0
        for invitation in Invitation.objects.all().iterator():
            generate_invitation_qr(invitation, outdir=outdir)
            count += 1
        self.stdout.write(
            self.style.SUCCESS(f"{count} QR Code(s) généré(s) dans {outdir}")
        )
