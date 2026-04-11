import io
import logging

from django.core.files.base import ContentFile
from django.http import HttpRequest
from ninja import File, Router, Status
from ninja.files import UploadedFile
from ninja.responses import codes_4xx
from PIL import Image
from srl.models import Players

from api.permissions import player_session_auth
from api.v1.schemas.auth import ProfileBGUploadResponse
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()


@router.post(
    "/me/profile-bg",
    response={200: ProfileBGUploadResponse, codes_4xx: ErrorResponse},
    summary="Upload Profile Background",
    description=(
        "Uploads a profile background image for the authenticated player. "
        "Accepts image files only (max 10 MB). Re-encodes to strip metadata."
    ),
    auth=player_session_auth,
)
def upload_profile_bg(
    request: HttpRequest,
    file: UploadedFile = File(...),  # type: ignore
) -> Status:
    player: Players = request.auth  # type: ignore

    if not file.content_type or not file.content_type.startswith("image/"):
        return Status(
            400,
            ErrorResponse(
                error="Uploaded file must be an image",
                details={"content_type": file.content_type},
            ),
        )

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
        with Image.open(io.BytesIO(raw)) as img:
            rgb = img.convert("RGB")
    except Exception as e:
        return Status(
            400,
            ErrorResponse(
                error="Uploaded file is not a valid image",
                details={"exception": str(e)},
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

    return Status(500, "There was an issue looking up that user.")


@router.delete(
    "/me/profile-bg",
    response={200: ProfileBGUploadResponse, codes_4xx: ErrorResponse},
    summary="Remove Profile Background",
    description="Removes the authenticated player's profile background image.",
    auth=player_session_auth,
)
def delete_profile_bg(
    request: HttpRequest,
) -> Status:
    player: Players = request.auth  # type: ignore

    if player.user:
        if player.user.profile_bg:
            player.user.profile_bg.delete(save=True)

    return Status(200, ProfileBGUploadResponse(profile_bg=None))
