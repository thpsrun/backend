from datetime import datetime
from typing import Any, Literal

from ninja import Schema
from pydantic import Field, field_validator, model_validator

from api.v1.schemas.base import RunStatusType
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
    def convert_players_manager(
        cls,
        v: Any,
    ) -> list[dict]:
        if isinstance(v, list):
            return v
        return []

    vid_status: RunStatusType = Field(
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


class SubmitPlayerEntry(Schema):
    """A player entry for run submission to SRC.

    For rel=user, provide the SRC user/player ID.
    For rel=guest, provide a display name.
    """

    rel: Literal["user", "guest"]
    id: str | None = Field(
        default=None,
        description="SRC player ID. Required when rel=user.",
    )
    name: str | None = Field(
        default=None,
        description="Guest display name. Required when rel=guest.",
    )

    @model_validator(mode="after")
    def validate_rel_fields(
        self,
    ) -> "SubmitPlayerEntry":
        if self.rel == "user" and not self.id:
            raise ValueError("id is required when rel=user")
        if self.rel == "guest" and not self.name:
            raise ValueError("name is required when rel=guest")
        return self


class RunSubmitSchema(Schema):
    """Request body for POST /auth/submissions/submit."""

    game_id: str = Field(
        ...,
        description="Game ID (must exist locally).",
    )
    category_id: str = Field(
        ...,
        description="Category ID (must exist for the game).",
    )
    level_id: str | None = Field(
        default=None,
        description="Level ID for IL runs (must exist for the game).",
    )
    platform_id: str = Field(
        ...,
        description="Platform ID (must be one of the game's platforms).",
    )
    emulated: bool = Field(
        default=False,
        description="Whether the run was played on an emulator.",
    )
    players: list[SubmitPlayerEntry] = Field(
        ...,
        min_length=1,
        description="At least one player. Supports user and guest entries.",
    )
    time: str | None = Field(
        default=None,
        description="Human-readable RTA time (e.g. '1h 23m 45s 678ms').",
    )
    timenl: str | None = Field(
        default=None,
        description="Human-readable load-removed time.",
    )
    timeigt: str | None = Field(
        default=None,
        description="Human-readable in-game time.",
    )
    video: str = Field(
        ...,
        description="Video proof URL (required). Must be a YouTube URL.",
    )

    @field_validator("video")
    @classmethod
    def validate_video_url(
        cls,
        v: str,
    ) -> str:
        from urllib.parse import urlparse

        parsed = urlparse(v)
        allowed_hosts = {
            "www.youtube.com",
            "youtube.com",
            "youtu.be",
            "m.youtube.com",
        }
        if parsed.scheme not in ("http", "https") or parsed.netloc not in allowed_hosts:
            raise ValueError("Video must be a YouTube URL")
        return v

    comment: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional run comment.",
    )
    date: str | None = Field(
        default=None,
        description="Date the run was performed (YYYY-MM-DD). SRC defaults to today.",
    )
    variable_values: dict[str, str] | None = Field(
        default=None,
        description="Variable/value ID mapping: {variable_id: value_id}.",
    )

    @model_validator(mode="after")
    def validate_at_least_one_time(
        self,
    ) -> "RunSubmitSchema":
        if not any([self.time, self.timenl, self.timeigt]):
            raise ValueError(
                "At least one timing value is required (time, timenl, or timeigt)."
            )
        return self

    @model_validator(mode="after")
    def validate_player_fields(
        self,
    ) -> "RunSubmitSchema":
        for i, p in enumerate(self.players):
            if p.rel == "user" and not p.id:
                raise ValueError(f"Player {i}: 'id' is required when rel='user'.")
            if p.rel == "guest" and not p.name:
                raise ValueError(f"Player {i}: 'name' is required when rel='guest'.")
        return self


class RunSubmitResponse(Schema):
    """Response after successful run submission to SRC."""

    run_id: str
    src_url: str
    vid_status: RunStatusType
    message: str


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


class SyncRetryResponse(Schema):
    task_id: int
    message: str
