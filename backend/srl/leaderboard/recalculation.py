import bisect
from dataclasses import dataclass, field
from datetime import datetime

from auditlog.models import GameAuditEvent
from auditlog.recorders import record_event
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import F, Prefetch, QuerySet
from django.db.models.functions import Coalesce

from srl.models import (
    Categories,
    Games,
    Players,
    RunHistory,
    Runs,
    Variables,
    VariableValues,
)
from srl.models.run_history import RunHistoryEndReason
from srl.srcom.utils import filter_by_variable_map
from srl.utils import calculate_bonus, points_formula, runs_share_player

TIME_COLUMN_MAP: dict[str, str] = {
    "rta": "time_secs",
    "lrt": "timenl_secs",
    "igt": "timeigt_secs",
}

# TODO: Yes this is a lot of spaghetti code. Please forgive me for now lol


def get_time_column(
    game_id: str,
    runtype: str = "main",
) -> str:
    """Get the game-level time column for a game.

    This is a game-only fallback. To honor the full precedence chain
    (Variable > Category > Game), use `get_leaderboard_time_column`.
    """
    game = Games.objects.only("defaulttime", "idefaulttime").get(id=game_id)
    if runtype == "main":
        return TIME_COLUMN_MAP.get(game.defaulttime, "time_secs")
    else:
        return TIME_COLUMN_MAP.get(game.idefaulttime, "time_secs")


def get_leaderboard_time_column(
    leaderboard: dict,
) -> str:
    """Resolve the effective time column for a leaderboard variant.

    Precedence: any variable VALUE on the leaderboard with a non-null
    `defaulttime` wins first; then any variable; then the category's
    `defaulttime`; then the game's `defaulttime` (or `idefaulttime` for IL).

    Performs up to four small queries; for batch processing across many
    leaderboards, use `build_leaderboard_metadata` plus `resolve_time_column`.
    """
    var_map = leaderboard.get("variable_value_map") or {}
    if var_map:
        value_timing = (
            VariableValues.objects.filter(
                value__in=list(var_map.values()),
                defaulttime__isnull=False,
            )
            .order_by("var_id")
            .values_list("defaulttime", flat=True)
            .first()
        )
        if value_timing:
            return TIME_COLUMN_MAP.get(value_timing, "time_secs")

        var_timing = (
            Variables.objects.filter(
                id__in=list(var_map.keys()),
                defaulttime__isnull=False,
            )
            .order_by("id")
            .values_list("defaulttime", flat=True)
            .first()
        )
        if var_timing:
            return TIME_COLUMN_MAP.get(var_timing, "time_secs")

    cat_id = leaderboard.get("category_id")
    if cat_id:
        cat_timing = (
            Categories.objects.filter(id=cat_id, defaulttime__isnull=False)
            .values_list("defaulttime", flat=True)
            .first()
        )
        if cat_timing:
            return TIME_COLUMN_MAP.get(cat_timing, "time_secs")

    return get_time_column(leaderboard["game_id"], leaderboard["runtype"])


def build_game_metadata(
    game_ids: set[str],
) -> tuple[dict[str, dict[str, str]], dict[str, bool]]:
    """Build game_time_columns and game_is_ce caches for the given game IDs."""
    game_time_columns: dict[str, dict[str, str]] = {}
    game_is_ce: dict[str, bool] = {}
    for game in Games.objects.filter(id__in=game_ids).only(
        "id", "defaulttime", "idefaulttime"
    ):
        game_time_columns[game.id] = {
            "main": TIME_COLUMN_MAP.get(game.defaulttime, "time_secs"),
            "il": TIME_COLUMN_MAP.get(game.idefaulttime, "time_secs"),
        }
        game_is_ce[game.id] = game.is_ce
    return game_time_columns, game_is_ce


def build_leaderboard_metadata(
    leaderboards: list[dict],
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, bool],
    dict[str, str],
    dict[str, str],
    dict[str, str],
]:
    """Build all caches needed to resolve timing across many leaderboards."""
    game_ids = {lb["game_id"] for lb in leaderboards}
    category_ids = {lb["category_id"] for lb in leaderboards if lb.get("category_id")}
    variable_ids: set[str] = set()
    value_ids: set[str] = set()
    for lb in leaderboards:
        var_map = lb.get("variable_value_map") or {}
        variable_ids.update(var_map.keys())
        value_ids.update(var_map.values())

    game_time_columns, game_is_ce = build_game_metadata(game_ids)

    value_timings: dict[str, str] = {}
    if value_ids:
        value_timings = dict(
            VariableValues.objects.filter(
                value__in=value_ids,
                defaulttime__isnull=False,
            ).values_list("value", "defaulttime"),
        )

    variable_timings: dict[str, str] = {}
    if variable_ids:
        variable_timings = dict(
            Variables.objects.filter(
                id__in=variable_ids,
                defaulttime__isnull=False,
            ).values_list("id", "defaulttime"),
        )

    category_timings: dict[str, str] = {}
    if category_ids:
        category_timings = dict(
            Categories.objects.filter(
                id__in=category_ids,
                defaulttime__isnull=False,
            ).values_list("id", "defaulttime"),
        )

    return (
        game_time_columns,
        game_is_ce,
        value_timings,
        variable_timings,
        category_timings,
    )


def resolve_time_column(
    leaderboard: dict,
    *,
    game_time_columns: dict[str, dict[str, str]],
    value_timings: dict[str, str],
    variable_timings: dict[str, str],
    category_timings: dict[str, str],
) -> str:
    """Resolve a leaderboard's time column from precomputed metadata.

    Mirrors `get_leaderboard_time_column` but reads from caches instead of
    the database, for use inside batch loops.
    """
    var_map = leaderboard.get("variable_value_map") or {}
    for var_id in sorted(var_map.keys()):
        val_id = var_map[var_id]
        vt = value_timings.get(val_id)
        if vt:
            return TIME_COLUMN_MAP.get(vt, "time_secs")
    for var_id in sorted(var_map.keys()):
        vt = variable_timings.get(var_id)
        if vt:
            return TIME_COLUMN_MAP.get(vt, "time_secs")

    cat_id = leaderboard.get("category_id")
    if cat_id:
        ct = category_timings.get(cat_id)
        if ct:
            return TIME_COLUMN_MAP.get(ct, "time_secs")

    return (
        game_time_columns.get(leaderboard["game_id"], {}).get(leaderboard["runtype"])
        or "time_secs"
    )


def _build_event_stream(
    runs: list[Runs],
) -> list[tuple[datetime, str, int, Runs]]:
    events: list[tuple[datetime, str, int, Runs]] = []

    for run in runs:
        is_obsolete = bool(run.obsolete)
        obsoleted_at = run.obsoleted_at
        effective_date = run.effective_date  # type: ignore

        events.append((effective_date, "ADD", 0, run))
        if is_obsolete and obsoleted_at is not None and obsoleted_at > effective_date:
            events.append((obsoleted_at, "REMOVE", 1, run))

    events.sort(key=lambda e: (e[0], e[2]))
    return events


@dataclass
class _WalkerState:
    runtype: str
    is_ce: bool
    max_points: int

    active_pool: dict[str, tuple[Runs, float]] = field(default_factory=dict)
    active_entries: dict[str, tuple["RunHistory", float]] = field(default_factory=dict)
    player_best_runs: dict[str, list[tuple[float, str]]] = field(default_factory=dict)
    run_to_players: dict[str, set[str]] = field(default_factory=dict)

    current_wr_id: str | None = None
    current_wr_time: float | None = None
    current_wr_player_ids: set[str] = field(default_factory=set)

    runs_streak_updates: dict[str, int] = field(default_factory=dict)
    runs_streak_starts: dict[str, datetime] = field(default_factory=dict)

    closed_entries: list["RunHistory"] = field(default_factory=list)
    new_entries: list["RunHistory"] = field(default_factory=list)
    entries_created_count: int = 0


def _player_ids_for(
    state: _WalkerState,
    run: Runs,
) -> set[str]:
    if run.id not in state.run_to_players:
        state.run_to_players[run.id] = {p.id for p in run.players.all()}
    return state.run_to_players[run.id]


def _is_already_slower(
    state: _WalkerState,
    run_time: float,
    player_ids: set[str],
) -> bool:
    """True if any player on the run already has a faster (or equal) PB."""
    for pid in player_ids:
        stack = state.player_best_runs.get(pid)
        if stack and run_time >= stack[0][0]:
            return True
    return False


def _close_active_entry(
    state: _WalkerState,
    run_id: str,
    end_date: datetime,
    end_reason: str,
) -> None:
    if run_id not in state.active_entries:
        return
    entry, _ = state.active_entries.pop(run_id)
    entry.end_date = end_date
    entry.end_reason = end_reason
    state.closed_entries.append(entry)


def _open_active_entry(
    state: _WalkerState,
    run: Runs,
    run_time: float,
    start_date: datetime,
    points: int,
    streak_start_date: datetime | None = None,
) -> RunHistory:
    entry = RunHistory(
        run=run,
        start_date=start_date,
        end_date=None,
        end_reason=None,
        points=points,
        streak_start_date=streak_start_date,
    )
    state.new_entries.append(entry)
    state.active_entries[run.id] = (entry, run_time)
    state.entries_created_count += 1
    return entry


def _emit_closed_entry(
    state: _WalkerState,
    run: Runs,
    start_date: datetime,
    end_date: datetime,
    end_reason: str,
    points: int,
) -> None:
    entry = RunHistory(
        run=run,
        start_date=start_date,
        end_date=end_date,
        end_reason=end_reason,
        points=points,
    )
    state.new_entries.append(entry)
    state.entries_created_count += 1


def _is_short_run(
    run_time: float,
    runtype: str,
) -> bool:
    return runtype == "il" and run_time < 60.0


def _resolve_streak_start(
    state: _WalkerState,
    event_date: datetime,
    new_wr_player_ids: set[str],
) -> datetime:
    """Return the streak's start date for a new WR."""
    if state.current_wr_id is not None and runs_share_player(
        state.current_wr_player_ids, new_wr_player_ids
    ):
        prior_start = state.runs_streak_starts.get(state.current_wr_id)
        if prior_start is not None:
            return prior_start
    return event_date


def _streak_months_capped(
    streak_start: datetime,
    event_date: datetime,
) -> int:
    delta = relativedelta(event_date, streak_start)
    months = delta.years * 12 + delta.months
    return min(max(0, months), settings.STREAK_MAX_MONTHS)


def _handle_add(
    state: _WalkerState,
    run: Runs,
    event_date: datetime,
) -> None:
    run_time = float(run.p_time_secs or 0.0)
    if not run_time:
        return

    player_ids = _player_ids_for(state, run)

    if _is_already_slower(state, run_time, player_ids):
        if state.current_wr_time is None:
            return
        is_short = _is_short_run(run_time, state.runtype)
        formula_points = points_formula(
            state.current_wr_time,
            run_time,
            state.max_points,
            short=is_short,
        )
        _emit_closed_entry(
            state,
            run,
            event_date,
            event_date,
            RunHistoryEndReason.OBSOLETED,
            formula_points,
        )
        return

    state.active_pool[run.id] = (run, run_time)
    for pid in player_ids:
        bisect.insort(state.player_best_runs.setdefault(pid, []), (run_time, run.id))

    # Close older PB entries for affected players unless co-op overlap keeps them.
    for pid in player_ids:
        stack = state.player_best_runs[pid]
        if len(stack) > 1:
            old_run_id = stack[1][1]
            if old_run_id in state.active_entries:
                others_still_pb = any(
                    other_pid != pid
                    and state.player_best_runs.get(other_pid)
                    and state.player_best_runs[other_pid][0][1] == old_run_id
                    for other_pid in state.run_to_players.get(old_run_id, set())
                )
                if not others_still_pb:
                    _close_active_entry(
                        state,
                        old_run_id,
                        event_date,
                        RunHistoryEndReason.OBSOLETED,
                    )

    is_new_wr = state.current_wr_time is None or run_time < state.current_wr_time

    if is_new_wr:
        previous_active = list(state.active_entries.keys())
        for active_run_id in previous_active:
            entry_run, active_run_time = state.active_pool[active_run_id]
            reason = (
                RunHistoryEndReason.LOST_WR
                if active_run_id == state.current_wr_id
                else RunHistoryEndReason.RECALCULATION
            )
            _close_active_entry(state, active_run_id, event_date, reason)

            if active_run_id == run.id:
                continue

            is_short = _is_short_run(active_run_time, state.runtype)
            formula_points = points_formula(
                run_time,
                active_run_time,
                state.max_points,
                short=is_short,
            )
            _open_active_entry(
                state,
                entry_run,
                active_run_time,
                event_date,
                formula_points,
            )

        streak_start = _resolve_streak_start(
            state,
            event_date,
            new_wr_player_ids=player_ids,
        )
        inherited_bonus = _streak_months_capped(streak_start, event_date)

        wr_points = state.max_points + calculate_bonus(
            state.runtype,
            inherited_bonus,
            state.is_ce,
        )
        _open_active_entry(
            state,
            run,
            run_time,
            event_date,
            wr_points,
            streak_start_date=streak_start,
        )
        state.runs_streak_updates[run.id] = inherited_bonus
        state.runs_streak_starts[run.id] = streak_start

        state.current_wr_id = run.id
        state.current_wr_time = run_time
        state.current_wr_player_ids = player_ids
    else:
        is_short = _is_short_run(run_time, state.runtype)
        formula_points = points_formula(
            state.current_wr_time,  # type: ignore
            run_time,
            state.max_points,
            short=is_short,
        )
        # A run that ties the current WR scores at max_points (formula
        # returns max_points when wr == run). Track its streak anchor too,
        # since /pointslb's place-based filter and build_streaks both treat
        # the tied submission as a fresh per-player streak starter.
        tied_co_wr_streak: datetime | None = None
        if run_time == state.current_wr_time:
            tied_co_wr_streak = event_date
        _open_active_entry(
            state,
            run,
            run_time,
            event_date,
            formula_points,
            streak_start_date=tied_co_wr_streak,
        )


def _handle_remove(
    state: _WalkerState,
    run: Runs,
    event_date: datetime,
) -> None:
    if run.id not in state.active_pool:
        return

    _, run_time = state.active_pool.pop(run.id)
    player_ids = _player_ids_for(state, run)

    for pid in player_ids:
        stack = state.player_best_runs.get(pid)
        if not stack:
            continue
        try:
            stack.remove((run_time, run.id))
        except ValueError:
            pass

    is_wr_removal = run.id == state.current_wr_id

    _close_active_entry(state, run.id, event_date, RunHistoryEndReason.OBSOLETED)

    if is_wr_removal:
        if not state.active_pool:
            state.current_wr_id = None
            state.current_wr_time = None
            state.current_wr_player_ids = set()
            return

        new_wr_id, (new_wr_run, new_wr_time) = min(
            state.active_pool.items(),
            key=lambda kv: kv[1][1],
        )
        new_wr_player_ids = _player_ids_for(state, new_wr_run)

        streak_start = _resolve_streak_start(
            state,
            event_date,
            new_wr_player_ids=new_wr_player_ids,
        )
        inherited_bonus = _streak_months_capped(streak_start, event_date)

        previous_active = [aid for aid in state.active_entries if aid != new_wr_id]
        for active_run_id in previous_active:
            active_run, active_run_time = state.active_pool[active_run_id]
            _close_active_entry(
                state,
                active_run_id,
                event_date,
                RunHistoryEndReason.RECALCULATION,
            )
            is_short = _is_short_run(active_run_time, state.runtype)
            formula_points = points_formula(
                new_wr_time,
                active_run_time,
                state.max_points,
                short=is_short,
            )
            _open_active_entry(
                state,
                active_run,
                active_run_time,
                event_date,
                formula_points,
            )

        _close_active_entry(
            state,
            new_wr_id,
            event_date,
            RunHistoryEndReason.RECALCULATION,
        )
        wr_points = state.max_points + calculate_bonus(
            state.runtype,
            inherited_bonus,
            state.is_ce,
        )
        _open_active_entry(
            state,
            new_wr_run,
            new_wr_time,
            event_date,
            wr_points,
            streak_start_date=streak_start,
        )
        state.runs_streak_updates[new_wr_id] = inherited_bonus
        state.runs_streak_starts[new_wr_id] = streak_start

        state.current_wr_id = new_wr_id
        state.current_wr_time = new_wr_time
        state.current_wr_player_ids = new_wr_player_ids
    else:
        for pid in player_ids:
            stack = state.player_best_runs.get(pid) or []
            if not stack:
                continue
            promoted_time, promoted_id = stack[0]
            if promoted_id in state.active_entries:
                continue

            promoted_run, _ = state.active_pool[promoted_id]
            is_short = _is_short_run(promoted_time, state.runtype)
            formula_points = points_formula(
                state.current_wr_time,  # type: ignore
                promoted_time,
                state.max_points,
                short=is_short,
            )
            _open_active_entry(
                state,
                promoted_run,
                promoted_time,
                event_date,
                formula_points,
            )


def get_runs_for_leaderboard(
    leaderboard: dict,
) -> QuerySet[Runs]:
    """Get all verified runs for a speedrun leaderboard, sorted by effective date."""
    base_qs = Runs.objects.filter(
        game_id=leaderboard["game_id"],
        category_id=leaderboard["category_id"],
        level_id=leaderboard["level_id"],
        runtype=leaderboard["runtype"],
        vid_status="verified",
    ).exclude(
        v_date__isnull=True,
        date__isnull=True,
    )
    base_qs = filter_by_variable_map(base_qs, leaderboard["variable_value_map"])
    return base_qs.annotate(
        effective_date=Coalesce(F("v_date"), F("date")),
    ).order_by("effective_date")


def clear_leaderboard_history(
    leaderboard: dict,
) -> int:
    """Delete existing RunHistory entries for a leaderboard variant.

    Needed before re-processing to avoid duplicates.
    """
    run_ids = list(get_runs_for_leaderboard(leaderboard).values_list("id", flat=True))
    if not run_ids:
        return 0
    deleted, _ = RunHistory.objects.filter(run_id__in=run_ids).delete()
    return deleted


def process_leaderboard(
    leaderboard: dict,
    dry_run: bool,
    game_is_ce: dict[str, bool],
) -> tuple[int, int, int]:
    runs = list(
        get_runs_for_leaderboard(leaderboard).prefetch_related(
            Prefetch("players", queryset=Players.objects.only("id")),
            "runvariablevalues_set__variable",
            "runvariablevalues_set__value",
        ),
    )
    if not runs:
        return 0, 0, 0

    game_id = leaderboard["game_id"]
    runtype = leaderboard["runtype"]
    is_ce = game_is_ce.get(game_id, False)
    max_points = (
        settings.POINTS_MAX_CE
        if is_ce
        else (settings.POINTS_MAX_FG if runtype == "main" else settings.POINTS_MAX_IL)
    )

    state = _WalkerState(
        runtype=runtype,
        is_ce=is_ce,
        max_points=max_points,
    )

    events = _build_event_stream(runs)

    for event_date, kind, _, run in events:
        if kind == "ADD":
            _handle_add(state, run, event_date)
        else:
            _handle_remove(state, run, event_date)

    if not dry_run and state.new_entries:
        RunHistory.objects.bulk_create(state.new_entries, batch_size=500)

    runs_to_fix = _sync_runs_points(state, runs, dry_run=dry_run)

    if not dry_run:
        try:

            verbose = (
                Games.objects.filter(pk=game_id)
                .values_list("verbose_recalc_log", flat=True)
                .first()
            )
            if verbose:
                record_event(
                    game=game_id,
                    event_type=GameAuditEvent.EventType.RECALC_BOARD,
                    summary=(
                        f"Recalculating Board: {len(runs)} runs, "
                        f"{state.entries_created_count} history entries"
                    ),
                    payload={
                        "category_id": leaderboard.get("category_id"),
                        "level_id": leaderboard.get("level_id"),
                        "runtype": runtype,
                        "variable_value_map": leaderboard.get("variable_value_map"),
                        "entries_created": state.entries_created_count,
                        "runs_processed": len(runs),
                        "runs_updated": runs_to_fix,
                    },
                )
        except Exception:
            pass

    return state.entries_created_count, len(runs), runs_to_fix


def _assign_places(
    state: _WalkerState,
) -> dict[str, int]:
    """Rank the current non-obsolete runs and assign competition placements.

    Recalculations usually occur during reconciliation, point changes, or something else major;
    because of this, this shouldn't run super often. The API has ways to handle this properly, but
    when you are dealing with lot of data (e.g. schema conversion), this is needed to properly
    wire and set things up."""
    ranked = sorted(
        state.active_pool.values(),
        key=lambda item: (item[1], item[0].effective_date),
    )

    places: dict[str, int] = {}
    current_place = 1
    tied_placements = 0
    previous_time: float | None = None

    for run, run_time in ranked:
        if previous_time is not None and run_time != previous_time:
            current_place += tied_placements
            tied_placements = 0
        places[run.id] = current_place
        tied_placements += 1
        previous_time = run_time

    return places


def _sync_runs_points(
    state: _WalkerState,
    runs: list[Runs],
    dry_run: bool,
) -> int:
    """Sync each Run's points/bonus/place to the final state."""
    points_map: dict[str, int] = {
        run_id: entry.points for run_id, (entry, _) in state.active_entries.items()
    }
    places_map = _assign_places(state)

    runs_to_update: list[Runs] = []
    for run in runs:
        expected_points = points_map.get(run.id, 0)
        expected_bonus = (
            state.runs_streak_updates.get(run.id, 0) if run.id in points_map else 0
        )
        expected_place = places_map.get(run.id, 0)

        if (
            run.points != expected_points
            or run.bonus != expected_bonus
            or run.place != expected_place
        ):
            run.points = expected_points
            run.bonus = expected_bonus
            run.place = expected_place
            runs_to_update.append(run)

    if runs_to_update and not dry_run:
        Runs.objects.bulk_update(
            runs_to_update,
            ["points", "bonus", "place"],
            batch_size=500,
        )

    return len(runs_to_update)
