import contextvars
import hashlib
import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import F, Model

from srl.models import ReconciliationItem, ReconciliationJob
from srl.models.reconciliation import (
    ReconAction,
    ReconPhase,
    ReconScope,
    ReconSourceOfTruth,
)

LOCK_TTL_SECONDS = 3600
ITEM_BATCH_SIZE = 100
CANCEL_CHECK_INTERVAL_SECONDS = 2.0
_COUNTED_RECORD_TYPES = {"run", "series_game"}

logger = logging.getLogger(__name__)


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
    """Bind `job` and reset every job-scoped contextvar for the duration of the context."""
    job_token = _current_job.set(job)
    cancel_token = _last_cancel_check.set((0.0, False))
    items_token = _pending_items.set([])
    counts_token = _pending_counts.set({})
    try:
        yield
    finally:
        _current_job.reset(job_token)
        _last_cancel_check.reset(cancel_token)
        _pending_items.reset(items_token)
        _pending_counts.reset(counts_token)


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


def _bump_count(
    bucket: str,
) -> None:
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
    if record_type in _COUNTED_RECORD_TYPES:
        bucket = ReconAction(action).bucket
        if bucket:
            _bump_count(bucket)
    if len(items) >= ITEM_BATCH_SIZE:
        flush_counts()


def record_reconciliation_item(
    record_type: str,
    record_id: Any,
    action: str,
    *,
    changes: dict | None = None,
    error: str = "",
) -> None:
    """Public helper to record a ReconciliationItem from outside the correct path."""
    job = current_job()
    if job is None:
        return
    _record_item(
        job,
        record_type,
        record_id,
        action,
        changes or {},
        error,
    )


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
    """Upserts a ReconciliationItem, recording changes if they exist and starts a new one if none
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
