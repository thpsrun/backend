import time
from textwrap import dedent

import requests as http_requests
from django.http import HttpRequest
from ninja import Router, Status
from ninja.responses import codes_4xx
from srl.models import Players, RunPlayers

from api.rate_limiting import auth_rate_limit
from api.v1.schemas.auth import SRCVerifyRequest, SRCVerifyResponse
from api.v1.schemas.base import ErrorResponse

router = Router()


@router.post(
    "/verify-src",
    response={200: SRCVerifyResponse, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Verify SRC Account",
    description=dedent(
        """
    Verifies a player's Speedrun.com account via their SRC API key.
    On success, stores the verified player ID in the session and returns the player's name.
    The API key is used only for this request and is never stored.
    """
    ),
    auth=None,
)
@auth_rate_limit
def verify_src(
    request: HttpRequest,
    body: SRCVerifyRequest,
) -> Status:
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
    except (KeyError, ValueError) as e:
        return Status(
            400,
            ErrorResponse(
                error="Unexpected response from Speedrun.com API",
                details={"exception": str(e)},
            ),
        )

    try:
        player = Players.objects.get(id=src_user_id)
    except Players.DoesNotExist:
        return Status(
            404,
            ErrorResponse(
                error="No player found for this SRC account",
                details=None,
            ),
        )

    if player.claim_status != Players.ClaimStatus.UNCLAIMED:
        return Status(
            409,
            ErrorResponse(
                error="An account already exists for this player",
                details=None,
            ),
        )

    has_verified_run = RunPlayers.objects.filter(
        player=player,
        run__vid_status="verified",
    ).exists()

    if not has_verified_run:
        return Status(
            403,
            ErrorResponse(
                error="You must have at least one verified run to register",
                details=None,
            ),
        )

    request.session["src_verified_player_id"] = player.id
    request.session["src_verified_at"] = int(time.time())

    return Status(
        200,
        SRCVerifyResponse(
            player_id=player.id,
            player_name=player.name,
        ),
    )
