import logging
import re
import time
from collections.abc import Callable

from api.client_ip import client_ip
from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse

from accounts.privileges import is_gated
from accounts.turnstile import TurnstileUnavailable, verify_turnstile

logger = logging.getLogger("accounts.turnstile")

# Backend pages rendered inside the OAuth popup. They postMessage their result back to
# the React opener, which only works when COOP does not sever window.opener.
_OAUTH_POPUP_PATH_RE = re.compile(
    r"^/accounts/("
    r"oauth-connect-complete/"
    r"|oauth-reauth-complete/"
    r"|oauth-signup-complete/"
    r"|oauth-login-complete/"
    r"|social/login/(cancelled|error)/"
    r"|[^/]+/login/callback/.*"
    r")$",
)


class OAuthPopupCOOPMiddleware:
    """Relax Cross-Origin-Opener-Policy on backend pages loaded in OAuth popups.

    Runs after SecurityMiddleware so its header takes precedence.
    """

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        """Store the downstream handler."""
        self.get_response = get_response

    def __call__(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        """Override COOP on popup pages after the response is built."""
        response = self.get_response(request)
        if _OAUTH_POPUP_PATH_RE.match(request.path):
            response.headers["Cross-Origin-Opener-Policy"] = (  # type: ignore
                "unsafe-none"
            )
        return response


_TURNSTILE_PROTECTED: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/_allauth/browser/v1/auth/login"),
        ("POST", "/_allauth/browser/v1/auth/password/request"),
        ("POST", "/_allauth/browser/v1/auth/provider/signup"),
        # provider/redirect starts the OAuth handshake and can be hit with either verb,
        # so both are gated to keep bots from kicking off provider flows.
        ("GET", "/_allauth/browser/v1/auth/provider/redirect"),
        ("POST", "/_allauth/browser/v1/auth/provider/redirect"),
        ("POST", "/api/v1/auth/register"),
    }
)

_TURNSTILE_HEADER = "HTTP_X_TURNSTILE_TOKEN"


def _turnstile_error(
    code: str,
    message: str,
) -> JsonResponse:
    """Build a 403 in the allauth-headless error shape the frontend already parses."""
    return JsonResponse(
        {
            "status": 403,
            "errors": [{"code": code, "message": message}],
        },
        status=403,
    )


def _client_ip_or_none(
    request: HttpRequest,
) -> str | None:
    """Return the client IP, or None when it could not be determined."""
    ip = client_ip(request)
    return None if ip == "unknown" else ip


class TurnstileMiddleware:
    """Verify a Cloudflare Turnstile token on a fixed allow-list of auth endpoints."""

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        """Store the downstream handler."""
        self.get_response = get_response

    def __call__(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        """Reject protected requests that lack a valid Turnstile token."""
        key = (request.method or "", request.path)
        if key not in _TURNSTILE_PROTECTED:
            return self.get_response(request)

        if not settings.TURNSTILE_SECRET_KEY:
            return self.get_response(request)

        remote_ip = _client_ip_or_none(request)
        log_ctx = {"path": request.path, "remote_ip": remote_ip}

        token = request.META.get(_TURNSTILE_HEADER, "")
        if not isinstance(token, str) or not token:
            logger.warning("turnstile token missing", extra=log_ctx)
            return _turnstile_error(
                "turnstile_required",
                "Verification required.",
            )

        try:
            ok = verify_turnstile(token, remote_ip)
        except TurnstileUnavailable:
            # Fail closed: a Cloudflare outage blocks logins rather than waving
            # everything through, but with a distinct code so the UI can explain it.
            logger.warning("turnstile siteverify unavailable", extra=log_ctx)
            return _turnstile_error(
                "turnstile_unavailable",
                "Verification service unavailable.",
            )
        if not ok:
            logger.warning("turnstile token rejected", extra=log_ctx)
            return _turnstile_error(
                "turnstile_failed",
                "Verification failed.",
            )

        logger.info("turnstile verified", extra=log_ctx)
        return self.get_response(request)


_PATH_RATE_LIMITS: dict[tuple[str, str], tuple[int, int]] = {
    ("POST", "/_allauth/browser/v1/auth/password/request"): (3, 3600),
    ("POST", "/_allauth/browser/v1/auth/email/verify/resend"): (3, 3600),
    ("POST", "/api/v1/auth/me/email/change"): (3, 3600),
    ("POST", "/api/v1/auth/me/email/resend"): (3, 3600),
    ("POST", "/api/v1/auth/register/correct-email"): (3, 3600),
    ("POST", "/api/v1/auth/me/resync"): (5, 3600),
}


def _rate_limit_error(
    ttl: int,
) -> JsonResponse:
    response = JsonResponse(
        {
            "status": 429,
            "errors": [
                {
                    "code": "rate_limited",
                    "message": "Too many attempts. Try again later.",
                },
            ],
        },
        status=429,
    )
    response.headers["Retry-After"] = str(ttl)
    return response


class PathRateLimitMiddleware:
    """Per-IP, per-(method, path) fixed-window rate limit for sensitive auth endpoints."""

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        self.get_response = get_response

    def __call__(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        key = (request.method or "", request.path)
        config = _PATH_RATE_LIMITS.get(key)
        if config is None:
            return self.get_response(request)
        if getattr(settings, "RATE_LIMIT_DISABLED", False):
            return self.get_response(request)

        limit, window = config
        ip = client_ip(request)
        now = int(time.time())
        window_start = now - (now % window)
        ttl = (window_start + window) - now

        cache_key = f"path_rl:{request.method}:{request.path}:{ip}:{window_start}"
        cache.add(cache_key, 0, ttl)
        try:
            count: int = cache.incr(cache_key)
        except ValueError:
            cache.add(cache_key, 1, ttl)
            count = 1

        if count > limit:
            logger.warning(
                "path rate limit exceeded",
                extra={
                    "path": request.path,
                    "method": request.method,
                    "remote_ip": ip,
                    "ttl": ttl,
                },
            )
            return _rate_limit_error(ttl)

        return self.get_response(request)


class MFASetupRequiredMiddleware:
    """Block privileged users (superusers, game moderators) until they have a TOTP or passkey."""

    ALLOWLISTED_PREFIXES = (
        "/_allauth/",
        "/accounts/",
        "/illiad/",
    )

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        self.get_response = get_response

    def _is_allowlisted(
        self,
        path: str,
    ) -> bool:
        prefixes = self.ALLOWLISTED_PREFIXES + (
            settings.STATIC_URL,
            settings.MEDIA_URL,
        )
        return any(prefix and path.startswith(prefix) for prefix in prefixes)

    def __call__(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        if (
            getattr(settings, "MFA_ENFORCE_FOR_PRIVILEGED", True)
            and request.user.is_authenticated
            and not self._is_allowlisted(request.path)
            and is_gated(request.user)
        ):
            return JsonResponse(
                {
                    "status": 403,
                    "data": {
                        "flows": [{"id": "mfa_setup_required"}],
                        "accepted_types": ["totp", "webauthn"],
                    },
                    "meta": {"is_authenticated": True},
                },
                status=403,
            )
        return self.get_response(request)
