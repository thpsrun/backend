from celery import shared_task
from django.utils import timezone

from srl.models import ReconciliationJob
from srl.models.reconciliation import ReconPhase, ReconStatus


@shared_task(
    bind=True,
    name="srl.run_bounded_game_reconciliation",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_bounded_game_reconciliation(
    self,
    job_id: str,
) -> None:
    """Routine GAME reconcile: bounded to recent runs, single task, no phase fan-out.

    Arguments:
        job_id (str): UUID string of the `ReconciliationJob``to process.
    """
    # Lazy import to prevent circular dependency errors.
    from srl.srcom.recent_reconcile import reconcile_recent_game_runs
    from srl.srcom.reconciliation import CancellationRequested, release_lock

    job = ReconciliationJob.objects.get(id=job_id)
    job.status = ReconStatus.RUNNING.value

    job.phase = ReconPhase.P1.value
    job.started_at = timezone.now()
    job.celery_task_id = self.request.id or ""
    job.save(update_fields=["status", "phase", "started_at", "celery_task_id"])

    status = ReconStatus.SUCCEEDED.value
    error_summary = ""
    try:
        reconcile_recent_game_runs(job.target_id, job_id=str(job.id))
    except CancellationRequested:
        status = ReconStatus.CANCELLED.value
    except Exception as exc:
        status = ReconStatus.FAILED.value
        error_summary = str(exc)[:4000]

    job.status = status
    job.finished_at = timezone.now()
    job.error_summary = error_summary
    job.save(update_fields=["status", "finished_at", "error_summary"])
    release_lock(job)
