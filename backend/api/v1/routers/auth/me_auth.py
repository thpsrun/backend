import hashlib
import logging

from accounts.oauth_connect import write_intent as write_connect_intent
from accounts.oauth_reauth import write_intent
from allauth.account.adapter import get_adapter
from allauth.account.internal.flows.reauthentication import did_recently_authenticate
from allauth.mfa.models import Authenticator
from allauth.socialaccount import signals as socialaccount_signals
from allauth.socialaccount.adapter import get_adapter as get_socialaccount_adapter
from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.providers.base.constants import AuthProcess
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponseRedirect
from django.utils import timezone
from ninja import Router, Status

from api.permissions import session_only
from api.rate_limiting import auth_rate_limit
from api.v1.schemas.auth import (
    AuthenticatorListItem,
    AuthMethodsResponse,
    OAuthConnectInitiateResponse,
    OAuthReauthInitiateResponse,
    SocialAccountListItem,
    SocialAccountListResponse,
)
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()

User = get_user_model()


def _authenticator_public_id(
    auth_pk: int,
) -> str:
    """Derive a deterministic, non-enumerable id for an Authenticator row.

    The real DB primary key is never returned to clients. The hash is keyed
    with SECRET_KEY so callers cannot precompute the mapping.
    """
    payload = f"{settings.SECRET_KEY}:{auth_pk}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _log_security_event(
    event: str,
    request: HttpRequest,
    user,
    **fields,
) -> None:
    """Log a structured security event with user, IP, and user-agent context."""
    extra = {
        "event": event,
        "user_id": getattr(user, "pk", None),
        "ip": request.META.get("REMOTE_ADDR"),
        "ua": request.META.get("HTTP_USER_AGENT", "")[:200],
        **fields,
    }
    logger.info("auth.event", extra=extra)


def _social_accounts_for(
    user,
) -> list[SocialAccountListItem]:
    """List the user's linked social accounts for API responses."""
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
    """List the user's authenticators using public, non-enumerable ids."""
    items: list[AuthenticatorListItem] = []
    for a in Authenticator.objects.filter(user=user).order_by("created_at"):
        data = a.data or {}
        items.append(
            AuthenticatorListItem(
                type=a.type,
                id=_authenticator_public_id(a.pk),
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
    auth=session_only("profile.edit_own"),
)
def get_auth_methods(
    request: HttpRequest,
) -> Status:
    user = request.auth  # type: ignore
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
    auth=session_only("profile.edit_own"),
)
def list_social_accounts(
    request: HttpRequest,
) -> Status:
    user = request.auth  # type: ignore
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
    auth=session_only("profile.edit_own"),
)
@auth_rate_limit
def delete_social_account(
    request: HttpRequest,
    provider: str,
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
    adapter = get_socialaccount_adapter(request)
    session_key = getattr(request.session, "session_key", None)
    try:
        with transaction.atomic():
            locked_user = User.objects.select_for_update().get(pk=user.pk)
            account = (
                SocialAccount.objects.select_for_update()
                .filter(user=locked_user, provider=provider)
                .first()
            )
            if account is None:
                return Status(
                    404,
                    ErrorResponse(
                        error="no_social_account",
                        details=None,
                    ),
                )
            accounts = list(SocialAccount.objects.filter(user=locked_user))
            try:
                adapter.validate_disconnect(account, accounts)
            except ValidationError as exc:
                code = exc.message if hasattr(exc, "message") else str(exc.messages[0])
                return Status(
                    409,
                    ErrorResponse(
                        error=code,  # type: ignore
                        details=None,
                    ),
                )
            account.delete()
            socialaccount_signals.social_account_removed.send(
                sender=SocialAccount,
                request=request,
                socialaccount=account,
            )

            _revoke_other_sessions(locked_user, session_key)
    except User.DoesNotExist:
        return Status(
            401,
            ErrorResponse(
                error="user_not_found",
                details=None,
            ),
        )
    try:
        request.session.cycle_key()
    except Exception:
        logger.exception("session_cycle_failed", extra={"user_id": user.pk})
    _log_security_event(
        "social_account_disconnected",
        request,
        user,
        provider=provider,
    )
    return Status(
        204,
        None,
    )


def _user_has_alternative_auth(user) -> bool:
    """Check if the user has any alternative auth method (social or passkey).

    Ensures that users cannot perform a race condition check to prevent users from being
    completely locked out of their accounts.
    """
    if SocialAccount.objects.select_for_update().filter(user=user).exists():
        return True
    if (
        Authenticator.objects.select_for_update()
        .filter(user=user, type=Authenticator.Type.WEBAUTHN)
        .exists()
    ):
        return True
    return False


def _revoke_other_sessions(
    user,
    current_session_key: str | None,
) -> int:
    """Delete every other live session for `user`; returns the number deleted."""
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
    """Notify the user by email that their password was removed."""
    adapter = get_adapter()
    ctx = {"user": user}
    try:
        adapter.send_mail(
            "account/email/password_deleted",
            user.email,
            ctx,
        )
    except Exception:
        logger.exception(
            "password_deletion_email_failed",
            extra={"user_id": user.pk},
        )


@router.delete(
    "/me/auth/password",
    response={
        204: None,
        401: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Delete My Password",
    description=(
        "Removes the password from the account. Requires at least one OAuth"
        " account or WebAuthn passkey, plus a re-authentication proof."
    ),
    auth=session_only("profile.edit_own"),
)
@auth_rate_limit
def delete_password(
    request: HttpRequest,
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
    session_key = getattr(request.session, "session_key", None)
    try:
        with transaction.atomic():
            locked_user = User.objects.select_for_update().get(pk=user.pk)
            if not _user_has_alternative_auth(locked_user):
                return Status(
                    409,
                    ErrorResponse(
                        error="no_alternative_auth",
                        details=None,
                    ),
                )
            locked_user.set_unusable_password()
            locked_user.save(update_fields=["password"])
            _revoke_other_sessions(locked_user, session_key)
    except User.DoesNotExist:
        return Status(
            401,
            ErrorResponse(
                error="user_not_found",
                details=None,
            ),
        )
    try:
        request.session.cycle_key()
    except Exception:
        logger.exception("session_cycle_failed", extra={"user_id": user.pk})
    _send_password_deletion_email(user)
    _log_security_event("password_removed", request, user)
    return Status(
        204,
        None,
    )


@router.post(
    "/me/auth/reauthenticate/oauth/{provider}",
    response={
        200: OAuthReauthInitiateResponse,
        400: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Initiate OAuth Reauthentication",
    description=(
        "Returns a provider authorize URL for re-verifying ownership of an already-linked OAuth "
        "account. Completing the flow stamps the recent-authentication timestamp for sensitive "
        "actions."
    ),
    auth=session_only("profile.edit_own"),
)
@auth_rate_limit
def initiate_oauth_reauth(
    request: HttpRequest,
    provider: str,
) -> Status:
    user = request.auth  # type: ignore
    if provider not in settings.SOCIALACCOUNT_PROVIDERS:
        return Status(
            400,
            ErrorResponse(
                error="unsupported_provider",
                details=None,
            ),
        )
    account = SocialAccount.objects.filter(user=user, provider=provider).first()
    if account is None:
        return Status(
            404,
            ErrorResponse(
                error="no_social_account",
                details=None,
            ),
        )
    social_adapter = get_socialaccount_adapter(request)
    try:
        provider_obj = social_adapter.get_provider(request, provider)
    except Exception:
        return Status(
            400,
            ErrorResponse(
                error="unsupported_provider",
                details=None,
            ),
        )

    # AuthProcess.LOGIN only drives the provider round-trip; the reauth intent
    # written below is what routes the callback into the reauth flow instead of
    # a normal login.
    redirect_response = provider_obj.redirect(
        request,
        process=AuthProcess.LOGIN,
        next_url=None,
    )
    if not isinstance(redirect_response, HttpResponseRedirect):
        return Status(
            400,
            ErrorResponse(
                error="provider_redirect_failed",
                details=None,
            ),
        )
    authorize_url = redirect_response["Location"]
    write_intent(
        request,
        provider=provider,
        user_id=user.pk,
        social_account_id=account.pk,
    )
    _log_security_event(
        "oauth_reauth_initiated",
        request,
        user,
        provider=provider,
    )
    return Status(
        200,
        OAuthReauthInitiateResponse(
            authorize_url=authorize_url,
        ),
    )


@router.post(
    "/me/auth/connect/oauth/{provider}",
    response={
        200: OAuthConnectInitiateResponse,
        400: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Initiate OAuth Connect",
    description=(
        "Returns a provider authorize URL for linking a new social account to the current "
        "user. Open the URL in a popup; the backend redirects the popup to a completion "
        "page that postMessages the result to the opener. Returns 409 `already_linked` if "
        "the user already has this provider linked."
    ),
    auth=session_only("profile.edit_own"),
)
@auth_rate_limit
def initiate_oauth_connect(
    request: HttpRequest,
    provider: str,
) -> Status:
    user = request.auth  # type: ignore
    if provider not in settings.SOCIALACCOUNT_PROVIDERS:
        return Status(
            400,
            ErrorResponse(
                error="unsupported_provider",
                details=None,
            ),
        )
    if SocialAccount.objects.filter(user=user, provider=provider).exists():
        return Status(
            409,
            ErrorResponse(
                error="already_linked",
                details=None,
            ),
        )
    social_adapter = get_socialaccount_adapter(request)
    try:
        provider_obj = social_adapter.get_provider(request, provider)
    except Exception:
        return Status(
            400,
            ErrorResponse(
                error="unsupported_provider",
                details=None,
            ),
        )

    redirect_response = provider_obj.redirect(
        request,
        process=AuthProcess.CONNECT,
        next_url=None,
    )
    if not isinstance(redirect_response, HttpResponseRedirect):
        return Status(
            400,
            ErrorResponse(
                error="provider_redirect_failed",
                details=None,
            ),
        )
    authorize_url = redirect_response["Location"]
    write_connect_intent(
        request,
        provider=provider,
        user_id=user.pk,
    )
    _log_security_event(
        "oauth_connect_initiated",
        request,
        user,
        provider=provider,
    )
    return Status(
        200,
        OAuthConnectInitiateResponse(
            authorize_url=authorize_url,
        ),
    )
