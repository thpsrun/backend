from datetime import date

from dateutil.relativedelta import relativedelta
from django.conf import settings

from srl.models.runs import Runs
from srl.utils import calculate_bonus, get_streak_start_date


def apply_streaks_to_leaderboard(
    leaderboard_dict: dict,
) -> list[Runs]:
    """Apply the WR streak bonus to every co-WR run on a leaderboard variant.

    A variant can have several runs tied at the fastest time (co-WRs). Each independently holds
    (or, for a fresh tie, starts) its own streak, so the bonus must be evaluated for all of them.
    Selecting a single WR run (e.g. via `.order_by(time_col).first()`, whose tie-break is
    arbitrary) silently drops a long-standing holder's bonus when a newcomer ties their time.

    Arguments:
        leaderboard_dict (dict): The leaderboard variant signature (as built by
            `resolve_leaderboard` / `enumerate_leaderboard_variants`).

    Returns:
        list[Runs]: The co-WR runs whose bonus/points were changed and saved.
    """
    from srl.leaderboard.recalculation import (
        get_leaderboard_time_column,
        get_runs_for_leaderboard,
    )

    time_col = get_leaderboard_time_column(leaderboard_dict)

    ranked = list(
        get_runs_for_leaderboard(leaderboard_dict)
        .exclude(**{f"{time_col}__lte": 0})
        .exclude(**{f"{time_col}__isnull": True})
        .order_by(time_col)
        .select_related("game")
        .prefetch_related("players")
    )

    if not ranked:
        return []

    best_time = getattr(ranked[0], time_col)

    updated: list[Runs] = []
    for run in ranked:
        # Runs come back sorted by the board's timing column, so once the time exceeds the
        # fastest we are past the co-WR set and can stop.
        if getattr(run, time_col) != best_time:
            break

        result = apply_streak_to_run(run)

        if result is not None:
            new_bonus, new_points = result
            run.bonus = new_bonus
            run.points = new_points
            run.save(update_fields=["bonus", "points"])
            updated.append(run)

    return updated


def apply_streak_to_run(
    run: Runs,
    check_date: date | None = None,
) -> tuple[int, int] | None:
    """Calculate streak bonus for a WR run and return updated values.

    Requires run.game (select_related) and run.players (prefetch_related)
    to be loaded before calling.

    Arguments:
        run: A verified WR run (place=1, obsolete=False).
        check_date: Date to calculate streak against. Defaults to today.

    Returns:
        Tuple of (new_bonus, new_points) if the run needs updating,
        or None if no change is needed.
    """
    if check_date is None:
        check_date = date.today()

    game = run.game
    if not game or game.is_ce:
        return None

    streak_start = get_streak_start_date(run)
    if not streak_start:
        return None

    if check_date <= streak_start:
        return None

    delta = relativedelta(check_date, streak_start)
    months_held = delta.years * 12 + delta.months

    if months_held <= 0:
        return None

    new_bonus = min(months_held, settings.STREAK_MAX_MONTHS)

    if new_bonus == run.bonus:
        return None

    if run.runtype == "main":
        max_points = game.pointsmax
    else:
        max_points = game.ipointsmax

    streak_bonus = calculate_bonus(run.runtype, new_bonus, game.is_ce)
    new_points = max_points + streak_bonus

    return new_bonus, new_points
