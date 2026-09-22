from django.core.management.base import BaseCommand

from validation.code_service import generate_invitation_code
from validation.constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP
from validation.models import Invitation


class Command(BaseCommand):
    help = "Génère des codes ATC24-XXXXXX ou VIP-XXXXXX (secrets)."

    def add_arguments(self, parser):
        parser.add_argument("count", type=int, nargs="?", default=10)
        parser.add_argument(
            "--type",
            choices=[PARTICIPANT_RECIPIENT, PARTICIPANT_VIP],
            default=PARTICIPANT_RECIPIENT,
        )
        parser.add_argument(
            "--create",
            action="store_true",
            help="Créer des invitations brouillon avec ces codes",
        )

    def handle(self, *args, **options):
        count = options["count"]
        ptype = options["type"]
        for _ in range(count):
            code = generate_invitation_code(ptype)
            if options["create"]:
                Invitation.objects.create(
                    code=code,
                    last_name="À définir",
                    first_name="À définir",
                    participant_type=ptype,
                    category="Récipiendaire" if ptype == PARTICIPANT_RECIPIENT else "VIP",
                    places=1,
                )
            self.stdout.write(code)
        self.stdout.write(self.style.SUCCESS(f"{count} code(s) généré(s)."))
