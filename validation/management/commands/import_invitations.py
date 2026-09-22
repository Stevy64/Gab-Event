from django.core.management.base import BaseCommand, CommandError

from validation.services import import_invitations_from_path


class Command(BaseCommand):
    help = "Importe les invitations depuis un fichier Excel (.xlsx)."

    def add_arguments(self, parser):
        parser.add_argument("filepath", type=str, help="Chemin vers le fichier .xlsx")

    def handle(self, *args, **options):
        filepath = options["filepath"]
        result = import_invitations_from_path(filepath)
        for err in result.errors:
            self.stderr.write(self.style.WARNING(err))
        if result.errors and not result.imported:
            raise CommandError("Import échoué.")
        self.stdout.write(
            self.style.SUCCESS(
                f"Import terminé : {result.created} créée(s), "
                f"{result.updated} mise(s) à jour."
            )
        )
