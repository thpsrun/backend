from datetime import datetime

from ninja import Schema
from pydantic import ConfigDict, Field, field_validator

ALLOWED_EXPIRY_DAYS: tuple[int, ...] = (30, 90, 180, 365)


class APIKeyCreateRequest(Schema):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "label": "CI bot",
                "description": "Posts run results from CI",
                "expiry_days": 180,
                "scope_capabilities": ["runs.create", "runs.update"],
                "scope_games": ["n2680o1p"],
            },
        },
    )

    label: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable label for the key",
    )
    description: str = Field(
        default="",
        description="Optional free-form description",
    )
    expiry_days: int = Field(
        default=180,
        ge=1,
        le=365,
        description="Days until key expires; must be one of 30/90/180/365",
    )
    scope_capabilities: list[str] = Field(
        default_factory=list,
        description="Capabilities the key may exercise; empty = owner's full natural scope",
    )
    scope_games: list[str] = Field(
        default_factory=list,
        description="Game IDs the key is restricted to; empty = all games",
    )

    @field_validator("expiry_days")
    @classmethod
    def allowed_expiry(
        cls,
        v: int,
    ) -> int:
        if v not in ALLOWED_EXPIRY_DAYS:
            raise ValueError(
                f"expiry_days must be one of {ALLOWED_EXPIRY_DAYS}",
            )
        return v


class APIKeyPatchRequest(Schema):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "label": "CI bot (renamed)",
                "description": "Updated description",
            },
        },
    )

    label: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class APIKeyResponse(Schema):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "key_01HXYZABC123",
                "label": "CI bot",
                "description": "Posts run results from CI",
                "prefix": "thps_pk_abcd",
                "scope_capabilities": ["runs.create", "runs.update"],
                "scope_games": ["n2680o1p"],
                "created": "2026-04-26T10:00:00Z",
                "expiry_date": "2026-10-23T10:00:00Z",
                "last_used": "2026-04-26T11:30:00Z",
                "last_used_ip": "192.0.2.10",
                "revoked": False,
                "revoked_reason": "",
                "revoked_at": None,
            },
        },
    )

    id: str
    label: str
    description: str
    prefix: str
    scope_capabilities: list[str]
    scope_games: list[str]
    created: datetime
    expiry_date: datetime | None
    last_used: datetime | None
    last_used_ip: str | None
    revoked: bool
    revoked_reason: str
    revoked_at: datetime | None


class APIKeyCreateResponse(APIKeyResponse):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "key_01HXYZABC123",
                "label": "CI bot",
                "description": "Posts run results from CI",
                "prefix": "thps_pk_abcd",
                "scope_capabilities": ["runs.create", "runs.update"],
                "scope_games": ["n2680o1p"],
                "created": "2026-04-26T10:00:00Z",
                "expiry_date": "2026-10-23T10:00:00Z",
                "last_used": None,
                "last_used_ip": None,
                "revoked": False,
                "revoked_reason": "",
                "revoked_at": None,
                "key": "thps_pk_abcdEXAMPLEFULLKEYVALUEONLYSHOWNONCE",
            },
        },
    )

    key: str


class GameEmbed(Schema):
    id: str
    name: str
    slug: str


class CapabilitiesResponse(Schema):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "capabilities": [
                    "runs.create",
                    "runs.update",
                    "runs.delete",
                ],
                "games": [
                    {
                        "id": "n2680o1p",
                        "name": "Tony Hawk's Pro Skater 4",
                        "slug": "thps4",
                    },
                ],
            },
        },
    )

    capabilities: list[str]
    games: list[GameEmbed]
