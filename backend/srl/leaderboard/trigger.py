from auditlog.models import GameAuditEvent
from auditlog.recorders import record_event
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
    cause: str | None = None,
    actor_user_id: int | None = None,
) -> None:
    """Dispatch async leaderboard recalculation for a verified run.

    Arguments:
        run (Runs): A Run instance that was just verified or had its time updated.
        cause (str | None): Caller-supplied label describing why the recalc fires
            (e.g. "vid_status=verified", "time edited"). Recorded in the
            game's audit log; safe to omit.
        actor_user_id (int | None): Optional user id to attribute the recalc to in the audit
            log. Forwarded to the Celery tasks so the actor context survives
            the broker hop.
    """

    leaderboard = resolve_leaderboard(run)
    with_streaks = _wr_check(run, leaderboard)

    record_event(
        game=run.game.id,
        event_type=GameAuditEvent.EventType.RUN_RECALC,
        summary=f"Run recalc: {run.pk}",
        target=run,
        payload={
            "run_id": run.pk,
            "cause": cause,
            "with_streaks": with_streaks,
        },
    )

    recalc = recalculate_leaderboard_task.si(
        leaderboard,
        actor_user_id=actor_user_id,
    )
    if with_streaks:
        chain(
            recalc,
            recalculate_streaks_task.si(
                leaderboard,
                actor_user_id=actor_user_id,
            ),
        ).delay()
    else:
        recalc.delay()
