from __future__ import annotations

import logging
from urllib.parse import unquote

from allauth.account.internal.flows.reauthentication import did_recently_authenticate
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from ninja import Router, Status

from api.permissions import session_only
from api.v1.routers.auth.me import _build_profile_response
from api.v1.schemas.auth import PlayerProfileResponse
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.email import (
    EmailChangeRequest,
    EmailChangeResponse,
    EmailStateResponse,
    EmailVerifyRequest,
)

logger = logging.getLogger(__name__)
router = Router()


def _primary(user) -> EmailAddress | None:
    return EmailAddress.objects.filter(user=user, primary=True).first()


def _pending(user) -> EmailAddress | None:
    return (
        EmailAddress.objects.filter(user=user, primary=False, verified=False)
        .order_by("-id")
        .first()
    )


def _pending_expires_at(pending: EmailAddress | None):
    # HMAC verification mode does not persist a confirmation row, so the precise
    # expiry timestamp is not available here. The token itself carries its own expiry
    # (EMAIL_CONFIRMATION_EXPIRE_DAYS, default 3) and is validated at verify time.
    return None


@router.get(
    "/me/email",
    response={
        200: EmailStateResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Get My Email State",
    description="Returns the current verified email plus any pending change in flight.",
    auth=session_only("profile.edit_own"),
)
def get_email_state(
    request: HttpRequest,
) -> Status:
    user = request.auth  # type: ignore
    primary = _primary(user)
    pending = _pending(user)
    return Status(
        200,
        EmailStateResponse(
            email=primary.email if primary else (user.email or ""),
            verified=bool(primary and primary.verified),
            pending_email=pending.email if pending else None,
            pending_expires_at=_pending_expires_at(pending),
        ),
    )


@router.post(
    "/me/email/change",
    response={
        202: EmailChangeResponse,
        400: ErrorResponse,
        401: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Request Email Change",
    description="""\
Initiates a change of the user's primary email address. Sends a 6-digit verification
code to the new address. Requires recent reauthentication.
""",
    auth=session_only("profile.edit_own"),
)
def change_email(
    request: HttpRequest,
    body: EmailChangeRequest,
) -> Status:
    user = request.auth  # type: ignore
    if not did_recently_authenticate(request):
        return Status(
            401,
            ErrorResponse(
                error="reauth_required",
                details=None,
            ),
        )

    new_email = body.new_email.strip()
    primary = _primary(user)
    if primary is not None and new_email.lower() == primary.email.lower():
        return Status(
            400,
            ErrorResponse(
                error="same_email",
                details=None,
            ),
        )

    if (
        EmailAddress.objects.filter(
            email__iexact=new_email,
            verified=True,
        )
        .exclude(user=user)
        .exists()
    ):
        return Status(
            409,
            ErrorResponse(error="email_taken", details=None),
        )

    with transaction.atomic():
        EmailAddress.objects.filter(
            user=user,
            primary=False,
        ).delete()
        pending = EmailAddress.objects.create(
            user=user,
            email=new_email,
            primary=False,
            verified=False,
        )
    pending.send_confirmation(request, signup=False)

    expires = _pending_expires_at(pending)
    return Status(
        202,
        EmailChangeResponse(
            status="verification_sent",
            new_email=new_email,
            expires_at=expires,
        ),
    )


@router.post(
    "/me/email/verify",
    response={
        200: PlayerProfileResponse,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Verify Email Change",
    description="Verifies a pending email change with the 6-digit code.",
    auth=session_only("profile.edit_own"),
)
def verify_email_change(
    request: HttpRequest,
    body: EmailVerifyRequest,
) -> Status:
    user = request.auth  # type: ignore
    pending = _pending(user)
    if pending is None:
        return Status(
            400,
            ErrorResponse(error="no_pending_change", details=None),
        )

    # Tolerate URL-encoded keys (the HMAC contains ':' separators that some
    # frontends/email clients percent-encode in transit).
    code = unquote(body.code).strip()
    confirmation = EmailConfirmationHMAC.from_key(code)
    if (
        confirmation is None
        or confirmation.email_address.pk != pending.pk
        or confirmation.email_address.user.id != user.pk
    ):
        logger.info(
            "me/email/verify rejected: user=%s pending_pk=%s code_len=%d "
            "raw_len=%d hmac_match=%s",
            user.pk,
            pending.pk,
            len(code),
            len(body.code),
            confirmation is not None,
        )
        return Status(
            400,
            ErrorResponse(error="invalid_or_expired_code", details=None),
        )

    try:
        confirmed = confirmation.confirm(request)
    except IntegrityError:
        return Status(
            400,
            ErrorResponse(
                error="invalid_or_expired_code",
                details=None,
            ),
        )
    if confirmed is None:
        return Status(
            400,
            ErrorResponse(
                error="invalid_or_expired_code",
                details=None,
            ),
        )

    return Status(200, _build_profile_response(request.auth.player))  # type: ignore


@router.post(
    "/me/email/resend",
    response={
        204: None,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Resend Email Change Code",
    description="Resends the verification code to the pending email address.",
    auth=session_only("profile.edit_own"),
)
def resend_email_code(
    request: HttpRequest,
) -> Status:
    user = request.auth  # type: ignore
    pending = _pending(user)
    if pending is None:
        return Status(
            400,
            ErrorResponse(
                error="no_pending_change",
                details=None,
            ),
        )
    pending.send_confirmation(request, signup=False)
    return Status(204, None)


@router.delete(
    "/me/email/pending",
    response={
        204: None,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Cancel Pending Email Change",
    description="Discards any pending email change. Idempotent.",
    auth=session_only("profile.edit_own"),
)
def cancel_pending_change(
    request: HttpRequest,
) -> Status:
    user = request.auth  # type: ignore
    EmailAddress.objects.filter(
        user=user,
        primary=False,
        verified=False,
    ).delete()
    return Status(204, None)
