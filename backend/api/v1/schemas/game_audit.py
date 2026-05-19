from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


_EXAMPLE_API_MUTATION: dict[str, Any] = {
    "id": 12345,
    "created_at": "2026-05-17T13:42:11Z",
    "event_type": "timing_config_change",
    "actor_kind": "api_key",
    "actor_user_id": 17,
    "actor_username": "thepackle",
    "actor_api_key_id": "2f5WxpNy.sha512$$...",
    "actor_label": "qwee",
    "target_app": "srl",
    "target_model": "games",
    "target_id": "thps2",
    "target_repr": "Games thps2",
    "summary": "Games.defaulttime changed",
}

_EXAMPLE_RECALC_DISPATCH: dict[str, Any] = {
    "id": 12350,
    "created_at": "2026-05-17T13:42:14Z",
    "event_type": "recalc_dispatch",
    "actor_kind": "user",
    "actor_user_id": 17,
    "actor_username": "thepackle",
    "actor_api_key_id": None,
    "actor_label": "thepackle",
    "target_app": "",
    "target_model": "",
    "target_id": "",
    "target_repr": "",
    "summary": "Recalc dispatched: 14 board(s) (812 runs scanned)",
}

_EXAMPLE_SRC_SYNC: dict[str, Any] = {
    "id": 12360,
    "created_at": "2026-05-17T13:43:02Z",
    "event_type": "src_sync_attempt",
    "actor_kind": "system",
    "actor_user_id": None,
    "actor_username": None,
    "actor_api_key_id": None,
    "actor_label": "",
    "target_app": "srl",
    "target_model": "srcsynctask",
    "target_id": "9991",
    "target_repr": "SRCSyncTask 9991",
    "summary": "SRC verify synced (run z0rkn8wm, attempt 1)",
}

_EXAMPLE_API_MUTATION_WITH_PAYLOAD: dict[str, Any] = {
    **_EXAMPLE_API_MUTATION,
    "payload": {
        "model": "Games",
        "field": "defaulttime",
        "previous": "realtime_noloads",
        "new": "ingame",
        "recalc_dispatched": True,
        "rebackfill_dispatched": True,
    },
}


class AuditRowSummary(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                _EXAMPLE_API_MUTATION,
                _EXAMPLE_RECALC_DISPATCH,
                _EXAMPLE_SRC_SYNC,
            ],
        },
    )

    id: int
    created_at: datetime
    event_type: str
    actor_kind: str
    actor_user_id: int | None = None
    actor_username: str | None = None
    actor_api_key_id: str | None = None
    actor_label: str
    target_app: str
    target_model: str
    target_id: str
    target_repr: str
    summary: str


class AuditRowDetail(AuditRowSummary):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                _EXAMPLE_API_MUTATION_WITH_PAYLOAD,
                {
                    **_EXAMPLE_RECALC_DISPATCH,
                    "payload": {
                        "boards_count": 14,
                        "runs_scanned": 812,
                        "duration_ms": 47,
                        "triggered_by": "Games.defaulttime",
                    },
                },
                {
                    **_EXAMPLE_SRC_SYNC,
                    "payload": {
                        "run_id": "z0rkn8wm",
                        "action": "verify",
                        "status": "synced",
                        "attempts": 1,
                        "error_category": "",
                        "last_error": "",
                    },
                },
            ],
        },
    )

    payload: dict[str, Any] | None = None


class AuditListResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "count": 2,
                "results": [
                    _EXAMPLE_API_MUTATION,
                    _EXAMPLE_RECALC_DISPATCH,
                ],
            },
        },
    )

    count: int
    results: list[AuditRowSummary] | list[AuditRowDetail]
