from api.signals import disable_history_signals
from api.v1.routers.utils.cache_utils import _HISTORY_CACHE_PREFIX
from django.core.cache import caches
from django.db import transaction
from django_redis import get_redis_connection

from srl.leaderboard.recalculation import (
    build_leaderboard_metadata,
    clear_leaderboard_history,
    process_leaderboard,
)
from srl.tasks._common import RECALC_LOCK_TTL_SECONDS, recalc_lock_key


def _purge_history_cache_for_scopes(
    scopes: list,
) -> None:
    """Best-effort invalidate the pointslb history cache for the given scopes."""

    cache = caches["default"]
    delete_pattern = getattr(cache, "delete_pattern", None)
    if delete_pattern is None:
        return
    for scope in scopes:
        delete_pattern(f"{_HISTORY_CACHE_PREFIX}:{scope}:*")


def run_leaderboard_recompute(
    leaderboard_dict: dict,
) -> None:
    """Clear and rebuild a single leaderboard variant's history and points."""
    from srl.leaderboard.streaks import apply_streaks_to_leaderboard

    game_is_ce = build_leaderboard_metadata([leaderboard_dict])
    scopes = ["all", leaderboard_dict["game_id"]]
    with transaction.atomic():
        with disable_history_signals():
            clear_leaderboard_history(leaderboard_dict)
            process_leaderboard(leaderboard_dict, dry_run=False, game_is_ce=game_is_ce)
            apply_streaks_to_leaderboard(leaderboard_dict)
        transaction.on_commit(lambda: _purge_history_cache_for_scopes(scopes))


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
