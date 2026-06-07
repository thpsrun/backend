import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "website.settings")

app = Celery("website")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Importing this module connects the Celery signal handlers (task_failure,
# worker_process_shutdown) that report failures and abnormal worker exits to Sentry.
from website import observability  # noqa: E402,F401
