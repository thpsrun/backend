import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any, NoReturn

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings
from django.http import HttpRequest, HttpResponseRedirect

logger = logging.getLogger(__name__)

CONNECT_INTENT_SESSION_KEY = "_oauth_connect_intent"
CONNECT_COMPLETE_URL_NAME = "oauth_connect_complete"
_CONNECT_COMPLETE_URL_PATH = "/accounts/oauth-connect-complete/"


def write_intent(
    request: HttpRequest,
    *,
    provider: str,
    user_id: int,
) -> None:
    request.session[CONNECT_INTENT_SESSION_KEY] = {
        "provider": provider,
        "user_id": user_id,
        "created_at": datetime.now(dt_timezone.utc).isoformat(),
    }
    request.session.modified = True


def read_intent(
    request: HttpRequest,
) -> dict[str, Any] | None:
    intent = request.session.get(CONNECT_INTENT_SESSION_KEY)
    if not intent:
        return None
    if is_intent_expired(intent):
        clear_intent(request)
        return None
    return intent


def peek_intent(
    request: HttpRequest,
) -> dict[str, Any] | None:
    intent = request.session.get(CONNECT_INTENT_SESSION_KEY)
    if not intent:
        return None
    return intent


def clear_intent(
    request: HttpRequest,
) -> None:
    if CONNECT_INTENT_SESSION_KEY in request.session:
        del request.session[CONNECT_INTENT_SESSION_KEY]
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
    provider: str = "",
) -> ImmediateHttpResponse:
    qs = f"?status={status}"
    if reason:
        qs += f"&reason={reason}"
    if provider:
        qs += f"&provider={provider}"
    return ImmediateHttpResponse(
        HttpResponseRedirect(f"{_CONNECT_COMPLETE_URL_PATH}{qs}"),
    )


def _fail(
    request: HttpRequest,
    reason: str,
    provider: str | None = None,
) -> NoReturn:
    clear_intent(request)
    _log_event(
        request,
        "oauth_connect_failed",
        reason=reason,
        provider=provider,
    )
    raise _complete_redirect("error", reason)


def handle_connect(
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

    # The provider account is already linked to someone else.
    taken = (
        SocialAccount.objects.filter(
            provider=sociallogin.account.provider,
            uid=sociallogin.account.uid,
        )
        .exclude(user=user)
        .exists()
    )
    if taken:
        _fail(request, "account_taken", provider=intent_provider)

    if SocialAccount.objects.filter(user=user, provider=intent_provider).exists():
        _fail(request, "already_linked", provider=intent_provider)

    _log_event(
        request,
        "oauth_connect_validated",
        provider=intent_provider,
    )
