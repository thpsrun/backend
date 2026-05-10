import hashlib
import json
from itertools import product

from celery import shared_task
from django.db import OperationalError
from django.db.models import Count, QuerySet
from django.utils import timezone
from pydantic import RootModel

from srl.models import Games, Platforms, Players, RunHistory, Runs, VariableValues
from srl.models.run_history import RunHistoryEndReason
from srl.srcom.reconciliation import check_reconciliation, current_job
from srl.srcom.schema.src import SrcRunsPlayers, SrcVariablesModel
from srl.utils import (
    calculate_bonus,
    convert_time,
    points_formula,
    src_api,
    time_conversion,
)

TIME_COLUMNS: dict[str, str] = {
    "realtime": "time_secs",
    "realtime_noloads": "timenl_secs",
    "ingame": "timeigt_secs",
}


def variables_hash(
    variables: dict[str, str],
) -> str:
    payload = json.dumps(variables, sort_keys=True).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def build_leaderboard_combos(
    variables: list[SrcVariablesModel],
    category_id: str,
    is_il: bool,
    level_id: str | None = None,
) -> list[list[tuple[str, str]]]:
    """Builds all possible variable:value combinations for a category's leaderboards.

    Filters variables by subcategory status, scope type, and category applicability,
    then generates every combination of variable-value pairs using itertools.product.

    Arguments:
        variables (list[SrcVariablesModel]): All variables for the game.
        category_id (str): Unique SRC ID for the category being processed.
        is_il (bool): Whether the category is per-level (True) or per-game (False).
        level_id (str | None): Unique SRC ID for the level, used for single-level scope filtering.

    Returns:
        list[list[tuple[str, str]]]: Each inner list is one combo of (var_id, val_id) tuples.
            Returns [[]] (one empty combo) if no subcategory variables apply.
    """
    scope_types = (
        {"global", "all-level", "single-level"} if is_il else {"global", "full-game"}
    )

    var_dict: dict[str, list[str]] = {}

    for variable in variables:
        if not variable.is_subcategory:
            continue
        if variable.scope.type not in scope_types:
            continue
        if variable.category is not None and variable.category != category_id:
            continue
        if (
            variable.scope.type == "single-level"
            and variable.scope.level is not None
            and variable.scope.level != level_id
        ):
            continue
        var_dict[variable.id] = list(variable.values.values.keys())

    if not var_dict:
        return [[]]

    keys = list(var_dict.keys())
    values_lists = [var_dict[key] for key in keys]
    return [list(zip(keys, vals)) for vals in product(*values_lists)]


def create_leaderboard_link(
    game_id: str,
    category_id: str,
    il_id: str | None = None,
    var_combo: list[tuple[str, str]] | None = None,
) -> dict:
    """Helper function that creates the SRC leaderboard link to be queried.

    Arguments:
        game_id (str): Unique SRC ID for a game.
        category_id (str): Unique SRC ID for a category.
        il_id (str | None): Unique SRC ID for a level.
        var_combo (list[tuple[str, str]] | None): List of (variable_id, value_id) tuples.
    """
    base_url = "https://speedrun.com/api/v1/leaderboards/"
    if il_id:
        url = f"{base_url}{game_id}/level/{il_id}/{category_id}"
    else:
        url = f"{base_url}{game_id}/category/{category_id}"

    if var_combo:
        var_string = "&".join(f"var-{var_id}={val_id}" for var_id, val_id in var_combo)
        url += f"?{var_string}&embed=players"
    else:
        url += "?embed=players"

    return src_api(url)  # type: ignore # I don't care enough to fix this sue me.


def filter_by_variable_map(
    qs: QuerySet,
    variable_value_map: dict[str, str],
) -> QuerySet:
    """Filter a Runs queryset to a specific variable/value combination."""
    if variable_value_map:
        for var_id, val_id in variable_value_map.items():
            qs = qs.filter(
                runvariablevalues__variable_id=var_id,
                runvariablevalues__value_id=val_id,
            )
    else:
        qs = qs.annotate(rv_count=Count("runvariablevalues", distinct=True)).filter(
            rv_count=0
        )
    return qs


def build_var_name(
    base_name: str,
    run_variables: dict,
) -> str:
    """Helper function that creates the subcategory name for a speedrun.

    Arguments:
        base_name (str): Usually the level or category name.
        run_variables (dict): Variable:value pairs within a run.
    """
    if not run_variables:
        return base_name

    value_ids = list(run_variables.values())
    values_map = dict(
        VariableValues.objects.filter(value__in=value_ids)
        .only("value", "name")
        .values_list("value", "name")
    )
    value_names = [values_map.get(v, v) for v in value_ids]
    return f"{base_name} ({', '.join(value_names)})"


def lrt_fix(
    default: dict,
) -> dict:
    """Fix an SRC API quirk where LRT-only runs have their LRT set to RTA instead.

    Arguments:
        default (dict): Dictionary information about a specific run.

    Returns:
        default (dict): Fixed dictionary information about a specific run.
    """
    if default["time_secs"] > 0 and default["timenl_secs"] == 0:
        default["timenl"] = convert_time(default["time_secs"])
        default["timenl_secs"] = default["time_secs"]
        default["time"] = "0"
        default["time_secs"] = 0.0

    return default


@shared_task(pydantic=True)
def update_standings(
    is_wr: bool,
    game_id: str,
    category_id: str,
    variable_value_map: dict[str, str],
    max_points: int,
    run_type: str,
    default_time_type: str,
    level_id: str | None = None,
    recon_job_id: str | None = None,
) -> None:
    """Re-rank a leaderboard variant after a record submission.

    When a new world record is set, all subsequent runs are re-ranked and their points
    recomputed. When `is_wr=False`, only `place` values are refreshed.

    Arguments:
        is_wr (bool): Re-evaluate points for the whole variant when True.
        game_id (str): Unique SRC ID of the game.
        category_id (str): Unique SRC ID of the category that scopes this variant.
        variable_value_map (dict[str, str]): {variable_id: value_id} for the variant.
        max_points (int): Maximum number of points within the speedrun.
        run_type (str): "main" or "il".
        default_time_type (str): Default time type of the record.
        level_id (str | None): Unique SRC ID of the level for IL leaderboards.
    """
    with check_reconciliation(recon_job_id):
        time_col = TIME_COLUMNS[default_time_type]

        base_qs = Runs.objects.only(
            "place",
            "points",
            "bonus",
            "time_secs",
            "timenl_secs",
            "timeigt_secs",
        ).filter(
            game=game_id,
            category=category_id,
            level=level_id,
            obsolete=False,
        )
        base_qs = filter_by_variable_map(base_qs, variable_value_map)
        all_category_runs = base_qs.filter(runtype=run_type)

        runs = list(all_category_runs.order_by(time_col))
        if not runs:
            return
        wr_time = getattr(runs[0], time_col)

        is_ce = Games.objects.only("name").get(id=game_id).is_ce

        current_place = 1
        tied_placements = 0
        previous_time = None
        runs_to_update: list[Runs] = []

        for run in runs:
            run_time = getattr(run, time_col)

            if is_wr:
                if run_time == wr_time:
                    bonus_value = calculate_bonus(run_type, run.bonus or 0, is_ce)
                    points = max_points + bonus_value
                else:
                    points = points_formula(
                        wr=wr_time,
                        run=run_time,
                        max_points=max_points,
                        short=wr_time < 60,
                    )
            else:
                points = run.points

            if previous_time is not None and run_time != previous_time:
                current_place += tied_placements
                tied_placements = 0

            run.place = current_place
            run.points = points
            runs_to_update.append(run)

            tied_placements += 1
            previous_time = run_time

        Runs.objects.bulk_update(runs_to_update, ["place", "points"])


class SrcRunsPlayersList(RootModel[list[SrcRunsPlayers]]):
    pass


@shared_task(
    pydantic=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 5},
)
def update_obsolete(
    game_id: str,
    category_id: str,
    variable_value_map: dict[str, str],
    players: SrcRunsPlayersList,
    run_type: str,
    default_time_type: str,
    level_id: str | None = None,
    recon_job_id: str | None = None,
) -> None:
    """Mark a player's older runs as obsolete after a new run is submitted.

    Arguments:
        game_id (str): Unique SRC ID of the game.
        category_id (str): Unique SRC ID of the category that scopes this variant.
        variable_value_map (dict[str, str]): {variable_id: value_id} for the variant.
        players (SrcRunsPlayersList): RootModel-wrapped list of players for the run.
        run_type (str): "main" or "il".
        default_time_type (str): Default time type of the record.
        level_id (str | None): Unique SRC ID of the level for IL leaderboards.
    """
    with check_reconciliation(recon_job_id):
        time_col = TIME_COLUMNS[default_time_type]

        base_qs = Runs.objects.filter(
            runtype=run_type,
            game_id=game_id,
            category_id=category_id,
            level_id=level_id,
            obsolete=False,
        )
        base_qs = filter_by_variable_map(base_qs, variable_value_map)

        obsolete_run_ids: list[str] = []
        for player in players.root:
            if player.rel == "guest":
                continue
            player_runs = list(
                base_qs.filter(run_players__player__id=player.id)
                .order_by(time_col)
                .values_list("id", flat=True),
            )
            if len(player_runs) > 1:
                obsolete_run_ids.extend(player_runs[1:])

        if not obsolete_run_ids:
            return

        now = timezone.now()
        Runs.objects.filter(id__in=obsolete_run_ids).update(
            obsolete=True,
            obsoleted_at=now,
        )
        RunHistory.objects.filter(
            run_id__in=obsolete_run_ids,
            end_date__isnull=True,
        ).update(
            end_date=now,
            end_reason=RunHistoryEndReason.OBSOLETED,
        )

        # Phase 3 handles recalc per variant during reconciliation, so skip
        # the immediate recalc in that path to avoid duplicate work.
        if current_job() is None:
            sample_run = (
                Runs.objects.filter(id__in=obsolete_run_ids)
                .select_related("category", "level", "game")
                .first()
            )
            if sample_run is not None:
                from srl.leaderboard.resolution import resolve_leaderboard
                from srl.tasks import recalculate_leaderboard_task

                leaderboard = resolve_leaderboard(sample_run)
                recalculate_leaderboard_task.delay(leaderboard)


def create_run_default(
    run_data: dict,
    place: int,
    lrtfix: bool,
) -> dict:
    try:
        platform = Platforms.objects.only("id").get(id=run_data["system"]["platform"])
    except Platforms.DoesNotExist:
        platform = None

    try:
        approver = Players.objects.only("id").get(id=run_data["status"]["examiner"])
    except Players.DoesNotExist:
        approver = None

    run_rta, run_nl, run_igt = time_conversion(run_data["times"])

    default = {
        "runtype": "main" if run_data["level"] is None else "il",
        "game_id": run_data["game"],
        "category_id": run_data["category"],
        "place": place,
        "url": run_data["weblink"],
        "video": run_data["video_uri"],
        "date": run_data["date"],
        "v_date": run_data["status"]["verify_date"],
        "time": run_rta,
        "time_secs": run_data["times"]["realtime_t"],
        "timenl": run_nl,
        "timenl_secs": run_data["times"]["realtime_noloads_t"],
        "timeigt": run_igt,
        "timeigt_secs": run_data["times"]["ingame_t"],
        "platform_id": platform.id if platform else None,
        "emulated": run_data["system"]["emulated"],
        "vid_status": run_data["status"]["status"],
        "approver": approver,
        "description": run_data["comment"],
    }

    if lrtfix:
        default = lrt_fix(default)

    return default
