import logging

from api.permissions import player_session_auth
from api.rate_limiting import auth_rate_limit
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.submissions import (
    ChangePlayersRequest,
    ChangePlayersResponse,
    ModerationGameGroup,
    SubmissionHubResponse,
    SubmissionRunSchema,
    SyncStatusSchema,
    VerifyRejectRequest,
    VerifyRejectResponse,
)
from django.db import transaction
from django.http import HttpRequest
from ninja import Router, Status
from ninja.responses import codes_4xx
from srl.leaderboard.trigger import recalculate_run
from srl.models import Players, Runs, SRCCredential, SRCSyncTask
from srl.models.run_players import RunPlayers
from srl.tasks import sync_src_action

logger = logging.getLogger(__name__)

router = Router()


def _get_sync_statuses(
    run_ids: list[str],
) -> dict[str, list[SyncStatusSchema]]:
    """Fetch active SRC sync tasks for a batch of runs.

    Returns a dict keyed by run_id with lists of SyncStatusSchema.
    Only returns pending/failed tasks (synced tasks are not shown).
    """
    sync_tasks = SRCSyncTask.objects.filter(
        run_id__in=run_ids,
        status__in=[
            SRCSyncTask.Status.PENDING,
            SRCSyncTask.Status.FAILED,
        ],
    ).order_by("-created_at")

    result: dict[str, list[SyncStatusSchema]] = {}
    for task in sync_tasks:
        if task.run_id not in result:
            result[task.run_id] = []
        result[task.run_id].append(
            SyncStatusSchema(
                action=task.action,
                status=task.status,
                attempts=task.attempts,
                last_error=task.last_error,
                updated_at=task.updated_at,
            ),
        )
    return result


def _build_run_players(run: Runs) -> list[dict]:
    """Build ordered player list from prefetched RunPlayers."""
    rps = run.run_players.select_related(
        "player__countrycode",
    ).order_by("order")
    return [
        {
            "id": rp.player.id,
            "name": rp.player.name,
            "countrycode": (
                rp.player.countrycode.id
                if rp.player.countrycode
                else None
            ),
        }
        for rp in rps
    ]


def _has_src_key(player: Players) -> bool:
    """Check if the player has a stored SRC API key."""
    return SRCCredential.objects.filter(user=player.user).exists()


@router.get(
    "/submissions",
    auth=player_session_auth,
    response={200: SubmissionHubResponse, codes_4xx: ErrorResponse},
    summary="Submission Hub",
    description=(
        "Returns the authenticated player's pending run submissions. "
        "If the player moderates any games, also includes a moderation "
        "queue with pending runs for those games. Each run includes "
        "SRC sync status for any in-flight moderator actions."
    ),
)
@auth_rate_limit
def get_submissions(
    request: HttpRequest,
) -> SubmissionHubResponse:
    player: Players = request.auth  # type: ignore

    pending_qs = (
        Runs.objects.filter(
            run_players__player=player,
            vid_status="new",
        )
        .select_related("game", "category", "level")
        .prefetch_related(
            "run_players__player__countrycode",
            "runvariablevalues_set__value",
        )
        .order_by("-date")
    )

    all_run_ids = [r.id for r in pending_qs]

    moderation_queue = None
    moderated_games = list(player.moderated_games.all())
    mod_runs_list: list[Runs] = []

    if moderated_games:
        mod_qs = (
            Runs.objects.filter(
                game__in=moderated_games,
                vid_status="new",
            )
            .select_related("game", "category", "level")
            .prefetch_related(
                "run_players__player__countrycode",
                "runvariablevalues_set__value",
            )
            .order_by("game__name", "-date")
        )
        mod_runs_list = list(mod_qs)
        all_run_ids.extend(r.id for r in mod_runs_list)

    sync_map = _get_sync_statuses(all_run_ids) if all_run_ids else {}

    pending_runs = []
    for run in pending_qs:
        schema = SubmissionRunSchema.from_orm(run)
        schema.players = _build_run_players(run)
        schema.src_sync = sync_map.get(run.id, [])
        pending_runs.append(schema)

    if moderated_games:
        game_groups: dict[str, ModerationGameGroup] = {}
        for run in mod_runs_list:
            gid = run.game_id
            if gid not in game_groups:
                game_groups[gid] = ModerationGameGroup(
                    game_id=gid,
                    game_name=run.game.name,
                    game_slug=run.game.slug,
                    pending_count=0,
                    pending_runs=[],
                )
            schema = SubmissionRunSchema.from_orm(run)
            schema.players = _build_run_players(run)
            schema.src_sync = sync_map.get(run.id, [])
            game_groups[gid].pending_runs.append(schema)
            game_groups[gid].pending_count += 1

        moderation_queue = list(game_groups.values())

    return SubmissionHubResponse(
        pending_runs=pending_runs,
        moderation_queue=moderation_queue,
    )


@router.put(
    "/submissions/{run_id}/status",
    auth=player_session_auth,
    response={200: VerifyRejectResponse, codes_4xx: ErrorResponse},
    summary="Verify or Reject a Run",
    description=(
        "Verifies or rejects a pending run. Updates the local database "
        "immediately, then queues an async task to sync the action to "
        "speedrun.com. Requires a stored SRC API key and moderator "
        "status for the run's game."
    ),
)
@auth_rate_limit
def update_run_status(
    request: HttpRequest,
    run_id: str,
    body: VerifyRejectRequest,
) -> Status:
    player: Players = request.auth  # type: ignore

    if not _has_src_key(player):
        return Status(
            403,
            ErrorResponse(
                error=(
                    "No SRC API key stored. "
                    "Add one at /auth/me/src-key."
                ),
                details=None,
            ),
        )

    run = (
        Runs.objects.filter(id=run_id)
        .select_related("game")
        .first()
    )
    if not run:
        return Status(
            404,
            ErrorResponse(error="Run not found.", details=None),
        )

    if not player.moderated_games.filter(id=run.game_id).exists():
        return Status(
            403,
            ErrorResponse(
                error="You are not a moderator for this game.",
                details=None,
            ),
        )

    if run.vid_status != "new":
        return Status(
            400,
            ErrorResponse(
                error=f"Run is already {run.vid_status}.",
                details=None,
            ),
        )

    if body.status == "rejected" and not body.reason:
        return Status(
            400,
            ErrorResponse(
                error="A reason is required when rejecting a run.",
                details=None,
            ),
        )

    # Update local DB immediately (optimistic)
    run.vid_status = body.status
    run.approver = player
    run.save(update_fields=["vid_status", "approver"])

    if body.status == "verified":
        recalculate_run(run)

    # Build SRC API payload and queue sync task
    src_payload: dict = {"status": {"status": body.status}}
    if body.status == "rejected" and body.reason:
        src_payload["status"]["reason"] = body.reason

    action = (
        SRCSyncTask.ActionType.VERIFY
        if body.status == "verified"
        else SRCSyncTask.ActionType.REJECT
    )
    sync_task = SRCSyncTask.objects.create(
        run=run,
        action=action,
        payload=src_payload,
        moderator=player,
    )
    sync_src_action.delay(sync_task.id)

    action_word = (
        "verified" if body.status == "verified" else "rejected"
    )
    return Status(
        200,
        VerifyRejectResponse(
            run_id=run_id,
            status=body.status,
            src_sync_status="pending",
            message=(
                f"Run {run_id} has been {action_word} locally. "
                f"SRC sync is in progress."
            ),
        ),
    )


@router.put(
    "/submissions/{run_id}/players",
    auth=player_session_auth,
    response={200: ChangePlayersResponse, codes_4xx: ErrorResponse},
    summary="Change Run Players",
    description=(
        "Changes the players credited on a run. Updates local database "
        "immediately, then queues an async task to sync to speedrun.com. "
        "Guest players are synced to SRC but not stored locally."
    ),
)
@auth_rate_limit
def update_run_players(
    request: HttpRequest,
    run_id: str,
    body: ChangePlayersRequest,
) -> Status:
    player: Players = request.auth  # type: ignore

    if not _has_src_key(player):
        return Status(
            403,
            ErrorResponse(
                error=(
                    "No SRC API key stored. "
                    "Add one at /auth/me/src-key."
                ),
                details=None,
            ),
        )

    run = (
        Runs.objects.filter(id=run_id)
        .select_related("game")
        .first()
    )
    if not run:
        return Status(
            404,
            ErrorResponse(error="Run not found.", details=None),
        )

    if not player.moderated_games.filter(id=run.game_id).exists():
        return Status(
            403,
            ErrorResponse(
                error="You are not a moderator for this game.",
                details=None,
            ),
        )

    # Resolve player names to DB records before making changes
    resolved_players: list[tuple[str, Players | None, str]] = []
    for p in body.players:
        if p.rel == "user":
            matches = list(Players.objects.filter(name=p.name))
            if len(matches) == 0:
                return Status(
                    400,
                    ErrorResponse(
                        error=(
                            f"Player '{p.name}' not found "
                            f"in the database."
                        ),
                        details=None,
                    ),
                )
            if len(matches) > 1:
                return Status(
                    400,
                    ErrorResponse(
                        error=(
                            f"Multiple players found with "
                            f"name '{p.name}'. Please contact "
                            f"an admin to resolve this."
                        ),
                        details=None,
                    ),
                )
            resolved_players.append(
                ("user", matches[0], p.name),
            )
        else:
            resolved_players.append(("guest", None, p.name))

    # Update local RunPlayers immediately
    with transaction.atomic():
        RunPlayers.objects.filter(run=run).delete()
        for idx, (rel, player_obj, _) in enumerate(
            resolved_players,
            start=1,
        ):
            if rel == "user" and player_obj:
                RunPlayers.objects.create(
                    run=run,
                    player=player_obj,
                    order=idx,
                )

    # Build SRC API payload and queue sync task
    src_players = []
    for rel, player_obj, name in resolved_players:
        if rel == "user" and player_obj:
            src_players.append(
                {"rel": "user", "id": player_obj.id},
            )
        else:
            src_players.append({"rel": "guest", "name": name})

    sync_task = SRCSyncTask.objects.create(
        run=run,
        action=SRCSyncTask.ActionType.CHANGE_PLAYERS,
        payload={"players": src_players},
        moderator=player,
    )
    sync_src_action.delay(sync_task.id)

    updated_players = _build_run_players(run)
    return Status(
        200,
        ChangePlayersResponse(
            run_id=run_id,
            players=updated_players,
            src_sync_status="pending",
            message=(
                f"Players updated locally for run {run_id}. "
                f"SRC sync is in progress."
            ),
        ),
    )
