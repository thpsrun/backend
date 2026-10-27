from datetime import UTC, datetime
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

_DURATION_FIELDS: tuple[str, ...] = ("time", "timeWithLoads", "igt")


def _to_duration(
    secs: float | None,
) -> str | None:
    """Format seconds as a protoJSON duration, matching speedruncompy's `Duration_` serializer.

    Arguments:
        secs (float | None): The run time in seconds.

    Returns:
        duration (str | None): e.g. "5014.97s", or None when there is no positive time.
    """
    if not secs or secs <= 0:
        return None
    return f"{round(float(secs), 3)}s"


def _to_timestamp(
    value: datetime | None,
) -> str:
    """Format a datetime UTC string, matching speedruncompy's `Timestamp_`.

    Arguments:
        value (datetime | None): The run date; None falls back to the Unix epoch, as before.

    Returns:
        timestamp (str): e.g. "2026-10-15T00:00:00Z".
    """
    value = value or datetime.fromtimestamp(0, UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _legacy_tuple_to_duration(
    value: dict[str, int],
) -> str | None:
    """Convert a pre-protoJSON {hour, minute, second, millisecond} dict into a duration."""
    secs = (
        value.get("hour", 0) * 3600
        + value.get("minute", 0) * 60
        + value.get("second", 0)
        + value.get("millisecond", 0) / 1000
    )
    return _to_duration(secs)


def upgrade_legacy_run_settings(
    payload: dict[str, Any],
) -> dict[str, Any]:
    upgraded = dict(payload)
    if "date" in upgraded:
        date_val = upgraded.pop("date")
        if "performedAt" not in upgraded:
            upgraded["performedAt"] = _to_timestamp(
                datetime.fromtimestamp(date_val or 0, UTC),
            )
    for field in _DURATION_FIELDS:
        value = upgraded.get(field)
        if isinstance(value, dict):
            value = _legacy_tuple_to_duration(value)
        if value is None:
            upgraded.pop(field, None)
        else:
            upgraded[field] = value
    return upgraded


def snapshot_run(
    run: Runs,
) -> dict[str, Any]:
    """Converts the v2 API fields into a dict."""
    variables_repr = sorted(
        RunVariableValues.objects.filter(run=run).values_list(
            "variable_id",
            "value_id",
        ),
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
        time_field = _to_duration(lrt_secs)
        time_with_loads_field = _to_duration(rta_secs)
    else:
        time_field = _to_duration(rta_secs)
        time_with_loads_field = None

    igt_field = _to_duration(igt_secs)

    values = [
        {"variableId": var_id, "valueId": val_id}
        for (var_id, val_id) in snapshot.get("variables", [])
    ]

    payload: dict[str, Any] = {
        "gameId": snapshot.get("game_id"),
        "categoryId": snapshot.get("category_id"),
        "platformId": snapshot.get("platform_id"),
        "emulator": bool(snapshot.get("emulated")),
        "video": snapshot.get("video") or "",
        "comment": snapshot.get("description") or "",
        "performedAt": _to_timestamp(snapshot.get("date")),
        "playerNames": list(snapshot.get("player_names") or []),
        "values": values,
    }
    if run_id is not None:
        payload["runId"] = run_id
    level_id = snapshot.get("level_id")
    if level_id is not None:
        payload["levelId"] = level_id
    if time_field is not None:
        payload["time"] = time_field
    if igt_field is not None:
        payload["igt"] = igt_field
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
