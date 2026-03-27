from typing import Any

from celery import shared_task
from django.db import transaction

from srl.models import (
    Categories,
    Games,
    Levels,
    RunPlayers,
    Runs,
    RunVariableValues,
    Variables,
    VariableValues,
)
from srl.srcom.categories import sync_categories
from srl.srcom.levels import sync_levels
from srl.srcom.players import sync_players
from srl.srcom.variables import sync_variables
from srl.srcom.schema.internal import RunSyncContext, RunSyncTimesContext
from srl.srcom.schema.src import (
    SrcGamesModel,
    SrcLeaderboardModel,
    SrcRunsModel,
)
from srl.srcom.utils import (
    build_leaderboard_combos,
    create_leaderboard_link,
    create_run_default,
    filter_by_variable_map,
    src_api,
    update_obsolete,
    update_standings,
)
from srl.utils import points_formula


@shared_task
def sync_game_runs(
    game_id: str,
    reset: int = 0,
) -> None:
    if reset == 1:
        RunVariableValues.objects.filter(run__game__id=game_id).delete()
        VariableValues.objects.filter(var__game__id=game_id).delete()
        Variables.objects.filter(game=game_id).delete()
        Categories.objects.filter(game=game_id).delete()
        Levels.objects.filter(game=game_id).delete()
        Runs.objects.filter(game=game_id, obsolete=False).delete()

    game_check: dict[str, Any] = src_api(
        f"https://speedrun.com/api/v1/games/"
        f"{game_id}?embed=platforms,levels,categories,variables"
    )

    if isinstance(game_check, dict):
        game = SrcGamesModel.model_validate(game_check)

        if game.categories:
            for category in game.categories:
                sync_categories.delay(category)

        if game.levels:
            for level in game.levels:
                sync_levels.delay(level)

        if game.variables:
            for variable in game.variables:
                sync_variables.delay(variable)

        if game.categories:
            variables = game.variables or []

            for category in game.categories:
                is_il = category.type == "per-level"

                if is_il and game.levels:
                    for level in game.levels:
                        combos = build_leaderboard_combos(
                            variables=variables,
                            category_id=category.id,
                            is_il=True,
                            level_id=level.id,
                        )
                        for combo in combos:
                            lb_data = create_leaderboard_link(
                                game_id=game.id,
                                category_id=category.id,
                                il_id=level.id,
                                var_combo=combo if combo else None,
                            )
                            if lb_data:
                                sync_leaderboards.delay(lb_data)
                else:
                    combos = build_leaderboard_combos(
                        variables=variables,
                        category_id=category.id,
                        is_il=False,
                    )
                    for combo in combos:
                        lb_data = create_leaderboard_link(
                            game_id=game.id,
                            category_id=category.id,
                            var_combo=combo if combo else None,
                        )
                        if lb_data:
                            sync_leaderboards.delay(lb_data)


@shared_task
def sync_leaderboards(
    leaderboard_data: dict,
) -> None:
    """Orchestrates the leaderboard to `Runs` workflow.

    Arguments:
        leaderboard_data (dict): Object from the leaderboards API endpoint on SRC.
    """
    lrt_fix_check = False

    src_lb = SrcLeaderboardModel.model_validate(leaderboard_data)

    game_info = Games.objects.only(
        "id",
        "idefaulttime",
        "ipointsmax",
        "defaulttime",
        "pointsmax",
    ).get(id=src_lb.game)

    category_info = Categories.objects.only(
        "id",
        "name",
        "defaulttime",
    ).get(id=src_lb.category)

    level_info = None
    if src_lb.level:
        level_info = Levels.objects.only(
            "id",
            "name",
        ).get(id=src_lb.level)

        max_points = game_info.ipointsmax
        if game_info.idefaulttime == "realtime_noloads":
            lrt_fix_check = True
    else:
        max_points = game_info.pointsmax
        if game_info.defaulttime == "realtime_noloads":
            lrt_fix_check = True

    run_variables = src_lb.runs[0].run.values

    base_context = RunSyncContext(
        game_id=game_info.id,
        category_id=category_info.id,
        category_name=category_info.name,
        category_type=category_info.type,
        level_id=src_lb.level,
        level_name=level_info.name if level_info else None,
        wr_time_secs=0.0,
        max_points=max_points,
        default_time_type=src_lb.timing,
        variable_value_map=dict(run_variables) if run_variables else {},
        download_pfp=False,
        lrt_fix=lrt_fix_check,
        players_data=src_lb.players.data if src_lb.players else [],
        runs_data=src_lb.runs[0],
    )

    for lb_run in src_lb.runs:
        run_context = base_context.model_copy(update={"runs_data": lb_run})

        sync_run.delay(run_context)


@shared_task(pydantic=True)
def sync_obsolete_runs(
    player: str,
) -> None:
    run_data: dict[str, Any] | None = src_api(
        f"https://speedrun.com/api/v1/runs?user={player}&max=200&embed=players,game,level,category",
        True,
    )

    if run_data is not None:
        all_runs: list[dict[str, Any]] = run_data["data"]
        offset = 0

        while run_data["pagination"]["max"] == run_data["pagination"]["size"]:
            offset += 200
            run_data = src_api(
                f"https://speedrun.com/api/v1/"
                f"runs?user={player}&max=200&offset={offset}&embed=players,game,level,category",
                True,
            )

            if run_data is None:
                break

            all_runs.extend(run_data["data"])

        for run in all_runs:
            lrt_fix_check = False
            run = SrcRunsModel.model_validate(run)

            if run.status.status == "verified":
                game_info = (
                    Games.objects.only(
                        "id",
                        "defaulttime",
                        "idefaulttime",
                    )
                    .filter(id=run.game)
                    .first()
                )

                if game_info:
                    if not Runs.objects.only("id").filter(id=run.id).exists():
                        if game_info.defaulttime == "realtime_noloads":
                            lrt_fix_check = True
                        else:
                            if game_info.idefaulttime == "realtime_noloads":
                                lrt_fix_check = True

                        default: dict = create_run_default(
                            run.model_dump(),
                            place=0,
                            lrtfix=lrt_fix_check,
                        )
                        default["points"] = 0
                        default["obsolete"] = True

                        with transaction.atomic():
                            run_obj, _ = Runs.objects.update_or_create(
                                id=run.id,
                                defaults=default,
                            )

                            RunPlayers.objects.filter(run=run_obj).delete()
                            for order, player_data in enumerate(run.players, start=1):
                                if player_data.id and player_data.rel == "user":
                                    RunPlayers.objects.create(
                                        run=run_obj,
                                        player_id=player_data.id,
                                        order=order,
                                    )


@shared_task(pydantic=True)
def sync_run(
    context_data: RunSyncContext,
) -> None:
    """Creates or updates a `Runs` model object based on the `context_data` argument.

    Arguments:
        runs_data (RunSyncContext): Pydantic model contextual information related to runs, usually
            created from the leaderboards endpoint and `sync_leaderboards` function.
    """
    player_ids: list[str] = []

    place = context_data.runs_data.place
    run_data = context_data.runs_data.run
    if run_data.players is not None:
        default: dict = create_run_default(
            run_data=run_data.model_dump(),
            place=place,
            lrtfix=context_data.lrt_fix,
        )

        base_wr_query = filter_by_variable_map(
            Runs.objects.filter(
                game=context_data.game_id,
                obsolete=False,
                place=1,
            ),
            context_data.variable_value_map,
        )
        if context_data.category_type == "per-game":
            wr_pull = base_wr_query.filter(runtype="main").first()
        else:
            wr_pull = base_wr_query.filter(runtype="il").first()

        if place > 0:
            if place == 1:
                points = context_data.max_points
            else:
                wr_times = RunSyncTimesContext.model_validate(
                    wr_pull if wr_pull else run_data
                )

                if context_data.default_time_type == "realtime":
                    wr = (
                        wr_times.timeigt_secs
                        if wr_times.time_secs == 0
                        else wr_times.time_secs
                    )
                elif context_data.default_time_type == "realtime_noloads":
                    wr = wr_times.timenl_secs
                else:
                    wr = (
                        wr_times.time_secs
                        if wr_times.timeigt_secs == 0
                        else wr_times.timeigt_secs
                    )

                points = points_formula(
                    wr=wr,
                    run=run_data.times.primary_t,
                    max_points=context_data.max_points,
                    short=True if wr < 60 else False,
                )
        else:
            points = 0

        default["points"] = points

        for player_data in context_data.players_data:
            if player_data.id and player_data.rel == "user":
                player_ids.append(player_data.id)

        if run_data.level:
            default["level_id"] = run_data.level

        with transaction.atomic():
            run_obj, _ = Runs.objects.update_or_create(
                id=run_data.id,
                defaults=default,
            )

            RunPlayers.objects.filter(run=run_obj).delete()
            for order, player_id in enumerate(player_ids, start=1):
                RunPlayers.objects.create(
                    run=run_obj,
                    player_id=player_id,
                    order=order,
                )

        if len(run_data.values) > 0:
            for var_id, val_id in run_data.values.items():
                RunVariableValues.objects.update_or_create(
                    run=run_obj,
                    variable_id=var_id,
                    value_id=val_id,
                )

        if place >= 1:
            update_standings(
                is_wr=(place == 1),
                game_id=context_data.game_id,
                variable_value_map=context_data.variable_value_map,
                max_points=context_data.max_points,
                run_type=default["runtype"],
                default_time_type=context_data.default_time_type,
            )

        update_obsolete(
            game_id=context_data.game_id,
            variable_value_map=context_data.variable_value_map,
            players=run_data.players,
            run_type=default["runtype"],
            default_time_type=context_data.default_time_type,
        )

        for player in player_ids:
            sync_players(player)
