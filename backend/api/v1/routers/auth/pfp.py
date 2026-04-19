import logging
import os

from django.conf import settings
from django.http import HttpRequest
from ninja import File, Router, Status
from ninja.files import UploadedFile
from ninja.responses import codes_4xx
from srl.models import Players

from api.permissions import player_session_auth
from api.v1.routers.utils.images import ImageValidationError, validate_image
from api.v1.schemas.auth import PfpUploadResponse
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()

PFP_DIR: str = os.path.join(settings.MEDIA_ROOT, "pfp")
PFP_MAX_PIXELS: int = 4_000_000
os.makedirs(PFP_DIR, exist_ok=True)


@router.post(
    "/me/pfp",
    response={200: PfpUploadResponse, codes_4xx: ErrorResponse},
    summary="Upload Profile Picture",
    description=(
        "Uploads a new profile picture for the authenticated player. "
        "Accepts JPEG, PNG, WEBP, or GIF images up to 5 MB and 4 MP. "
        "Saves to static/pfp/`playerid`.jpg."
    ),
    auth=player_session_auth,
)
def upload_pfp(
    request: HttpRequest,
    file: UploadedFile = File(...),  # type: ignore
) -> Status:
    player: Players = request.auth  # type: ignore

    if not file.size or file.size > 5 * 1024 * 1024:
        return Status(
            400,
            ErrorResponse(
                error="Image exceeds maximum size of 5 MB",
                details=None,
            ),
        )

    raw: bytes = b"".join(file.chunks())

    try:
        rgb = validate_image(raw, file.content_type, max_pixels=PFP_MAX_PIXELS)
    except ImageValidationError as e:
        return Status(
            400,
            ErrorResponse(
                error=e.message,
                details=None,
            ),
        )

    safe_id = "".join(c for c in player.id if c.isalnum() or c in "-_")
    file_path = os.path.join(PFP_DIR, f"{safe_id}.jpg")
    temp_path = f"{file_path}.tmp"

    try:
        rgb.save(temp_path, "JPEG", quality=85)
        os.replace(temp_path, file_path)
    except OSError:
        logger.exception("Failed to write pfp for player %s", player.id)
        return Status(
            500,
            ErrorResponse(
                error="Failed to save profile picture",
                details=None,
            ),
        )

    pfp_url = f"{settings.MEDIA_URL}pfp/{player.id}.jpg"
    player.pfp = pfp_url
    player.save(update_fields=["pfp"])

    return Status(200, PfpUploadResponse(pfp=pfp_url))
