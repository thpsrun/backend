from collections import defaultdict
from uuid import UUID

from django.db.models import Count
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError
from srl.models import ReconciliationJob
from srl.models.reconciliation import ReconAction, ReconStatus
from srl.srcom.reconciliation import acquire_lock, lock_holder, release_lock
from srl.tasks import run_bounded_game_reconciliation

from api.permissions import authed
from api.v1.schemas.reconciliation import (
    CancelConflictOut,
    ConflictOut,
    ItemListOut,
    JobDetailOut,
    JobListOut,
    JobOut,
    ReconcileRequest,
    ReconcileScope,
)

router = Router()

RECENT_ITEMS_LIMIT = 20

ACTIVE_STATUSES = {ReconStatus.PENDING.value, ReconStatus.RUNNING.value}

_BREAKDOWN_BUCKETS = ("created", "updated", "skipped", "failed")


def _compute_breakdown(
    job: ReconciliationJob,
) -> dict[str, dict[str, int]]:
    """Group ReconciliationItem rows by (record_type, action) and reshape into
    {record_type: {created, updated, skipped, failed}}. Each record_type that
    has any items appears as a key; buckets always contain all four counters.

    Both SKIPPED_LOCAL_WINS and SKIPPED_NO_CHANGE map to the "skipped" bucket
    via ReconAction.bucket, so we accumulate with += rather than =."""
    rows = job.items.values("record_type", "action").annotate(n=Count("id"))

    breakdown: dict[str, dict[str, int]] = defaultdict(
        lambda: {b: 0 for b in _BREAKDOWN_BUCKETS},
    )
    for row in rows:
        try:
            bucket = ReconAction(row["action"]).bucket
        except ValueError:
            continue
        if bucket is None:
            continue
        breakdown[row["record_type"]][bucket] += row["n"]

    return dict(breakdown)


def _job_to_out(
    job: ReconciliationJob,
) -> dict:
    return {
        "id": job.id,
        "scope": job.scope,
        "target_id": job.target_id or None,
        "target_descriptor": job.target_descriptor or None,
        "source_of_truth": job.source_of_truth,
        "status": job.status,
        "phase": job.phase,
        "counts": job.counts,
        "requested_by": job.requested_by.username if job.requested_by else None,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error_summary": job.error_summary,
        "celery_task_id": job.celery_task_id,
    }


def _dispatch_recon_job(
    job_id: str,
) -> None:
    run_bounded_game_reconciliation.delay(job_id)


@router.post(
    "/admin/reconcile",
    auth=authed("reconcile.admin"),
    response={202: JobOut, 409: ConflictOut},
    summary="Start Reconciliation Job (Superuser)",
    description=(
        "Creates and queues a reconciliation job for the given scope and target. "
        "Returns 409 if a reconciliation is already in progress for the same target. "
        "Superuser access only."
    ),
)
def start_reconciliation(
    request: HttpRequest,
    payload: ReconcileRequest,
):
    if payload.scope != ReconcileScope.GAME:
        raise HttpError(422, "Only GAME-scope reconciliation is supported.")

    job = ReconciliationJob.objects.create(
        scope=payload.scope.value,
        target_id=payload.target_id or "",
        target_descriptor=(
            payload.target_descriptor.model_dump() if payload.target_descriptor else {}
        ),
        source_of_truth=payload.source_of_truth.value,
        requested_by=request.user if request.user.is_authenticated else None,
    )
    if not acquire_lock(job):
        existing_id = lock_holder(job)
        job.delete()
        return 409, ConflictOut(
            detail="A reconciliation is already in progress for this target.",
            existing_job_id=UUID(existing_id),
        )
    _dispatch_recon_job(str(job.id))
    return 202, _job_to_out(job)


@router.get(
    "/admin/reconcile",
    auth=authed("reconcile.admin"),
    response=JobListOut,
    summary="List Reconciliation Jobs (Superuser)",
    description=(
        "Returns a paginated list of reconciliation jobs. "
        "Filterable by status, scope, and target_id. "
        "Superuser access only."
    ),
)
def list_jobs(
    request: HttpRequest,
    status: str | None = None,
    scope: str | None = None,
    target_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    qs = ReconciliationJob.objects.all().order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    if scope:
        qs = qs.filter(scope=scope)
    if target_id:
        qs = qs.filter(target_id=target_id)
    total = qs.count()
    items = [_job_to_out(j) for j in qs[offset : offset + limit]]
    return {"items": items, "total": total}


@router.get(
    "/admin/reconcile/{job_id}",
    auth=authed("reconcile.admin"),
    response=JobDetailOut,
    summary="Get Reconciliation Job Detail (Superuser)",
    description=(
        "Returns detailed information about a reconciliation job, "
        "including the most recent items and a per-record-type breakdown "
        "of all reconciliation items. "
        "Superuser access only."
    ),
)
def get_job(
    request: HttpRequest,
    job_id: UUID,
):
    job = get_object_or_404(ReconciliationJob, id=job_id)
    out = _job_to_out(job)
    out["recent_items"] = list(
        job.items.order_by("-id")[:RECENT_ITEMS_LIMIT].values(
            "record_type",
            "record_id",
            "action",
            "phase",
            "changes",
            "error",
        ),
    )
    out["breakdown"] = _compute_breakdown(job)
    return out


@router.get(
    "/admin/reconcile/{job_id}/items",
    auth=authed("reconcile.admin"),
    response=ItemListOut,
    summary="List Reconciliation Job Items (Superuser)",
    description=(
        "Returns a paginated list of reconciliation items for a given job. "
        "Filterable by phase, action, and record_type. "
        "Superuser access only."
    ),
)
def list_items(
    request: HttpRequest,
    job_id: UUID,
    phase: str | None = None,
    action: str | None = None,
    record_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    job = get_object_or_404(ReconciliationJob, id=job_id)
    qs = job.items.order_by("id")
    if phase:
        qs = qs.filter(phase=phase)
    if action:
        qs = qs.filter(action=action)
    if record_type:
        qs = qs.filter(record_type=record_type)
    total = qs.count()
    rows = list(
        qs[offset : offset + limit].values(
            "id",
            "record_type",
            "record_id",
            "action",
            "phase",
            "changes",
            "error",
            "created_at",
        ),
    )
    return {"items": rows, "total": total}


@router.post(
    "/admin/reconcile/{job_id}/cancel",
    auth=authed("reconcile.admin"),
    response={200: JobOut, 409: CancelConflictOut},
    summary="Cancel Reconciliation Job (Superuser)",
    description=(
        "Requests cancellation of a pending or running reconciliation job. "
        "Returns 409 if the job is already in a terminal state. "
        "Superuser access only."
    ),
)
def cancel_job(
    request: HttpRequest,
    job_id: UUID,
):
    job = get_object_or_404(ReconciliationJob, id=job_id)
    if job.status not in ACTIVE_STATUSES:
        return 409, CancelConflictOut(detail=f"Job is already {job.status.lower()}.")

    if job.cancel_requested:
        # Idempotent: a second cancel request is a no-op.
        return 200, _job_to_out(job)

    job.cancel_requested = True
    job.save(update_fields=["cancel_requested"])

    if job.status == ReconStatus.PENDING.value and not job.celery_task_id:
        # No worker has claimed this; finalize directly so it doesn't sit forever.
        job.status = ReconStatus.CANCELLED.value
        job.finished_at = timezone.now()
        job.error_summary = "cancelled before worker picked up task"
        job.save(update_fields=["status", "finished_at", "error_summary"])
        release_lock(job)
        return 200, _job_to_out(job)

    if job.celery_task_id:
        try:
            from website.celery import app as celery_app

            celery_app.control.revoke(job.celery_task_id, terminate=False)
        except Exception:
            pass
    return 200, _job_to_out(job)
