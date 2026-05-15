import logging

import requests as http_requests
from django.http import HttpRequest
from ninja import Router, Status
from srl.encryption import encrypt_src_key
from srl.models import Players

from api.permissions import authed
from api.rate_limiting import auth_rate_limit
from api.v1.schemas.auth import SRCKeyRequest, SRCKeyStatusResponse
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()


@router.post(
    "/me/src-key",
    response={
        200: SRCKeyStatusResponse,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Store SRC API Key",
    description=(
        "Stores an encrypted Speedrun.com API key for the authenticated player. "
        "The key is verified against the SRC API to confirm it belongs to the "
        "authenticated player before storage."
    ),
    auth=authed("profile.edit_own"),
)
@auth_rate_limit
def set_src_key(
    request: HttpRequest,
    body: SRCKeyRequest,
) -> Status:
    player: Players = request.auth.player  # type: ignore

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
    response={
        204: None,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Remove SRC API Key",
    description=(
        "Removes the stored SRC API key for the authenticated player. "
        "After removal, the player will not be able to approve runs until "
        "they re-submit their key."
    ),
    auth=authed("profile.edit_own"),
)
def delete_src_key(
    request: HttpRequest,
) -> Status:
    player: Players = request.auth.player  # type: ignore

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
