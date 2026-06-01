from datetime import datetime

from ninja import Schema


class BotSessionResponse(Schema):
    status: str
    validated_at: datetime | None
    last_refresh_attempt_at: datetime | None
    v2_enabled_override: bool | None
    v2_effective_enabled: bool
    disabled_by_circuit_breaker: bool
    last_severe_error_at: datetime | None
    last_severe_error_category: str
    queued_edit_count: int
    failed_edit_count: int

    class Config:
        json_schema_extra = {
            "example": {
                "status": "active",
                "validated_at": "2026-05-03T18:00:00Z",
                "last_refresh_attempt_at": "2026-05-03T18:00:00Z",
                "v2_enabled_override": None,
                "v2_effective_enabled": True,
                "disabled_by_circuit_breaker": False,
                "last_severe_error_at": None,
                "last_severe_error_category": "",
                "queued_edit_count": 0,
                "failed_edit_count": 0,
            },
        }


class KillSwitchRequest(Schema):
    override: bool | None

    class Config:
        json_schema_extra = {
            "example": {"override": False},
        }


class KillSwitchResponse(Schema):
    v2_enabled_override: bool | None
    v2_effective_enabled: bool
    disabled_by_circuit_breaker: bool
    replay_queued_count: int

    class Config:
        json_schema_extra = {
            "example": {
                "v2_enabled_override": True,
                "v2_effective_enabled": True,
                "disabled_by_circuit_breaker": False,
                "replay_queued_count": 3,
            },
        }
