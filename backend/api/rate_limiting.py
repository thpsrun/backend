import time
from collections.abc import Callable
from functools import wraps

from django.core.cache import cache
from django.http import HttpRequest, JsonResponse

from api.client_ip import client_ip

_AUTH_RATE_LIMIT: int = 5
_AUTH_RATE_WINDOW: int = 60  # 1 minute


def auth_rate_limit(
    func: Callable,
) -> Callable:
    """Per-IP rate limiter for auth endpoints. 5 requests per minute per IP.

    Defends against brute-force and player enumeration attacks on /register.
    """

    @wraps(func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        ip: str = client_ip(request)
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
                headers={"Retry-After": str(ttl)},
            )

        return func(request, *args, **kwargs)

    return wrapper
