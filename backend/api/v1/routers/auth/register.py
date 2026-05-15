import requests as http_requests
from django.contrib.auth import get_user_model, login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from ninja import Router, Status
from srl.encryption import encrypt_src_key
from srl.models import Players, RunPlayers

from api.csrf import enforce_csrf
from api.rate_limiting import auth_rate_limit
from api.v1.schemas.auth import RegisterRequest, RegisterResponse
from api.v1.schemas.base import ErrorResponse

User = get_user_model()

router = Router()


@router.post(
    "/register",
    response={
        201: RegisterResponse,
        400: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Register Account",
    description="""\
Verifies the caller's Speedrun.com identity via their SRC API key,
creates a Django user, links it to the matching player, and logs the user in.
If save_key is true, the API key is encrypted and stored for future use.
""",
    auth=None,
)
@auth_rate_limit
def register(
    request: HttpRequest,
    body: RegisterRequest,
) -> Status:
    enforce_csrf(request)

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

    try:
        validate_password(body.password1)
    except ValidationError as e:
        return Status(
            400,
            ErrorResponse(
                error="Password does not meet security requirements",
                details={"password_errors": list(e.messages)},
            ),
        )

    try:
        with transaction.atomic():
            user: User = User.objects.create_user(
                username=body.username,
                email=body.email,
                password=body.password1,
            )
            player.user = user
            player.claim_status = Players.ClaimStatus.CLAIMED
            player.sync_paused = True
            player.save(update_fields=["user", "claim_status", "sync_paused"])

            if body.save_key:
                user.encrypted_api_key = encrypt_src_key(body.src_api_key)
                user.save(update_fields=["encrypted_api_key"])
    except IntegrityError:
        return Status(
            409,
            ErrorResponse(
                error="Username or email already in use",
                details=None,
            ),
        )

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    return Status(
        201,
        RegisterResponse(
            player_id=player.id,
            player_name=player.name,
            username=user.username,
        ),
    )
