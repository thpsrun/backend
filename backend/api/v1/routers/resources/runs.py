from typing import Annotated, Literal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from ninja import Query, Router, Status
from srl.leaderboard.trigger import recalculate_run
from srl.models import (
    Categories,
    Games,
    Levels,
    Platforms,
    Players,
    RunPlayers,
    Runs,
    RunVariableValues,
    SRCSyncTask,
    Variables,
    VariableValues,
)
from srl.srcom.v2 import is_v2_enabled
from srl.srcom.v2.runs import (
    build_settings_payload,
    compute_v2_eligible_diff,
    snapshot_run,
)
from srl.tasks import sync_src_action, sync_src_settings
from srl.time_parser import parse_time
from srl.utils import convert_time

from api.permissions import authed, public_read
from api.v1.routers.auth.moderation import (
    ModerationError,
    _apply_moderation,
)
from api.v1.routers.utils.embeds import (
    InvalidEmbedsError,
    parse_embeds,
    serialize_category_embed,
    serialize_game_embed,
    serialize_level_embed,
    serialize_platform_embed,
)
from api.v1.routers.utils.resolvers import (
    game_from_body,
    game_from_run_path,
    run_from_path,
)
from api.v1.schemas.base import ErrorResponse, RunStatusType, RunTypeType
from api.v1.schemas.runs import (
    RunCreateSchema,
    RunImportIssuesSchema,
    RunModSchema,
    RunSchema,
    RunUpdateSchema,
)
from api.v1.utils import get_or_generate_id

router = Router()


def get_run_players(
    run: Runs,
) -> list[dict]:
    """Get all players for a run as a list of dicts, ordered by their participation order.

    This is always included in run responses (not an embed)."""
    run_players = sorted(run.run_players.all(), key=lambda rp: rp.order)

    players_list = []
    for rp in run_players:
        players_list.append(
            {
                "id": rp.player.id,
                "name": (rp.player.nickname if rp.player.nickname else rp.player.name),
                "url": rp.player.url,
                "country": (
                    rp.player.countrycode.name if rp.player.countrycode else None
                ),
                "pronouns": rp.player.pronouns,
                "twitch": rp.player.twitch,
                "youtube": rp.player.youtube,
                "twitter": rp.player.twitter,
                "bluesky": rp.player.bluesky,
            }
        )

    return players_list


def get_run_variables(
    run: Runs,
) -> dict[str, str]:
    """Get variable_id:value_id mapping for a run.

    This is always included in run responses (not an embed).
    Returns the through table data as {variable_id: value_id} pairs."""
    variable_mapping: dict[str, str] = {}

    run_variable_values = run.runvariablevalues_set.all()

    for rvv in run_variable_values:
        if rvv.variable and rvv.value:
            variable_mapping[rvv.variable.id] = rvv.value.value

    return variable_mapping


def apply_run_embeds(
    run: Runs,
    embed_fields: list[str],
) -> dict:
    """Apply requested embeds to a run instance.

    This is the most complex embed function of all of the endpoints due to the
    complex relations it will have with other models."""
    embeds = {}

    if "game" in embed_fields and run.game:
        embeds["game"] = serialize_game_embed(run.game)

    if "category" in embed_fields and run.category:
        embeds["category"] = serialize_category_embed(run.category)

    if "level" in embed_fields and run.level:
        embeds["level"] = serialize_level_embed(run.level)

    if "platform" in embed_fields and run.platform:
        embeds["platform"] = serialize_platform_embed(run.platform)

    if "variables" in embed_fields:
        try:
            variables_data = []
            for rv in run.runvariablevalues_set.all():
                if rv.variable and rv.value:
                    variables_data.append(
                        {
                            "variable": {
                                "id": rv.variable.id,
                                "name": rv.variable.name,
                                "slug": rv.variable.slug,
                                "scope": rv.variable.scope,
                            },
                            "value": {
                                "value": rv.value.value,
                                "name": rv.value.name,
                                "slug": rv.value.slug,
                            },
                        }
                    )

            embeds["variables"] = variables_data
        except Exception:
            embeds["variables"] = []

    return embeds


def normalize_time_fields(
    data: dict,
) -> Status | None:
    """Normalize RTA/LRT/IGT display strings from their `*_secs` source of truth.

    Consolidates logic that transforms the `_*secs` times into display strings that can be properly
    digested on the frontend or through the API."""
    time_pairs = (
        ("time", "time_secs"),
        ("timenl", "timenl_secs"),
        ("timeigt", "timeigt_secs"),
    )
    for str_field, secs_field in time_pairs:
        has_str = str_field in data
        has_secs = secs_field in data
        if not has_str and not has_secs:
            continue

        if has_secs and data[secs_field] is not None:
            secs = data[secs_field]
        elif has_str:
            raw = data[str_field]
            if raw in (None, "", "0"):
                secs = None if raw is None else 0.0
            else:
                try:
                    secs = parse_time(raw)
                except ValueError:
                    return Status(
                        422,
                        ErrorResponse(
                            error=f"Invalid time format for {str_field}: {raw!r}",
                            details=None,
                        ),
                    )
        else:
            secs = None

        if secs is None:
            data[str_field] = None
            data[secs_field] = None
        elif secs == 0:
            data[str_field] = "0"
            data[secs_field] = 0.0
        else:
            data[str_field] = convert_time(secs)
            data[secs_field] = secs

    return None


@router.get(
    "/all",
    response={
        200: list[RunSchema],
        400: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get All Runs",
    description="""\
Retrieve runs with extensive filtering and search capabilities.

Supported Parameters:
- `game_id` (str | None): Filter by specific game ID or slug
- `category_id` (str | None): Filter by specific category ID
- `level_id` (str | None): Filter by specific level ID (for IL runs)
- `player_id` (str | None): Filter by specific player ID
- `runtype` (str | None): Filter by run type (`main` or `il`)
- `place` (int | None): Filter by leaderboard position
- `status` (str | None): Filter by verification status (`verified`, `new`, `rejected`, or `review`)
- `sort` (str): Ordering. `default` (leaderboard: -v_date, place) or `newest` (most recently
  created first). Default `default`.
- `search`: Search in category name, level name, or variable value names
- `embed`: Comma-separated list of resources to embed
- `limit`: Results per page (default 50, max 100)
- `offset`: Results to skip (default 0)

Examples:
- `/runs/all?game_id=thps4` - All runs for THPS4
- `/runs/all?game_id=thps4&category_id=any&place=1` - THPS4 Any% world records
- `/runs/all?player_id=v8lponvj&runtype=main` - Player's full-game runs
- `/runs/all?search=normal&place=1&status=verified` - Verified WRs with "normal" in cat/level.
- `/runs/all?game_id=thps4&level_id=alcatraz&embed=player,game` - Alcatraz ILs with embeds
- `/runs/all?sort=newest&limit=20` - 20 most recently created runs (any status)
- `/runs/all?sort=newest&status=review&limit=20` - recent runs awaiting review
""",
    auth=public_read(),
)
def get_all_runs(
    request: HttpRequest,
    game_id: Annotated[str | None, Query(description="Filter by game")] = None,
    category_id: Annotated[str | None, Query(description="Filter by category")] = None,
    level_id: Annotated[str | None, Query(description="Filter by level")] = None,
    player_id: Annotated[str | None, Query(description="Filter by player")] = None,
    runtype: Annotated[RunTypeType | None, Query(description="Filter by type")] = None,
    place: Annotated[int | None, Query(ge=1, description="Filter by place")] = None,
    status: Annotated[
        RunStatusType | None, Query(description="Filter by status")
    ] = None,
    search: Annotated[
        str | None,
        Query(description="Search category/level/variable value names"),
    ] = None,
    embed: Annotated[str | None, Query(description="Comma-separated embeds")] = None,
    sort: Annotated[
        Literal["default", "newest"],
        Query(
            description=(
                "Result ordering: 'default' = leaderboard order (-v_date, place); "
                "'newest' = most recently created first (-created_at)."
            ),
        ),
    ] = "default",
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of returned objects (default 50, less than 100)",
        ),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Offset from 0"),
    ] = 0,
) -> Status:
    embed_fields = parse_embeds(embed, "runs")

    try:
        queryset = (
            Runs.objects.all()
            .select_related("game", "category", "level", "platform")
            .prefetch_related(
                "run_players__player__countrycode",
                "runvariablevalues_set__variable",
                "runvariablevalues_set__value",
            )
        )

        if sort == "newest":
            queryset = queryset.order_by("-created_at", "-id")
        else:
            queryset = queryset.order_by("-v_date", "place")

        if game_id:
            queryset = queryset.filter(Q(game__id=game_id) | Q(game__slug=game_id))
        if category_id:
            queryset = queryset.filter(category__id=category_id)
        if level_id:
            queryset = queryset.filter(level__id=level_id)
        if player_id:
            queryset = queryset.filter(run_players__player__id=player_id)
        if runtype:
            queryset = queryset.filter(runtype=runtype)
        if place:
            queryset = queryset.filter(place=place)
        if status:
            queryset = queryset.filter(vid_status=status)
        if search:
            queryset = queryset.filter(
                Q(category__name__icontains=search)
                | Q(level__name__icontains=search)
                | Q(runvariablevalues__value__name__icontains=search)
            ).distinct()

        runs = queryset[offset : offset + limit]

        run_schemas = []
        for run in runs:
            run_data = RunSchema.model_validate(run)

            run_data.players = get_run_players(run)
            run_data.variables = get_run_variables(run)

            if embed_fields:
                embed_data = apply_run_embeds(run, embed_fields)
                for field, data in embed_data.items():
                    setattr(run_data, field, data)

            run_schemas.append(run_data)

        return Status(200, run_schemas)

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve runs",
                details={"exception": str(e)},
            ),
        )


@router.get(
    "/{id}",
    response={
        200: RunSchema,
        400: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get Run by ID",
    description="""\
Retrieve a single run by its ID with full details and optional embeds.

Supported Parameters:
- `id` (str): Unique ID of the run being queried.
- `embed` (list | None): Comma-separated list of resources to embed.

Response Fields:
- `players`: Array of all players who participated in this run (always included).

Supported Embeds:
- `game`: Includes the metadata of the game related to the run queried.
- `category`: Includes the metadata of the category related to the run queried.
- `level`: Include the metadata of the level related to the run queried (if an IL run).
- `platform`: Include the metadata of the platform the run was played on.
- `variables`: Include the metadata of the variables and values related to the run.

Examples:
- `/runs/y8dwozoj` - Basic run data with players.
- `/runs/y8dwozoj?embed=game` - Include game metadata.
- `/runs/y8dwozoj?embed=game,category,platform,variables` - Full run details with embeds.
""",
    auth=public_read(),
)
def get_run(
    request: HttpRequest,
    id: str,
    embed: Annotated[str | None, Query(description="Comma-separated embeds")] = None,
) -> Status:
    if len(id) > 15:
        return Status(
            400,
            ErrorResponse(
                error="ID must be 15 characters or less",
                details=None,
            ),
        )

    try:
        embed_fields = parse_embeds(embed, "runs")
    except InvalidEmbedsError as e:
        return Status(
            400,
            ErrorResponse(
                error=str(e),
                details={"valid_embeds": sorted(e.valid)},
            ),
        )

    try:
        run = (
            Runs.objects.filter(id__iexact=id)
            .select_related("game", "category", "level", "platform", "approver")
            .prefetch_related(
                "run_players__player__countrycode",
                "runvariablevalues_set__variable",
                "runvariablevalues_set__value",
            )
            .first()
        )
        if not run:
            return Status(
                404,
                ErrorResponse(
                    error="Run ID does not exist",
                    details=None,
                ),
            )

        run_data = RunSchema.model_validate(run)

        run_data.players = get_run_players(run)
        run_data.variables = get_run_variables(run)

        if embed_fields:
            embed_data = apply_run_embeds(run, embed_fields)
            for field, data in embed_data.items():
                setattr(run_data, field, data)

        return Status(200, run_data)

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve run",
                details={"exception": str(e)},
            ),
        )


@router.get(
    "/{id}/import-issues",
    response={
        200: RunImportIssuesSchema,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get Run Import Issues",
    description="""\
Retrieve the import validation flags for a single run.

Requires an API key (or session) with the `games.audit.view` capability scoped to the run's
game. Returns only the run id and its import issue flags; fetch `GET /runs/{id}` separately
for game, category, and player context.
""",
    auth=authed("games.audit.view", target_resolver=game_from_run_path),
)
def get_run_import_issues(
    request: HttpRequest,
    id: str,
) -> Status:
    try:
        run = (
            Runs.objects.filter(id__iexact=id)
            .only("id", "has_import_issues", "import_issues")
            .first()
        )
        if not run:
            return Status(
                404,
                ErrorResponse(
                    error="Run ID does not exist",
                    details=None,
                ),
            )

        return Status(200, RunImportIssuesSchema.model_validate(run))

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve run import issues",
                details={"exception": str(e)},
            ),
        )


@router.post(
    "/",
    response={
        201: RunModSchema,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        422: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Create Run",
    description="""\
Create a new speedrun record with full validation.

Complex Validation:
- Game/category/level relationships must be valid.
- Players must exist if specified.
- Variable values must match variable constraints.
- Run type must match category type.

Request Body:
- `game_id` (str): Game ID the run belongs to.
- `category_id` (str | None): Category ID the run belongs to.
- `level_id` (str | None): Level ID (for IL runs).
- `player_ids` (list[str] | None): List of player IDs in order of participation.
- `runtype` (str): Run type (`main` or `il`).
- `place` (int): Leaderboard position.
- `vid_status` (str): Verification state (`verified`, `new`, `rejected`, or `review`);
  defaults to `verified`.
- `time` (str | None): Formatted time string (e.g., "1:23.456").
- `time_secs` (float | None): Time in seconds (for sorting/calculations).
- `video` (str | None): Video URL.
- `date` (datetime | None): Submission date (ISO format).
- `v_date` (datetime | None): Verification date (ISO format).
- `url` (str): Speedrun.com URL.
- `variable_values` (dict[str, str] | None): Variable value selections as key-value pairs.

Variable Values Format:
```json
{
    "variable_values": {
        "variable_id_1": "value_id_1",
        "variable_id_2": "value_id_2"
    }
}
```
""",
    auth=authed("games.manage", target_resolver=game_from_body),
)
def create_run(
    request: HttpRequest,
    run_data: RunCreateSchema,
) -> Status:
    try:
        game = Games.objects.filter(id=run_data.game_id).first()
        if not game:
            return Status(
                400,
                ErrorResponse(
                    error="Game does not exist",
                    details=None,
                ),
            )

        category = None
        if run_data.category_id:
            category = Categories.objects.filter(
                id=run_data.category_id, game=game
            ).first()
            if not category:
                return Status(
                    400,
                    ErrorResponse(
                        error="Category does not exist for this game",
                        details=None,
                    ),
                )

        level = None
        if run_data.level_id:
            level = Levels.objects.filter(id=run_data.level_id, game=game).first()
            if not level:
                return Status(
                    400,
                    ErrorResponse(
                        error="Level does not exist for this game",
                        details=None,
                    ),
                )

        players_list = []
        if run_data.player_ids:
            for player_id in run_data.player_ids:
                player = Players.objects.filter(id=player_id).first()
                if not player:
                    return Status(
                        400,
                        ErrorResponse(
                            error=f"Player with ID '{player_id}' does not exist",
                            details=None,
                        ),
                    )
                players_list.append(player)

        if category and run_data.runtype == "main" and category.type != "per-game":
            return Status(
                400,
                ErrorResponse(
                    error="Main runs require per-game categories",
                    details=None,
                ),
            )
        if (
            level
            and run_data.runtype == "il"
            and category
            and category.type != "per-level"
        ):
            return Status(
                400,
                ErrorResponse(
                    error="IL runs require per-level categories",
                    details=None,
                ),
            )

        try:
            run_id = get_or_generate_id(
                run_data.id,
                lambda id: Runs.objects.filter(id=id).exists(),
            )
        except ValueError as e:
            return Status(
                400,
                ErrorResponse(
                    error="ID Already Exists",
                    details={"exception": str(e)},
                ),
            )

        platform = None
        if run_data.platform_id:
            platform = Platforms.objects.filter(id=run_data.platform_id).first()
            if not platform:
                return Status(
                    400,
                    ErrorResponse(
                        error="Platform does not exist",
                        details=None,
                    ),
                )

        approver = None
        if run_data.approver_id:
            approver = Players.objects.filter(id=run_data.approver_id).first()
            if not approver:
                return Status(
                    400,
                    ErrorResponse(
                        error="Approver does not exist",
                        details=None,
                    ),
                )

        create_data = run_data.model_dump(
            exclude={
                "game_id",
                "category_id",
                "level_id",
                "platform_id",
                "approver_id",
                "player_ids",
                "variable_values",
            }
        )
        create_data["id"] = run_id

        time_error = normalize_time_fields(create_data)
        if time_error:
            return time_error

        with transaction.atomic():
            run = Runs.objects.create(
                game=game,
                category=category,
                level=level,
                platform=platform,
                approver=approver,
                **create_data,
            )

            RunPlayers.objects.bulk_create(
                [
                    RunPlayers(run=run, player=player, order=index)
                    for index, player in enumerate(players_list, start=1)
                ]
            )

            if run_data.variable_values:
                rvv_objs = []
                for var_id, value_id in run_data.variable_values.items():
                    variable = Variables.objects.filter(id=var_id).first()
                    value = VariableValues.objects.filter(
                        value=value_id,
                        var=variable,
                    ).first()

                    if variable and value:
                        rvv_objs.append(
                            RunVariableValues(
                                run=run,
                                variable=variable,
                                value=value,
                            )
                        )
                if rvv_objs:
                    RunVariableValues.objects.bulk_create(rvv_objs)

            try:
                run.validate_allowed_method_data()
            except ValidationError:
                raise

        refetched_run = (
            Runs.objects.filter(id=run.id)
            .select_related("category", "level", "platform")
            .prefetch_related(
                "run_players__player__countrycode",
                "runvariablevalues_set__variable",
                "runvariablevalues_set__value",
            )
            .first()
        )
        if refetched_run is None:
            return Status(
                500,
                ErrorResponse(
                    error="Run Creation Failed",
                    details={"exception": "Failed to refetch created run"},
                ),
            )
        refetched_run.refresh_import_issues()

        if refetched_run.vid_status == "verified":
            from srl.leaderboard.resolution import resolve_leaderboard
            from srl.srcom.utils import apply_player_obsolescence

            leaderboard = resolve_leaderboard(refetched_run)
            apply_player_obsolescence(
                game_id=leaderboard["game_id"],
                category_id=leaderboard["category_id"],
                variable_value_map=leaderboard["variable_value_map"],
                player_ids=list(refetched_run.players.values_list("id", flat=True)),
                run_type=leaderboard["runtype"],
                level_id=leaderboard["level_id"],
            )
            refetched_run.refresh_from_db(fields=["obsolete", "obsoleted_at"])

        response = RunModSchema.model_validate(refetched_run)
        response.players = get_run_players(refetched_run)
        response.variables = get_run_variables(refetched_run)

        if refetched_run.vid_status == "verified":
            actor_user_id = (
                request.user.pk
                if getattr(request.user, "is_authenticated", False)
                else None
            )
            recalculate_run(refetched_run, actor_user_id=actor_user_id)

        return Status(201, response)

    except ValidationError as e:
        return Status(
            422,
            ErrorResponse(
                error="Run timing validation failed",
                details={"exception": str(e)},
            ),
        )
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Run Creation Failed",
                details={"exception": str(e)},
            ),
        )


@router.put(
    "/{id}",
    response={
        200: RunModSchema,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        422: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Update Run",
    description="""\
Updates the run based on its unique ID.

Supported Parameters:
- `id` (str): Unique ID of the run being edited.

Request Body:
- `game_id` (str | None): Updated game ID.
- `category_id` (str | None): Updated category ID.
- `level_id` (str | None): Updated level ID (for IL runs).
- `player_ids` (list[str] | None): Updated list of player IDs in order of participation.
- `runtype` (str | None): Updated run type (`main` or `il`).
- `place` (int | None): Updated leaderboard position.
- `time` (str | None): Updated formatted time string (e.g., "1:23.456").
- `time_secs` (float | None): Updated time in seconds (for sorting/calculations).
- `video` (str | None): Updated video URL.
- `date` (datetime | None): Updated submission date (ISO format).
- `v_date` (datetime | None): Updated verification date (ISO format).
- `url` (str | None): Updated Speedrun.com URL.
- `variable_values` (dict[str, str] | None): Updated variable value selections as key-value
    pairs.
""",
    auth=authed("runs.edit_any", target_resolver=run_from_path),
)
def update_run(
    request: HttpRequest,
    id: str,
    run_data: RunUpdateSchema,
) -> Status:
    try:
        run = (
            Runs.objects.filter(id__iexact=id)
            .select_related("game", "category", "level", "platform", "approver")
            .prefetch_related(
                "run_players__player",
                "runvariablevalues_set__variable",
                "runvariablevalues_set__value",
            )
            .first()
        )
        if not run:
            return Status(
                404,
                ErrorResponse(
                    error="Run Doesn't Exist",
                    details=None,
                ),
            )

        # Capture pre-update state for trigger detection
        old_vid_status = run.vid_status
        old_time_secs = run.time_secs
        old_timenl_secs = run.timenl_secs
        old_timeigt_secs = run.timeigt_secs
        pre_edit_snapshot = snapshot_run(run)

        # Timing gaps that already exist before this edit. A required method missing here is a
        # pre-existing condition (recorded as a non-blocking import issue post-save), not
        # something this update introduced, so it must not block an unrelated write.
        preexisting_missing = set(run.missing_required_methods())

        update_data = run_data.model_dump(exclude_unset=True)

        time_error = normalize_time_fields(update_data)
        if time_error:
            return time_error

        if "game_id" in update_data:
            game = Games.objects.filter(id=update_data["game_id"]).first()
            if not game:
                return Status(
                    400,
                    ErrorResponse(
                        error="Game Doesn't Exist",
                        details=None,
                    ),
                )
            run.game = game
            del update_data["game_id"]

        if "category_id" in update_data:
            if update_data["category_id"]:
                category = Categories.objects.filter(
                    id=update_data["category_id"], game=run.game
                ).first()
                if not category:
                    return Status(
                        400,
                        ErrorResponse(
                            error="Category Doesn't Exist for This Game",
                            details=None,
                        ),
                    )
                run.category = category
            else:
                run.category = None
            del update_data["category_id"]

        if "level_id" in update_data:
            if update_data["level_id"]:
                level = Levels.objects.filter(
                    id=update_data["level_id"], game=run.game
                ).first()
                if not level:
                    return Status(
                        400,
                        ErrorResponse(
                            error="Level Doesn't Exist for This Game",
                            details=None,
                        ),
                    )
                run.level = level
            else:
                run.level = None
            del update_data["level_id"]

        if "platform_id" in update_data:
            if update_data["platform_id"]:
                platform = Platforms.objects.filter(
                    id=update_data["platform_id"],
                ).first()
                if not platform:
                    return Status(
                        400,
                        ErrorResponse(
                            error="Platform does not exist",
                            details=None,
                        ),
                    )
                run.platform = platform
            else:
                run.platform = None
            del update_data["platform_id"]

        if "approver_id" in update_data:
            if update_data["approver_id"]:
                approver = Players.objects.filter(
                    id=update_data["approver_id"],
                ).first()
                if not approver:
                    return Status(
                        400,
                        ErrorResponse(
                            error="Approver does not exist",
                            details=None,
                        ),
                    )
                run.approver = approver
            else:
                run.approver = None
            del update_data["approver_id"]

        with transaction.atomic():
            if "player_ids" in update_data:
                new_ids = update_data["player_ids"]
                if new_ids:
                    players_id = {
                        p.id: p for p in Players.objects.filter(id__in=new_ids)
                    }
                    missing = [pid for pid in new_ids if pid not in players_id]
                    if missing:
                        return Status(
                            400,
                            ErrorResponse(
                                error=f"Player ID(s) don't exist: {', '.join(missing)}",
                                details=None,
                            ),
                        )
                RunPlayers.objects.filter(run=run).delete()
                if new_ids:
                    RunPlayers.objects.bulk_create(
                        [
                            RunPlayers(run=run, player=players_id[pid], order=i)
                            for i, pid in enumerate(new_ids, start=1)
                        ]
                    )
                del update_data["player_ids"]
            if "variable_values" in update_data:
                RunVariableValues.objects.filter(run=run).delete()

                if update_data["variable_values"]:
                    rvv_objs = []
                    for var_id, value_id in update_data["variable_values"].items():
                        variable = Variables.objects.filter(
                            id=var_id,
                        ).first()
                        value = VariableValues.objects.filter(
                            value=value_id,
                            var=variable,
                        ).first()

                        if variable and value:
                            rvv_objs.append(
                                RunVariableValues(
                                    run=run,
                                    variable=variable,
                                    value=value,
                                )
                            )
                    if rvv_objs:
                        RunVariableValues.objects.bulk_create(rvv_objs)

                del update_data["variable_values"]

            for field, value in update_data.items():
                setattr(run, field, value)

            moderation_sync_task = None
            if run_data.moderator_action is not None:
                actor_player = getattr(request.user, "player", None)
                if actor_player is None:
                    raise ModerationError(
                        403,
                        "This endpoint requires a claimed Player profile "
                        "when using moderator_action.",
                    )
                moderation_sync_task = _apply_moderation(
                    run=run,
                    action_in=run_data.moderator_action,
                    actor_player=actor_player,
                )

            try:
                run.validate_allowed_method_data(ignore=preexisting_missing)
            except ValidationError:
                raise

            run.save()

        refetched_run = (
            Runs.objects.filter(id=run.id)
            .select_related("category", "level", "platform")
            .prefetch_related(
                "run_players__player__countrycode",
                "runvariablevalues_set__variable",
                "runvariablevalues_set__value",
            )
            .first()
        )
        if refetched_run is None:
            return Status(
                500,
                ErrorResponse(
                    error="Run Update Failed",
                    details={"exception": "Failed to refetch updated run"},
                ),
            )
        refetched_run.refresh_import_issues()

        deduped_obsolete_ids: list[str] = []
        if refetched_run.vid_status == "verified":
            from srl.leaderboard.resolution import resolve_leaderboard
            from srl.srcom.utils import apply_player_obsolescence

            leaderboard = resolve_leaderboard(refetched_run)
            deduped_obsolete_ids = apply_player_obsolescence(
                game_id=leaderboard["game_id"],
                category_id=leaderboard["category_id"],
                variable_value_map=leaderboard["variable_value_map"],
                player_ids=list(refetched_run.players.values_list("id", flat=True)),
                run_type=leaderboard["runtype"],
                level_id=leaderboard["level_id"],
            )
            refetched_run.refresh_from_db(fields=["obsolete", "obsoleted_at"])

        response = RunModSchema.model_validate(refetched_run)
        response.players = get_run_players(refetched_run)
        response.variables = get_run_variables(refetched_run)

        became_verified = (
            old_vid_status != "verified" and refetched_run.vid_status == "verified"
        )
        time_changed_while_verified = refetched_run.vid_status == "verified" and (
            refetched_run.time_secs != old_time_secs
            or refetched_run.timenl_secs != old_timenl_secs
            or refetched_run.timeigt_secs != old_timeigt_secs
        )
        if became_verified or time_changed_while_verified or deduped_obsolete_ids:
            recalc_actor_user_id = (
                request.user.pk
                if getattr(request.user, "is_authenticated", False)
                else None
            )
            recalculate_run(refetched_run, actor_user_id=recalc_actor_user_id)

        if is_v2_enabled():
            post_edit_snapshot = snapshot_run(refetched_run)
            diff = compute_v2_eligible_diff(pre_edit_snapshot, post_edit_snapshot)
            if diff:
                payload = build_settings_payload(refetched_run, post_edit_snapshot)
                moderator = None
                user = getattr(request, "user", None)
                if user is not None and getattr(user, "is_authenticated", False):
                    moderator = getattr(user, "player", None)
                edit_task = SRCSyncTask.objects.create(
                    run=refetched_run,
                    action=SRCSyncTask.ActionType.EDIT_RUN,
                    moderator=moderator,
                    payload=payload,
                )
                actor_user_id = (
                    user.pk if user is not None and user.is_authenticated else None
                )
                sync_src_settings.delay(edit_task.id, actor_user_id=actor_user_id)

        if moderation_sync_task is not None:
            mod_actor_user_id = (
                request.user.pk
                if getattr(request.user, "is_authenticated", False)
                else None
            )
            sync_src_action.delay(
                moderation_sync_task.id,
                actor_user_id=mod_actor_user_id,
            )

        return Status(200, response)

    except ModerationError as e:
        return Status(
            e.code,
            ErrorResponse(
                error=e.message,
                details=None,
            ),
        )
    except ValidationError as e:
        return Status(
            422,
            ErrorResponse(
                error="Run timing validation failed",
                details={"exception": str(e)},
            ),
        )
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Run Update Failed",
                details={"exception": str(e)},
            ),
        )


@router.delete(
    "/{id}",
    response={
        200: dict[str, str],
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Delete Run",
    description="""\
Deletes the selected run by its ID.

Supported Parameters:
- `id` (str): Unique ID of the run being deleted.
""",
    auth=authed("runs.delete", target_resolver=run_from_path),
)
def delete_run(
    request: HttpRequest,
    id: str,
) -> Status:
    try:
        run = (
            Runs.objects.filter(id__iexact=id)
            .select_related("game")
            .prefetch_related("run_players__player")
            .first()
        )
        if not run:
            return Status(
                404,
                ErrorResponse(
                    error="Run does not exist",
                    details=None,
                ),
            )

        game_name = run.game.name if run.game else "Unknown"
        run_player_entries = run.run_players.all()
        player_names = (
            ", ".join([rp.player.name for rp in run_player_entries])
            if run_player_entries
            else "Anonymous"
        )

        run.delete()
        return Status(
            200,
            {"message": f"Run by {player_names} in {game_name} deleted successfully"},
        )

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to delete run",
                details={"exception": str(e)},
            ),
        )
