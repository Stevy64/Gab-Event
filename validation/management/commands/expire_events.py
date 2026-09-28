from django.core.management.base import BaseCommand

from validation.event_lifecycle import expire_due_events


class Command(BaseCommand):
    help = (
        "Ferme les liens d’invitation expirés et archive les événements "
        "arrivés en fin de validité (selon la formule). Aucune suppression."
    )

    def handle(self, *args, **options):
        result = expire_due_events(force=True)
        self.stdout.write(
            self.style.SUCCESS(
                f"Archivés : {result.archived} · Liens fermés : {result.links_closed}"
            )
        )
