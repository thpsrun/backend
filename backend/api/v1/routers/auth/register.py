from datetime import timedelta

import requests as http_requests
from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Status
from srl.encryption import encrypt_src_key
from srl.models import Players, RunPlayers

from api.csrf import enforce_csrf
from api.rate_limiting import auth_rate_limit
from api.v1.schemas.auth import (
    CorrectEmailRequest,
    CorrectEmailResponse,
    RegisterRequest,
    RegisterResponse,
)
from api.v1.schemas.base import ErrorResponse

User = get_user_model()

router = Router()


@router.post(
    "/register",
    response={
        202: RegisterResponse,
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

    email_address, _ = EmailAddress.objects.update_or_create(
        user=user,
        email=body.email,
        defaults={"primary": True, "verified": False},
    )
    email_address.send_confirmation(request, signup=True)

    return Status(
        202,
        RegisterResponse(
            status="verification_required",
            email=user.email,
            username=user.username,
            src_user_id=src_user_id,
        ),
    )


@router.post(
    "/register/correct-email",
    response={
        200: CorrectEmailResponse,
        400: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Correct Signup Email",
    description="""\
This endpoint allows for a user to fix a mistyped email address. The user re-verifies themselves
with their SRC API Key, then they can replace the pending email and have a new code sent to them.
""",
    auth=None,
)
@auth_rate_limit
def correct_email(
    request: HttpRequest,
    body: CorrectEmailRequest,
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
            ErrorResponse(error="src_api_unavailable", details=None),
        )
    if src_response.status_code != 200:
        return Status(
            400,
            ErrorResponse(error="src_api_invalid", details=None),
        )
    try:
        src_user_id: str = src_response.json()["data"]["id"]
    except (KeyError, ValueError):
        return Status(
            400,
            ErrorResponse(error="src_api_invalid", details=None),
        )

    generic_response = Status(
        200,
        CorrectEmailResponse(
            status="verification_sent",
            email=body.new_email,
        ),
    )

    try:
        player = Players.objects.select_related("user").get(id=src_user_id)
    except Players.DoesNotExist:
        return generic_response
    user = player.user
    if user is None:
        return generic_response

    recency_window = timedelta(
        days=settings.ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS,
    )
    if user.date_joined < timezone.now() - recency_window:
        return generic_response

    primary = EmailAddress.objects.filter(user=user, primary=True).first()
    if primary is not None and primary.verified:
        return generic_response

    if (
        EmailAddress.objects.filter(
            email__iexact=body.new_email,
            verified=True,
        )
        .exclude(user=user)
        .exists()
    ):
        return generic_response

    try:
        with transaction.atomic():
            user.email = body.new_email
            user.save(update_fields=["email"])
            if primary is None:
                primary = EmailAddress.objects.create(
                    user=user,
                    email=body.new_email,
                    primary=True,
                    verified=False,
                )
            else:
                primary.email = body.new_email
                primary.verified = False
                primary.save(update_fields=["email", "verified"])
    except IntegrityError:
        return generic_response

    primary.send_confirmation(request, signup=True)
    return generic_response
