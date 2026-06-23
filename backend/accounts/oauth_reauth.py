import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any, NoReturn

from allauth.account.internal.flows.login import record_authentication
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings
from django.http import HttpRequest, HttpResponseRedirect

logger = logging.getLogger(__name__)

REAUTH_INTENT_SESSION_KEY = "_oauth_reauth_intent"
REAUTH_COMPLETE_URL_NAME = "oauth_reauth_complete"
_REAUTH_COMPLETE_URL_PATH = "/accounts/oauth-reauth-complete/"


def write_intent(
    request: HttpRequest,
    *,
    provider: str,
    user_id: int,
    social_account_id: int,
) -> None:
    request.session[REAUTH_INTENT_SESSION_KEY] = {
        "provider": provider,
        "user_id": user_id,
        "social_account_id": social_account_id,
        "created_at": datetime.now(dt_timezone.utc).isoformat(),
    }
    request.session.modified = True


def clear_intent(
    request: HttpRequest,
) -> None:
    if REAUTH_INTENT_SESSION_KEY in request.session:
        del request.session[REAUTH_INTENT_SESSION_KEY]
        request.session.modified = True


def is_intent_expired(
    intent: dict[str, Any],
) -> bool:
    created_at_raw = intent.get("created_at")
    if not isinstance(created_at_raw, str):
        return True
    try:
        created_at = datetime.fromisoformat(created_at_raw)
    except ValueError:
        return True
    ttl = timedelta(seconds=settings.OAUTH_REAUTH_INTENT_TTL_SECONDS)
    return datetime.now(dt_timezone.utc) - created_at > ttl


def peek_intent(
    request: HttpRequest,
) -> dict[str, Any] | None:
    """Return the stored intent without checking TTL or auto-clearing.

    Use this from contexts that want to handle expiry explicitly (e.g., the
    OAuth adapter, which needs to surface `intent_expired` to the popup).
    Pair it with `is_intent_expired` to decide whether to honor the intent.
    """
    intent = request.session.get(REAUTH_INTENT_SESSION_KEY)
    if not intent:
        return None
    return intent


def _log_event(
    request: HttpRequest,
    event: str,
    **fields: Any,
) -> None:
    extra = {
        "event": event,
        "user_id": getattr(getattr(request, "user", None), "pk", None),
        "ip": request.META.get("REMOTE_ADDR"),
        **fields,
    }
    logger.info("auth.event", extra=extra)


def _complete_redirect(
    status: str,
    reason: str = "",
) -> ImmediateHttpResponse:
    qs = f"?status={status}"
    if reason:
        qs += f"&reason={reason}"
    return ImmediateHttpResponse(
        HttpResponseRedirect(f"{_REAUTH_COMPLETE_URL_PATH}{qs}"),
    )


def _fail(
    request: HttpRequest,
    reason: str,
    provider: str | None = None,
) -> NoReturn:
    clear_intent(request)
    _log_event(
        request,
        "oauth_reauth_failed",
        reason=reason,
        provider=provider,
    )
    raise _complete_redirect("error", reason)


def handle_reauth(
    request: HttpRequest,
    sociallogin: SocialLogin,
    intent: dict[str, Any],
) -> None:
    if is_intent_expired(intent):
        _fail(request, "intent_expired")
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        _fail(request, "not_authenticated")
    if user.pk != intent.get("user_id"):
        _fail(request, "user_mismatch")
    intent_provider = intent.get("provider")
    if sociallogin.account.provider != intent_provider:
        _fail(request, "provider_mismatch", provider=intent_provider)
    try:
        existing = SocialAccount.objects.get(
            pk=intent.get("social_account_id"),
            user=user,
        )
    except SocialAccount.DoesNotExist:
        _fail(request, "account_mismatch", provider=intent_provider)
    if sociallogin.account.uid != existing.uid:
        _fail(request, "account_mismatch", provider=intent_provider)

    record_authentication(
        request,
        user,
        method="socialaccount",
        provider=intent_provider,
        uid=existing.uid,
        reauthenticated=True,
    )
    clear_intent(request)
    _log_event(
        request,
        "oauth_reauth_success",
        provider=intent_provider,
    )
    raise _complete_redirect("ok")
