import logging

import requests as http_requests
from django.db import transaction
from django.http import HttpRequest
from ninja import Router, Status
from ninja.responses import codes_4xx
from srl.encryption import decrypt_src_key
from srl.leaderboard.trigger import recalculate_run
from srl.models import Players, Runs, RunVariableValues, SRCSyncTask
from srl.models.categories import Categories
from srl.models.games import Games
from srl.models.levels import Levels
from srl.models.platforms import Platforms
from srl.models.run_players import RunPlayers
from srl.models.variable_values import VariableValues
from srl.models.variables import Variables
from srl.tasks import sync_src_action
from srl.time_parser import parse_time
from srl.utils import convert_time

from api.permissions import player_session_auth
from api.rate_limiting import auth_rate_limit
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.players import extract_gradients
from api.v1.schemas.submissions import (
    ChangePlayersRequest,
    ChangePlayersResponse,
    ModerationGameGroup,
    RunSubmitResponse,
    RunSubmitSchema,
    SubmissionHubResponse,
    SubmissionRunSchema,
    SyncStatusSchema,
    VerifyRejectRequest,
    VerifyRejectResponse,
)

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
        if task.run.id not in result:
            result[task.run.id] = []
        result[task.run.id].append(
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
    rps = sorted(run.run_players.all(), key=lambda rp: rp.order)
    return [
        {
            "id": rp.player.id,
            "name": rp.player.name,
            "countrycode": (
                rp.player.countrycode.id if rp.player.countrycode else None
            ),
            "gradients": extract_gradients(rp.player),
        }
        for rp in rps
    ]


def _has_src_key(player: Players) -> bool:
    """Check if the player has a stored SRC API key."""
    if not player.user:
        return False
    return player.user.encrypted_api_key is not None


SRC_API_BASE = "https://www.speedrun.com/api/v1"
SRC_TIMEOUT = 15


def _build_src_run_payload(
    body: RunSubmitSchema,
    time_secs: dict[str, float],
) -> dict:
    """Build the SRC API payload for POST /runs."""
    run_data: dict = {
        "game": body.game_id,
        "category": body.category_id,
        "players": [],
        "times": {},
        "video": body.video,
        "platform": body.platform_id,
        "emulated": body.emulated,
    }

    if body.level_id:
        run_data["level"] = body.level_id

    if body.comment:
        run_data["comment"] = body.comment

    if body.date:
        run_data["date"] = body.date

    for player in body.players:
        if player.rel == "user":
            run_data["players"].append(
                {"rel": "user", "id": player.id},
            )
        else:
            run_data["players"].append(
                {"rel": "guest", "name": player.name},
            )

    if "realtime" in time_secs:
        run_data["times"]["realtime"] = time_secs["realtime"]
    if "realtime_noloads" in time_secs:
        run_data["times"]["realtime_noloads"] = time_secs["realtime_noloads"]
    if "ingame" in time_secs:
        run_data["times"]["ingame"] = time_secs["ingame"]

    if body.variable_values:
        run_data["variables"] = {
            var_id: {"type": "pre-defined", "value": val_id}
            for var_id, val_id in body.variable_values.items()
        }

    return {"run": run_data}


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
            "run_players__player__user",
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
                "run_players__player__user",
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
                error=("No SRC API key stored. " "Add one at /auth/me/src-key."),
                details=None,
            ),
        )

    run = Runs.objects.filter(id=run_id).select_related("game").first()
    if not run:
        return Status(
            404,
            ErrorResponse(error="Run not found.", details=None),
        )

    if not player.moderated_games.filter(id=run.game.id).exists():
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

    run.vid_status = body.status
    run.approver = player
    run.save(update_fields=["vid_status", "approver"])

    if body.status == "verified":
        recalculate_run(run)

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

    action_word = "verified" if body.status == "verified" else "rejected"
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
                error=("No SRC API key stored. " "Add one at /auth/me/src-key."),
                details=None,
            ),
        )

    run = Runs.objects.filter(id=run_id).select_related("game").first()
    if not run:
        return Status(
            404,
            ErrorResponse(error="Run not found.", details=None),
        )

    if not player.moderated_games.filter(id=run.game.id).exists():
        return Status(
            403,
            ErrorResponse(
                error="You are not a moderator for this game.",
                details=None,
            ),
        )

    resolved_players: list[tuple[str, Players | None, str]] = []
    for p in body.players:
        if p.rel == "user":
            matches = list(Players.objects.filter(name=p.name))
            if len(matches) == 0:
                return Status(
                    400,
                    ErrorResponse(
                        error=(f"Player '{p.name}' not found " f"in the database."),
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


@router.post(
    "/submissions/submit",
    response={
        201: RunSubmitResponse,
        codes_4xx: ErrorResponse,
        503: ErrorResponse,
    },
    auth=player_session_auth,
    url_name="submit_run",
)
@auth_rate_limit
def submit_run(
    request: HttpRequest,
    body: RunSubmitSchema,
) -> Status:
    """Submit a run to SRC and create a local record on success."""
    player: Players = request.auth  # type: ignore

    if not player.user or not player.user.encrypted_api_key:
        return Status(
            400,
            ErrorResponse(
                error=("No SRC API key configured. " "Add one in profile settings."),
                details=None,
            ),
        )
    try:
        api_key = decrypt_src_key(player.user.encrypted_api_key)
    except Exception as e:
        logger.exception(
            "Failed to decrypt SRC API key for player %s",
            player.id,
        )
        return Status(
            400,
            ErrorResponse(
                error=(
                    "SRC API key could not be decrypted. "
                    "Please re-add it in profile settings."
                ),
                details={"exception": str(e)},
            ),
        )

    try:
        game = Games.objects.get(id=body.game_id)
    except Games.DoesNotExist:
        return Status(
            422,
            ErrorResponse(
                error=f"Game not found: {body.game_id}",
                details=None,
            ),
        )

    try:
        category = Categories.objects.get(
            id=body.category_id,
            game=game,
        )
    except Categories.DoesNotExist:
        return Status(
            422,
            ErrorResponse(
                error=("Category not found for game: " f"{body.category_id}"),
                details=None,
            ),
        )

    level = None
    if body.level_id:
        try:
            level = Levels.objects.get(id=body.level_id, game=game)
        except Levels.DoesNotExist:
            return Status(
                422,
                ErrorResponse(
                    error=("Level not found for game: " f"{body.level_id}"),
                    details=None,
                ),
            )

    try:
        platform = Platforms.objects.get(id=body.platform_id)
    except Platforms.DoesNotExist:
        return Status(
            422,
            ErrorResponse(
                error=f"Platform not found: {body.platform_id}",
                details=None,
            ),
        )
    if not game.platforms.filter(id=body.platform_id).exists():
        return Status(
            422,
            ErrorResponse(
                error=(
                    f"Platform {body.platform_id} is not valid " f"for game {game.id}"
                ),
                details=None,
            ),
        )

    user_player_map: dict[str, Players] = {}
    for p in body.players:
        if p.rel == "user":
            try:
                user_player_map[p.id] = Players.objects.get(
                    id=p.id,
                )
            except Players.DoesNotExist:
                return Status(
                    422,
                    ErrorResponse(
                        error=f"Player not found: {p.id}",
                        details=None,
                    ),
                )

    if body.variable_values:
        for var_id, val_id in body.variable_values.items():
            try:
                Variables.objects.get(id=var_id)
            except Variables.DoesNotExist:
                return Status(
                    422,
                    ErrorResponse(
                        error=f"Variable not found: {var_id}",
                        details=None,
                    ),
                )
            try:
                VariableValues.objects.get(
                    value=val_id,
                    var_id=var_id,
                )
            except VariableValues.DoesNotExist:
                return Status(
                    422,
                    ErrorResponse(
                        error=(
                            f"Variable value not found: "
                            f"{val_id} for variable {var_id}"
                        ),
                        details=None,
                    ),
                )

    time_secs: dict[str, float] = {}
    time_display: dict[str, str] = {}
    time_seconds: dict[str, float] = {}
    time_fields = [
        ("realtime", body.time, "time", "time_secs"),
        ("realtime_noloads", body.timenl, "timenl", "timenl_secs"),
        ("ingame", body.timeigt, "timeigt", "timeigt_secs"),
    ]
    for src_key, raw_value, str_field, secs_field in time_fields:
        if raw_value:
            try:
                parsed = parse_time(raw_value)
            except ValueError:
                return Status(
                    422,
                    ErrorResponse(
                        error=(
                            f"Invalid time format for " f"{str_field}: {raw_value!r}"
                        ),
                        details=None,
                    ),
                )
            time_secs[src_key] = parsed
            time_display[str_field] = convert_time(parsed)
            time_seconds[secs_field] = parsed

    src_payload = _build_src_run_payload(body, time_secs)

    try:
        src_response = http_requests.post(
            f"{SRC_API_BASE}/runs",
            json=src_payload,
            headers={"X-API-Key": api_key},
            timeout=SRC_TIMEOUT,
        )
    except http_requests.ConnectionError:
        return Status(
            503,
            ErrorResponse(
                error="Could not connect to SRC. Try again later.",
                details=None,
            ),
        )
    except http_requests.Timeout:
        return Status(
            503,
            ErrorResponse(
                error=("SRC is currently unavailable (timeout). " "Try again later."),
                details=None,
            ),
        )

    if src_response.status_code == 401:
        return Status(
            401,
            ErrorResponse(
                error=(
                    "SRC API key is invalid or expired. "
                    "Update it in profile settings."
                ),
                details=None,
            ),
        )
    elif src_response.status_code == 400:
        return Status(
            400,
            ErrorResponse(
                error="Speedrun.com rejected the submission",
                details=None,
            ),
        )
    elif src_response.status_code == 420:
        return Status(
            429,
            ErrorResponse(
                error=("SRC is rate limiting requests. " "Try again in a few minutes."),
                details=None,
            ),
        )
    elif src_response.status_code >= 500:
        return Status(
            503,
            ErrorResponse(
                error=("SRC is currently unavailable. " "Try again later."),
                details=None,
            ),
        )
    elif src_response.status_code not in (200, 201):
        return Status(
            400,
            ErrorResponse(
                error=("Unexpected SRC response " f"({src_response.status_code})."),
                details=None,
            ),
        )

    try:
        src_data = src_response.json()
        src_run_id = src_data["data"]["id"]
    except (KeyError, TypeError, ValueError) as e:
        logger.error(
            "Unexpected SRC response format: %s (error: %s)",
            src_response.text[:500],
            str(e),
        )
        return Status(
            400,
            ErrorResponse(
                error=(
                    "SRC accepted the run but returned "
                    "an unexpected response format."
                ),
                details=None,
            ),
        )

    runtype = "il" if level else "main"
    src_run_url = f"https://www.speedrun.com/run/{src_run_id}"

    with transaction.atomic():
        run = Runs.objects.create(
            id=src_run_id,
            game=game,
            category=category,
            level=level,
            platform=platform,
            emulated=body.emulated,
            runtype=runtype,
            place=0,
            url=src_run_url,
            video=body.video,
            vid_status="new",
            date=body.date,
            description=body.comment,
            time=time_display.get("time"),
            time_secs=time_seconds.get("time_secs"),
            timenl=time_display.get("timenl"),
            timenl_secs=time_seconds.get("timenl_secs"),
            timeigt=time_display.get("timeigt"),
            timeigt_secs=time_seconds.get("timeigt_secs"),
        )

        for i, p in enumerate(body.players):
            if p.rel == "user" and p.id in user_player_map:
                RunPlayers.objects.create(
                    run=run,
                    player=user_player_map[p.id],
                    order=i + 1,
                )

        if body.variable_values:
            for var_id, val_id in body.variable_values.items():
                RunVariableValues.objects.create(
                    run=run,
                    variable_id=var_id,
                    value_id=val_id,
                )

    return Status(
        201,
        RunSubmitResponse(
            run_id=src_run_id,
            src_url=src_run_url,
            vid_status="new",
            message=(
                "Run submitted to SRC and saved locally. " "Pending verification."
            ),
        ),
    )
