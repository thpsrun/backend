from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from auditlog.context import clear_actor, set_actor


class AuditActorMiddleware:
    """Populate the audit actor for Django session-auth views (/illiad/, /_allauth/)."""

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        self.get_response = get_response

    def __call__(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        try:
            response = self.get_response(request)
            if not request.path.startswith("/api/"):
                raw_user = getattr(request, "user", None)
                user = (
                    raw_user
                    if raw_user is not None
                    and getattr(raw_user, "is_authenticated", False)
                    else None
                )
                if user is not None:
                    label = getattr(user, "username", "") or ""
                    set_actor(user=user, api_key=None, label=label[:128])
            return response
        finally:
            clear_actor()
