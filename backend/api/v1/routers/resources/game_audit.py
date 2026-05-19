from __future__ import annotations

from datetime import datetime

from django.db.models import Q
from django.http import HttpRequest
from ninja import Query, Router, Status
from ninja.errors import HttpError

from auditlog.models import GameAuditEvent

from api.permissions import authed
from api.v1.routers.utils.resolvers import game_from_path
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.game_audit import (
    AuditListResponse,
    AuditRowDetail,
    AuditRowSummary,
)

router = Router()


@router.get(
    "/{slug}/audit",
    auth=authed("games.audit.view", target_resolver=game_from_path),
    response={
        200: AuditListResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Per-Game Audit Log (Moderator)",
    description=(
        "Game moderators (and superusers) can read the audit log for a game. "
        "Returns paginated events ordered by most recent first. Filter by event_type "
        "(repeat the parameter for multi-value), actor user, target, or date range. "
        "Set include_payload=true to inline each row's full JSON payload."
    ),
)
def list_audit(
    request: HttpRequest,
    slug: str,
    event_type: list[str] | None = Query(None),
    actor_user_id: int | None = Query(None),
    target_model: str | None = Query(None),
    target_id: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    include_payload: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Status:
    # Match live game by slug OR an orphaned row whose snapshot remembers the
    # slug (game FK is null because the game was deleted; see auditlog 0002).
    qs = (
        GameAuditEvent.objects
        .filter(
            Q(game__slug=slug)
            | Q(game__isnull=True, game_slug_snapshot=slug),
        )
        .select_related("actor_user")
    )

    if event_type:
        qs = qs.filter(event_type__in=event_type)
    if actor_user_id is not None:
        qs = qs.filter(actor_user_id=actor_user_id)
    if target_model:
        qs = qs.filter(target_model=target_model)
    if target_id:
        qs = qs.filter(target_id=target_id)
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    if until is not None:
        qs = qs.filter(created_at__lt=until)

    total = qs.count()
    page = qs.order_by("-created_at")[offset:offset + limit]

    results: list[AuditRowDetail] | list[AuditRowSummary]
    if include_payload:
        results = [
            AuditRowDetail(
                id=row.id,
                created_at=row.created_at,
                event_type=row.event_type,
                actor_kind=row.actor_kind,
                actor_user_id=row.actor_user_id,
                actor_username=(
                    row.actor_user.username if row.actor_user_id else None
                ),
                actor_api_key_id=row.actor_api_key_id,
                actor_label=row.actor_label,
                target_app=row.target_app,
                target_model=row.target_model,
                target_id=row.target_id,
                target_repr=row.target_repr,
                summary=row.summary,
                payload=row.payload,
            )
            for row in page
        ]
    else:
        results = [
            AuditRowSummary(
                id=row.id,
                created_at=row.created_at,
                event_type=row.event_type,
                actor_kind=row.actor_kind,
                actor_user_id=row.actor_user_id,
                actor_username=(
                    row.actor_user.username if row.actor_user_id else None
                ),
                actor_api_key_id=row.actor_api_key_id,
                actor_label=row.actor_label,
                target_app=row.target_app,
                target_model=row.target_model,
                target_id=row.target_id,
                target_repr=row.target_repr,
                summary=row.summary,
            )
            for row in page
        ]

    return Status(
        200,
        AuditListResponse(count=total, results=results),
    )


@router.get(
    "/{slug}/audit/{audit_id}",
    auth=authed("games.audit.view", target_resolver=game_from_path),
    response={
        200: AuditRowDetail,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Per-Game Audit Log Entry (Moderator)",
    description=(
        "Game moderators (and superusers) can fetch a single audit log entry "
        "including its full payload."
    ),
)
def get_audit(
    request: HttpRequest,
    slug: str,
    audit_id: int,
) -> Status:
    row = (
        GameAuditEvent.objects
        .filter(
            Q(game__slug=slug)
            | Q(game__isnull=True, game_slug_snapshot=slug),
            pk=audit_id,
        )
        .select_related("actor_user")
        .first()
    )
    if row is None:
        raise HttpError(404, "Audit entry not found")
    return Status(
        200,
        AuditRowDetail(
            id=row.id,
            created_at=row.created_at,
            event_type=row.event_type,
            actor_kind=row.actor_kind,
            actor_user_id=row.actor_user_id,
            actor_username=(
                row.actor_user.username if row.actor_user_id else None
            ),
            actor_api_key_id=row.actor_api_key_id,
            actor_label=row.actor_label,
            target_app=row.target_app,
            target_model=row.target_model,
            target_id=row.target_id,
            target_repr=row.target_repr,
            summary=row.summary,
            payload=row.payload,
        ),
    )
