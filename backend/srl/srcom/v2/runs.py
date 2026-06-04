from typing import Any

from srl.models import RunPlayers, Runs, RunVariableValues
from srl.srcom.utils import src_method_to_internal

V2_ELIGIBLE_FIELDS: frozenset[str] = frozenset(
    {
        "time_secs",
        "timenl_secs",
        "timeigt_secs",
        "category_id",
        "level_id",
        "platform_id",
        "emulated",
        "video",
        "description",
        "date",
        "variables",
    },
)


def _to_runtime_tuple(
    secs: float | None,
) -> dict[str, int] | None:
    if not secs or secs <= 0:
        return None
    total_ms = int(round(secs * 1000))
    hours, rem = divmod(total_ms, 3600 * 1000)
    minutes, rem = divmod(rem, 60 * 1000)
    seconds, milliseconds = divmod(rem, 1000)
    return {
        "hour": hours,
        "minute": minutes,
        "second": seconds,
        "millisecond": milliseconds,
    }


def snapshot_run(
    run: Runs,
) -> dict[str, Any]:
    """Converts the v2 API fields into a dict."""
    variables_repr = sorted(
        [
            (rvv.variable.id, rvv.value_id)
            for rvv in RunVariableValues.objects.filter(run=run)
        ],
    )
    player_names = [
        rp.player.name
        for rp in (
            RunPlayers.objects.filter(run=run)
            .select_related("player")
            .order_by("order")
        )
    ]
    return {
        "id": run.id,
        "game_id": run.game.id,
        "time_secs": run.time_secs,
        "timenl_secs": run.timenl_secs,
        "timeigt_secs": run.timeigt_secs,
        "category_id": run.category.id if run.category else None,
        "level_id": run.level.id if run.level else None,
        "platform_id": run.platform.id if run.platform else None,
        "emulated": run.emulated,
        "video": run.video,
        "description": run.description,
        "date": run.date,
        "variables": variables_repr,
        "player_names": player_names,
        "primary_method": run._primary_timing_method(),
    }


def compute_v2_eligible_diff(
    old: dict[str, Any],
    new: dict[str, Any],
) -> set[str]:
    return {f for f in V2_ELIGIBLE_FIELDS if old.get(f) != new.get(f)}


def _build_run_settings(
    snapshot: dict[str, Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    """Builds a V2 API RunSettings dict from a snapshot."""
    method = src_method_to_internal(snapshot.get("primary_method")) or "rta"

    rta_secs = snapshot.get("time_secs")
    lrt_secs = snapshot.get("timenl_secs")
    igt_secs = snapshot.get("timeigt_secs")

    if method == "lrt":
        time_field = _to_runtime_tuple(lrt_secs)
        time_with_loads_field = _to_runtime_tuple(rta_secs)
    else:
        time_field = _to_runtime_tuple(rta_secs)
        time_with_loads_field = None

    igt_field = _to_runtime_tuple(igt_secs)

    values = [
        {"variableId": var_id, "valueId": val_id}
        for (var_id, val_id) in snapshot.get("variables", [])
    ]

    date_val = snapshot.get("date")
    date_int = int(date_val.timestamp()) if date_val else 0

    payload: dict[str, Any] = {
        "gameId": snapshot.get("game_id"),
        "categoryId": snapshot.get("category_id"),
        "platformId": snapshot.get("platform_id"),
        "emulator": bool(snapshot.get("emulated")),
        "video": snapshot.get("video") or "",
        "comment": snapshot.get("description") or "",
        "date": date_int,
        "playerNames": list(snapshot.get("player_names") or []),
        "values": values,
        "time": time_field,
        "igt": igt_field,
    }
    if run_id is not None:
        payload["runId"] = run_id
    level_id = snapshot.get("level_id")
    if level_id is not None:
        payload["levelId"] = level_id
    if time_with_loads_field is not None:
        payload["timeWithLoads"] = time_with_loads_field
    return payload


def build_settings_payload(
    run: Runs,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Builds a V2 API RunSettings object for editing an existing run."""
    return _build_run_settings(snapshot, run_id=run.id)


def build_submit_payload(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Builds a V2 API RunSettings object for submitting a NEW run."""
    return _build_run_settings(snapshot, run_id=None)
