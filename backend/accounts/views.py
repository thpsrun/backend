from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from accounts.oauth_reauth import clear_intent, read_intent

ALLOWED_STATUSES = frozenset({"ok", "error", "cancelled"})
ALLOWED_REASONS = frozenset(
    {
        "not_authenticated",
        "user_mismatch",
        "intent_expired",
        "provider_mismatch",
        "account_mismatch",
        "provider_error",
    }
)


@require_GET
def oauth_reauth_complete(
    request: HttpRequest,
) -> HttpResponse:
    raw_status = request.GET.get("status", "")
    raw_reason = request.GET.get("reason", "")
    status = raw_status if raw_status in ALLOWED_STATUSES else "error"
    reason = raw_reason if raw_reason in ALLOWED_REASONS else ""
    return render(
        request,
        "account/oauth_reauth_complete.html",
        {
            "status": status,
            "reason": reason,
            "frontend_origin": settings.FRONTEND_URL,
        },
    )


@require_GET
def oauth_reauth_cancelled(
    request: HttpRequest,
) -> HttpResponse:
    if read_intent(request) is None:
        return HttpResponseRedirect(f"{settings.FRONTEND_URL}/login/cancelled/")
    clear_intent(request)
    base = reverse("oauth_reauth_complete")
    return HttpResponseRedirect(f"{base}?status=cancelled")


@require_GET
def oauth_reauth_error(
    request: HttpRequest,
) -> HttpResponse:
    if read_intent(request) is None:
        return HttpResponseRedirect(f"{settings.FRONTEND_URL}/login/error/")
    clear_intent(request)
    base = reverse("oauth_reauth_complete")
    return HttpResponseRedirect(f"{base}?status=error&reason=provider_error")
