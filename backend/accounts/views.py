from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from accounts.oauth_connect import (
    clear_intent as clear_connect_intent,
)
from accounts.oauth_connect import (
    peek_intent as peek_connect_intent,
)
from accounts.oauth_reauth import (
    clear_intent as clear_reauth_intent,
)
from accounts.oauth_reauth import (
    peek_intent as peek_reauth_intent,
)

ALLOWED_STATUSES = frozenset({"ok", "error", "cancelled"})

REAUTH_ALLOWED_REASONS = frozenset(
    {
        "not_authenticated",
        "user_mismatch",
        "intent_expired",
        "provider_mismatch",
        "account_mismatch",
        "provider_error",
    }
)

CONNECT_ALLOWED_REASONS = frozenset(
    {
        "not_authenticated",
        "user_mismatch",
        "intent_expired",
        "provider_mismatch",
        "already_linked",
        "account_taken",
        "provider_error",
    }
)

CONNECT_ALLOWED_PROVIDERS = frozenset(settings.SOCIALACCOUNT_PROVIDERS.keys())


@require_GET
def oauth_reauth_complete(
    request: HttpRequest,
) -> HttpResponse:
    raw_status = request.GET.get("status", "")
    raw_reason = request.GET.get("reason", "")
    status = raw_status if raw_status in ALLOWED_STATUSES else "error"
    reason = raw_reason if raw_reason in REAUTH_ALLOWED_REASONS else ""
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
def oauth_connect_complete(
    request: HttpRequest,
) -> HttpResponse:
    raw_status = request.GET.get("status", "")
    raw_reason = request.GET.get("reason", "")
    raw_provider = request.GET.get("provider", "")
    status = raw_status if raw_status in ALLOWED_STATUSES else "error"
    reason = raw_reason if raw_reason in CONNECT_ALLOWED_REASONS else ""
    provider = raw_provider if raw_provider in CONNECT_ALLOWED_PROVIDERS else ""
    return render(
        request,
        "account/oauth_connect_complete.html",
        {
            "status": status,
            "reason": reason,
            "provider": provider,
            "frontend_origin": settings.FRONTEND_URL,
        },
    )


@require_GET
def socialaccount_login_cancelled(
    request: HttpRequest,
) -> HttpResponse:
    if peek_connect_intent(request) is not None:
        clear_connect_intent(request)
        return HttpResponseRedirect(
            f"{reverse('oauth_connect_complete')}?status=cancelled",
        )
    if peek_reauth_intent(request) is not None:
        clear_reauth_intent(request)
        return HttpResponseRedirect(
            f"{reverse('oauth_reauth_complete')}?status=cancelled",
        )
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}/login/cancelled/")


@require_GET
def socialaccount_login_error(
    request: HttpRequest,
) -> HttpResponse:
    if peek_connect_intent(request) is not None:
        clear_connect_intent(request)
        return HttpResponseRedirect(
            f"{reverse('oauth_connect_complete')}?status=error&reason=provider_error",
        )
    if peek_reauth_intent(request) is not None:
        clear_reauth_intent(request)
        return HttpResponseRedirect(
            f"{reverse('oauth_reauth_complete')}?status=error&reason=provider_error",
        )
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}/login/error/")
