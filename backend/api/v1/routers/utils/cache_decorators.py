from functools import wraps
from typing import Any, Callable

from django.core.cache import caches

_CACHE_MISS = object()


def cache_response(
    timeout: int | None = 604800,
    cache_name: str = "default",
    key_function: Callable[..., str] | None = None,
    skip: Callable[..., bool] | None = None,
) -> Any:
    def decorator(
        function: Callable,
    ) -> Callable:
        @wraps(function)
        def wrapper(
            request,
            *args,
            **kwargs,
        ) -> Any:
            if skip is not None:
                if skip(request, *args, **kwargs):
                    return function(
                        request,
                        *args,
                        **kwargs,
                    )

            if key_function:
                cache_key = key_function(
                    request,
                    *args,
                    **kwargs,
                )
            else:
                cache_key = f"{function.__name__}:{args}:{kwargs}"

            cache = caches[cache_name]

            cached_response = cache.get(cache_key, _CACHE_MISS)
            if cached_response is not _CACHE_MISS:
                return cached_response

            response = function(
                request,
                *args,
                **kwargs,
            )

            cache.set(
                cache_key,
                response,
                timeout=timeout,
            )

            return response

        return wrapper

    return decorator
