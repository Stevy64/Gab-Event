from django.apps import AppConfig


class ValidationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "validation"
    verbose_name = "Gab Event"

    def ready(self):
        from . import signals  # noqa: F401
