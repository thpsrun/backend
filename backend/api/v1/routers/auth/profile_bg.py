import io
import logging

from django.core.files.base import ContentFile
from django.http import HttpRequest
from ninja import File, Router, Status
from ninja.files import UploadedFile
from ninja.responses import codes_4xx
from srl.models import Players

from api.permissions import authed
from api.v1.routers.utils.images import ImageValidationError, validate_image
from api.v1.schemas.auth import ProfileBGUploadResponse
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()

PROFILE_BG_MAX_PIXELS: int = 12_000_000


@router.post(
    "/me/profile-bg",
    response={200: ProfileBGUploadResponse, codes_4xx: ErrorResponse},
    summary="Upload Profile Background",
    description=(
        "Uploads a profile background image for the authenticated player. "
        "Accepts JPEG, PNG, WEBP, or GIF images up to 10 MB and 12 MP. "
        "Re-encodes to strip metadata."
    ),
    auth=authed("profile.edit_own"),
)
def upload_profile_bg(
    request: HttpRequest,
    file: UploadedFile = File(...),  # type: ignore
) -> Status:
    player: Players = request.auth.player  # type: ignore

    if not file.size or file.size > 10 * 1024 * 1024:
        return Status(
            400,
            ErrorResponse(
                error="Image exceeds maximum size of 10 MB",
                details=None,
            ),
        )

    raw: bytes = b"".join(file.chunks())

    try:
        rgb = validate_image(raw, file.content_type, max_pixels=PROFILE_BG_MAX_PIXELS)
    except ImageValidationError as e:
        return Status(
            400,
            ErrorResponse(
                error=e.message,
                details=None,
            ),
        )

    buffer = io.BytesIO()
    rgb.save(buffer, "JPEG", quality=85)
    buffer.seek(0)

    safe_id = "".join(c for c in player.id if c.isalnum() or c in "-_")
    filename = f"{safe_id}.jpg"

    if player.user:
        if player.user.profile_bg:
            player.user.profile_bg.delete(save=False)

        player.user.profile_bg.save(
            filename,
            ContentFile(buffer.getvalue()),
            save=True,
        )

        return Status(
            200,
            ProfileBGUploadResponse(profile_bg=player.user.profile_bg.url),
        )

    return Status(
        500,
        ErrorResponse(
            error="User account not found.",
            details=None,
        ),
    )


@router.delete(
    "/me/profile-bg",
    response={200: ProfileBGUploadResponse, codes_4xx: ErrorResponse},
    summary="Remove Profile Background",
    description="Removes the authenticated player's profile background image.",
    auth=authed("profile.edit_own"),
)
def delete_profile_bg(
    request: HttpRequest,
) -> Status:
    player: Players = request.auth.player  # type: ignore

    if player.user:
        if player.user.profile_bg:
            player.user.profile_bg.delete(save=True)

    return Status(200, ProfileBGUploadResponse(profile_bg=None))
