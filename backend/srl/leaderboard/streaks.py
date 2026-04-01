from datetime import date

from dateutil.relativedelta import relativedelta
from django.conf import settings

from srl.models.runs import Runs
from srl.utils import calculate_bonus, get_streak_start_date


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
