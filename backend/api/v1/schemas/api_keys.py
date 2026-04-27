from datetime import datetime

from ninja import Schema
from pydantic import Field, field_validator

ALLOWED_EXPIRY_DAYS: tuple[int, ...] = (30, 90, 180, 365)


class APIKeyCreateRequest(Schema):
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
    label: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class APIKeyResponse(Schema):
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
    key: str


class GameEmbed(Schema):
    id: str
    name: str
    slug: str


class CapabilitiesResponse(Schema):
    capabilities: list[str]
    games: list[GameEmbed]
