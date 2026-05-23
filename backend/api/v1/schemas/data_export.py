from datetime import datetime
from uuid import UUID

from ninja import Schema
from pydantic import ConfigDict


class DataExportItem(Schema):
    id: UUID
    status: str
    requested_at: datetime
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    file_size_bytes: int | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "9b3c2e1a-1c4d-4d3e-9a2b-1c4d4d3e9a2b",
                "status": "READY",
                "requested_at": "2026-05-22T18:00:00Z",
                "completed_at": "2026-05-22T18:01:30Z",
                "expires_at": "2026-05-29T18:01:30Z",
                "file_size_bytes": 124583,
            },
        },
    )


class DataExportListResponse(Schema):
    exports: list[DataExportItem]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "exports": [
                    {
                        "id": "9b3c2e1a-1c4d-4d3e-9a2b-1c4d4d3e9a2b",
                        "status": "READY",
                        "requested_at": "2026-05-22T18:00:00Z",
                        "completed_at": "2026-05-22T18:01:30Z",
                        "expires_at": "2026-05-29T18:01:30Z",
                        "file_size_bytes": 124583,
                    },
                ],
            },
        },
    )


class DataExportThrottledResponse(Schema):
    detail: str
    retry_after_seconds: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "You can only request one export per 24 hours.",
                "retry_after_seconds": 64321,
            },
        },
    )
