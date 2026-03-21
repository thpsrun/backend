from textwrap import dedent

from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from ninja import Router, Status
from ninja.responses import codes_4xx
from srl.models import Players

from api.rate_limiting import auth_rate_limit
from api.v1.schemas.auth import RegisterRequest, RegisterResponse
from api.v1.schemas.base import ErrorResponse

router = Router()


@router.post(
    "/register",
    response={201: RegisterResponse, codes_4xx: ErrorResponse},
    summary="Register Account",
    description=dedent(
        """
    Requires a prior call to /auth/verify-src that stored the player ID in the session.
    Creates a Django user, links it to the verified player, and logs the user in.
    """
    ),
    auth=None,
)
@auth_rate_limit
def register(
    request: HttpRequest,
    body: RegisterRequest,
) -> Status:
    player_id: str | None = request.session.get("src_verified_player_id")

    if not player_id:
        return Status(
            403,
            ErrorResponse(
                error="SRC verification required before registering",
                details=None,
            ),
        )

    try:
        player = Players.objects.get(id=player_id)
    except Players.DoesNotExist:
        return Status(
            404,
            ErrorResponse(
                error="Player not found",
                details=None,
            ),
        )

    if player.claim_status != Players.ClaimStatus.UNCLAIMED:
        return Status(
            409,
            ErrorResponse(
                error="This player account has already been claimed",
                details=None,
            ),
        )

    if body.password1 != body.password2:
        return Status(
            400,
            ErrorResponse(
                error="Passwords do not match",
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
    except IntegrityError:
        return Status(
            409,
            ErrorResponse(
                error="Username or email already in use",
                details=None,
            ),
        )

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.pop("src_verified_player_id", None)

    return Status(
        201,
        RegisterResponse(
            player_id=player.id,
            player_name=player.name,
            username=user.username,
        ),
    )
