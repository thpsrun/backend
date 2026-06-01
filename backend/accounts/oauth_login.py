import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any, NoReturn

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialLogin
from django.conf import settings
from django.http import HttpRequest, HttpResponseRedirect

logger = logging.getLogger(__name__)

LOGIN_INTENT_SESSION_KEY = "_oauth_login_intent"
LOGIN_COMPLETE_URL_NAME = "oauth_login_complete"
_LOGIN_COMPLETE_URL_PATH = "/accounts/oauth-login-complete/"


def write_intent(
    request: HttpRequest,
    *,
    provider: str,
) -> None:
    request.session[LOGIN_INTENT_SESSION_KEY] = {
        "provider": provider,
        "created_at": datetime.now(dt_timezone.utc).isoformat(),
    }
    request.session.modified = True


def read_intent(
    request: HttpRequest,
) -> dict[str, Any] | None:
    intent = request.session.get(LOGIN_INTENT_SESSION_KEY)
    if not intent:
        return None
    if is_intent_expired(intent):
        clear_intent(request)
        return None
    return intent


def peek_intent(
    request: HttpRequest,
) -> dict[str, Any] | None:
    """Return the stored intent without checking TTL or auto-clearing."""
    intent = request.session.get(LOGIN_INTENT_SESSION_KEY)
    if not intent:
        return None
    return intent


def clear_intent(
    request: HttpRequest,
) -> None:
    if LOGIN_INTENT_SESSION_KEY in request.session:
        del request.session[LOGIN_INTENT_SESSION_KEY]
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
    ttl = timedelta(seconds=settings.OAUTH_LOGIN_INTENT_TTL_SECONDS)
    return datetime.now(dt_timezone.utc) - created_at > ttl


def _log_event(
    request: HttpRequest,
    event: str,
    **fields: Any,
) -> None:
    extra = {
        "event": event,
        "ip": request.META.get("REMOTE_ADDR"),
        **fields,
    }
    logger.info("auth.event", extra=extra)


def _complete_redirect(
    status: str,
    reason: str = "",
    provider: str = "",
) -> ImmediateHttpResponse:
    qs = f"?status={status}"
    if reason:
        qs += f"&reason={reason}"
    if provider:
        qs += f"&provider={provider}"
    return ImmediateHttpResponse(
        HttpResponseRedirect(f"{_LOGIN_COMPLETE_URL_PATH}{qs}"),
    )


def _fail(
    request: HttpRequest,
    reason: str,
    provider: str | None = None,
) -> NoReturn:
    clear_intent(request)
    _log_event(
        request,
        "oauth_login_failed",
        reason=reason,
        provider=provider,
    )
    raise _complete_redirect("error", reason, provider or "")


def handle_login(
    request: HttpRequest,
    sociallogin: SocialLogin,
    intent: dict[str, Any],
) -> None:
    if is_intent_expired(intent):
        _fail(request, "intent_expired")
    intent_provider = intent.get("provider")
    if sociallogin.account.provider != intent_provider:
        _fail(request, "provider_mismatch", provider=intent_provider)
    if not sociallogin.is_existing:
        _fail(request, "no_link", provider=intent_provider)
    if sociallogin.user is not None and not sociallogin.user.is_active:
        _fail(request, "banned", provider=intent_provider)
    clear_intent(request)
    _log_event(
        request,
        "oauth_login_validated",
        provider=intent_provider,
    )
