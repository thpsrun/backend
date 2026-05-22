import logging

from accounts.oauth_login import (
    _LOGIN_COMPLETE_URL_PATH,
)
from accounts.oauth_login import (
    write_intent as write_login_intent,
)
from allauth.socialaccount.adapter import get_adapter as get_socialaccount_adapter
from allauth.socialaccount.providers.base.constants import AuthProcess
from django.conf import settings
from django.http import HttpRequest, HttpResponseRedirect
from ninja import Router, Status

from api.csrf import enforce_csrf
from api.rate_limiting import auth_rate_limit
from api.v1.schemas.auth import OAuthLoginInitiateResponse
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()


def _log_event(
    event: str,
    request: HttpRequest,
    **fields,
) -> None:
    extra = {
        "event": event,
        "ip": request.META.get("REMOTE_ADDR"),
        "ua": request.META.get("HTTP_USER_AGENT", "")[:200],
        **fields,
    }
    logger.info("auth.event", extra=extra)


@router.post(
    "/oauth-login/{provider}",
    response={
        200: OAuthLoginInitiateResponse,
        400: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Initiate OAuth Login",
    description=(
        "Returns a provider authorize URL for logging into an existing account via OAuth. "
        "Open the URL in a popup; once the provider redirects back, the backend logs the "
        "user in (existing account) or surfaces a `no_link` / `banned` error, then "
        "redirects the popup to a completion page that postMessages the result to the opener."
    ),
    auth=None,
)
@auth_rate_limit
def initiate_oauth_login(
    request: HttpRequest,
    provider: str,
) -> Status:
    enforce_csrf(request)

    if getattr(request.user, "is_authenticated", False):
        return Status(
            409,
            ErrorResponse(
                error="already_authenticated",
                details=None,
            ),
        )
    if provider not in settings.SOCIALACCOUNT_PROVIDERS:
        return Status(
            400,
            ErrorResponse(
                error="unsupported_provider",
                details=None,
            ),
        )
    social_adapter = get_socialaccount_adapter(request)
    try:
        provider_obj = social_adapter.get_provider(request, provider)
    except Exception:
        return Status(
            400,
            ErrorResponse(
                error="unsupported_provider",
                details=None,
            ),
        )

    next_url = request.build_absolute_uri(
        f"{_LOGIN_COMPLETE_URL_PATH}?status=ok&provider={provider}",
    )
    redirect_response = provider_obj.redirect(
        request,
        process=AuthProcess.LOGIN,
        next_url=next_url,
        headless=True,
    )
    if not isinstance(redirect_response, HttpResponseRedirect):
        return Status(
            400,
            ErrorResponse(
                error="provider_redirect_failed",
                details=None,
            ),
        )
    authorize_url = redirect_response["Location"]
    write_login_intent(request, provider=provider)
    _log_event("oauth_login_initiated", request, provider=provider)
    return Status(
        200,
        OAuthLoginInitiateResponse(
            authorize_url=authorize_url,
        ),
    )
