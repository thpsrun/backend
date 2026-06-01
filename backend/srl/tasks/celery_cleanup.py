from datetime import timedelta

from api.models import APIActivityLog
from celery import shared_task
from django.utils import timezone

from ._common import API_ACTIVITY_LOG_RETENTION_DAYS


@shared_task(name="srl.tasks.prune_api_activity_log")
def prune_api_activity_log() -> int:
    """Delete APIActivityLog rows older than the retention window (90 days).

    Wired into ``CELERY_BEAT_SCHEDULE`` as ``prune-api-activity-log-daily``."""
    cutoff = timezone.now() - timedelta(days=API_ACTIVITY_LOG_RETENTION_DAYS)
    deleted, _ = APIActivityLog.objects.filter(created_at__lt=cutoff).delete()
    return deleted
