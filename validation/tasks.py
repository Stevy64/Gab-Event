from celery import shared_task

from .event_lifecycle import expire_due_events


@shared_task
def expire_events_task():
    expire_due_events(force=True)
