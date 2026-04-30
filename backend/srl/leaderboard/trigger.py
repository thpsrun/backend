from celery import chain
from django.db.models import Min

from srl.leaderboard.recalculation import (
    get_leaderboard_time_column,
    get_runs_for_leaderboard,
)
from srl.leaderboard.resolution import resolve_leaderboard
from srl.models.runs import Runs
from srl.tasks import recalculate_leaderboard_task, recalculate_streaks_task


def _wr_check(
    run: Runs,
    leaderboard: dict,
) -> bool:
    """Check if a run's time could make it a WR on its leaderboard."""
    time_col = get_leaderboard_time_column(leaderboard)

    run_time = getattr(run, time_col) or 0
    if run_time <= 0:
        run_time = getattr(run, "time_secs") or 0
    if run_time <= 0:
        return False

    result = (
        get_runs_for_leaderboard(leaderboard)
        .exclude(id=run.id)
        .exclude(**{f"{time_col}__lte": 0})
        .exclude(**{f"{time_col}__isnull": True})
        .aggregate(min_time=Min(time_col))
    )
    current_wr_time = result["min_time"]

    if current_wr_time is None:
        return True

    return run_time < current_wr_time


def recalculate_run(
    run: Runs,
) -> None:
    """Dispatch async leaderboard recalculation for a verified run.

    Resolves the run's leaderboard variant, dispatches the recalculation task,
    and conditionally chains streak recalculation if the run could affect WR.

    This is the single entry point; call it from any endpoint that verifies a run.

    Arguments:
        run: A Run instance that was just verified or had its time updated.
    """
    leaderboard = resolve_leaderboard(run)
    recalc = recalculate_leaderboard_task.si(leaderboard)

    if _wr_check(run, leaderboard):
        chain(recalc, recalculate_streaks_task.si(leaderboard)).delay()
    else:
        recalc.delay()
