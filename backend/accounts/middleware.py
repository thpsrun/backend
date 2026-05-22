import re
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

_OAUTH_POPUP_PATH_RE = re.compile(
    r"^/accounts/("
    r"oauth-connect-complete/"
    r"|oauth-reauth-complete/"
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
        self.get_response = get_response

    def __call__(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        response = self.get_response(request)
        if _OAUTH_POPUP_PATH_RE.match(request.path):
            response.headers["Cross-Origin-Opener-Policy"] = "unsafe-none"
        return response
