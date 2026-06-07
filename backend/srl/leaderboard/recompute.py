from django.db import transaction
from django_redis import get_redis_connection

from srl.leaderboard.recalculation import (
    build_leaderboard_metadata,
    clear_leaderboard_history,
    process_leaderboard,
)
from srl.tasks._common import RECALC_LOCK_TTL_SECONDS, recalc_lock_key


def run_leaderboard_recompute(
    leaderboard_dict: dict,
) -> None:
    """Clear and rebuild a single leaderboard variant's history and points.

    The lock-free core shared by the Celery task and the synchronous verify path. Callers are
    responsible for holding the per-variant recalc lock (see `recompute_variant_locked`).
    """
    _, game_is_ce, *_ = build_leaderboard_metadata([leaderboard_dict])
    with transaction.atomic():
        clear_leaderboard_history(leaderboard_dict)
        process_leaderboard(leaderboard_dict, dry_run=False, game_is_ce=game_is_ce)


def recompute_variant_locked(
    leaderboard_dict: dict,
) -> bool:
    """Acquire the per-variant recalc lock and recompute inline. Returns False if locked.

    Used by the verify request to guarantee points are assigned before it returns. If another worker
    already holds the lock for this variant, it will recompute with our just-committed run included,
    so returning False is safe.
    """
    lock_key = recalc_lock_key(leaderboard_dict)
    redis = get_redis_connection("default")
    if not redis.set(lock_key, "1", nx=True, ex=RECALC_LOCK_TTL_SECONDS):
        return False
    try:
        run_leaderboard_recompute(leaderboard_dict)
        return True
    finally:
        try:
            redis.delete(lock_key)
        except Exception:
            pass
