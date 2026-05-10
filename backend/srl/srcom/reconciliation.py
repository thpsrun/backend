import contextvars
import hashlib
import json
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import F, Model
from django.utils import timezone

from srl.models import ReconciliationItem, ReconciliationJob
from srl.models.reconciliation import (
    ReconAction,
    ReconPhase,
    ReconScope,
    ReconSourceOfTruth,
    ReconStatus,
)
from srl.tasks import dispatch_phase_2, dispatch_phase_3

LOCK_TTL_SECONDS = 3600
ERROR_SUMMARY_MAX_LEN = 4000
ITEM_BATCH_SIZE = 100
CANCEL_CHECK_INTERVAL_SECONDS = 2.0


class CancellationRequested(Exception):
    pass


_current_job: contextvars.ContextVar[ReconciliationJob | None] = contextvars.ContextVar(
    "recon_job",
    default=None,
)


@contextmanager
def reconciliation_context(
    job: ReconciliationJob,
) -> Iterator[None]:
    token = _current_job.set(job)
    try:
        yield
    finally:
        _current_job.reset(token)


def current_job() -> ReconciliationJob | None:
    return _current_job.get()


_last_cancel_check: contextvars.ContextVar[tuple[float, bool]] = contextvars.ContextVar(
    "recon_last_cancel_check",
    default=(0.0, False),
)


def check_cancelled() -> None:
    job = current_job()
    if job is None:
        return
    last_at, last_value = _last_cancel_check.get()
    now = time.monotonic()
    if last_value:
        raise CancellationRequested()
    if now - last_at < CANCEL_CHECK_INTERVAL_SECONDS:
        return
    job.refresh_from_db(fields=["cancel_requested"])
    _last_cancel_check.set((now, bool(job.cancel_requested)))
    if job.cancel_requested:
        raise CancellationRequested()


class _ModelPkEncoder(DjangoJSONEncoder):
    def default(  # type: ignore
        self,
        obj: Any,
    ) -> Any:
        if isinstance(obj, Model):
            return obj.pk
        return super().default(obj)


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, cls=_ModelPkEncoder))


def _compute_diff(
    existing: Any,
    defaults: dict,
) -> dict[str, dict[str, Any]]:
    diff: dict[str, dict[str, Any]] = {}
    for field, after in defaults.items():
        before = getattr(existing, field, None)
        before_is_model = isinstance(before, Model)
        after_is_model = isinstance(after, Model)
        if before_is_model or after_is_model:
            before_pk = before.pk if before_is_model else None
            after_pk = after.pk if after_is_model else None
            if before_pk == after_pk:
                continue
            diff[field] = {"before": before_pk, "after": after_pk}
            continue
        if before == after:
            continue
        diff[field] = {"before": _jsonable(before), "after": _jsonable(after)}
    return diff


_pending_items: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "recon_pending_items",
    default=None,
)
_pending_counts: contextvars.ContextVar[dict[str, int] | None] = contextvars.ContextVar(
    "recon_pending_counts",
    default=None,
)


def _ensure_pending_items() -> list:
    pending = _pending_items.get()
    if pending is None:
        pending = []
        _pending_items.set(pending)
    return pending


def _ensure_pending_counts() -> dict[str, int]:
    pending = _pending_counts.get()
    if pending is None:
        pending = {}
        _pending_counts.set(pending)
    return pending


def _bump_count(bucket: str) -> None:
    pending = _ensure_pending_counts()
    pending[bucket] = pending.get(bucket, 0) + 1


def _record_item(
    job: ReconciliationJob,
    record_type: str,
    record_id: Any,
    action: str,
    changes: dict,
    error: str = "",
) -> None:

    items = _ensure_pending_items()
    items.append(
        ReconciliationItem(
            job=job,
            record_type=record_type,
            record_id=str(record_id),
            action=action,
            changes=changes,
            error=error,
            phase=job.phase or ReconPhase.P1.value,
        ),
    )
    if record_type == "run":
        bucket = ReconAction(action).bucket
        if bucket:
            _bump_count(bucket)
    if len(items) >= ITEM_BATCH_SIZE:
        flush_counts()


def flush_counts() -> None:
    """Persist buffered ReconciliationItems and increment job counters atomically."""
    job = current_job()
    if job is None:
        return

    items = _pending_items.get() or []
    if items:
        from srl.models import ReconciliationItem

        ReconciliationItem.objects.bulk_create(items, batch_size=ITEM_BATCH_SIZE)
        items.clear()

    counts = _pending_counts.get()
    if counts:
        update_kwargs = {
            f"counts_{bucket}": F(f"counts_{bucket}") + delta
            for bucket, delta in counts.items()
        }
        ReconciliationJob.objects.filter(id=job.id).update(**update_kwargs)
        counts.clear()


def reconciliation_upsert_check(
    model: type[Model],
    *,
    defaults: dict,
    record_type: str,
    **lookup: Any,
) -> Any:
    """Upserts a ReconciliaitonItem, recording changes if they exist and starts a new one if none
    exists."""

    job = current_job()
    if job is None:
        instance, _ = model.objects.update_or_create(defaults=defaults, **lookup)
        return instance

    if not defaults:
        existing = model.objects.filter(**lookup).first()
        if existing is None:
            instance = model.objects.create(**lookup)
            _record_item(job, record_type, instance.pk, ReconAction.CREATED.value, {})
            return instance
        _record_item(
            job,
            record_type,
            existing.pk,
            ReconAction.SKIPPED_NO_CHANGE.value,
            {},
        )
        return existing

    existing = model.objects.filter(**lookup).first()

    if existing is None:
        instance = model.objects.create(**lookup, **defaults)
        _record_item(job, record_type, instance.pk, ReconAction.CREATED.value, {})
        return instance

    if getattr(existing, "sync_paused", False):
        _record_item(
            job,
            record_type,
            existing.pk,
            ReconAction.SKIPPED_LOCAL_WINS.value,
            {},
        )
        return existing

    if job.source_of_truth == ReconSourceOfTruth.THPS_RUN.value:
        _record_item(
            job,
            record_type,
            existing.pk,
            ReconAction.SKIPPED_LOCAL_WINS.value,
            {},
        )
        return existing

    diff = _compute_diff(existing, defaults)
    if not diff:
        _record_item(
            job,
            record_type,
            existing.pk,
            ReconAction.SKIPPED_NO_CHANGE.value,
            {},
        )
        return existing

    for field, after in defaults.items():
        setattr(existing, field, after)
    existing.save(update_fields=list(defaults.keys()))
    _record_item(job, record_type, existing.pk, ReconAction.UPDATED.value, diff)
    return existing


def _normalized_descriptor(
    descriptor: dict,
) -> str:
    return json.dumps(descriptor, sort_keys=True, default=str)


def lock_key_for(
    job: ReconciliationJob,
) -> str:
    if job.scope == ReconScope.LEADERBOARD.value:
        digest = hashlib.sha256(
            _normalized_descriptor(job.target_descriptor).encode(),
        ).hexdigest()
        return f"recon:lock:LEADERBOARD:{digest}"
    return f"recon:lock:{job.scope}:{job.target_id}"


def acquire_lock(
    job: ReconciliationJob,
) -> bool:
    return cache.add(lock_key_for(job), str(job.id), timeout=LOCK_TTL_SECONDS)


def release_lock(
    job: ReconciliationJob,
) -> None:
    cache.delete(lock_key_for(job))


def lock_holder(
    job: ReconciliationJob,
) -> str | None:
    return cache.get(lock_key_for(job))


def increment_pending(
    job_id: Any,
    n: int = 1,
) -> None:
    ReconciliationJob.objects.filter(id=job_id).update(
        pending_children=F("pending_children") + n,
    )


def decrement_pending(
    job_id: Any,
) -> bool:
    """Atomically decrement pending_children.

    Returns True if this caller drovethe counter to 0 while the job is still RUNNING (i.e. owns
    the finalize). This is useful to ensuring the task actually ends."""

    with connection.cursor() as cur:
        # TODO: Django 6.X doesn't have proper support to change this without it being raw SQL.
        # Will revisit this in a future update to handle this better.
        cur.execute(
            "UPDATE srl_reconciliationjob "
            "SET pending_children = pending_children - 1 "
            "WHERE id = %s AND pending_children > 0 "
            "RETURNING pending_children, status",
            [str(job_id)],
        )
        row = cur.fetchone()
    if row is None:
        return False
    pending, status = row
    return pending == 0 and status == ReconStatus.RUNNING.value


def record_failure(
    job_id: Any,
    message: str,
) -> None:
    snippet = (message or "")[:500]
    with transaction.atomic():
        try:
            job = ReconciliationJob.objects.select_for_update().get(id=job_id)
        except ReconciliationJob.DoesNotExist:
            return
        job.failure_count = (job.failure_count or 0) + 1
        if snippet:
            existing = job.error_summary or ""
            sep = "\n" if existing else ""
            combined = f"{existing}{sep}{snippet}"
            job.error_summary = combined[-ERROR_SUMMARY_MAX_LEN:]
        job.save(update_fields=["failure_count", "error_summary"])


def _next_phase(
    job: ReconciliationJob,
) -> str | None:
    """Return the next phase to dispatch, or None if current is not a valid pre-finalize state."""
    if job.phase == ReconPhase.P1.value:
        if job.scope == ReconScope.RUN.value:
            return ReconPhase.P3.value
        return ReconPhase.P2.value
    if job.phase == ReconPhase.P2.value:
        return ReconPhase.P3.value
    return None


def finalize_after_drain(
    job_id: Any,
) -> None:
    """Called when pending_children drains to 0 to finalize the job."""

    with transaction.atomic():
        try:
            job = ReconciliationJob.objects.select_for_update().get(id=job_id)
        except ReconciliationJob.DoesNotExist:
            return

        if job.status != ReconStatus.RUNNING.value:
            return

        if job.cancel_requested:
            _finalize(job, status=ReconStatus.CANCELLED.value)
            return

        if job.phase == ReconPhase.P1.value and (job.failure_count or 0) > 0:
            _finalize(job, status=ReconStatus.FAILED.value)
            return

        if job.phase == ReconPhase.P3.value:
            _finalize(job, status=ReconStatus.SUCCEEDED.value)
            return

        next_phase = _next_phase(job)
        if next_phase is None:
            _finalize(
                job,
                status=ReconStatus.FAILED.value,
                error=f"invalid phase transition: {job.phase}",
            )
            return

        job.phase = next_phase
        job.save(update_fields=["phase"])
        dispatch_target = next_phase

    job_id_str = str(job_id)
    dispatcher = (
        dispatch_phase_2 if dispatch_target == ReconPhase.P2.value else dispatch_phase_3
    )
    increment_pending(job_id_str, 1)
    try:
        dispatcher.delay(recon_job_id=job_id_str)
    except Exception:
        decrement_pending(job_id_str)
        raise


def _finalize(
    job: ReconciliationJob,
    *,
    status: str,
    error: str | None = None,
) -> None:
    job.status = status
    job.finished_at = timezone.now()
    if error:
        job.error_summary = error
    elif status == ReconStatus.FAILED.value and not job.error_summary:
        if (job.failure_count or 0) > 0:
            job.error_summary = (
                f"{job.failure_count} subtask(s) failed during phase {job.phase}"
            )
        else:
            job.error_summary = f"failure during phase {job.phase}"
    job.save(update_fields=["status", "finished_at", "error_summary"])

    from srl.srcom.recon_accumulators import clear_accumulators

    job_id_str = str(job.id)
    transaction.on_commit(lambda: release_lock(job))
    transaction.on_commit(lambda: clear_accumulators(job_id_str))


def _dispatch_with_pending(
    job_id: str,
    n: int,
    fn: Callable[[], Any],
) -> Any:
    """Increment pending_children by n, run fn(); on failure compensate by
    decrementing n times."""
    increment_pending(job_id, n)
    try:
        return fn()
    except Exception:
        for _ in range(n):
            decrement_pending(job_id)
        raise


def dispatch_with_recon(
    task: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Dispatch a Celery task via .delay(). If a reconciliation context is
    active, increment the job's pending_children and pass recon_job_id to the
    child so it joins the job."""
    job = current_job()
    if job is None:
        return task.delay(*args, **kwargs)
    job_id = str(job.id)
    return _dispatch_with_pending(
        job_id,
        1,
        lambda: task.delay(*args, recon_job_id=job_id, **kwargs),
    )


def dispatch_chain_with_recon(
    *signatures: Any,
) -> Any:
    """Dispatch a Celery chain. Each signature in order; later tasks run after
    earlier ones complete. Increments pending_children by len(signatures) and
    injects recon_job_id into each (cloned) signature's kwargs when active."""
    from celery import chain

    job = current_job()
    if job is None:
        return chain(*signatures).apply_async()
    job_id = str(job.id)

    # signature.clone(kwargs=...) silently drops the kwargs argument so this just mutates it so it
    # is better passed.
    cloned = []
    for sig in signatures:
        c = sig.clone()
        c.kwargs = {**(c.kwargs or {}), "recon_job_id": job_id}
        cloned.append(c)
    return _dispatch_with_pending(
        job_id,
        len(cloned),
        lambda: chain(*cloned).apply_async(),
    )


@contextmanager
def check_reconciliation(
    recon_job_id: str | None,
) -> Iterator[None]:
    """Used to check reconciliation and its context.

    If recon_job_id is set, re-establish the reconciliation context, capture failures into the job,
    flush counts on exit, then decrement pending_children and finalize when it hits 0.
    """
    if recon_job_id is None:
        yield
        return
    try:
        job = ReconciliationJob.objects.get(id=recon_job_id)
    except ReconciliationJob.DoesNotExist:
        yield
        return

    try:
        with reconciliation_context(job):
            try:
                yield
            except CancellationRequested:
                pass
            except Exception as exc:
                record_failure(recon_job_id, str(exc))
            finally:
                try:
                    flush_counts()
                except Exception:
                    pass
    finally:
        try:
            if decrement_pending(recon_job_id):
                finalize_after_drain(recon_job_id)
        except Exception:
            pass
