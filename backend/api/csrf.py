from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import CsrfViewMiddleware
from ninja.errors import HttpError

CSRF_SAFE_METHODS: frozenset[str] = frozenset(("GET", "HEAD", "OPTIONS", "TRACE"))


def _noop_get_response(
    _request: HttpRequest,
) -> HttpResponse:
    """Placeholder `get_response` for `CsrfViewMiddleware`."""
    return HttpResponse()


def enforce_csrf(
    request: HttpRequest,
) -> None:
    """Raise HttpError(403) if CSRF verification fails on an unsafe method."""
    if request.method in CSRF_SAFE_METHODS:
        return
    # django-ninja routes bypass Django's global CSRF protection, so the check is run
    # by hand here. Only session-authenticated callers go through this; API-key auth
    # is not browser-ambient and skips CSRF entirely (see permissions._resolve_caller).
    middleware = CsrfViewMiddleware(_noop_get_response)
    middleware.process_request(request)
    reason = middleware.process_view(request, None, (), {})
    if reason is not None:
        raise HttpError(403, "CSRF verification failed")
