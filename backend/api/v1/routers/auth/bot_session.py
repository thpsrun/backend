import logging
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.http import HttpRequest
from ninja import Router, Status
from srl.models import BotSession, SRCSyncTask
from srl.srcom.v2 import is_v2_enabled
from srl.srcom.v2.session import refresh_bot_session
from srl.tasks import replay_failed_edits

from api.permissions import authed
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.bot_session import (
    BotSessionResponse,
    KillSwitchRequest,
    KillSwitchResponse,
)

logger = logging.getLogger(__name__)
router = Router()


def _replay_window_cutoff() -> datetime:
    """Oldest created_at an EDIT_RUN task may have and still be eligible for replay."""
    days = getattr(settings, "SRC_V2_REPLAY_MAX_AGE_DAYS", 7)
    return datetime.now(timezone.utc) - timedelta(days=days)


def _edit_run_count(
    status: str,
) -> int:
    """Count EDIT_RUN sync tasks with the given status inside the replay window."""
    return SRCSyncTask.objects.filter(
        action=SRCSyncTask.ActionType.EDIT_RUN,
        status=status,
        created_at__gte=_replay_window_cutoff(),
    ).count()


def _to_response(
    bs: BotSession,
) -> BotSessionResponse:
    """Build the BotSessionResponse for a BotSession row."""
    return BotSessionResponse(
        status=bs.status,
        validated_at=bs.validated_at,
        last_refresh_attempt_at=bs.last_refresh_attempt_at,
        v2_enabled_override=bs.v2_enabled_override,
        v2_effective_enabled=is_v2_enabled(),
        disabled_by_circuit_breaker=bs.disabled_by_circuit_breaker,
        last_severe_error_at=bs.last_severe_error_at,
        last_severe_error_category=bs.last_severe_error_category,
        queued_edit_count=_edit_run_count(SRCSyncTask.Status.PENDING),
        failed_edit_count=_edit_run_count(SRCSyncTask.Status.FAILED),
    )


@router.get(
    "/admin/bot-session",
    auth=authed("sync_logs.admin"),
    response={
        200: BotSessionResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="SRC v2 Bot Session Status",
    description=(
        "Returns the status of the shared SRC v2 bot session: "
        "current state, last validation timestamp, kill-switch override, "
        "and effective v2-enabled flag."
    ),
)
def get_bot_session(
    request: HttpRequest,
) -> Status:
    return Status(200, _to_response(BotSession.load()))


@router.post(
    "/admin/bot-session/refresh",
    auth=authed("sync_logs.admin"),
    response={
        200: BotSessionResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Trigger v2 Bot Session Refresh",
    description=(
        "Manually triggers refresh_bot_session(). Intended for ops "
        "use when the bot session has expired and tasks are parking."
    ),
)
def post_refresh(
    request: HttpRequest,
) -> Status:
    refresh_bot_session()
    return Status(200, _to_response(BotSession.load()))


@router.put(
    "/admin/bot-session/kill-switch",
    auth=authed("sync_logs.admin"),
    response={
        200: KillSwitchResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Set v2 Kill Switch Override",
    description=(
        "Sets the runtime override for SRC_V2_ENABLED. Send "
        '{"override": true|false} to force on/off, or '
        '{"override": null} to clear the override and inherit env.'
    ),
)
def put_kill_switch(
    request: HttpRequest,
    body: KillSwitchRequest,
) -> Status:
    bs = BotSession.load()
    was_effective_enabled = is_v2_enabled()
    bs.v2_enabled_override = body.override
    bs.save(update_fields=["v2_enabled_override"])
    now_effective_enabled = is_v2_enabled()

    replay_queued_count = 0
    if not was_effective_enabled and now_effective_enabled:
        # Any off->on transition clears the breaker, regardless of
        # whether the admin sent override=True or override=null while
        # the env default is True.
        if bs.disabled_by_circuit_breaker:
            bs.disabled_by_circuit_breaker = False
            bs.save(update_fields=["disabled_by_circuit_breaker"])

        replay_queued_count = SRCSyncTask.objects.filter(
            action=SRCSyncTask.ActionType.EDIT_RUN,
            status=SRCSyncTask.Status.FAILED,
            created_at__gte=_replay_window_cutoff(),
        ).count()
        replay_failed_edits.delay()

    return Status(
        200,
        KillSwitchResponse(
            v2_enabled_override=bs.v2_enabled_override,
            v2_effective_enabled=now_effective_enabled,
            disabled_by_circuit_breaker=bs.disabled_by_circuit_breaker,
            replay_queued_count=replay_queued_count,
        ),
    )
