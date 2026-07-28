from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.utils import timezone

from srl.models import ReconciliationJob
from srl.models.reconciliation import GameReconcileMode, ReconPhase, ReconStatus


@shared_task(
    bind=True,
    name="srl.run_bounded_game_reconciliation",
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=settings.RECON_SWEEP_TIME_LIMIT_SECONDS,
    soft_time_limit=settings.RECON_SWEEP_SOFT_TIME_LIMIT_SECONDS,
)
def run_bounded_game_reconciliation(
    self,
    job_id: str,
) -> None:
    """GAME reconcile task: branches on job.mode to run a recent-run pass or a full sweep.

    Arguments:
        job_id (str): UUID string of the `ReconciliationJob` to process.
    """
    # Lazy imports to avoid a circular import error.
    from srl.srcom.recent_reconcile import (
        reconcile_game_sweep,
        reconcile_recent_game_runs,
    )
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
        if job.mode == GameReconcileMode.FULL_GAME.value:
            reconcile_game_sweep(job.target_id, job_id=str(job.id), runtype="main")
        elif job.mode == GameReconcileMode.IL.value:
            reconcile_game_sweep(job.target_id, job_id=str(job.id), runtype="il")
        elif job.mode == GameReconcileMode.RECENT.value:
            reconcile_recent_game_runs(
                job.target_id,
                job_id=str(job.id),
                limit=job.run_limit,
            )
        else:
            raise ValueError(f"Unknown reconcile mode: {job.mode!r}")
    except CancellationRequested:
        status = ReconStatus.CANCELLED.value
    except SoftTimeLimitExceeded:
        status = ReconStatus.FAILED.value
        error_summary = (
            "Job exceeded the soft time limit "
            f"({settings.RECON_SWEEP_SOFT_TIME_LIMIT_SECONDS}s) and was aborted."
        )
    except Exception as exc:
        status = ReconStatus.FAILED.value
        error_summary = str(exc)[:4000]

    job.status = status
    job.finished_at = timezone.now()
    job.error_summary = error_summary
    job.save(update_fields=["status", "finished_at", "error_summary"])
    release_lock(job)
