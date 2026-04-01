from datetime import datetime
from typing import Any, Literal

from ninja import Schema
from pydantic import Field, field_validator

from api.v1.schemas.runs import PlayerRunEmbedSchema


class SyncStatusSchema(Schema):
    """SRC sync status for a moderator action on a run."""

    action: str
    status: str
    attempts: int
    last_error: str
    updated_at: datetime


class SubmissionRunSchema(PlayerRunEmbedSchema):
    """A pending run in the submission hub.

    Extends PlayerRunEmbedSchema with vid_status and SRC sync state.
    Inherits game/category/level serialization and timing nesting.
    """

    @field_validator("players", mode="before")
    @classmethod
    def convert_players_manager(cls, v: Any) -> list[dict]:
        if isinstance(v, list):
            return v
        return []

    vid_status: str = Field(
        ...,
        description="Verification status: new, verified, or rejected",
    )
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="Run notes/description",
    )
    src_sync: list[SyncStatusSchema] = Field(
        default_factory=list,
        description="SRC sync status for any pending moderator actions.",
    )


class ModerationGameGroup(Schema):
    """Pending runs grouped by game for the moderation queue."""

    game_id: str
    game_name: str
    game_slug: str
    pending_count: int
    pending_runs: list[SubmissionRunSchema]


class SubmissionHubResponse(Schema):
    """Response for GET /auth/submissions."""

    pending_runs: list[SubmissionRunSchema]
    moderation_queue: list[ModerationGameGroup] | None = None


class VerifyRejectRequest(Schema):
    """Request body for PUT /auth/submissions/{run_id}/status."""

    status: Literal["verified", "rejected"]
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Required when rejecting a run.",
    )


class VerifyRejectResponse(Schema):
    """Response after verify/reject action is queued."""

    run_id: str
    status: str
    src_sync_status: str
    message: str


class PlayerEntry(Schema):
    """A single player in a change-players request.

    For rel=user, provide the player's name as it appears in the
    database. The player is looked up by name and must exist locally.
    For rel=guest, provide a display name (no DB lookup).
    """

    rel: Literal["user", "guest"]
    name: str = Field(
        ...,
        min_length=1,
        description=(
            "Player name (looked up in DB when rel=user) "
            "or guest display name (when rel=guest)."
        ),
    )


class ChangePlayersRequest(Schema):
    """Request body for PUT /auth/submissions/{run_id}/players."""

    players: list[PlayerEntry] = Field(
        ...,
        min_length=1,
        description="Complete list of players (replaces existing).",
    )


class ChangePlayersResponse(Schema):
    """Response after change-players action is queued."""

    run_id: str
    players: list[dict]
    src_sync_status: str
    message: str


# --- Superuser sync log schemas ---


class SyncLogRunSchema(Schema):
    """Minimal run info embedded in a sync log entry."""

    id: str
    game_name: str
    game_slug: str
    category_name: str | None = None
    level_name: str | None = None
    url: str


class SyncLogEntry(Schema):
    """Full sync task detail for the admin sync log viewer."""

    id: int
    run: SyncLogRunSchema
    action: str
    status: str
    payload: dict
    moderator_name: str | None = None
    attempts: int
    max_attempts: int
    last_error: str
    created_at: datetime
    updated_at: datetime


class SyncLogResponse(Schema):
    """Paginated response for GET /auth/admin/sync-logs."""

    count: int
    results: list[SyncLogEntry]
