import logging

import requests as http_requests
import sentry_sdk
from celery import shared_task
from django.core.management import call_command
from django.db import transaction
from django.db.models import Min

from srl.leaderboard.recalculation import (
    build_leaderboard_metadata,
    clear_leaderboard_history,
    get_leaderboard_time_column,
    get_runs_for_leaderboard,
    process_leaderboard,
)
from srl.leaderboard.streaks import apply_streak_to_run


@shared_task
def recalculate_leaderboard_task(
    leaderboard_dict: dict,
) -> None:
    """Recalculate points and history for a single leaderboard variant.

    Clears existing RunHistory for the variant, then rebuilds from scratch.
    Dispatched by recalculate_run() when a run is verified.
    """
    (
        game_time_columns,
        game_is_ce,
        value_timings,
        variable_timings,
        category_timings,
    ) = build_leaderboard_metadata([leaderboard_dict])

    with transaction.atomic():
        clear_leaderboard_history(leaderboard_dict)
        process_leaderboard(
            leaderboard_dict,
            dry_run=False,
            game_is_ce=game_is_ce,
            game_time_columns=game_time_columns,
            value_timings=value_timings,
            variable_timings=variable_timings,
            category_timings=category_timings,
        )


@shared_task
def recalculate_streaks_task(
    leaderboard_dict: dict,
) -> None:
    """Recalculate streak bonus for the current WR on a leaderboard variant.

    Finds the fastest verified run on the leaderboard and applies streak logic.
    Only dispatched when recalculate_run detects a potential WR change.
    """
    time_col = get_leaderboard_time_column(leaderboard_dict)

    runs_qs = (
        get_runs_for_leaderboard(leaderboard_dict)
        .exclude(**{f"{time_col}__lte": 0})
        .exclude(**{f"{time_col}__isnull": True})
    )

    # Find the fastest run (WR) on this leaderboard via DB aggregate
    result = runs_qs.aggregate(min_time=Min(time_col))
    wr_time = result["min_time"]
    if wr_time is None:
        return

    wr_run = (
        runs_qs.filter(**{time_col: wr_time})
        .select_related("game")
        .prefetch_related("players")
        .first()
    )
    if not wr_run:
        return

    result = apply_streak_to_run(wr_run)
    if result is not None:
        new_bonus, new_points = result
        wr_run.bonus = new_bonus
        wr_run.points = new_points
        wr_run.save(update_fields=["bonus", "points"])


@shared_task
def build_streaks_task() -> None:
    """Run the full build_streaks management command.

    Used by the daily Celery Beat schedule (midnight UTC) to award monthly
    anniversary bonuses to current WR holders.
    """
    call_command("build_streaks")


logger = logging.getLogger(__name__)

SRC_API_BASE = "https://www.speedrun.com/api/v1"
SRC_TIMEOUT = 15

# Backoff schedule in seconds: 30s, 60s, 120s, 300s, 600s
RETRY_BACKOFF = [30, 60, 120, 300, 600]


@shared_task
def sync_src_action(
    sync_task_id: int,
) -> None:
    """Execute an SRC API sync operation with retry logic.

    Retrieves the SRCSyncTask, decrypts the moderator's API key, and
    calls the appropriate SRC endpoint. On retryable failures (420, 503,
    connection errors), re-queues itself with exponential backoff. After
    5 failed attempts, marks the task as failed and reports to Sentry.
    """
    from srl.encryption import decrypt_src_key
    from srl.models import SRCSyncTask

    try:
        sync_task = SRCSyncTask.objects.select_related(
            "run",
            "moderator__user",
        ).get(id=sync_task_id)
    except SRCSyncTask.DoesNotExist:
        logger.error("SRCSyncTask %d not found.", sync_task_id)
        return

    if sync_task.status == SRCSyncTask.Status.SYNCED:
        return

    user = sync_task.moderator.user
    if not user or not user.encrypted_api_key:
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.last_error = "No SRC API key stored for moderator"
        sync_task.save(
            update_fields=["status", "last_error", "updated_at"],
        )
        sentry_sdk.capture_message(
            f"SRC sync failed: no valid API key for " f"sync task {sync_task_id}",
            level="error",
        )
        return

    try:
        api_key = decrypt_src_key(user.encrypted_api_key)
    except Exception as e:
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.last_error = f"Cannot decrypt SRC API key: {e}"
        sync_task.save(
            update_fields=["status", "last_error", "updated_at"],
        )
        sentry_sdk.capture_message(
            f"SRC sync failed: no valid API key for " f"sync task {sync_task_id}",
            level="error",
        )
        return

    run_id = sync_task.run_id
    if sync_task.action in (
        SRCSyncTask.ActionType.VERIFY,
        SRCSyncTask.ActionType.REJECT,
    ):
        url = f"{SRC_API_BASE}/runs/{run_id}/status"
    elif sync_task.action == SRCSyncTask.ActionType.CHANGE_PLAYERS:
        url = f"{SRC_API_BASE}/runs/{run_id}/players"
    else:
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.last_error = f"Unknown action: {sync_task.action}"
        sync_task.save(
            update_fields=["status", "last_error", "updated_at"],
        )
        return

    sync_task.attempts += 1
    try:
        response = http_requests.put(
            url,
            json=sync_task.payload,
            headers={"X-API-Key": api_key},
            timeout=SRC_TIMEOUT,
        )
    except http_requests.RequestException as e:
        _handle_retryable_failure(
            sync_task,
            f"Connection error: {e}",
        )
        return

    # Permanent failures (don't retry)
    if response.status_code in (400, 401, 403, 404):
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.last_error = (
            f"SRC returned {response.status_code}: " f"{response.text[:500]}"
        )
        sync_task.save(
            update_fields=[
                "status",
                "attempts",
                "last_error",
                "updated_at",
            ],
        )
        sentry_sdk.capture_message(
            f"SRC sync permanently failed for task "
            f"{sync_task_id}: HTTP {response.status_code}",
            level="error",
        )
        return

    # Retryable failures (420 rate limit, 503 unavailable)
    if response.status_code in (420, 503):
        _handle_retryable_failure(
            sync_task,
            f"SRC returned {response.status_code}: " f"{response.text[:200]}",
        )
        return

    if response.status_code not in (200, 204):
        _handle_retryable_failure(
            sync_task,
            f"Unexpected status {response.status_code}: " f"{response.text[:200]}",
        )
        return

    # Success
    sync_task.status = SRCSyncTask.Status.SYNCED
    sync_task.last_error = ""
    sync_task.save(
        update_fields=[
            "status",
            "attempts",
            "last_error",
            "updated_at",
        ],
    )
    logger.info(
        "SRC sync task %d completed: %s run %s",
        sync_task_id,
        sync_task.action,
        run_id,
    )


def _handle_retryable_failure(
    sync_task: "SRCSyncTask",
    error_msg: str,
) -> None:
    """Handles attempts to retry the SRC API.

    Re-queues the task with exponential backoff if under max_attempts.
    After max_attempts, marks as failed and reports to Sentry.
    """
    sync_task.last_error = error_msg
    sync_task.save(
        update_fields=["attempts", "last_error", "updated_at"],
    )

    if sync_task.attempts >= sync_task.max_attempts:
        sync_task.status = sync_task.Status.FAILED
        sync_task.save(update_fields=["status", "updated_at"])
        sentry_sdk.capture_message(
            f"SRC sync task {sync_task.id} failed after "
            f"{sync_task.attempts} attempts: {error_msg}",
            level="error",
        )
        logger.error(
            "SRC sync task %d failed after %d attempts: %s",
            sync_task.id,
            sync_task.attempts,
            error_msg,
        )
        return

    backoff_idx = min(
        sync_task.attempts - 1,
        len(RETRY_BACKOFF) - 1,
    )
    delay = RETRY_BACKOFF[backoff_idx]
    logger.warning(
        "SRC sync task %d attempt %d failed, retrying in %ds: %s",
        sync_task.id,
        sync_task.attempts,
        delay,
        error_msg,
    )
    sync_src_action.apply_async(
        args=[sync_task.id],
        countdown=delay,
    )
