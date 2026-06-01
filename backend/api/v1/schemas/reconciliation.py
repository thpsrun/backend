from datetime import datetime
from enum import Enum
from typing import Self
from uuid import UUID

from ninja import Schema
from pydantic import ConfigDict, Field, model_validator


class ReconcileScope(str, Enum):
    RUN = "RUN"
    LEADERBOARD = "LEADERBOARD"
    GAME = "GAME"
    SERIES = "SERIES"


class SourceOfTruth(str, Enum):
    """Source of Truth is how to reconciliation determines who 'wins' when there is differences."""

    SRC = "SRC"
    THPS_RUN = "THPS_RUN"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Phase(str, Enum):
    """Phases are the different gates in which runs are reconciled - separated into Phases 1 - 3.

    - PENDING: Literally just means the job is pending start.
    - Phase 1: Surface-level checks (usually `/leaderboard` or `/runs` from the SRC API.)
    - Phase 2: Obsolete-level checks (only done after you find all of the Players).
    - Phase 3: Re-compute of all reconciled changes (points, placements, RunHistory, etc.)
    """

    PENDING = "PENDING"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class ItemPhase(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class LeaderboardTarget(Schema):
    game_id: str
    category_id: str
    level_id: str | None = None
    variable_values: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "game_id": "kdkn7w6d",
                "category_id": "rklgmpz2",
                "level_id": None,
                "variable_values": {"e8m07e3l": "9qjld7eq"},
            },
        },
    )


class ReconcileRequest(Schema):
    scope: ReconcileScope
    source_of_truth: SourceOfTruth = SourceOfTruth.SRC
    target_id: str | None = None
    target_descriptor: LeaderboardTarget | None = None

    @model_validator(mode="after")
    def _check_target_shape(self) -> Self:
        if self.scope == ReconcileScope.LEADERBOARD and self.target_descriptor is None:
            raise ValueError("target_descriptor is required for LEADERBOARD scope")
        if (
            self.scope in {ReconcileScope.RUN, ReconcileScope.GAME}
            and not self.target_id
        ):
            raise ValueError("target_id is required for RUN and GAME scope")
        if self.scope == ReconcileScope.SERIES and not self.target_id:
            raise ValueError("target_id is required for SERIES scope")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "scope": "GAME",
                    "source_of_truth": "SRC",
                    "target_id": "thps3",
                },
                {
                    "scope": "SERIES",
                    "source_of_truth": "SRC",
                    "target_id": "thps",
                },
            ],
        },
    )


class ItemSummary(Schema):
    """Summary of a reconciliation action on a single record.

    Attributes:
        record_type (str): Type of record affected (run, player, etc.).
        record_id (str): ID of the affected record.
        action (str): Action taken (created, updated, skipped, failed).
        phase: (ItemPhase): The phase currently being done.
        changes (dict[str, dict]): Dictionary of field changes {field: {old, new}}.
        error (str): Error message if action failed.
    """

    record_type: str
    record_id: str
    action: str
    phase: ItemPhase
    changes: dict[str, dict] = Field(default_factory=dict)
    error: str = ""


class ItemDetailOut(ItemSummary):
    """Detailed item record with timestamps.

    Attributes:
        id (int): Primary key of the item record.
        created_at (datetime): Timestamp when the item was recorded.
    """

    id: int
    created_at: datetime


class JobOut(Schema):
    """Response schema for a reconciliation job.

    Attributes:
        id (UUID): Unique job ID (UUID).
        scope (ReconcileScope): Scope of the reconciliation.
        target_id (str | None): ID of the target (if applicable).
        target_descriptor (dict | None): Descriptor of the target (if applicable).
        source_of_truth (SourceOfTruth): The authoritative data source.
        status (JobStatus): Current job status (PENDING, RUNNING, SUCCEEDED, FAILED, CANCELLED).
        counts (dict): Counter dict with keys created, updated, skipped, failed.
        requested_by (str | None): Username of the API key owner.
        created_at (datetime): Timestamp when the job was created.
        started_at (datetime | None): Timestamp when the job started processing.
        finished_at (datetime | None): Timestamp when the job completed.
        error_summary (str): Summary of any errors encountered.
        celery_task_id (str): ID of the background Celery task.
    """

    id: UUID
    scope: ReconcileScope
    target_id: str | None
    target_descriptor: dict | None
    source_of_truth: SourceOfTruth
    status: JobStatus
    phase: Phase
    counts: dict
    requested_by: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_summary: str
    celery_task_id: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "9d8c1a2e-2b3f-4d4e-9aa0-1b2c3d4e5f60",
                "scope": "GAME",
                "target_id": "thps3",
                "target_descriptor": None,
                "source_of_truth": "SRC",
                "status": "SUCCEEDED",
                "phase": "P3",
                "counts": {
                    "created": 12,
                    "updated": 480,
                    "skipped": 0,
                    "failed": 1,
                },
                "requested_by": "admin",
                "created_at": "2026-05-08T18:42:11Z",
                "started_at": "2026-05-08T18:42:12Z",
                "finished_at": "2026-05-08T18:43:55Z",
                "error_summary": "",
                "celery_task_id": "abcd-1234",
            },
        },
    )


class JobDetailOut(JobOut):
    """Extended job response with a breakdown of job tasks.

    Attributes:
        recent_items (list[ItemSummary]): List of recent reconciliation items for this job.
        breakdown (dict[str, dict[str, int]]): Per-record-type counts of {created, updated, skipped,
            failed}. counts_* on the job is runs-only; breakdown surfaces the rest.
    """

    recent_items: list[ItemSummary] = Field(default_factory=list)
    breakdown: dict[str, dict[str, int]] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "9d8c1a2e-2b3f-4d4e-9aa0-1b2c3d4e5f60",
                "scope": "GAME",
                "target_id": "thps3",
                "target_descriptor": None,
                "source_of_truth": "SRC",
                "status": "SUCCEEDED",
                "phase": "P3",
                "counts": {
                    "created": 9,
                    "updated": 45,
                    "skipped": 46,
                    "failed": 0,
                },
                "requested_by": "admin",
                "created_at": "2026-05-08T18:42:11Z",
                "started_at": "2026-05-08T18:42:12Z",
                "finished_at": "2026-05-08T18:43:55Z",
                "error_summary": "",
                "celery_task_id": "abcd-1234",
                "recent_items": [],
                "breakdown": {
                    "run": {
                        "created": 9,
                        "updated": 45,
                        "skipped": 46,
                        "failed": 0,
                    },
                    "category": {
                        "created": 0,
                        "updated": 2,
                        "skipped": 8,
                        "failed": 0,
                    },
                    "variable_value": {
                        "created": 0,
                        "updated": 0,
                        "skipped": 31,
                        "failed": 0,
                    },
                    "player": {
                        "created": 1,
                        "updated": 0,
                        "skipped": 12,
                        "failed": 0,
                    },
                },
            },
        },
    )


class JobListOut(Schema):
    """Paginated list of reconciliation jobs."""

    items: list[JobOut]
    total: int


class ItemListOut(Schema):
    """Paginated list of reconciliation items."""

    items: list[ItemDetailOut]
    total: int


class ConflictOut(Schema):
    """Conflict response when a job is already in progress for the same target."""

    detail: str
    existing_job_id: UUID

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "A reconciliation is already in progress for this target.",
                "existing_job_id": "9d8c1a2e-2b3f-4d4e-9aa0-1b2c3d4e5f60",
            },
        },
    )


class CancelConflictOut(Schema):
    """Conflict response when cancelling a job already in a terminal state."""

    detail: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"detail": "Job is already succeeded."},
        },
    )
