from datetime import timedelta

from django.http import HttpRequest
from django.utils import timezone
from ninja import Query, Router, Status
from srl.models import SRCSyncTask
from srl.tasks import sync_src_action, sync_src_settings

from api.permissions import authed
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.submissions import (
    SyncLogEntry,
    SyncLogResponse,
    SyncLogRunSchema,
    SyncRetryResponse,
)

router = Router()


@router.get(
    "/admin/sync-logs",
    auth=authed("sync_logs.admin"),
    response={
        200: SyncLogResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="SRC Sync Logs (Superuser)",
    description=(
        "Superuser access only: Returns SRC sync task logs with full error details. "
        "Filterable by status, action, game, and max age. Ordered by most recent first."
    ),
)
def get_sync_logs(
    request: HttpRequest,
    status: str | None = Query(
        None,
        description="Filter by status: pending, synced, or failed",
    ),
    action: str | None = Query(
        None,
        description=("Filter by action: verify, reject, change_players, or edit_run"),
    ),
    error_category: str | None = Query(
        None,
        description=(
            "Filter by error category: auth, api_contract, "
            "api_server, validation, rate_limit, network, "
            "mailbox, unknown."
        ),
    ),
    game_id: str | None = Query(
        None,
        description="Filter by game ID",
    ),
    max_age_hours: float | None = Query(
        None,
        gt=0,
        description=(
            "Only return tasks created within the last N hours. "
            "Accepts fractional values (e.g. 0.5, 24, 168)."
        ),
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Status:
    qs = SRCSyncTask.objects.select_related(
        "run__game",
        "run__category",
        "run__level",
        "moderator",
    ).order_by("-created_at")

    if status:
        qs = qs.filter(status=status)
    if action:
        qs = qs.filter(action=action)
    if error_category:
        qs = qs.filter(error_category=error_category)
    if game_id:
        qs = qs.filter(run__game_id=game_id)
    if max_age_hours is not None:
        cutoff = timezone.now() - timedelta(hours=max_age_hours)
        qs = qs.filter(created_at__gte=cutoff)

    total = qs.count()
    tasks = qs[offset : offset + limit]

    results = []
    for task in tasks:
        run = task.run
        results.append(
            SyncLogEntry(
                id=task.id,
                run=SyncLogRunSchema(
                    id=run.id,
                    game_name=run.game.name,
                    game_slug=run.game.slug,
                    category_name=(run.category.name if run.category else None),
                    level_name=(run.level.name if run.level else None),
                    url=run.url,
                ),
                action=task.action,
                status=task.status,
                payload=task.payload,
                moderator_name=(task.moderator.name if task.moderator else None),
                attempts=task.attempts,
                max_attempts=task.max_attempts,
                last_error=task.last_error,
                error_category=task.error_category,
                created_at=task.created_at,
                updated_at=task.updated_at,
            ),
        )

    return Status(
        200,
        SyncLogResponse(count=total, results=results),
    )


@router.post(
    "/admin/sync-logs/{task_id}/retry",
    auth=authed("sync_logs.admin"),
    response={
        200: SyncRetryResponse,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Retry Failed Sync Task (Superuser)",
    description=(
        "Superuser access only: Resets a failed SRC sync task to pending and re-queues it."
    ),
)
def retry_sync_task(
    request: HttpRequest,
    task_id: int,
) -> Status:
    try:
        sync_task = SRCSyncTask.objects.get(id=task_id)
    except SRCSyncTask.DoesNotExist:
        return Status(
            404,
            ErrorResponse(
                error="Sync task not found.",
                details=None,
            ),
        )

    if sync_task.status != SRCSyncTask.Status.FAILED:
        return Status(
            400,
            ErrorResponse(
                error=(
                    f"Can only retry failed tasks. "
                    f"Current status: {sync_task.status}."
                ),
                details=None,
            ),
        )

    sync_task.status = SRCSyncTask.Status.PENDING
    sync_task.attempts = 0
    sync_task.last_error = ""
    sync_task.error_category = ""
    sync_task.save(
        update_fields=[
            "status",
            "attempts",
            "last_error",
            "error_category",
            "updated_at",
        ],
    )
    if sync_task.action == SRCSyncTask.ActionType.EDIT_RUN:
        sync_src_settings.delay(sync_task.id)
    else:
        sync_src_action.delay(sync_task.id)

    return Status(
        200,
        {"task_id": sync_task.id, "message": "Sync task re-queued."},
    )
