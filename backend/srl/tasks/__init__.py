from srl.srcom.recon_dispatch import PHASE_2, PHASE_3, register_phase_task
from srl.tasks.celery_cleanup import prune_api_activity_log
from srl.tasks.recalc import (
    build_streaks_task,
    rebackfill_game_runs,
    recalculate_game_boards,
    recalculate_leaderboard_task,
    recalculate_streaks_task,
)

from ._common import actor_from_user_id, save_sync_task
from .reconciliation import (
    SERIES_RECON_ALL_TARGET,
    dispatch_phase_2,
    dispatch_phase_3,
    run_reconciliation_job,
    run_series_reconciliation,
    sweep_stuck_reconciliation_jobs,
)
from .src_discover import (
    discover_new_series_games,
    discover_runs,
    dispatch_run_discovery,
)
from .src_sync import (
    refresh_bot_session,
    replay_failed_edits,
    sync_src_action,
    sync_src_settings,
    trip_circuit_breaker,
)

register_phase_task(PHASE_2, dispatch_phase_2)
register_phase_task(PHASE_3, dispatch_phase_3)

__all__ = [
    "SERIES_RECON_ALL_TARGET",
    "actor_from_user_id",
    "build_streaks_task",
    "discover_runs",
    "discover_new_series_games",
    "dispatch_phase_2",
    "dispatch_phase_3",
    "dispatch_run_discovery",
    "prune_api_activity_log",
    "rebackfill_game_runs",
    "recalculate_game_boards",
    "recalculate_leaderboard_task",
    "recalculate_streaks_task",
    "refresh_bot_session",
    "replay_failed_edits",
    "run_reconciliation_job",
    "run_series_reconciliation",
    "save_sync_task",
    "sweep_stuck_reconciliation_jobs",
    "sync_src_action",
    "sync_src_settings",
    "trip_circuit_breaker",
]
