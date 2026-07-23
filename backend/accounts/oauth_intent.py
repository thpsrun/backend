"""Unified OAuth intent flows (login / signup / connect / reauth).

Each provider callback is preceded by a short-lived "intent" the initiating API router stores in
the session. The social-account adapter (accounts/adapters.py) peeks the intent on the callback and
dispatches to the matching handle_* validator below. A single OAuthIntentFlow carries each flow's
configuration plus the shared session/log/redirect scaffolding; the four handle_* functions hold the
flow-specific, security-relevant validation.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any, NoReturn

from allauth.account.internal.flows.login import record_authentication
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings
from django.http import HttpRequest, HttpResponseRedirect

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OAuthIntentFlow:
    """Configuration plus shared session/log/redirect scaffolding for one OAuth intent flow."""

    name: str
    session_key: str
    complete_url_name: str
    complete_url_path: str
    ttl_setting: str
    event_prefix: str

    def write_intent(
        self,
        request: HttpRequest,
        *,
        provider: str,
        **extra: Any,
    ) -> None:
        """Store a pending intent for this flow in the session.

        Arguments:
            request (HttpRequest): The request whose session holds the intent.
            provider (str): The social provider id (e.g. "discord").
            extra (Any): Flow-specific fields (e.g. user_id, social_account_id).
        """
        request.session[self.session_key] = {
            "provider": provider,
            **extra,
            "created_at": datetime.now(dt_timezone.utc).isoformat(),
        }
        request.session.modified = True

    def peek_intent(
        self,
        request: HttpRequest,
    ) -> dict[str, Any] | None:
        """Return the stored intent without checking TTL or auto-clearing it."""
        intent = request.session.get(self.session_key)
        if not intent:
            return None
        return intent

    def clear_intent(
        self,
        request: HttpRequest,
    ) -> None:
        """Remove any stored intent for this flow from the session."""
        if self.session_key in request.session:
            del request.session[self.session_key]
            request.session.modified = True

    def is_intent_expired(
        self,
        intent: dict[str, Any],
    ) -> bool:
        """Report whether the intent is older than this flow's configured TTL.

        Arguments:
            intent (dict): The stored intent, expected to carry an ISO `created_at`.
        Returns:
            expired (bool): True when malformed or past the TTL window.
        """
        created_at_raw = intent.get("created_at")
        if not isinstance(created_at_raw, str):
            return True
        try:
            created_at = datetime.fromisoformat(created_at_raw)
        except ValueError:
            return True
        ttl = timedelta(seconds=getattr(settings, self.ttl_setting))
        return datetime.now(dt_timezone.utc) - created_at > ttl

    def log_event(
        self,
        request: HttpRequest,
        event: str,
        **fields: Any,
    ) -> None:
        """Emit a structured auth.event log line, always including the acting user_id."""
        extra = {
            "event": event,
            "user_id": getattr(getattr(request, "user", None), "pk", None),
            "ip": request.META.get("REMOTE_ADDR"),
            **fields,
        }
        logger.info("auth.event", extra=extra)

    def complete_redirect(
        self,
        status: str,
        reason: str = "",
        provider: str = "",
    ) -> ImmediateHttpResponse:
        """Build the popup-completion redirect for this flow (forwards provider when set)."""
        qs = f"?status={status}"
        if reason:
            qs += f"&reason={reason}"
        if provider:
            qs += f"&provider={provider}"
        return ImmediateHttpResponse(
            HttpResponseRedirect(f"{self.complete_url_path}{qs}"),
        )

    def fail(
        self,
        request: HttpRequest,
        reason: str,
        provider: str | None = None,
    ) -> NoReturn:
        """Clear the intent, log the failure, and raise the error completion redirect."""
        self.clear_intent(request)
        self.log_event(
            request,
            f"{self.event_prefix}_failed",
            reason=reason,
            provider=provider,
        )
        raise self.complete_redirect("error", reason, provider or "")


LOGIN_FLOW = OAuthIntentFlow(
    name="login",
    session_key="_oauth_login_intent",
    complete_url_name="oauth_login_complete",
    complete_url_path="/accounts/oauth-login-complete/",
    ttl_setting="OAUTH_LOGIN_INTENT_TTL_SECONDS",
    event_prefix="oauth_login",
)
SIGNUP_FLOW = OAuthIntentFlow(
    name="signup",
    session_key="_oauth_signup_intent",
    complete_url_name="oauth_signup_complete",
    complete_url_path="/accounts/oauth-signup-complete/",
    ttl_setting="OAUTH_SIGNUP_INTENT_TTL_SECONDS",
    event_prefix="oauth_signup",
)
CONNECT_FLOW = OAuthIntentFlow(
    name="connect",
    session_key="_oauth_connect_intent",
    complete_url_name="oauth_connect_complete",
    complete_url_path="/accounts/oauth-connect-complete/",
    ttl_setting="OAUTH_CONNECT_INTENT_TTL_SECONDS",
    event_prefix="oauth_connect",
)
REAUTH_FLOW = OAuthIntentFlow(
    name="reauth",
    session_key="_oauth_reauth_intent",
    complete_url_name="oauth_reauth_complete",
    complete_url_path="/accounts/oauth-reauth-complete/",
    ttl_setting="OAUTH_REAUTH_INTENT_TTL_SECONDS",
    event_prefix="oauth_reauth",
)


def handle_login(
    request: HttpRequest,
    sociallogin: SocialLogin,
    intent: dict[str, Any],
) -> None:
    """Validate a pending login intent against the provider callback."""
    if LOGIN_FLOW.is_intent_expired(intent):
        LOGIN_FLOW.fail(request, "intent_expired")
    intent_provider = intent.get("provider")
    if sociallogin.account.provider != intent_provider:
        LOGIN_FLOW.fail(request, "provider_mismatch", provider=intent_provider)
    if not sociallogin.is_existing:
        LOGIN_FLOW.fail(request, "no_link", provider=intent_provider)
    if sociallogin.user is not None and not sociallogin.user.is_active:
        LOGIN_FLOW.fail(request, "banned", provider=intent_provider)
    LOGIN_FLOW.clear_intent(request)
    LOGIN_FLOW.log_event(request, "oauth_login_validated", provider=intent_provider)


def handle_signup(
    request: HttpRequest,
    sociallogin: SocialLogin,
    intent: dict[str, Any],
) -> None:
    """Validate a pending signup intent against the provider callback."""
    if SIGNUP_FLOW.is_intent_expired(intent):
        SIGNUP_FLOW.fail(request, "intent_expired")
    intent_provider = intent.get("provider")
    if sociallogin.account.provider != intent_provider:
        SIGNUP_FLOW.fail(request, "provider_mismatch", provider=intent_provider)
    if sociallogin.is_existing:
        SIGNUP_FLOW.fail(request, "already_linked", provider=intent_provider)
    SIGNUP_FLOW.clear_intent(request)
    SIGNUP_FLOW.log_event(request, "oauth_signup_validated", provider=intent_provider)


def handle_connect(
    request: HttpRequest,
    sociallogin: SocialLogin,
    intent: dict[str, Any],
) -> None:
    """Validate a pending connect intent against the provider callback.

    Leaves the intent in the session on success so allauth can finish linking; the adapter's
    get_connect_redirect_url clears it once the link lands.
    """
    if CONNECT_FLOW.is_intent_expired(intent):
        CONNECT_FLOW.fail(request, "intent_expired")
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        CONNECT_FLOW.fail(request, "not_authenticated")
    if user.pk != intent.get("user_id"):
        CONNECT_FLOW.fail(request, "user_mismatch")
    intent_provider = intent.get("provider")
    if sociallogin.account.provider != intent_provider:
        CONNECT_FLOW.fail(request, "provider_mismatch", provider=intent_provider)

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
        CONNECT_FLOW.fail(request, "account_taken", provider=intent_provider)

    if SocialAccount.objects.filter(user=user, provider=intent_provider).exists():
        CONNECT_FLOW.fail(request, "already_linked", provider=intent_provider)

    CONNECT_FLOW.log_event(request, "oauth_connect_validated", provider=intent_provider)


def handle_reauth(
    request: HttpRequest,
    sociallogin: SocialLogin,
    intent: dict[str, Any],
) -> None:
    """Validate a pending reauthentication intent and stamp recent auth on success."""
    if REAUTH_FLOW.is_intent_expired(intent):
        REAUTH_FLOW.fail(request, "intent_expired")
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        REAUTH_FLOW.fail(request, "not_authenticated")
    if user.pk != intent.get("user_id"):
        REAUTH_FLOW.fail(request, "user_mismatch")
    intent_provider = intent.get("provider")
    if sociallogin.account.provider != intent_provider:
        REAUTH_FLOW.fail(request, "provider_mismatch", provider=intent_provider)
    try:
        existing = SocialAccount.objects.get(
            pk=intent.get("social_account_id"),
            user=user,
        )
    except SocialAccount.DoesNotExist:
        REAUTH_FLOW.fail(request, "account_mismatch", provider=intent_provider)
    if sociallogin.account.uid != existing.uid:
        REAUTH_FLOW.fail(request, "account_mismatch", provider=intent_provider)

    record_authentication(
        request,
        user,
        method="socialaccount",
        provider=intent_provider,
        uid=existing.uid,
        reauthenticated=True,
    )
    REAUTH_FLOW.clear_intent(request)
    REAUTH_FLOW.log_event(request, "oauth_reauth_success", provider=intent_provider)
    raise REAUTH_FLOW.complete_redirect("ok", provider=intent_provider)
