import time
from collections import defaultdict
from io import StringIO

from auditlog.models import GameAuditEvent
from auditlog.recorders import record_event
from celery import chain, shared_task
from celery.exceptions import MaxRetriesExceededError
from django.core.management import call_command
from django_redis import get_redis_connection

from srl.leaderboard.recalculation import (
    get_leaderboard_time_column,
    get_runs_for_leaderboard,
)
from srl.leaderboard.streaks import apply_streak_to_run
from srl.models import Games, Runs, RunVariableValues
from srl.srcom.utils import variables_hash

from ._common import (
    RECALC_LOCK_TTL_SECONDS,
    actor_from_user_id,
    logger,
    recalc_lock_key,
)


@shared_task(
    bind=True,
    name="srl.tasks.recalculate_leaderboard_task",
    acks_late=True,
    reject_on_worker_lost=True,
)
def recalculate_leaderboard_task(
    self,
    leaderboard_dict: dict,
    *,
    actor_user_id: int | None = None,
) -> None:
    """Recalculate points and history for a single leaderboard variant.

    Clears existing RunHistory for the variant, then rebuilds from scratch. Dispatched by
    recalculate_run() when a run is verified, and by Phase 3 of a reconciliation job (one dispatch
    per affected variant)."""

    lock_key = recalc_lock_key(leaderboard_dict)
    redis = get_redis_connection("default")
    if not redis.set(lock_key, "1", nx=True, ex=RECALC_LOCK_TTL_SECONDS):
        # Another worker holds the lock for this variant. Brief retry handles the common case
        # where two upstreams dispatched the same variant; after that we yield without writing.
        try:
            raise self.retry(countdown=30, max_retries=3)
        except MaxRetriesExceededError:
            with actor_from_user_id(actor_user_id):
                return
            return

    try:
        with actor_from_user_id(actor_user_id):
            from srl.leaderboard.recompute import run_leaderboard_recompute

            run_leaderboard_recompute(leaderboard_dict)
    finally:
        try:
            redis.delete(lock_key)
        except Exception:
            logger.exception(
                "recalc_lock_release_failed",
                extra={"lock_key": lock_key},
            )


@shared_task(
    name="srl.tasks.recalculate_streaks_task",
    acks_late=True,
    reject_on_worker_lost=True,
)
def recalculate_streaks_task(
    leaderboard_dict: dict,
    *,
    actor_user_id: int | None = None,
) -> None:
    """Recalculate streak bonus for the current WR on a leaderboard variant."""

    with actor_from_user_id(actor_user_id):
        time_col = get_leaderboard_time_column(leaderboard_dict)

        wr_run = (
            get_runs_for_leaderboard(leaderboard_dict)
            .exclude(**{f"{time_col}__lte": 0})
            .exclude(**{f"{time_col}__isnull": True})
            .order_by(time_col)
            .select_related("game")
            .prefetch_related("players")
            .first()
        )
        if wr_run is None:
            return

        result = apply_streak_to_run(wr_run)
        if result is not None:
            new_bonus, new_points = result
            wr_run.bonus = new_bonus
            wr_run.points = new_points
            wr_run.save(update_fields=["bonus", "points"])


@shared_task(name="srl.tasks.build_streaks_task")
def build_streaks_task() -> None:
    """Daily Celery schedule entry: award monthly anniversary streak bonuses."""
    call_command("build_streaks")


@shared_task(name="srl.tasks.rebackfill_game_runs")
def rebackfill_game_runs(
    game_slug: str,
    *,
    triggered_by: str | None = None,
    actor_user_id: int | None = None,
) -> dict:
    """Copy timing data into each run's resolved primary slot, then recompute points.

    Runs `backfill_run_primary_data` so every run has a value in the column the leaderboard now
    ranks by, then dispatches a full board recalc so `Run.points`/`Run.bonus` reflect the new
    ranking."""

    with actor_from_user_id(actor_user_id):
        buf = StringIO()
        call_command(
            "backfill_run_primary_data",
            game=game_slug,
            stdout=buf,
        )
        recalculate_game_boards.delay(
            game_slug,
            triggered_by=triggered_by,
            actor_user_id=actor_user_id,
        )
        return {
            "game_slug": game_slug,
            "output": buf.getvalue(),
        }


@shared_task(name="srl.tasks.recalculate_game_boards")
def recalculate_game_boards(
    game_slug: str,
    triggered_by: str | None = None,
    actor_user_id: int | None = None,
) -> dict:
    """Rebuild every leaderboard variant for a game, then re-apply WR streaks.

    Dispatches `recalculate_leaderboard_task` -> `recalculate_streaks_task` as a Celery chain per
    unique variant so each variant's RunHistory, points, and streak bonus all get rebuilt without
    having to call build_run_history / build_streaks separately."""

    with actor_from_user_id(actor_user_id):
        start = time.monotonic()
        game = Games.objects.filter(slug=game_slug).first()
        if game is None:
            return {"game_slug": game_slug, "boards": 0}

        base_runs = Runs.objects.filter(
            game=game,
            obsolete=False,
            vid_status="verified",
        )
        variant_keys = base_runs.values("category_id", "level_id", "runtype").distinct()

        rvvs_by_run: dict[str, dict[str, str]] = defaultdict(dict)
        for run_id, var_id, val_id in RunVariableValues.objects.filter(
            run__in=base_runs,
        ).values_list("run_id", "variable_id", "value_id"):
            rvvs_by_run[run_id][var_id] = val_id

        seen: set[tuple] = set()
        boards_dispatched = 0
        for vk in variant_keys:
            category_id = vk["category_id"]
            level_id = vk["level_id"]
            runtype = vk["runtype"]

            variant_run_ids = list(
                base_runs.filter(
                    category_id=category_id,
                    level_id=level_id,
                    runtype=runtype,
                ).values_list("id", flat=True),
            )
            seen_hashes: set[str] = set()
            for run_id in variant_run_ids:
                var_map = rvvs_by_run.get(run_id, {})
                vh = variables_hash(var_map) if var_map else ""
                if vh in seen_hashes:
                    continue
                seen_hashes.add(vh)
                key = (category_id, level_id, runtype, vh)
                if key in seen:
                    continue
                seen.add(key)

                leaderboard = {
                    "game_id": game.id,
                    "category_id": category_id,
                    "level_id": level_id,
                    "runtype": runtype,
                    "variable_value_map": var_map,
                }
                chain(
                    recalculate_leaderboard_task.si(
                        leaderboard,
                        actor_user_id=actor_user_id,
                    ),
                    recalculate_streaks_task.si(
                        leaderboard,
                        actor_user_id=actor_user_id,
                    ),
                ).delay()
                boards_dispatched += 1

        duration_ms = int((time.monotonic() - start) * 1000)
        record_event(
            game=game,
            event_type=GameAuditEvent.EventType.RECALC_DISPATCH,
            summary=f"Recalc dispatched: {boards_dispatched} board(s)",
            payload={
                "boards_count": boards_dispatched,
                "duration_ms": duration_ms,
                "triggered_by": triggered_by,
            },
        )

        return {"game_slug": game_slug, "boards": boards_dispatched}


@shared_task(name="srl.tasks.sweep_unranked_verified_runs")
def sweep_unranked_verified_runs() -> int:
    """Re-queue a board recalc for any verified, non-obsolete run that has no points.

    Runs a recalc can never score are skipped instead of being re-queued every run, so the sweep
    cannot spin on them forever; a run with import issues (e.g. a missing required timing method) or
    no resolved primary time has no scoreable time. They are logged for manual attention.

    Returns:
        int: The number of runs actually re-queued for recalculation (excludes skipped ones).
    """
    from srl.leaderboard.trigger import recalculate_run

    orphans = Runs.objects.filter(
        vid_status="verified", obsolete=False, points=0
    ).select_related("game")
    count = 0
    unscoreable: list[str] = []
    for run in orphans:
        if run.has_import_issues or run.p_time_secs is None:
            unscoreable.append(run.id)
            continue
        recalculate_run(run, cause="unranked_verified_sweeper")
        count += 1

    if unscoreable:
        logger.warning(
            "sweep_unranked_verified_runs: skipped %d unscoreable run(s) "
            "(import issues or no primary time); needs manual attention: %s",
            len(unscoreable),
            unscoreable,
        )
    return count
