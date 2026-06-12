import logging
from collections import defaultdict

from celery import chain, shared_task
from django.db import transaction

from srl.leaderboard.recalculation import get_leaderboard_time_column
from srl.models import (
    Categories,
    Games,
    Levels,
    Players,
    RunPlayers,
    Runs,
    RunVariableValues,
    Variables,
    VariableValues,
)
from srl.srcom.categories import sync_categories
from srl.srcom.import_progress import bump
from srl.srcom.levels import sync_levels
from srl.srcom.players import sync_players
from srl.srcom.reconciliation import (
    check_cancelled,
    current_job,
    reconciliation_upsert_check,
)
from srl.srcom.schema.internal import RunSyncContext, RunSyncTimesContext
from srl.srcom.schema.src import SrcGamesModel, SrcLeaderboardModel, SrcRunsModel
from srl.srcom.utils import (
    build_leaderboard_combos,
    create_leaderboard_link,
    create_run_default,
    filter_by_variable_map,
    src_method_to_internal,
    update_obsolete,
    update_standings,
    variables_hash,
)
from srl.srcom.variables import sync_variables
from srl.utils import points_formula, src_api, src_api_paginate

logger = logging.getLogger(__name__)


@shared_task
def sync_game_runs(
    game_id: str,
    reset: int = 0,
    progress_key: str | None = None,
) -> None:
    dispatched = 0
    try:
        if reset == 1:
            with transaction.atomic():
                Runs.objects.filter(game=game_id).delete()
                VariableValues.objects.filter(var__game__id=game_id).delete()
                Variables.objects.filter(game=game_id).delete()
                Categories.objects.filter(game=game_id).delete()
                Levels.objects.filter(game=game_id).delete()

        game_check = src_api(
            f"https://speedrun.com/api/v1/games/"
            f"{game_id}?embed=platforms,levels,categories,variables"
        )
        if not isinstance(game_check, dict):
            return

        game = SrcGamesModel.model_validate(game_check)

        for category in game.categories or []:
            sync_categories(category)
        for level in game.levels or []:
            sync_levels(level)
        for variable in game.variables or []:
            sync_variables(variable)

        variables = game.variables or []
        for category in game.categories or []:
            is_il = category.type == "per-level"
            level_iter = game.levels if (is_il and game.levels) else [None]

            for level in level_iter:
                combos = build_leaderboard_combos(
                    variables=variables,
                    category_id=category.id,
                    is_il=is_il,
                    level_id=level.id if level else None,
                )
                for combo in combos:
                    check_cancelled()
                    lb_data = create_leaderboard_link(
                        game_id=game.id,
                        category_id=category.id,
                        il_id=level.id if level else None,
                        var_combo=combo if combo else None,
                    )
                    if lb_data:
                        sync_leaderboards.delay(
                            lb_data,
                            progress_key=progress_key,
                        )
                        dispatched += 1
    finally:
        if progress_key:
            bump(
                progress_key,
                "lb_total",
                dispatched,
            )
            bump(
                progress_key,
                "games_enumerated",
                1,
            )


def _build_base_context(
    src_lb: SrcLeaderboardModel,
) -> RunSyncContext:
    # SRC's v1 API has a bug where if "realtime_noloads" is the only timing method
    # used, it surfaces as "time" (RTA). lrt_fix corrects that for now.
    lrt_fix_check = False

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
        level_info = Levels.objects.only("id", "name").get(id=src_lb.level)
        max_points = game_info.ipointsmax
        if game_info.idefaulttime == "lrt":
            lrt_fix_check = True
    else:
        max_points = game_info.pointsmax
        if game_info.defaulttime == "lrt":
            lrt_fix_check = True

    run_variables = src_lb.runs[0].run.values

    return RunSyncContext(
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
        runs_data=src_lb.runs[0],
    )


@shared_task
def sync_leaderboards(
    leaderboard_data: dict,
    progress_key: str | None = None,
) -> None:
    failed = False
    try:
        src_lb = SrcLeaderboardModel.model_validate(leaderboard_data)
        if not src_lb.runs:
            return
        if progress_key:
            bump(
                progress_key,
                "runs_total",
                len(src_lb.runs),
            )
        base_context = _build_base_context(src_lb)
        for lb_run in src_lb.runs:
            check_cancelled()
            run_context = base_context.model_copy(update={"runs_data": lb_run})
            sync_run.delay(
                run_context.model_dump(),
                progress_key=progress_key,
            )
    except Exception:
        failed = True
        raise
    finally:
        if progress_key:
            bump(progress_key, "lb_failed" if failed else "lb_done")


def _passes_scope_filter(
    scope_filter: dict | None,
    *,
    game_id: str,
    category_id: str,
    level_id: str | None,
    variables: dict[str, str],
) -> bool:
    """Return True if a SRC run matches the reconciliation scope_filter."""

    if scope_filter is None:
        return True
    kind = scope_filter.get("kind")
    if kind == "game":
        return game_id == scope_filter["game_id"]
    if kind == "leaderboard":
        return (
            game_id == scope_filter["game_id"]
            and category_id == scope_filter["category_id"]
            and level_id == scope_filter.get("level_id")
            and variables == scope_filter.get("variables", {})
        )
    raise ValueError(f"unknown scope_filter kind: {kind!r}")


def _resolve_obsoleted_at_for_player(
    player_id: str,
) -> None:
    """Set obsoleted_at on the player's obsolete runs from chronology."""
    player_runs = list(
        Runs.objects.filter(
            run_players__player_id=player_id,
            vid_status="verified",
        )
        .exclude(v_date__isnull=True, date__isnull=True)
        .order_by("v_date", "date")
        .distinct()
    )
    if not player_runs:
        return

    run_ids = [r.id for r in player_runs]

    rp_rows = RunPlayers.objects.filter(run_id__in=run_ids).values_list(
        "run_id",
        "player_id",
    )
    tmp: dict[str, set[str]] = defaultdict(set)
    for run_id, pid in rp_rows:
        tmp[run_id].add(pid)
    player_sets: dict[str, frozenset[str]] = {
        rid: frozenset(s) for rid, s in tmp.items()
    }

    rvv_rows = RunVariableValues.objects.filter(run_id__in=run_ids).values_list(
        "run_id",
        "variable_id",
        "value_id",
    )
    rvv_by_run: dict[str, dict[str, str]] = defaultdict(dict)
    for rid, var_id, val_id in rvv_rows:
        rvv_by_run[rid][var_id] = val_id

    groups: dict[tuple, list[tuple[Runs, dict[str, str]]]] = defaultdict(list)
    for r in player_runs:
        ps = player_sets.get(r.id, frozenset())
        rvvs = rvv_by_run.get(r.id, {})
        vh = variables_hash(rvvs)
        key = (ps, r.game_id, r.category_id, r.level_id, r.runtype, vh)
        groups[key].append((r, rvvs))

    updates: list[Runs] = []
    for key, group_runs in groups.items():
        _, game_id, cat_id, level_id, runtype, _ = key
        group_runs.sort(key=lambda item: (item[0].v_date or item[0].date))  # type: ignore

        leaderboard_dict = {
            "game_id": game_id,
            "category_id": cat_id,
            "level_id": level_id,
            "runtype": runtype,
            "variable_value_map": group_runs[0][1],
        }
        time_field = get_leaderboard_time_column(leaderboard_dict)

        pb_time = float("inf")
        pb_run: Runs | None = None

        for r, _ in group_runs:
            rt = float(getattr(r, time_field) or 0.0)
            if rt <= 0:
                continue
            if rt < pb_time:
                if pb_run is not None and pb_run.obsolete:
                    new_obs_at = r.v_date or r.date
                    if pb_run.obsoleted_at != new_obs_at:
                        pb_run.obsoleted_at = new_obs_at
                        updates.append(pb_run)
                pb_time = rt
                pb_run = r

    if updates:
        Runs.objects.bulk_update(updates, ["obsoleted_at"], batch_size=200)


def _ensure_category_for_obsolete_run(
    src_run: SrcRunsModel,
) -> bool:
    """Make sure src_run.category exists locally; sync on demand or fall back to embed."""
    if not src_run.category:
        return True
    if Categories.objects.filter(id=src_run.category).exists():
        return True

    try:
        sync_categories(src_run.category)
    except Exception:
        try:
            embedded = src_api(
                f"https://www.speedrun.com/api/v1/runs/{src_run.id}?embed=category",
            )
            assert isinstance(embedded, dict)
            cat_data = (embedded.get("category") or {}).get("data")
            if cat_data:
                reconciliation_upsert_check(
                    Categories,
                    defaults={
                        "name": cat_data.get("name") or "",
                        "game_id": src_run.game,
                        "type": cat_data.get("type") or "",
                        "url": cat_data.get("weblink") or "",
                        "rules": cat_data.get("rules") or "",
                    },
                    record_type="category",
                    id=cat_data["id"],
                )
        except Exception:
            pass

    return Categories.objects.filter(id=src_run.category).exists()


def _ensure_level_for_obsolete_run(
    src_run: SrcRunsModel,
) -> bool:
    if not src_run.level:
        return True
    if Levels.objects.filter(id=src_run.level).exists():
        return True

    try:
        sync_levels(src_run.level)
    except Exception:
        return False

    return Levels.objects.filter(id=src_run.level).exists()


def _persist_obsolete_run(
    src_run: SrcRunsModel,
    game_info: Games,
) -> bool:
    """Insert a verified obsolete run + its players + var values. Returns True if inserted."""
    lrt_fix_check = game_info.defaulttime == "lrt" or game_info.idefaulttime == "lrt"
    default = create_run_default(
        src_run.model_dump(),
        place=0,
        lrtfix=lrt_fix_check,
    )
    default["points"] = 0
    default["obsolete"] = True
    if src_run.level:
        default["level_id"] = src_run.level

    with transaction.atomic():
        run_obj = reconciliation_upsert_check(
            Runs,
            defaults=default,
            record_type="run",
            id=src_run.id,
        )

        RunPlayers.objects.filter(run=run_obj).delete()
        RunPlayers.objects.bulk_create(
            [
                RunPlayers(run=run_obj, player_id=p.id, order=order)
                for order, p in enumerate(src_run.players, start=1)
                if p.id and p.rel == "user"
            ],
        )

        for var_id, val_id in (src_run.values or {}).items():
            reconciliation_upsert_check(
                RunVariableValues,
                defaults={},
                record_type="run_variable_value",
                run=run_obj,
                variable_id=var_id,
                value_id=val_id,
            )
    return True


@shared_task(pydantic=True)
def sync_obsolete_runs(
    player: str,
    scope_filter: dict | None = None,
    progress_key: str | None = None,
) -> None:
    failed = False
    try:
        counters: dict[str, int] = defaultdict(int)

        for raw_run in src_api_paginate(
            f"https://speedrun.com/api/v1/runs?user={player}",
        ):
            counters["total"] += 1
            try:
                src_run = SrcRunsModel.model_validate(raw_run)
            except Exception:
                counters["validation_err"] += 1
                continue

            if src_run.status.status != "verified":
                counters["unverified"] += 1
                continue

            run_variables: dict[str, str] = src_run.values or {}
            if not _passes_scope_filter(
                scope_filter,
                game_id=src_run.game,
                category_id=src_run.category,
                level_id=src_run.level,
                variables=run_variables,
            ):
                counters["filter"] += 1
                continue

            game_info = (
                Games.objects.only("id", "defaulttime", "idefaulttime")
                .filter(id=src_run.game)
                .first()
            )
            if game_info is None:
                counters["no_game"] += 1
                continue

            if not _ensure_category_for_obsolete_run(src_run):
                counters["no_category"] += 1
                continue

            if not _ensure_level_for_obsolete_run(src_run):
                counters["no_level"] += 1
                continue

            if Runs.objects.filter(id=src_run.id).exists():
                counters["exists"] += 1
                reconciliation_upsert_check(
                    Runs,
                    defaults={},
                    record_type="run",
                    id=src_run.id,
                )
                continue

            try:
                _persist_obsolete_run(src_run, game_info)
            except Exception:
                logger.exception(
                    "sync_obsolete_runs failed",
                    extra={"run_id": src_run.id, "player_id": player},
                )
                counters["db_err"] += 1
                continue

            counters["created"] += 1

        if counters["created"] > 0:
            try:
                _resolve_obsoleted_at_for_player(player)
            except Exception:
                pass
    except Exception:
        failed = True
        raise
    finally:
        if progress_key:
            bump(progress_key, "players_failed" if failed else "players_done")


@shared_task(pydantic=True)
def sync_run(
    context_data: RunSyncContext,
    progress_key: str | None = None,
) -> None:
    """Creates or updates a `Runs` model object based on the `context_data` argument.

    Arguments:
        context_data (RunSyncContext): Pydantic context built from the leaderboards endpoint.
    """
    failed = False
    try:
        place = context_data.runs_data.place
        run_data = context_data.runs_data.run
        if run_data.players is None:
            return

        default: dict = create_run_default(
            run_data=run_data.model_dump(),
            place=place,
            lrtfix=context_data.lrt_fix,
        )

        # When Phase 3 is kicked off, leaderboard and streaks recalculations are done. To
        # prevent deadlock on the database, if a reconciliation is going on it will just set
        # the points to 0. Otherwise it would assume world record incorrectly, fuck up the
        # formula, give like a bajillion points to a SmallIntField, crash the bot, and I cry.
        if current_job() is not None:
            points = 0
        elif place == 1:
            points = context_data.max_points
        elif place > 1:
            base_wr_query = filter_by_variable_map(
                Runs.objects.filter(
                    game=context_data.game_id,
                    category_id=context_data.category_id,
                    level_id=context_data.level_id,
                    obsolete=False,
                    place=1,
                ),
                context_data.variable_value_map,
            )
            if context_data.category_type == "per-game":
                wr_pull = base_wr_query.filter(runtype="main").first()
            else:
                wr_pull = base_wr_query.filter(runtype="il").first()

            # When a WR exists in the DB, read times via from_attributes;
            # otherwise validate from the SrcRunsTimes payload (aliased fields).
            if wr_pull is not None:
                wr_times = RunSyncTimesContext.model_validate(wr_pull)
            else:
                wr_times = RunSyncTimesContext.model_validate(
                    run_data.times.model_dump(),
                )

            default_time = src_method_to_internal(context_data.default_time_type)
            if default_time == "rta":
                wr = (
                    wr_times.timeigt_secs
                    if wr_times.time_secs == 0
                    else wr_times.time_secs
                )
            elif default_time == "lrt":
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
                short=wr < 60,
            )
        else:
            points = 0

        default["points"] = points
        default["obsolete"] = False
        default["obsoleted_at"] = None

        user_player_ids = [
            p.id for p in run_data.players if p is not None and p.id and p.rel == "user"
        ]

        if run_data.level:
            default["level_id"] = run_data.level

        # Does a quick check to ensure every user exists in the database before we join. In rare
        # circumstances, reconciliation can find a new runner and this could cause a foreign key
        # violation and crash the entire job.
        unique_player_ids = set(user_player_ids)
        existing_ids = set(
            Players.objects.filter(id__in=unique_player_ids).values_list(
                "id",
                flat=True,
            ),
        )
        missing_ids = unique_player_ids - existing_ids
        for pid in missing_ids:
            sync_players(pid)

        with transaction.atomic():
            run_obj = reconciliation_upsert_check(
                Runs,
                defaults=default,
                record_type="run",
                id=run_data.id,
            )

            RunPlayers.objects.filter(run=run_obj).delete()
            RunPlayers.objects.bulk_create(
                [
                    RunPlayers(run=run_obj, player_id=pid, order=order)
                    for order, pid in enumerate(user_player_ids, start=1)
                ],
            )

            for var_id, val_id in (run_data.values or {}).items():
                reconciliation_upsert_check(
                    RunVariableValues,
                    defaults={},
                    record_type="run_variable_value",
                    run=run_obj,
                    variable_id=var_id,
                    value_id=val_id,
                )

        run_obj.refresh_import_issues()

        # During a bounded reconcile (current_job set) runs land with points=0 and the job
        # recomputes each affected variant inline afterward, so skip the incremental standings
        # update here; outside reconciliation, update places immediately.
        if place >= 1 and current_job() is None:
            standings_sig = update_standings.si(
                is_wr=(place == 1),
                game_id=context_data.game_id,
                category_id=context_data.category_id,
                level_id=context_data.level_id,
                variable_value_map=context_data.variable_value_map,
                max_points=context_data.max_points,
                run_type=default["runtype"],
            )
            if place == 1:
                from srl.tasks import recalculate_streaks_task

                leaderboard = {
                    "game_id": context_data.game_id,
                    "category_id": context_data.category_id,
                    "level_id": context_data.level_id,
                    "runtype": default["runtype"],
                    "variable_value_map": context_data.variable_value_map,
                }
                chain(
                    standings_sig,
                    recalculate_streaks_task.si(leaderboard),
                ).delay()
            else:
                standings_sig.delay()

        update_obsolete.delay(
            game_id=context_data.game_id,
            category_id=context_data.category_id,
            level_id=context_data.level_id,
            variable_value_map=context_data.variable_value_map,
            players=[p.model_dump() for p in run_data.players if p is not None],
            run_type=default["runtype"],
        )

        for pid in unique_player_ids - missing_ids:
            sync_players(pid)
    except Exception:
        failed = True
        raise
    finally:
        if progress_key:
            bump(progress_key, "runs_failed" if failed else "runs_done")


@shared_task
def sync_single_run(
    run_id: str,
) -> None:
    check_cancelled()

    run_response = src_api(
        f"https://speedrun.com/api/v1/runs/{run_id}",
        raw=True,
    )
    assert isinstance(run_response, dict)
    if "data" not in run_response:
        return

    src_run = SrcRunsModel.model_validate(run_response["data"])

    if src_run.level:
        lb_url = (
            f"https://speedrun.com/api/v1/leaderboards/"
            f"{src_run.game}/level/{src_run.level}/{src_run.category}"
        )
    else:
        lb_url = (
            f"https://speedrun.com/api/v1/leaderboards/"
            f"{src_run.game}/category/{src_run.category}"
        )

    var_pairs = "&".join(f"var-{k}={v}" for k, v in (src_run.values or {}).items())
    query = "embed=players"
    if var_pairs:
        query = f"{var_pairs}&{query}"
    lb_url = f"{lb_url}?{query}"

    lb_response = src_api(lb_url, raw=True)
    assert isinstance(lb_response, dict)
    if "data" not in lb_response:
        return

    src_lb = SrcLeaderboardModel.model_validate(lb_response["data"])
    if not src_lb.runs:
        return

    target_lb_run = next(
        (lb_run for lb_run in src_lb.runs if lb_run.run.id == run_id),
        None,
    )
    if target_lb_run is None:
        # Run not on this leaderboard (rejected/new/obsoleted). sync_obsolete_runs
        # or the broader leaderboard sync will pick it up hopefully.
        return

    base_context = _build_base_context(src_lb)
    run_context = base_context.model_copy(update={"runs_data": target_lb_run})
    sync_run(run_context)
