import io
import logging
import os
from textwrap import dedent

import requests as http_requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import HttpRequest
from ninja import File, Router, Status
from ninja.files import UploadedFile
from ninja.responses import codes_4xx
from PIL import Image
from srl.encryption import encrypt_src_key
from srl.models import CountryCodes, Players

from api.permissions import player_session_auth
from api.rate_limiting import auth_rate_limit
from api.v1.schemas.auth import (
    CountryCodeResponse,
    ModeratedGameSchema,
    PfpUploadResponse,
    PlayerProfileResponse,
    PlayerUpdateRequest,
    ProfileBGUploadResponse,
    SRCKeyRequest,
    SRCKeyStatusResponse,
)
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()

PFP_DIR: str = os.path.join(settings.MEDIA_ROOT, "pfp")
os.makedirs(PFP_DIR, exist_ok=True)


@router.get(
    "/countries",
    response=list[CountryCodeResponse],
    summary="List Country Codes",
    description="Returns all available country codes sorted alphabetically by name.",
)
def list_countries(
    request: HttpRequest,
) -> list[CountryCodeResponse]:
    return [
        CountryCodeResponse(
            id=c.id,
            name=c.name,
            flag=c.flag.url if c.flag else None,
        )
        for c in CountryCodes.objects.all()
    ]


def _build_profile_response(
    player: Players,
) -> PlayerProfileResponse:
    moderated = list(player.moderated_games.all())

    has_src_key = False
    if player.user:
        has_src_key = player.user.encrypted_api_key is not None

    return PlayerProfileResponse(
        player_id=player.id,
        name=player.name,
        nickname=player.nickname,
        pronouns=player.pronouns,
        countrycode=player.countrycode.id if player.countrycode else None,
        twitch=player.twitch,
        youtube=player.youtube,
        twitter=player.twitter,
        bluesky=player.bluesky,
        discord=player.discord,
        therun_gg=player.user.therun_gg if player.user else None,
        pfp=player.pfp,
        ex_stream=player.ex_stream,
        claim_status=player.claim_status,
        username=player.user.username if player.user else "",
        is_superuser=player.user.is_superuser if player.user else False,
        has_src_key=has_src_key,
        bio=player.user.bio if player.user else None,
        short_bio=player.user.short_bio if player.user else None,
        gradient_1=player.user.gradient_1 if player.user else None,
        gradient_2=player.user.gradient_2 if player.user else None,
        gradient_3=player.user.gradient_3 if player.user else None,
        profile_bg=(
            player.user.profile_bg.url
            if player.user and player.user.profile_bg
            else None
        ),
        joined=player.joined,
        moderated_games=[
            ModeratedGameSchema(id=g.id, name=g.name, slug=g.slug) for g in moderated
        ],
    )


@router.get(
    "/me",
    response={200: PlayerProfileResponse, codes_4xx: ErrorResponse},
    summary="Get My Profile",
    description="Returns the current authenticated player's profile.",
    auth=player_session_auth,
)
def get_me(
    request: HttpRequest,
) -> Status:
    return Status(200, _build_profile_response(request.auth))  # type: ignore


@router.patch(
    "/me",
    response={200: PlayerProfileResponse, codes_4xx: ErrorResponse},
    summary="Update My Profile",
    description=dedent(
        """
    Updates editable fields on the current authenticated player's profile.
    Only non-null fields in the request body will be applied.
    """
    ),
    auth=player_session_auth,
)
def update_me(
    request: HttpRequest,
    body: PlayerUpdateRequest,
) -> Status:
    player: Players = request.auth  # type: ignore

    update_fields: list[str] = []

    for field in (
        "name",
        "nickname",
        "pronouns",
        "twitch",
        "youtube",
        "twitter",
        "bluesky",
        "discord",
        "ex_stream",
    ):
        if field in body.model_fields_set:
            setattr(player, field, getattr(body, field))
            update_fields.append(field)

    if "countrycode" in body.model_fields_set:
        country = CountryCodes.objects.filter(id=body.countrycode).first()
        if country is None:
            return Status(
                400,
                ErrorResponse(
                    error="Invalid country code",
                    details={"countrycode": body.countrycode},
                ),
            )
        player.countrycode = country
        update_fields.append("countrycode")

    if update_fields:
        player.save(update_fields=update_fields)

    user_update_fields: list[str] = []
    for field in ("bio", "short_bio", "gradient_1", "gradient_2", "gradient_3"):
        if field in body.model_fields_set:
            setattr(player.user, field, getattr(body, field))
            user_update_fields.append(field)

    if player.user:
        if user_update_fields:
            if player.user.gradient_2 is not None and player.user.gradient_1 is None:
                return Status(
                    400,
                    ErrorResponse(
                        error="gradient_2 requires gradient_1 to be set",
                        details=None,
                    ),
                )
            if player.user.gradient_3 is not None and player.user.gradient_2 is None:
                return Status(
                    400,
                    ErrorResponse(
                        error="gradient_3 requires gradient_2 to be set",
                        details=None,
                    ),
                )
            player.user.save(update_fields=user_update_fields)

    return Status(200, _build_profile_response(player))


@router.post(
    "/me/pfp",
    response={200: PfpUploadResponse, codes_4xx: ErrorResponse},
    summary="Upload Profile Picture",
    description=dedent(
        """
    Uploads a new profile picture for the authenticated player.
    Accepts image files only (max 5 MB). Saves to static/pfp/`playerid`.jpg.
    """
    ),
    auth=player_session_auth,
)
def upload_pfp(
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

    if not file.size or file.size > 5 * 1024 * 1024:
        return Status(
            400,
            ErrorResponse(
                error="Image exceeds maximum size of 5 MB",
                details=None,
            ),
        )

    # Takes the full content and re-encodes with Pillow to strip the file of extra metadata and crap
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


@router.post(
    "/me/profile-bg",
    response={200: ProfileBGUploadResponse, codes_4xx: ErrorResponse},
    summary="Upload Profile Background",
    description=dedent(
        """
    Uploads a profile background image for the authenticated player's user account.
    Accepts image files only (max 10 MB). Re-encodes to strip metadata.
    """
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


@router.post(
    "/me/src-key",
    response={200: SRCKeyStatusResponse, codes_4xx: ErrorResponse},
    summary="Store SRC API Key",
    description=dedent(
        """
    Stores an encrypted Speedrun.com API key for the authenticated player.
    Only available to players who are moderators of at least one game.
    The key is verified against the SRC API to confirm it belongs to the
    authenticated player before storage.
    """
    ),
    auth=player_session_auth,
)
@auth_rate_limit
def set_src_key(
    request: HttpRequest,
    body: SRCKeyRequest,
) -> Status:
    player: Players = request.auth  # type: ignore

    if not player.moderated_games.exists():
        return Status(
            403,
            ErrorResponse(
                error="Only moderators can store an SRC API key",
                details=None,
            ),
        )

    # Verify the SRC API key by calling the SRC profile endpoint
    try:
        src_response = http_requests.get(
            "https://www.speedrun.com/api/v1/profile",
            headers={"X-API-Key": body.src_api_key},
            timeout=10,
        )
    except http_requests.RequestException:
        return Status(
            400,
            ErrorResponse(
                error="Failed to contact Speedrun.com API",
                details=None,
            ),
        )

    if src_response.status_code != 200:
        return Status(
            400,
            ErrorResponse(
                error="Invalid or expired SRC API key",
                details=None,
            ),
        )

    try:
        src_data = src_response.json()
        src_user_id: str = src_data["data"]["id"]
    except (KeyError, ValueError):
        return Status(
            400,
            ErrorResponse(
                error="Unexpected response from Speedrun.com API",
                details=None,
            ),
        )

    # Ensure the API key belongs to the authenticated player
    if src_user_id != player.id:
        return Status(
            403,
            ErrorResponse(
                error="This SRC API key does not belong to your account",
                details=None,
            ),
        )

    if player.user:
        player.user.encrypted_api_key = encrypt_src_key(body.src_api_key)
        player.user.save(update_fields=["encrypted_api_key"])

    return Status(
        200,
        SRCKeyStatusResponse(
            has_src_key=True,
            message="SRC API key stored successfully",
        ),
    )


@router.delete(
    "/me/src-key",
    response={204: None, codes_4xx: ErrorResponse},
    summary="Remove SRC API Key",
    description=dedent(
        """
    Removes the stored SRC API key for the authenticated player.
    After removal, the player will not be able to approve runs until
    they re-submit their key.
    """
    ),
    auth=player_session_auth,
)
def delete_src_key(
    request: HttpRequest,
) -> Status:
    player: Players = request.auth  # type: ignore

    if not player.user or not player.user.encrypted_api_key:
        return Status(
            404,
            ErrorResponse(
                error="No SRC API key found",
                details=None,
            ),
        )

    player.user.encrypted_api_key = None
    player.user.save(update_fields=["encrypted_api_key"])

    return Status(204, None)


@router.delete(
    "/me",
    response={204: None, codes_4xx: ErrorResponse},
    summary="Delete My Account",
    description=dedent(
        """
    Deletes the authenticated player's account.
    Blanks the Player record (runs are preserved) and deletes the linked Django User.
    """
    ),
    auth=player_session_auth,
)
def delete_me(
    request: HttpRequest,
) -> Status:
    player: Players = request.auth  # type: ignore
    user = player.user
    old_pfp = player.pfp

    try:
        with transaction.atomic():
            player.name = "Anonymous"
            player.nickname = None
            player.pfp = None
            player.pronouns = None
            player.twitch = None
            player.youtube = None
            player.twitter = None
            player.bluesky = None
            player.discord = None
            player.countrycode = None
            player.claim_status = Players.ClaimStatus.DELETED
            player.sync_paused = True
            player.user = None
            player.save(
                update_fields=[
                    "name",
                    "nickname",
                    "pfp",
                    "pronouns",
                    "twitch",
                    "youtube",
                    "twitter",
                    "bluesky",
                    "discord",
                    "countrycode",
                    "claim_status",
                    "sync_paused",
                    "user",
                ]
            )

            player.moderated_games.clear()

            if user is not None:
                if user.profile_bg:
                    user.profile_bg.delete(save=False)
                user.delete()
    except Exception as e:
        logger.exception("Failed to delete account for player %s", player.id)
        return Status(
            500,
            ErrorResponse(
                error="Failed to delete account",
                details={"exception": str(e)},
            ),
        )

    if old_pfp:
        pfp_basename = os.path.basename(old_pfp)
        pfp_fs_path = os.path.join(PFP_DIR, pfp_basename)
        if not os.path.abspath(pfp_fs_path).startswith(
            os.path.abspath(PFP_DIR),
        ):
            logger.warning("Skipping suspicious pfp path: %s", old_pfp)
        else:
            try:
                os.remove(pfp_fs_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning(
                    "Failed to remove pfp file %s after account deletion",
                    pfp_fs_path,
                )

    logger.info(
        "Account deleted: player_id=%s user_id=%s",
        player.id,
        user.id if user else None,
    )

    return Status(204, None)
