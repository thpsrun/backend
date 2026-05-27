from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from srl.models import (
    Categories,
    Games,
    Levels,
    Players,
    RunPlayers,
    Runs,
    RunVariableValues,
    Series,
    Variables,
)
from srl.srcom.categories import sync_categories
from srl.srcom.games import sync_game
from srl.srcom.levels import sync_levels
from srl.srcom.players import sync_players
from srl.srcom.reconciliation import reconciliation_upsert_check
from srl.srcom.schema.src import SrcRunsModel
from srl.srcom.utils import create_run_default
from srl.srcom.variables import sync_variables
from srl.utils import src_api

log = logging.getLogger(__name__)

_DISPATCH_LOCK_KEY = "src_discovery:dispatch:lock"
_V1_RUNS_URL = "https://www.speedrun.com/api/v1/runs"

_SRC_TO_LOCAL_STATUS: dict[str, str] = {
    "new": Runs.VidStatus.NEW,
    "verified": Runs.VidStatus.VERIFIED,
    "rejected": Runs.VidStatus.REJECTED,
}


def _ensure_dependencies(
    payload: dict[str, Any],
) -> bool:
    """Ensure game/category/variables/values/level/players exist locally."""
    game_id = payload.get("game")
    if not game_id or not Games.objects.filter(id=game_id).exists():
        log.info(
            "src_discover: skipping run %s - game %s not yet imported",
            payload.get("id"),
            game_id,
        )
        return False

    category_id = payload.get("category")
    if category_id and not Categories.objects.filter(id=category_id).exists():
        try:
            sync_categories(category_id)
        except Exception as exc:
            log.warning(
                "src_discover: sync_categories(%s) failed for run %s: %s",
                category_id,
                payload.get("id"),
                exc,
            )
            return False

    for var_id in (payload.get("values") or {}).keys():
        if not Variables.objects.filter(id=var_id).exists():
            try:
                sync_variables(var_id)
            except Exception as exc:
                log.warning(
                    "src_discover: sync_variables(%s) failed for run %s: %s",
                    var_id,
                    payload.get("id"),
                    exc,
                )
                return False

    level_id = payload.get("level")
    if level_id and not Levels.objects.filter(id=level_id).exists():
        try:
            sync_levels(level_id)
        except Exception as exc:
            log.warning(
                "src_discover: sync_levels(%s) failed for run %s: %s",
                level_id,
                payload.get("id"),
                exc,
            )
            return False

    user_player_ids = [
        p.get("id")
        for p in (payload.get("players") or [])
        if isinstance(p, dict) and p.get("rel") == "user" and p.get("id")
    ]
    existing_ids = set(
        Players.objects.filter(id__in=user_player_ids).values_list(
            "id",
            flat=True,
        ),
    )
    for pid in set(user_player_ids) - existing_ids:
        try:
            sync_players(pid, download_pfp=True)
        except Exception as exc:
            log.warning(
                "src_discover: sync_players(%s) failed for run %s: %s",
                pid,
                payload.get("id"),
                exc,
            )
            return False

    return True


def _lightweight_upsert_run(
    payload: dict[str, Any],
    target_status: str,
) -> None:
    """Upsert a Runs row from a v1 listing payload without leaderboard side effects."""
    run_data = SrcRunsModel.model_validate(payload).model_dump()

    default = create_run_default(run_data, place=0, lrtfix=False)
    default["points"] = 0
    default["place"] = 0
    default["obsolete"] = False
    default["obsoleted_at"] = None
    default["vid_status"] = target_status

    user_player_ids = [
        p["id"]
        for p in (payload.get("players") or [])
        if isinstance(p, dict) and p.get("rel") == "user" and p.get("id")
    ]

    with transaction.atomic():
        run_obj = reconciliation_upsert_check(
            Runs,
            defaults=default,
            record_type="run",
            id=payload["id"],
        )

        RunPlayers.objects.filter(run=run_obj).delete()
        RunPlayers.objects.bulk_create(
            [
                RunPlayers(run=run_obj, player_id=pid, order=order)
                for order, pid in enumerate(user_player_ids, start=1)
            ],
        )

        for var_id, val_id in (payload.get("values") or {}).items():
            reconciliation_upsert_check(
                RunVariableValues,
                defaults={},
                record_type="run_variable_value",
                run=run_obj,
                variable_id=var_id,
                value_id=val_id,
            )


def _call_sync_single_run(
    run_id: str,
    success_reason: str,
) -> str:
    from srl.srcom.leaderboards import sync_single_run

    try:
        sync_single_run(run_id)
    except Exception as exc:
        log.warning(
            "src_discover: sync_single_run(%s) failed: %s",
            run_id,
            exc,
        )
        return "sync_single_run_failed"
    return success_reason


def _call_lightweight_upsert(
    payload: dict[str, Any],
    target_status: str,
    success_reason: str,
) -> str:
    try:
        _lightweight_upsert_run(payload, target_status)
    except Exception as exc:
        log.warning(
            "src_discover: lightweight upsert failed run=%s: %s",
            payload.get("id"),
            exc,
        )
        return "upsert_failed"
    return success_reason


def _process_run_payload(
    payload: dict[str, Any],
    src_status: str,
) -> str:
    """Apply the discovery state machine. Returns an outcome string for logging."""
    run_id = payload.get("id")
    if not run_id:
        return "no_id"

    target_status = _SRC_TO_LOCAL_STATUS.get(src_status)
    if target_status is None:
        return "unknown_status"

    local = Runs.objects.filter(id=run_id).only("id", "vid_status").first()

    if local is None:
        if not _ensure_dependencies(payload):
            return "deps_missing"
        if target_status == Runs.VidStatus.VERIFIED:
            return _call_sync_single_run(run_id, "verified_imported")
        reason = (
            "new_imported"
            if target_status == Runs.VidStatus.NEW
            else "rejected_imported"
        )
        return _call_lightweight_upsert(payload, target_status, reason)

    if target_status == Runs.VidStatus.NEW:
        return "skip_still_new"

    if not _ensure_dependencies(payload):
        return "deps_missing"

    if target_status == Runs.VidStatus.VERIFIED:
        return _call_sync_single_run(run_id, "verified_refreshed")

    return _call_lightweight_upsert(
        payload,
        Runs.VidStatus.REJECTED,
        "rejected_refreshed",
    )


@shared_task(name="srl.tasks.discover_runs")
def discover_runs(
    game_id: str,
) -> dict[str, int]:
    """Poll v1 for new/verified/rejected runs on `game_id` and reconcile locally."""
    limit = int(getattr(settings, "SRC_DISCOVERY_PER_GAME_LIMIT", 20))
    counts: dict[str, int] = {}

    statuses: list[tuple[str, str]] = [
        ("new", "submitted"),
        ("verified", "verify-date"),
        ("rejected", "verify-date"),
    ]

    for src_status, orderby in statuses:
        url = (
            f"{_V1_RUNS_URL}?game={game_id}&status={src_status}"
            f"&orderby={orderby}&direction=desc&max={int(limit)}"
        )
        try:
            data = src_api(url)
        except Exception as exc:
            log.warning(
                "src_discover: v1 list failed for game=%s status=%s: %s",
                game_id,
                src_status,
                exc,
            )
            continue

        runs = data if isinstance(data, list) else []
        for v1_run in runs:
            try:
                reason = _process_run_payload(v1_run, src_status)
            except Exception as exc:
                log.warning(
                    "src_discover: failed run=%s game=%s status=%s: %s",
                    (v1_run or {}).get("id"),
                    game_id,
                    src_status,
                    exc,
                )
                reason = "exception"
            counts[reason] = counts.get(reason, 0) + 1

    log.info(
        "src_discover: game=%s outcomes=%s",
        game_id,
        counts,
    )
    return counts


@shared_task(name="srl.tasks.dispatch_run_discovery")
def dispatch_run_discovery() -> dict:
    """Fan out per-game discovery once per minute under a cache lock."""
    poll_seconds = int(getattr(settings, "SRC_DISCOVERY_POLL_SECONDS", 60))
    lock_ttl = max(poll_seconds * 2, 60)
    acquired = cache.add(_DISPATCH_LOCK_KEY, "1", timeout=lock_ttl)
    if not acquired:
        log.info("src_discover: dispatch skipped - lock held")
        return {"skipped": True, "reason": "lock_held"}

    try:
        game_ids = list(Games.objects.values_list("id", flat=True))
        for gid in game_ids:
            discover_runs.delay(gid)
        return {"skipped": False, "dispatched": len(game_ids)}
    finally:
        cache.delete(_DISPATCH_LOCK_KEY)


@shared_task(name="srl.tasks.discover_new_series_games")
def discover_new_series_games() -> dict:
    """Walk each Series, import any new games, and reconcile their runs."""
    from srl.srcom.series import iter_series_games

    existing_ids = set(Games.objects.values_list("id", flat=True))
    added: list[str] = []
    for series in Series.objects.all():
        try:
            for game in iter_series_games(series.id):
                gid = game.get("id") if isinstance(game, dict) else None
                if not gid or gid in existing_ids:
                    continue
                try:
                    sync_game(gid)
                except Exception as exc:
                    log.warning(
                        "src_discover series-scan: sync_game(%s) failed: %s",
                        gid,
                        exc,
                    )
                    continue
                existing_ids.add(gid)
                added.append(gid)
        except Exception as exc:
            log.warning(
                "src_discover series-scan: iter_series_games(%s) failed: %s",
                series.id,
                exc,
            )
    return {"added": added, "count": len(added)}
