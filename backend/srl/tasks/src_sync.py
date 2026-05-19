from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import requests as http_requests
import sentry_sdk
from celery import shared_task
from django.conf import settings as cfg

from srl.encryption import decrypt_src_key
from srl.models import SRCSyncTask
from srl.srcom.v2 import is_v2_enabled
from srl.srcom.v2.client import (
    SrcV2AuthError,
    SrcV2Client,
    SrcV2ContractError,
    SrcV2Error,
    SrcV2NetworkError,
    SrcV2PermissionError,
    SrcV2RateLimited,
    SrcV2ServerError,
    SrcV2ValidationError,
)
from srl.srcom.v2.errors import ErrorCategory
from srl.srcom.v2.session import (
    refresh_bot_session as _refresh_bot_session,
)
from srl.srcom.v2.session import (
    trip_circuit_breaker as _trip_circuit_breaker,
)

from ._common import (
    actor_from_user_id,
    record_sync_outcome,
    save_sync_task,
)

V2_RETRY_BACKOFF = [30, 60, 120, 300, 600]
SRC_API_BASE = "https://www.speedrun.com/api/v1"
SRC_TIMEOUT = 15
RETRY_BACKOFF = [30, 60, 120, 300, 600]


# Re-export so tests can patch them on this module.
refresh_bot_session = _refresh_bot_session
trip_circuit_breaker = _trip_circuit_breaker


@shared_task(name="srl.tasks.sync_src_action")
def sync_src_action(
    sync_task_id: int,
    *,
    actor_user_id: int | None = None,
) -> None:
    """Execute an SRC v1 API sync operation (verify/reject/change-players) with retry.

    On retryable failures (420, 503, connection errors), re-queues itself with exponential
    backoff. After max_attempts, marks the task as failed and reports to Sentry."""

    with actor_from_user_id(actor_user_id):
        try:
            sync_task = SRCSyncTask.objects.select_related(
                "run",
                "moderator__user",
            ).get(id=sync_task_id)
        except SRCSyncTask.DoesNotExist:
            return

        if sync_task.status == SRCSyncTask.Status.SYNCED:
            return

        user = sync_task.moderator.user if sync_task.moderator else None
        if not user or not user.encrypted_api_key:
            save_sync_task(
                sync_task,
                status=SRCSyncTask.Status.FAILED,
                last_error="No SRC API key stored for moderator",
            )
            sentry_sdk.capture_message(
                f"SRC sync failed: no valid API key for sync task {sync_task_id}",
                level="error",
            )
            return

        try:
            api_key = decrypt_src_key(user.encrypted_api_key)
        except Exception as e:
            save_sync_task(
                sync_task,
                status=SRCSyncTask.Status.FAILED,
                last_error=f"Cannot decrypt SRC API key: {e}",
            )
            sentry_sdk.capture_message(
                f"SRC sync failed: cannot decrypt API key for sync task {sync_task_id}",
                level="error",
            )
            return

        run_id = sync_task.run.id
        if sync_task.action in (
            SRCSyncTask.ActionType.VERIFY,
            SRCSyncTask.ActionType.REJECT,
        ):
            url = f"{SRC_API_BASE}/runs/{run_id}/status"
        elif sync_task.action == SRCSyncTask.ActionType.CHANGE_PLAYERS:
            url = f"{SRC_API_BASE}/runs/{run_id}/players"
        else:
            save_sync_task(
                sync_task,
                status=SRCSyncTask.Status.FAILED,
                last_error=f"Unknown action: {sync_task.action}",
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
                actor_user_id=actor_user_id,
            )
            return

        if response.status_code in (400, 401, 403, 404):
            save_sync_task(
                sync_task,
                status=SRCSyncTask.Status.FAILED,
                attempts=sync_task.attempts,
                last_error=(
                    f"SRC returned {response.status_code}: {response.text[:500]}"
                ),
            )
            sentry_sdk.capture_message(
                f"SRC sync permanently failed for task "
                f"{sync_task_id}: HTTP {response.status_code}",
                level="error",
            )
            return

        if response.status_code in (420, 503):
            _handle_retryable_failure(
                sync_task,
                f"SRC returned {response.status_code}: {response.text[:200]}",
                actor_user_id=actor_user_id,
            )
            return

        if response.status_code not in (200, 204):
            _handle_retryable_failure(
                sync_task,
                f"Unexpected status {response.status_code}: {response.text[:200]}",
                actor_user_id=actor_user_id,
            )
            return

        save_sync_task(
            sync_task,
            status=SRCSyncTask.Status.SYNCED,
            attempts=sync_task.attempts,
            last_error="",
        )


def _handle_retryable_failure(
    sync_task: "SRCSyncTask",
    error_msg: str,
    actor_user_id: int | None = None,
) -> None:
    """Re-queue with exponential backoff, or mark FAILED after max_attempts."""

    if sync_task.attempts >= sync_task.max_attempts:
        save_sync_task(
            sync_task,
            status=sync_task.Status.FAILED,
            attempts=sync_task.attempts,
            last_error=error_msg,
        )
        sentry_sdk.capture_message(
            f"SRC sync task {sync_task.id} failed after "  # type: ignore
            f"{sync_task.attempts} attempts: {error_msg}",
            level="error",
        )
        return

    save_sync_task(
        sync_task,
        attempts=sync_task.attempts,
        last_error=error_msg,
    )

    backoff_idx = min(
        sync_task.attempts - 1,
        len(RETRY_BACKOFF) - 1,
    )
    delay = RETRY_BACKOFF[backoff_idx]
    sync_src_action.apply_async(
        args=[sync_task.id],  # type: ignore
        kwargs={"actor_user_id": actor_user_id},
        countdown=delay,
    )


@shared_task(name="srl.tasks.sync_src_settings")
def sync_src_settings(
    sync_task_id: int,
    *,
    actor_user_id: int | None = None,
) -> None:
    """Push a local run edit to SRC via v2 PutRunSettings."""

    with actor_from_user_id(actor_user_id):
        try:
            sync_task = SRCSyncTask.objects.select_related("run").get(id=sync_task_id)
        except SRCSyncTask.DoesNotExist:
            return

        if sync_task.status == SRCSyncTask.Status.SYNCED:
            return

        if not is_v2_enabled():
            save_sync_task(
                sync_task,
                status=SRCSyncTask.Status.FAILED,
                error_category=ErrorCategory.UNKNOWN,
                last_error="v2 disabled by kill switch",
            )
            return

        sync_task.attempts += 1

        try:
            client = SrcV2Client()
            client.put_run_settings(sync_task.payload)

            save_sync_task(
                sync_task,
                status=SRCSyncTask.Status.SYNCED,
                attempts=sync_task.attempts,
                error_category="",
                last_error="",
            )
            return

        except SrcV2PermissionError as exc:
            record_sync_outcome(
                sync_task,
                status=SRCSyncTask.Status.FAILED,
                category=ErrorCategory.AUTH,
                exc=exc,
            )
            sentry_sdk.capture_message(
                (
                    f"SRC v2 PutRunSettings forbidden on sync task "
                    f"{sync_task.id} (run {sync_task.run_id}); bot may have "  # type: ignore
                    f"lost moderator status on the game."
                ),
                level="error",
            )
            return

        except SrcV2AuthError as exc:
            record_sync_outcome(
                sync_task,
                status=SRCSyncTask.Status.PENDING,
                category=ErrorCategory.AUTH,
                exc=exc,
            )
            refresh_bot_session.delay()
            if sync_task.attempts < sync_task.max_attempts:
                sync_src_settings.apply_async(
                    args=[sync_task_id],  # type: ignore
                    kwargs={"actor_user_id": actor_user_id},
                    countdown=30,
                )
            else:
                save_sync_task(sync_task, status=SRCSyncTask.Status.FAILED)
            return

        except SrcV2ContractError as exc:
            record_sync_outcome(
                sync_task,
                status=SRCSyncTask.Status.FAILED,
                category=ErrorCategory.API_CONTRACT,
                exc=exc,
            )
            trip_circuit_breaker(
                reason=(
                    f"PutRunSettings response did not match v2 contract on "
                    f"sync task {sync_task.id}: {exc}"  # type: ignore
                ),
                category=ErrorCategory.API_CONTRACT,
            )
            return

        except SrcV2ValidationError as exc:
            record_sync_outcome(
                sync_task,
                status=SRCSyncTask.Status.FAILED,
                category=ErrorCategory.VALIDATION,
                exc=exc,
            )
            return

        except (SrcV2RateLimited, SrcV2ServerError, SrcV2NetworkError) as exc:
            if isinstance(exc, SrcV2RateLimited):
                category = ErrorCategory.RATE_LIMIT
            elif isinstance(exc, SrcV2ServerError):
                category = ErrorCategory.API_SERVER
            else:
                category = ErrorCategory.NETWORK

            if sync_task.attempts < sync_task.max_attempts:
                countdown = V2_RETRY_BACKOFF[
                    min(sync_task.attempts - 1, len(V2_RETRY_BACKOFF) - 1)
                ]
                record_sync_outcome(
                    sync_task,
                    status=SRCSyncTask.Status.PENDING,
                    category=category,
                    exc=exc,
                )
                sync_src_settings.apply_async(
                    args=[sync_task_id],  # type: ignore
                    kwargs={"actor_user_id": actor_user_id},
                    countdown=countdown,
                )
            else:
                record_sync_outcome(
                    sync_task,
                    status=SRCSyncTask.Status.FAILED,
                    category=category,
                    exc=exc,
                )
            return

        except SrcV2Error as exc:
            record_sync_outcome(
                sync_task,
                status=SRCSyncTask.Status.FAILED,
                category=exc.category,
                exc=exc,
            )
            return


@shared_task(name="srl.tasks.replay_failed_edits")
def replay_failed_edits() -> int:
    """Re-queue recent failed EDIT_RUN tasks when the kill switch flips back on.

    Tasks older than SRC_V2_REPLAY_MAX_AGE_DAYS are intentionally skipped; stale
    edits should be reviewed individually. Also no-ops if the v2 kill switch is
    still off, otherwise the re-queued tasks would fail immediately."""

    if not is_v2_enabled():
        return 0

    cutoff = datetime.now(dt_timezone.utc) - timedelta(
        days=getattr(cfg, "SRC_V2_REPLAY_MAX_AGE_DAYS", 7),
    )
    qs = SRCSyncTask.objects.filter(
        action=SRCSyncTask.ActionType.EDIT_RUN,
        status=SRCSyncTask.Status.FAILED,
        created_at__gte=cutoff,
    )
    count = 0
    for task in qs:
        task.status = SRCSyncTask.Status.PENDING
        task.error_category = ""
        task.last_error = ""
        task.attempts = 0
        task.save(
            update_fields=[
                "status",
                "error_category",
                "last_error",
                "attempts",
                "updated_at",
            ],
        )
        sync_src_settings.delay(task.id)  # type: ignore
        count += 1
    return count
