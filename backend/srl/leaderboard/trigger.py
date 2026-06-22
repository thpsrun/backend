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


def recalculate_run_sync(
    run: Runs,
    actor_user_id: int | None = None,
) -> None:
    """Recompute a run's leaderboard variant inline so points exist before the caller returns."""
    from srl.leaderboard.recompute import recompute_variant_locked
    from srl.srcom.utils import apply_player_obsolescence

    leaderboard = resolve_leaderboard(run)

    # Keep-best dedup before recomputing: a newly verified run must obsolete the same player's
    # slower runs in this variant. The SRC-discovery (finalize_run_standings) and API
    # create/update paths already do this; without it here the moderation/verify path leaves the
    # older run stranded (verified + not obsolete + points=0) until the discovery crawl repairs it.
    apply_player_obsolescence(
        game_id=leaderboard["game_id"],
        category_id=leaderboard["category_id"],
        variable_value_map=leaderboard["variable_value_map"],
        player_ids=list(run.players.values_list("id", flat=True)),
        run_type=leaderboard["runtype"],
        level_id=leaderboard["level_id"],
    )

    ran = recompute_variant_locked(leaderboard)
    if not ran:
        recalculate_run(
            run, cause="verify_sync_lock_contended", actor_user_id=actor_user_id
        )
        return

    with_streaks = _wr_check(run, leaderboard)

    record_event(
        game=run.game.id,
        event_type=GameAuditEvent.EventType.RUN_RECALC,
        summary=f"Run recalc: {run.pk}",
        target=run,
        payload={
            "run_id": run.pk,
            "cause": "verify_sync",
            "with_streaks": with_streaks,
        },
    )

    if with_streaks:
        recalculate_streaks_task.si(leaderboard, actor_user_id=actor_user_id).delay()
