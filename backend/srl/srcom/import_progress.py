import json
import time

from django.core.cache import cache

_TTL = 60 * 60 * 24

_RUN_METRICS = (
    "games_enumerated",
    "lb_total",
    "lb_done",
    "lb_failed",
    "runs_total",
    "runs_done",
    "runs_failed",
)
_OBSOLETE_METRICS = (
    "players_total",
    "players_done",
    "players_failed",
)


def _key(
    series_id: str,
    metric: str,
) -> str:
    return f"import:{series_id}:{metric}"


def seed(
    series_id: str,
    *,
    games_total: int,
    game_ids: list[str],
) -> None:
    cache.set(
        _key(series_id, "phase"),
        "metadata",
        _TTL,
    )
    cache.set(
        _key(series_id, "games_total"),
        games_total,
        _TTL,
    )
    cache.set(
        _key(series_id, "game_ids"),
        json.dumps(game_ids),
        _TTL,
    )
    cache.set(
        _key(series_id, "started_at"),
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        _TTL,
    )
    for metric in _RUN_METRICS + _OBSOLETE_METRICS:
        cache.set(
            _key(series_id, metric),
            0,
            _TTL,
        )


def seed_obsolete(
    series_id: str,
    *,
    players_total: int,
) -> None:
    cache.set(
        _key(series_id, "players_total"),
        players_total,
        _TTL,
    )
    cache.set(
        _key(series_id, "players_done"),
        0,
        _TTL,
    )
    cache.set(
        _key(series_id, "players_failed"),
        0,
        _TTL,
    )


def bump(
    series_id: str,
    metric: str,
    n: int = 1,
) -> None:
    key = _key(series_id, metric)
    try:
        cache.incr(key, n)
    except ValueError:
        cache.set(
            key,
            n,
            _TTL,
        )


def set_phase(
    series_id: str,
    phase: str,
) -> None:
    cache.set(
        _key(series_id, "phase"),
        phase,
        _TTL,
    )


def progress_get(
    series_id: str,
) -> dict | None:
    phase = cache.get(_key(series_id, "phase"))
    if phase is None:
        return None
    data: dict = {
        "phase": phase,
        "started_at": cache.get(_key(series_id, "started_at")),
        "games_total": cache.get(_key(series_id, "games_total")) or 0,
    }
    raw_ids = cache.get(_key(series_id, "game_ids"))
    data["game_ids"] = json.loads(raw_ids) if raw_ids else []
    for metric in _RUN_METRICS + _OBSOLETE_METRICS:
        data[metric] = cache.get(_key(series_id, metric)) or 0
    return data


def is_drained_runs(
    c: dict,
) -> bool:
    return (
        c["games_enumerated"] == c["games_total"]
        and c["lb_done"] + c["lb_failed"] == c["lb_total"]
        and c["runs_done"] + c["runs_failed"] == c["runs_total"]
    )


def is_drained_obsolete(
    c: dict,
) -> bool:
    return c["players_done"] + c["players_failed"] == c["players_total"]
