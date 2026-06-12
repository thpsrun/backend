from __future__ import annotations

import logging
import os
from datetime import timedelta
from uuid import UUID

from accounts.models import UserDataExport
from accounts.tasks import build_user_data_export
from django.conf import settings
from django.http import FileResponse, HttpRequest
from django.utils import timezone
from ninja import Router

from api.permissions import session_only
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.data_export import (
    DataExportItem,
    DataExportListResponse,
    DataExportThrottledResponse,
)

logger = logging.getLogger(__name__)

router = Router()

THROTTLE_WINDOW = timedelta(hours=24)


def _row_to_item(
    row: UserDataExport,
) -> DataExportItem:
    """Serialize a UserDataExport row into the API item shape."""
    return DataExportItem(
        id=row.id,
        status=row.status,
        requested_at=row.requested_at,
        completed_at=row.completed_at,
        expires_at=row.expires_at,
        file_size_bytes=row.file_size_bytes,
    )


@router.post(
    "/me/export",
    response={
        202: DataExportItem,
        401: ErrorResponse,
        403: ErrorResponse,
        429: DataExportThrottledResponse,
    },
    summary="Request a data export",
    description=(
        "Queues a build of the requesting user's account data export. Returns the new "
        "export record. Session authentication only; API keys are rejected with 403. "
        "Limited to one non-failed request per 24 hours."
    ),
    auth=session_only(),
)
def request_data_export(
    request: HttpRequest,
):
    user = request.user
    cutoff = timezone.now() - THROTTLE_WINDOW
    blocking = (
        UserDataExport.objects.filter(user=user, requested_at__gte=cutoff)
        .exclude(status=UserDataExport.Status.FAILED)
        .order_by("-requested_at")
        .first()
    )
    if blocking is not None:
        retry_at = blocking.requested_at + THROTTLE_WINDOW
        seconds = max(int((retry_at - timezone.now()).total_seconds()), 1)
        return 429, DataExportThrottledResponse(
            detail="You can only request one export per 24 hours.",
            retry_after_seconds=seconds,
        )

    row = UserDataExport.objects.create(user=user)
    build_user_data_export.delay(str(row.pk))
    return 202, _row_to_item(row)


@router.get(
    "/me/exports",
    response={
        200: DataExportListResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="List my data exports",
    description=(
        "Returns the last 10 export records for the requesting user, newest first. "
        "Session authentication only."
    ),
    auth=session_only(),
)
def list_data_exports(
    request: HttpRequest,
):
    rows = UserDataExport.objects.filter(user=request.user).order_by("-requested_at")[
        :10
    ]
    return 200, DataExportListResponse(exports=[_row_to_item(r) for r in rows])


@router.get(
    "/me/exports/{export_id}/download",
    response={
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Download a data export",
    description=(
        "Streams the zip archive for a READY, unexpired export owned by the requesting "
        "user. Session authentication only."
    ),
    auth=session_only(),
)
def download_data_export(
    request: HttpRequest,
    export_id: UUID,
):
    # Not-ready, expired, and missing-file all collapse into the same 404 so the
    # response never leaks export lifecycle state.
    row = UserDataExport.objects.filter(pk=export_id, user=request.user).first()
    if row is None:
        return 404, ErrorResponse(error="Export not found.")
    if row.status != UserDataExport.Status.READY:
        return 404, ErrorResponse(error="Export not found.")
    if row.expires_at is None or row.expires_at < timezone.now():
        return 404, ErrorResponse(error="Export not found.")
    if not row.file_path:
        return 404, ErrorResponse(error="Export not found.")

    abs_path = os.path.join(settings.MEDIA_ROOT, row.file_path)
    if not os.path.exists(abs_path):
        logger.error(
            "UserDataExport %s is READY but file is missing at %s",
            row.pk,
            abs_path,
        )
        return 404, ErrorResponse(error="Export not found.")

    filename = (
        f"thps-run-export-{row.completed_at.strftime('%Y-%m-%d')}.zip"
        if row.completed_at
        else f"thps-run-export-{row.pk}.zip"
    )
    return FileResponse(open(abs_path, "rb"), as_attachment=True, filename=filename)
