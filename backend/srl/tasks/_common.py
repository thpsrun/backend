import logging
from contextlib import contextmanager
from typing import Any, Iterator

from auditlog.context import clear_actor, set_actor
from auditlog.models import GameAuditEvent
from auditlog.recorders import record_event
from django.contrib.auth import get_user_model
from srl.models import SRCSyncTask
from srl.srcom.utils import variables_hash

logger = logging.getLogger(__name__)

RECALC_LOCK_TTL_SECONDS = 300
API_ACTIVITY_LOG_RETENTION_DAYS = 90


@contextmanager
def actor_from_user_id(
    user_id: int | None,
) -> Iterator[None]:
    """Re-establish actor context inside a Celery task body.

    ContextVar doesn't survive the broker hop, so callers thread `actor_user_id`
    through and the task re-binds it from the User row on entry."""

    if user_id is not None:
        try:
            User = get_user_model()
            user = User.objects.filter(pk=user_id).first()
            if user is not None:
                set_actor(
                    user=user,
                    label=(getattr(user, "username", "") or "")[:128],
                )
        except Exception:
            logger.exception(
                "actor_from_user_id_failed",
                extra={"user_id": user_id},
            )
    try:
        yield
    finally:
        clear_actor()


def save_sync_task(
    sync_task: "SRCSyncTask",
    **fields: Any,
) -> None:
    if not fields:
        sync_task.save()
        _emit_sync_audit(sync_task)
        return

    update_fields = list(fields.keys())
    for key, value in fields.items():
        setattr(sync_task, key, value)

    if "updated_at" not in update_fields:
        update_fields.append("updated_at")
    sync_task.save(update_fields=update_fields)
    _emit_sync_audit(sync_task)


def _emit_sync_audit(
    sync_task: "SRCSyncTask",
) -> None:
    try:
        run = getattr(sync_task, "run", None)
        if run is None:
            return
        game_id = getattr(run, "game_id", None)
        if not game_id:
            return

        record_event(
            game=game_id,
            event_type=GameAuditEvent.EventType.SRC_SYNC_ATTEMPT,
            summary=(
                f"SRC {sync_task.action} {sync_task.status} "
                f"(run {run.pk}, attempt {sync_task.attempts})"
            ),
            target=sync_task,
            payload={
                "run_id": run.pk,
                "action": sync_task.action,
                "status": sync_task.status,
                "attempts": sync_task.attempts,
                "error_category": getattr(sync_task, "error_category", "") or "",
                "last_error": (sync_task.last_error or "")[:500],
            },
        )
    except Exception:
        logger.exception(
            "sync_audit_emit_failed",
            extra={"sync_task_id": getattr(sync_task, "id", None)},
        )


def record_sync_outcome(
    sync_task: "SRCSyncTask",
    *,
    status: str,
    category: str,
    exc: Exception,
) -> None:
    """Single writer for sync_src_settings failure/pending paths.

    Replaces seven copy-paste blocks that all set
    (status, attempts, error_category=category, last_error=str(exc)[:1000])."""
    save_sync_task(
        sync_task,
        status=status,
        attempts=sync_task.attempts,
        error_category=category,
        last_error=str(exc)[:1000],
    )


def recalc_lock_key(
    leaderboard_dict: dict,
) -> str:
    """Stable Redis lock key for a leaderboard variant."""
    game_id = leaderboard_dict.get("game_id") or ""
    category_id = leaderboard_dict.get("category_id") or ""
    level_id = leaderboard_dict.get("level_id") or ""
    runtype = leaderboard_dict.get("runtype") or ""
    var_map = leaderboard_dict.get("variable_value_map") or {}
    vh = variables_hash(var_map) if var_map else ""
    return f"recalc:lock:{game_id}:{category_id}:{level_id}:{vh}:{runtype}"
