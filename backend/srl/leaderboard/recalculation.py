from django.conf import settings
from django.db.models import F, QuerySet
from django.db.models.functions import Coalesce
from srl.models import Games, RunHistory, Runs
from srl.models.run_history import RunHistoryEndReason
from srl.srcom.utils import filter_by_variable_map
from srl.utils import calculate_bonus, points_formula, runs_share_player

TIME_COLUMN_MAP: dict[str, str] = {
    "realtime": "time_secs",
    "realtime_noloads": "timenl_secs",
    "ingame": "timeigt_secs",
}


def get_time_column(
    game_id: str,
    runtype: str = "main",
) -> str:
    """Get the time column to use for a game based on its default timing method."""
    game = Games.objects.only("defaulttime", "idefaulttime").get(id=game_id)
    if runtype == "main":
        return TIME_COLUMN_MAP.get(game.defaulttime, "time_secs")
    else:
        return TIME_COLUMN_MAP.get(game.idefaulttime, "time_secs")


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
    game_time_columns: dict[str, dict[str, str]],
) -> tuple[int, int, int]:
    runs = list(get_runs_for_leaderboard(leaderboard).prefetch_related("players"))
    if not runs:
        return 0, 0, 0

    game_times = game_time_columns.get(leaderboard["game_id"], {})
    if leaderboard["runtype"] == "main":
        time_column = game_times.get("main", "time_secs")
    else:
        time_column = game_times.get("il", "time_secs")

    is_ce = game_is_ce.get(leaderboard["game_id"], False)
    if is_ce:
        max_points = settings.POINTS_MAX_CE
    elif leaderboard["runtype"] == "main":
        max_points = settings.POINTS_MAX_FG
    else:
        max_points = settings.POINTS_MAX_IL

    current_wr_time: float | None = None
    current_wr_run: Runs | None = None
    current_wr_player_ids: set[str] = set()
    # run_id -> (open RunHistory entry, run's time) for currently-active scoring periods
    active_entries: dict[str, tuple[RunHistory, float]] = {}
    # player_id -> (run_id, time) tracking each player's current PB
    player_best_runs: dict[str, tuple[str, float]] = {}
    entries_created_count = 0
    entries_to_update: list[RunHistory] = []
    runs_streak_updates: dict[str, int] = {}

    for run in runs:
        run_time = getattr(run, time_column) or 0
        if run_time <= 0:
            run_time = getattr(run, "time_secs") or 0
        if run_time <= 0:
            continue

        effective_date = run.effective_date  # type: ignore

        player_ids = [player.id for player in run.players.all()]

        # Close out any slower PB this player already had on this leaderboard
        for player_id in player_ids:
            if player_id in player_best_runs:
                old_run_id, old_time = player_best_runs[player_id]
                if run_time < old_time and old_run_id in active_entries:
                    old_entry, _ = active_entries[old_run_id]
                    old_entry.end_date = effective_date
                    old_entry.end_reason = RunHistoryEndReason.OBSOLETED
                    entries_to_update.append(old_entry)
                    del active_entries[old_run_id]

            if (
                player_id not in player_best_runs
                or run_time < player_best_runs[player_id][1]
            ):
                player_best_runs[player_id] = (run.id, run_time)

        is_new_wr = current_wr_time is None or run_time < current_wr_time

        if is_new_wr:
            old_wr_id = current_wr_run.id if current_wr_run else None
            new_wr_player_ids = set(player_ids)

            # Streak continues if the same player beat their own WR
            streak_continues = current_wr_run is not None and runs_share_player(
                current_wr_player_ids, new_wr_player_ids
            )

            old_bonus = 0
            if streak_continues and old_wr_id:
                old_bonus = runs_streak_updates.get(old_wr_id, 0)

            run_ids_to_update = list(active_entries.keys())

            for run_id in run_ids_to_update:
                entry, old_run_time = active_entries[run_id]

                entry.end_date = effective_date
                if run_id == old_wr_id:
                    entry.end_reason = RunHistoryEndReason.LOST_WR

                    if not streak_continues:
                        runs_streak_updates[run_id] = 0
                else:
                    entry.end_reason = RunHistoryEndReason.RECALCULATION
                entries_to_update.append(entry)

                new_points = points_formula(
                    wr=run_time,
                    run=old_run_time,
                    max_points=max_points,
                    short=True if run_time < 60 else False,
                )

                new_entry = RunHistory(
                    run_id=run_id,
                    start_date=effective_date,
                    end_date=None,
                    points=new_points,
                    end_reason=None,
                )
                if not dry_run:
                    new_entry.save()
                entries_created_count += 1
                active_entries[run_id] = (new_entry, old_run_time)

            current_wr_time = run_time
            current_wr_run = run
            current_wr_player_ids = new_wr_player_ids

            new_bonus = old_bonus if streak_continues else 0
            runs_streak_updates[run.id] = new_bonus

            streak_bonus = calculate_bonus(
                leaderboard["runtype"],
                new_bonus,
                is_ce,
            )
            new_wr_points = max_points + streak_bonus

            new_wr_entry = RunHistory(
                run_id=run.id,
                start_date=effective_date,
                end_date=None,
                points=new_wr_points,
                end_reason=None,
            )
            if not dry_run:
                new_wr_entry.save()
            entries_created_count += 1
            active_entries[run.id] = (new_wr_entry, run_time)

        else:
            points = points_formula(
                wr=current_wr_time,  # type: ignore
                run=run_time,
                max_points=max_points,
                short=True if current_wr_time < 60 else False,
            )

            new_entry = RunHistory(
                run_id=run.id,
                start_date=effective_date,
                end_date=None,
                points=points,
                end_reason=None,
            )
            if not dry_run:
                new_entry.save()
            entries_created_count += 1
            active_entries[run.id] = (new_entry, run_time)

    if not dry_run and entries_to_update:
        RunHistory.objects.bulk_update(
            entries_to_update,
            ["end_date", "end_reason"],
        )

    current_points_map: dict[str, int] = {
        run_id: entry.points for run_id, (entry, _) in active_entries.items()
    }

    runs_to_fix: list[Runs] = []
    for run in runs:
        expected_points = current_points_map.get(run.id)
        expected_streak = runs_streak_updates.get(run.id)
        needs_update = False

        if expected_points is not None and run.points != expected_points:
            run.points = expected_points
            needs_update = True

        if expected_streak is not None and run.bonus != expected_streak:
            run.bonus = expected_streak
            needs_update = True

        if needs_update:
            runs_to_fix.append(run)

    if not dry_run and runs_to_fix:
        Runs.objects.bulk_update(runs_to_fix, ["points", "bonus"])

    return entries_created_count, len(runs), len(runs_to_fix)
