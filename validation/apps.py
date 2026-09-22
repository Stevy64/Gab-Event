from django.apps import AppConfig


class ValidationConfig(AppConfig):
    """App Django : validation des invitations de cérémonie."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "validation"
    verbose_name = "Validation des invitations"
