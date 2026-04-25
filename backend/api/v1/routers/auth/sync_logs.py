import logging

from django.http import HttpRequest
from ninja import Query, Router, Status
from ninja.responses import codes_4xx
from srl.models import SRCSyncTask

from api.permissions import authed
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.submissions import (
    SyncLogEntry,
    SyncLogResponse,
    SyncLogRunSchema,
    SyncRetryResponse,
)

logger = logging.getLogger(__name__)

router = Router()


@router.get(
    "/admin/sync-logs",
    auth=authed("sync_logs.admin"),
    response={200: SyncLogResponse, codes_4xx: ErrorResponse},
    summary="SRC Sync Logs (Superuser)",
    description=(
        "Returns SRC sync task logs with full error details. "
        "Superuser access only. Filterable by status, action, "
        "and game. Ordered by most recent first."
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
        description=("Filter by action: verify, reject, or change_players"),
    ),
    game_id: str | None = Query(
        None,
        description="Filter by game ID",
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
    if game_id:
        qs = qs.filter(run__game_id=game_id)

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
    response={200: SyncRetryResponse, codes_4xx: ErrorResponse},
    summary="Retry Failed Sync Task (Superuser)",
    description=(
        "Resets a failed SRC sync task to pending and re-queues it. "
        "Superuser access only."
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

    from srl.tasks import sync_src_action

    sync_task.status = SRCSyncTask.Status.PENDING
    sync_task.attempts = 0
    sync_task.last_error = ""
    sync_task.save(
        update_fields=[
            "status",
            "attempts",
            "last_error",
            "updated_at",
        ],
    )
    sync_src_action.delay(sync_task.id)

    return Status(
        200,
        {"task_id": sync_task.id, "message": "Sync task re-queued."},
    )
