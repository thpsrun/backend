import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as dt_timezone
from functools import wraps
from typing import Any

from django.core.cache import cache
from django.http import HttpRequest, JsonResponse

from api.models import RoleAPIKey


@dataclass(frozen=True)
class RateLimitConfig:
    """Configuration for a rate limit tier."""

    description: str
    limit: int
    window_seconds: int


class RoleBasedRateLimit:
    """Custom rate limiter with different limits per API key role.

    Rate Limits Per Role:
    - public: 100 requests/hour (for unauthenticated)
    - read_only: 500 requests/hour
    - contributor: 1000 requests/hour
    - moderator: 2000 requests/hour
    - admin: 5000 requests/hour
    """

    ROLE_LIMITS: dict[str, RateLimitConfig] = {
        "public": RateLimitConfig("100/h", 100, 3600),
        "read_only": RateLimitConfig("500/h", 500, 3600),
        "contributor": RateLimitConfig("1000/h", 1000, 3600),
        "moderator": RateLimitConfig("2000/h", 2000, 3600),
        "admin": RateLimitConfig("5000/h", 5000, 3600),
    }

    def __init__(
        self,
        cache_prefix: str = "api_rate_limit",
    ):
        self.cache_prefix = cache_prefix

    def get_cache_key(
        self,
        identifier: str,
        window: str,
    ) -> str:
        """Generate cache key for rate limiting."""
        return f"{self.cache_prefix}:{identifier}:{window}"

    def _get_public_identifier(self, request: HttpRequest) -> str:
        """Get IP-based identifier for unauthenticated requests."""
        return f"ip_{request.META.get('REMOTE_ADDR', 'unknown')}"

    def get_rate_limit_info(
        self,
        request: HttpRequest,
    ) -> tuple[str, int, int, str]:
        """Get rate limit information for the request.

        Returns:
            tuple: (role, limit_count, window_seconds, identifier)
        """
        api_key_header = request.headers.get("X-API-Key")
        role = "public"
        identifier = self._get_public_identifier(request)

        if api_key_header:
            try:
                api_key_obj = RoleAPIKey.objects.get_from_key(api_key_header)  # type: ignore
                if api_key_obj:
                    role = api_key_obj.role
                    identifier = f"key_{api_key_obj.id}"
            except RoleAPIKey.DoesNotExist:
                pass

        config = self.ROLE_LIMITS[role]
        return role, config.limit, config.window_seconds, identifier

    def is_rate_limited(
        self,
        request: HttpRequest,
    ) -> tuple[bool, dict[str, Any]]:
        """Check if request should be rate limited.

        Uses atomic cache operations to prevent race conditions.

        Returns:
            tuple: (is_limited: bool, rate_info: dict)
        """
        role, limit_count, window_seconds, identifier = self.get_rate_limit_info(
            request
        )

        current_time = int(time.time())
        window_start = current_time - (current_time % window_seconds)
        window_end = window_start + window_seconds

        ttl = window_end - current_time

        cache_key = self.get_cache_key(identifier, str(window_start))

        cache.add(cache_key, 0, ttl)
        try:
            current_count = cache.incr(cache_key)
        except ValueError:
            cache.add(cache_key, 1, ttl)
            current_count = 1

        rate_info = {
            "role": role,
            "limit": limit_count,
            "current": current_count,
            "window_seconds": window_seconds,
            "reset_time": window_end,
            "identifier": identifier,
        }

        if current_count > limit_count:
            return True, rate_info

        return False, rate_info


role_rate_limiter = RoleBasedRateLimit()

_AUTH_RATE_LIMIT: int = 5
_AUTH_RATE_WINDOW: int = 60  # 1 minute


def auth_rate_limit(
    func: Callable,
) -> Callable:
    """Per-IP rate limiter for auth endpoints. 5 requests per minute per IP.

    Stricter than the global API rate limiter to defend against brute-force
    and player enumeration attacks on /register.
    """

    @wraps(func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        ip: str = request.META.get("REMOTE_ADDR", "unknown")
        current_time: int = int(time.time())
        window_start: int = current_time - (current_time % _AUTH_RATE_WINDOW)
        window_end: int = window_start + _AUTH_RATE_WINDOW
        ttl: int = window_end - current_time

        cache_key: str = f"auth_rl:ip_{ip}:{window_start}"
        cache.add(cache_key, 0, ttl)
        try:
            count: int = cache.incr(cache_key)
        except ValueError:
            cache.add(cache_key, 1, ttl)
            count = 1

        if count > _AUTH_RATE_LIMIT:
            return JsonResponse(
                {
                    "error": "Too many requests. Please try again later.",
                    "details": None,
                },
                status=429,
                headers={"Retry-After": str(window_end - current_time)},
            )

        return func(request, *args, **kwargs)

    return wrapper


def role_based_rate_limit(
    func: Callable,
) -> Callable:
    """Decorator for role-based rate limiting on Django Ninja endpoints.

    Usage:
        @role_based_rate_limit
        @router.get("/protected-endpoint")
        def protected_view(request):
            return {"message": "Success"}
    """

    @wraps(func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        is_limited, rate_info = role_rate_limiter.is_rate_limited(request)

        if is_limited:
            reset_time = datetime.fromtimestamp(
                rate_info["reset_time"], tz=dt_timezone.utc
            )
            return JsonResponse(
                {
                    "error": "Rate limit exceeded",
                    "details": {
                        "role": rate_info["role"],
                        "limit": rate_info["limit"],
                        "current": rate_info["current"],
                        "reset_time": reset_time.isoformat(),
                        "message": f"Rate limit exceeded for {rate_info['role']} role. "
                        f"Limit: {rate_info['limit']} requests per hour.",
                    },
                    "code": 429,
                },
                status=429,
                headers={
                    "X-RateLimit-Limit": str(rate_info["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(rate_info["reset_time"]),
                    "Retry-After": str(rate_info["reset_time"] - int(time.time())),
                },
            )

        response = func(request, *args, **kwargs)
        if hasattr(response, "headers"):
            response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(
                rate_info["limit"] - rate_info["current"]
            )
            response.headers["X-RateLimit-Reset"] = str(rate_info["reset_time"])

        return response

    return wrapper
