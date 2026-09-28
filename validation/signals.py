from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.db.utils import OperationalError, ProgrammingError
from django.dispatch import receiver

from .models import Event, Invitation, UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_profile(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        with transaction.atomic():
            UserProfile.objects.get_or_create(user=instance)
    except (ProgrammingError, OperationalError):
        # Colonnes pas encore créées pendant une migration historique.
        return


@receiver(post_save, sender=Event)
def bump_event_lifetime(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from .lifetime import record_event_created

        record_event_created(instance)
    except (ProgrammingError, OperationalError):
        return


@receiver(post_save, sender=Invitation)
def bump_invitation_lifetime(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from .lifetime import record_invitation_created

        record_invitation_created()
    except (ProgrammingError, OperationalError):
        return
