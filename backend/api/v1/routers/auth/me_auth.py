import logging

from allauth.mfa.models import Authenticator
from allauth.socialaccount.models import SocialAccount
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Status

from accounts.adapters import SocialAccountAdapter
from api.permissions import authed
from api.v1.schemas.auth import (
    AuthenticatorListItem,
    AuthMethodsResponse,
    DeletePasswordRequest,
    SocialAccountListItem,
    SocialAccountListResponse,
)
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()


def _social_accounts_for(
    user,
) -> list[SocialAccountListItem]:
    items: list[SocialAccountListItem] = []
    for sa in SocialAccount.objects.filter(user=user).order_by("date_joined"):
        extra = sa.extra_data or {}
        username = extra.get("username") or extra.get("login")
        items.append(
            SocialAccountListItem(
                provider=sa.provider,
                uid=sa.uid,
                username=username,
                last_login=sa.last_login,
            ),
        )
    return items


def _authenticators_for(
    user,
) -> list[AuthenticatorListItem]:
    items: list[AuthenticatorListItem] = []
    for a in Authenticator.objects.filter(user=user).order_by("created_at"):
        data = a.data or {}
        items.append(
            AuthenticatorListItem(
                type=a.type,
                id=a.pk,
                name=data.get("name"),
                added_at=a.created_at,
            ),
        )
    return items


@router.get(
    "/me/auth/methods",
    response={
        200: AuthMethodsResponse,
        401: ErrorResponse,
    },
    summary="List My Auth Methods",
    description=(
        "Returns password status, linked social accounts, and authenticators"
        " for the current user."
    ),
    auth=authed("profile.edit_own"),
)
def get_auth_methods(
    request: HttpRequest,
) -> Status:
    user = request.auth  # type: ignore[union-attr]
    return Status(
        200,
        AuthMethodsResponse(
            has_usable_password=user.has_usable_password(),
            social_accounts=_social_accounts_for(user),
            authenticators=_authenticators_for(user),
        ),
    )


@router.get(
    "/me/auth/social-accounts",
    response={
        200: SocialAccountListResponse,
        401: ErrorResponse,
    },
    summary="List Linked Social Accounts",
    description="Returns the social accounts (Discord, Twitch) linked to the current user.",
    auth=authed("profile.edit_own"),
)
def list_social_accounts(
    request: HttpRequest,
) -> Status:
    user = request.auth  # type: ignore[union-attr]
    return Status(
        200,
        SocialAccountListResponse(
            social_accounts=_social_accounts_for(user),
        ),
    )


@router.delete(
    "/me/auth/social-accounts/{provider}",
    response={
        204: None,
        401: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Unlink a Social Account",
    description=(
        "Removes the link to a social account."
        " Blocked if it is the user's last remaining auth method."
    ),
    auth=authed("profile.edit_own"),
)
def delete_social_account(
    request: HttpRequest,
    provider: str,
) -> Status:
    user = request.auth  # type: ignore[union-attr]
    account = SocialAccount.objects.filter(user=user, provider=provider).first()
    if account is None:
        return Status(
            404,
            ErrorResponse(error="no_social_account", details=None),
        )
    adapter = SocialAccountAdapter()
    accounts = list(SocialAccount.objects.filter(user=user))
    try:
        adapter.validate_disconnect(account, accounts)
    except ValidationError as exc:
        code = exc.message if hasattr(exc, "message") else str(exc.messages[0])
        return Status(
            409,
            ErrorResponse(error=code, details=None),
        )
    account.delete()
    return Status(204, None)


def _user_has_alternative_auth(user) -> bool:
    if SocialAccount.objects.filter(user=user).exists():
        return True
    if Authenticator.objects.filter(user=user, type=Authenticator.Type.WEBAUTHN).exists():
        return True
    return False


def _validate_mfa_code(
    user,
    code: str,
) -> bool:
    from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
    from allauth.mfa.totp.internal.auth import TOTP

    for authn in Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP):
        if TOTP(authn).validate_code(code):
            return True
    for authn in Authenticator.objects.filter(
        user=user,
        type=Authenticator.Type.RECOVERY_CODES,
    ):
        if RecoveryCodes(authn).validate_code(code):
            return True
    return False


def _revoke_other_sessions(
    user,
    current_session_key: str | None,
) -> int:
    target_id = str(user.pk)
    keys_to_kill: list[str] = []
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        if current_session_key and session.session_key == current_session_key:
            continue
        data = session.get_decoded()
        if data.get("_auth_user_id") == target_id:
            keys_to_kill.append(session.session_key)
    deleted, _ = Session.objects.filter(
        session_key__in=keys_to_kill,
    ).delete()
    return deleted


def _send_password_deletion_email(
    user,
) -> None:
    from allauth.account.adapter import get_adapter

    adapter = get_adapter()
    ctx = {"user": user}
    try:
        adapter.send_mail(
            "account/email/password_deleted",
            user.email,
            ctx,
        )
    except Exception as exc:
        logger.warning(
            "Failed to send password-deletion email for user_id=%s: %s",
            user.pk,
            exc,
        )


@router.delete(
    "/me/auth/password",
    response={
        204: None,
        401: ErrorResponse,
        409: ErrorResponse,
        501: ErrorResponse,
    },
    summary="Delete My Password",
    description=(
        "Removes the password from the account. Requires at least one OAuth"
        " account or WebAuthn passkey, plus a re-authentication proof."
    ),
    auth=authed("profile.edit_own"),
)
def delete_password(
    request: HttpRequest,
    body: DeletePasswordRequest,
) -> Status:
    user = request.auth  # type: ignore[union-attr]
    if not _user_has_alternative_auth(user):
        return Status(
            409,
            ErrorResponse(error="no_alternative_auth", details=None),
        )
    if body.webauthn_assertion is not None:
        return Status(
            501,
            ErrorResponse(
                error="webauthn_reauth_not_implemented",
                details=None,
            ),
        )
    reauth_ok = False
    if body.password and user.check_password(body.password):
        reauth_ok = True
    elif body.mfa_code and _validate_mfa_code(user, body.mfa_code):
        reauth_ok = True
    if not reauth_ok:
        return Status(
            401,
            ErrorResponse(error="reauth_required", details=None),
        )
    with transaction.atomic():
        user.set_unusable_password()
        user.save(update_fields=["password"])
    session_key = getattr(request.session, "session_key", None)
    _revoke_other_sessions(user, session_key)
    _send_password_deletion_email(user)
    return Status(204, None)
