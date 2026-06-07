import sentry_sdk
from celery.signals import task_failure, worker_process_shutdown


def on_task_failure(
    sender,
    task_id,
    exception,
    einfo,
    **kwargs,
) -> None:
    """Report task failures (including SoftTimeLimitExceeded) to Sentry with the task id."""
    name = getattr(sender, "name", "unknown")
    sentry_sdk.capture_message(
        f"Celery task failed: {name} ({task_id}): {exception!r}",
        level="error",
    )


def on_worker_process_shutdown(
    pid=None,
    exitcode=None,
    **kwargs,
) -> None:
    """Report abnormal worker child exits (OOM/SIGKILL/time-limit) to Sentry."""
    if exitcode not in (0, None):
        sentry_sdk.capture_message(
            f"Celery worker child {pid} exited abnormally: exitcode={exitcode}",
            level="error",
        )


task_failure.connect(on_task_failure, dispatch_uid="obs_task_failure")
worker_process_shutdown.connect(
    on_worker_process_shutdown,
    dispatch_uid="obs_worker_shutdown",
)
