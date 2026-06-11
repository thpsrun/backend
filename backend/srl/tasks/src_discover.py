from __future__ import annotations

import logging
from datetime import timezone as dt_timezone
from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from srl.models import (
    Categories,
    Games,
    Levels,
    Platforms,
    Players,
    RunPlayers,
    Runs,
    RunVariableValues,
    Series,
    Variables,
    VariableValues,
)
from srl.srcom.categories import sync_categories
from srl.srcom.games import sync_game
from srl.srcom.levels import sync_levels
from srl.srcom.players import sync_players
from srl.srcom.reconciliation import reconciliation_upsert_check
from srl.srcom.schema.src import SrcRunsModel
from srl.srcom.utils import create_run_default
from srl.srcom.variables import sync_variables
from srl.utils import src_api, src_api_probe

log = logging.getLogger(__name__)

_DISPATCH_LOCK_KEY = "src_discovery:dispatch:lock"
_GAME_DISCOVERY_LOCK_KEY = "src_discovery:game:{game_id}:lock"
_GAME_DISCOVERY_LOCK_TTL = 900
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

    for var_id, value_id in (payload.get("values") or {}).items():
        needs_sync = not Variables.objects.filter(id=var_id).exists()
        if not needs_sync and value_id:
            needs_sync = not VariableValues.objects.filter(
                var_id=var_id,
                value=value_id,
            ).exists()
        if not needs_sync:
            continue
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

        run_obj.refresh_import_issues()


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


# This batch of code is mainly to help identify if an SRC run's metadata is unchanged versus what
# we have in the local DB. The reason for this is, if we import runs and they are verified, then it
# would kick off recalculations of points and standings. The current code is kinda bad in that it
# will blindly ingest those runs, but these functions will help verify local vs SRC; if there is a
# change then it is ingested and recalculation can happen, and if not then we can ignore it.
def _norm_dt(
    value: Any,
) -> Any:
    """Normalize a datetime to UTC at second precision for stable comparison."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_timezone.utc)
    return value.astimezone(dt_timezone.utc).replace(microsecond=0)


def _ne_secs(
    src_val: Any,
    local_val: Any,
) -> bool:
    """True when two second-values differ at millisecond precision (None treated as 0)."""
    return round(float(src_val or 0.0), 3) != round(float(local_val or 0.0), 3)


def _ne_platform(
    src_platform: str | None,
    local_platform_id: str | None,
) -> bool:
    """True when the SRC platform differs from the stored platform."""
    src_platform = src_platform or None
    if src_platform == local_platform_id:
        return False
    if (
        src_platform is not None
        and not Platforms.objects.filter(id=src_platform).exists()
    ):
        src_platform = None
    return src_platform != local_platform_id


def _src_run_unchanged(
    payload: dict[str, Any],
    local: Runs,
) -> bool:
    """True when the SRC payload matches the stored run on every sync-sourced field.

    Compares only the fields create_run_default writes from SRC. Derived fields and the
    player/value tables are not compared. If a validation error occurs or another hicup comes up,
    then we will just assume the run needs to be re-applied to the local DB."""
    try:
        model = SrcRunsModel.model_validate(payload)
    except Exception:
        return False
    try:
        if model.status.status != local.vid_status:
            return False
        if _ne_secs(model.times.realtime_t, local.time_secs):
            return False
        if _ne_secs(model.times.realtime_noloads_t, local.timenl_secs):
            return False
        if _ne_secs(model.times.ingame_t, local.timeigt_secs):
            return False
        if (model.video_uri or None) != (local.video or None):
            return False
        if (model.comment or None) != (local.description or None):
            return False
        if bool(model.system.emulated) != bool(local.emulated):
            return False
        if _ne_platform(model.system.platform, local.platform_id):
            return False
        if _norm_dt(model.date) != _norm_dt(local.date):
            return False
        if _norm_dt(model.status.verify_date) != _norm_dt(local.v_date):
            return False
    except Exception:
        return False
    return True


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

    local = (
        Runs.objects.filter(id=run_id)
        .only(
            "id",
            "vid_status",
            "time_secs",
            "timenl_secs",
            "timeigt_secs",
            "video",
            "description",
            "date",
            "v_date",
            "platform",
            "emulated",
        )
        .first()
    )

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

    if _src_run_unchanged(payload, local):
        return "skipped_unchanged"

    if not _ensure_dependencies(payload):
        return "deps_missing"

    if target_status == Runs.VidStatus.VERIFIED:
        return _call_sync_single_run(run_id, "verified_refreshed")

    return _call_lightweight_upsert(
        payload,
        Runs.VidStatus.REJECTED,
        "rejected_refreshed",
    )


def _reconcile_deleted_unverified_runs(
    game_id: str,
    src_new_ids: set[str],
    counts: dict[str, int],
) -> None:
    """Remove local unverified runs that SRC no longer reports as existing."""
    local_unverified = list(
        Runs.objects.filter(
            game=game_id,
            vid_status__in=(Runs.VidStatus.NEW, Runs.VidStatus.REVIEW),
        ).values_list("id", flat=True),
    )

    for run_id in local_unverified:
        if run_id in src_new_ids:
            continue

        status_code, envelope = src_api_probe(f"{_V1_RUNS_URL}/{run_id}")

        if status_code == 404:
            _remove_deleted_run(run_id)
            counts["deleted_on_src"] = counts.get("deleted_on_src", 0) + 1
            continue

        if status_code != 200 or not isinstance(envelope, dict):
            log.warning(
                "src_discover: probe for run=%s game=%s returned %s; skipping",
                run_id,
                game_id,
                status_code,
            )
            counts["probe_failed"] = counts.get("probe_failed", 0) + 1
            continue

        run_payload = envelope.get("data")
        current_status = (
            (run_payload.get("status") or {}).get("status")
            if isinstance(run_payload, dict)
            else None
        )
        if (
            not isinstance(run_payload, dict)
            or current_status not in _SRC_TO_LOCAL_STATUS
        ):
            counts["probe_unknown"] = counts.get("probe_unknown", 0) + 1
            continue

        try:
            reason = _process_run_payload(run_payload, current_status)
        except Exception as exc:
            log.warning(
                "src_discover: reconcile of run=%s game=%s failed: %s",
                run_id,
                game_id,
                exc,
            )
            reason = "reconcile_failed"
        counts[reason] = counts.get(reason, 0) + 1


def _remove_deleted_run(
    run_id: str,
) -> None:
    """Hard-delete a local run confirmed deleted on SRC, plus its notifications."""
    from notifications.models import Notification

    with transaction.atomic():
        Notification.objects.filter(
            target_type="run",
            target_id=str(run_id),
        ).delete()
        Runs.objects.filter(id=run_id).delete()

    log.info(
        "src_discover: removed run=%s deleted on SRC",
        run_id,
    )


def _discover_runs(
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

    # Tracks SRC Run IDs that report as `new` so we can detect if the local database has different
    # runs known. If SRC is dead, just returns none and nothing happens.
    src_new_ids: set[str] | None = None
    new_truncated = False

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
        if src_status == "new":
            src_new_ids = {
                run_id
                for run_id in (r.get("id") for r in runs if isinstance(r, dict))
                if run_id
            }
            new_truncated = len(runs) >= limit
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

    if src_new_ids is not None and not new_truncated:
        _reconcile_deleted_unverified_runs(
            game_id,
            src_new_ids,
            counts,
        )

    log.info(
        "src_discover: game=%s outcomes=%s",
        game_id,
        counts,
    )
    return counts


@shared_task(name="srl.tasks.discover_runs")
def discover_runs(
    game_id: str,
) -> dict:
    """Run per-game discovery under a per-game mutex.

    SRC throttling can stretch a single pass well past the one-minute beat, so overlapping passes
    for the same game would race each other's run/player writes; skip instead and let the next beat.
    """
    lock_key = _GAME_DISCOVERY_LOCK_KEY.format(game_id=game_id)
    if not cache.add(lock_key, "1", timeout=_GAME_DISCOVERY_LOCK_TTL):
        log.info(
            "src_discover: game=%s skipped - discovery already running",
            game_id,
        )
        return {"skipped": True, "reason": "game_lock_held"}
    try:
        return _discover_runs(game_id)
    finally:
        cache.delete(lock_key)


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
