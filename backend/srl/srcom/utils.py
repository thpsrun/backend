from itertools import product

from celery import shared_task
from django.db.models import Count, QuerySet
from django.utils import timezone

from srl.models import Games, Platforms, Players, RunHistory, Runs, VariableValues
from srl.models.run_history import RunHistoryEndReason
from srl.srcom.schema.src import SrcRunsPlayers, SrcVariablesModel
from srl.utils import (
    calculate_bonus,
    convert_time,
    points_formula,
    src_api,
    time_conversion,
)


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

        value_ids = list(variable.values.values.keys())
        var_dict[variable.id] = value_ids

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
        var_string: str = "&".join(
            f"var-{var_id}={val_id}" for var_id, val_id in var_combo
        )
        url += f"?{var_string}&embed=players,game,category"
    else:
        url += "?embed=players,game,category"

    return src_api(url)


def filter_by_variable_map(
    qs: QuerySet,
    variable_value_map: dict[str, str],
) -> QuerySet:
    """Filter a Runs queryset to a specific variable/value combination.

    For non-empty maps, chains filter() calls so each (variable_id, value_id)
    pair must be present in the run's RunVariableValues.
    For an empty map, restricts to runs that have zero RunVariableValues rows.

    Arguments:
        qs (QuerySet): Base queryset of Runs to filter.
        variable_value_map (dict[str, str]): {variable_id: value_id} from the leaderboard combo.

    Returns:
        QuerySet: Filtered queryset scoped to the given variant.
    """
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
    """Helper function that fixes an issue with the SRC API regarding LRT times set to RTA.

    This is a temporary function (hopefully) that fixes an SRC API issue where runs that have
    load-time removed (LRT) but no real-time (RTA), will have the LRT set to RTA instead.

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
    variable_value_map: dict[str, str],
    max_points: int,
    run_type: str,
    default_time_type: str,
) -> None:
    """Helper function that handles updating a leaderboard's points and rankings upon a record.

    Whenever a new world record is achieved, that record would then become the top place (1). All
    subsequent runs would need to be re-ranked and their points be algorithmically fixed.

    Arguments:
        is_wr (bool): When `True`, it will re-evaluate all points within the category. If `False`,
            then the point re-evaluation is ignored.
        game_id (str): Unique SRC ID of the game.
        variable_value_map (dict[str, str]): {variable_id: value_id} for the leaderboard variant.
        max_points (int): Maximum number of points within the speedrun.
        run_type (str): Type of run that needs to be queried (e.g. "main" or "il").
        default_time_type (str): Default time type of the record.
    """
    current_place = 1
    tied_placements = 0
    previous_time = None
    runs_list: list = []

    # Dictionary to map default timing methods to the type of seconds used.
    time_columns = {
        "realtime": "time_secs",
        "realtime_noloads": "timenl_secs",
        "ingame": "timeigt_secs",
    }

    base_qs = Runs.objects.only(
        "place",
        "points",
        "bonus",
        "time_secs",
        "timenl_secs",
        "timeigt_secs",
    ).filter(
        game=game_id,
        obsolete=False,
    )
    base_qs = filter_by_variable_map(base_qs, variable_value_map)

    all_category_runs = base_qs.filter(runtype=run_type)
    runs = all_category_runs.order_by(time_columns[default_time_type])
    wr_time = getattr(runs[0], (time_columns[default_time_type]))

    is_ce = Games.objects.only("is_ce").get(id=game_id).is_ce

    for run in runs:
        run_time = getattr(run, (time_columns[default_time_type]))

        if is_wr:
            if run_time == wr_time:
                # Preserves a streak bonus for this run, if re-applied. Otherwise
                # it would be reset to the type's maximum.
                bonus_value = calculate_bonus(run_type, run.bonus or 0, is_ce)
                points = max_points + bonus_value
            else:
                points = points_formula(
                    wr=wr_time,
                    run=run_time,
                    max_points=max_points,
                    short=True if wr_time < 60 else False,
                )
        else:
            points = run.points

        if previous_time is not None and run_time != previous_time:
            current_place += tied_placements
            tied_placements = 0

        run.place = current_place
        run.points = points
        runs_list.append(run)

        tied_placements += 1
        previous_time = run_time

    Runs.objects.bulk_update(runs_list, ["place", "points"])


@shared_task(pydantic=True)
def update_obsolete(
    game_id: str,
    variable_value_map: dict[str, str],
    players: list[SrcRunsPlayers],
    run_type: str,
    default_time_type: str,
) -> None:
    """Helper function that, when a new run is submitted, will mark all older runs as obsolete.

    When a speedrun is added to the leaderboard, this function will find all of their old runs
    that have NOT been marked and perform logic to determine which is faster. The fastest time
    is removed, with all remaining runs (which should be one) to be marked as obsolete.

    Arguments:
        game_id (str): Unique SRC ID of the game.
        variable_value_map (dict[str, str]): {variable_id: value_id} for the leaderboard variant.
        players (list[SrcRunsPlayers]): Pydantic list of players passed onto the function.
        run_type (str): Type of run that needs to be queried (e.g. "main" or "il").
        default_time_type (str): Default time type of the record.
    """
    obsolete_runs: list = []

    # Dictionary to map default timing methods to the type of seconds used.
    time_columns = {
        "realtime": "time_secs",
        "realtime_noloads": "timenl_secs",
        "ingame": "timeigt_secs",
    }

    base_qs = (
        Runs.objects.select_related("game")
        .prefetch_related("run_players__player")
        .only(
            "id",
            "game__id",
            "obsolete",
            "time_secs",
            "timenl_secs",
            "timeigt_secs",
        )
        .filter(runtype=run_type, game_id=game_id, obsolete=False)
    )
    base_qs = filter_by_variable_map(base_qs, variable_value_map)

    for player in players:
        if player is not None and player.rel != "guest":
            player_runs = base_qs.filter(run_players__player__id=player.id)
            count = player_runs.count()

            if count > 1:
                best_run = player_runs.order_by(time_columns[default_time_type]).first()
                if best_run:
                    slowest = player_runs.exclude(id=best_run.id)
                    for run in slowest:
                        obsolete_runs.append(run.id)

    if obsolete_runs:
        now = timezone.now()
        Runs.objects.filter(id__in=obsolete_runs).update(
            obsolete=True,
            obsoleted_at=now,
        )
        RunHistory.objects.filter(
            run_id__in=obsolete_runs,
            end_date__isnull=True,
        ).update(
            end_date=now,
            end_reason=RunHistoryEndReason.OBSOLETED,
        )

        sample_run = (
            Runs.objects.filter(id__in=obsolete_runs)
            .select_related("category", "level", "game")
            .first()
        )
        if sample_run is not None:
            from srl.leaderboard.resolution import resolve_leaderboard
            from srl.tasks import recalculate_leaderboard_task

            leaderboard = resolve_leaderboard(sample_run)
            recalculate_leaderboard_task.si(leaderboard).delay()


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
