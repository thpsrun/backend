import logging
from textwrap import dedent
from typing import Any

import sentry_sdk
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI, Redoc, Router
from ninja.errors import ValidationError

from api.client_ip import client_ip
from api.v1.routers.auth.admin_api_keys import router as admin_api_keys_router
from api.v1.routers.auth.admin_game_display import router as admin_game_display_router
from api.v1.routers.auth.admin_navbar import router as admin_navbar_router
from api.v1.routers.auth.admin_users import router as admin_users_router
from api.v1.routers.auth.api_keys import router as api_keys_router
from api.v1.routers.auth.bot_session import router as bot_session_router
from api.v1.routers.auth.data_export import router as data_export_router
from api.v1.routers.auth.me import router as me_router
from api.v1.routers.auth.me_auth import router as me_auth_router
from api.v1.routers.auth.me_email import router as me_email_router
from api.v1.routers.auth.oauth_login import router as oauth_login_router
from api.v1.routers.auth.oauth_signup import router as oauth_signup_router
from api.v1.routers.auth.pfp import router as pfp_router
from api.v1.routers.auth.profile_bg import router as profile_bg_router
from api.v1.routers.auth.reconcile import router as reconcile_router
from api.v1.routers.auth.register import router as register_router
from api.v1.routers.auth.src_key import router as src_key_router
from api.v1.routers.auth.submissions import router as submissions_router
from api.v1.routers.auth.sync_logs import router as sync_logs_router
from api.v1.routers.guides.guides import router as guides_router
from api.v1.routers.guides.tags import router as tags_router
from api.v1.routers.pages.history import router as history_router
from api.v1.routers.pages.home import router as website_router
from api.v1.routers.pages.lbs import router as lbs_page_router
from api.v1.routers.pages.leaderboard import router as leaderboard_page_router
from api.v1.routers.pages.leaderboard_history import (
    router as leaderboard_history_router,
)
from api.v1.routers.pages.navbar import router as navbar_router
from api.v1.routers.resources.awards import router as awards_router
from api.v1.routers.resources.categories import router as categories_router
from api.v1.routers.resources.countries import router as countries_router
from api.v1.routers.resources.game_audit import router as game_audit_router
from api.v1.routers.resources.games import router as games_router
from api.v1.routers.resources.levels import router as levels_router
from api.v1.routers.resources.notifications import router as notifications_router
from api.v1.routers.resources.platforms import router as platforms_router
from api.v1.routers.resources.players import router as players_router
from api.v1.routers.resources.runs import router as runs_router
from api.v1.routers.resources.streams import router as streams_router
from api.v1.routers.resources.variables import router as variables_router
from api.v1.routers.utils.embeds import InvalidEmbedsError
from api.v1.schemas.base import ErrorResponse, ValidationErrorResponse

logger = logging.getLogger(__name__)

ninja_api: NinjaAPI = NinjaAPI(
    docs=Redoc(
        settings={
            "persistentAuthorization": False,
        }
    ),
    title="thps.run API",
    version="1.0.0",
    description=dedent("""
    This API provides access to the thps.run API and documents its functionality.

    AUTHENTICATION:
    - GET requests are public. No API key is required to access this information.
    - All other HTTP requests will require a valid API key in the X-API-Key header to proceed.
        - API keys can be acquired in your account settings.

    QUERYING:
    Depending on the endpoint chosen, you will be able to further refine queries to reduce the
    amount of data sent to your application. Here is an example:
    - `/api/v1/guides/all?query=thps4`: All guides belonging to THPS4 will be returned.

    EMBEDDING:
    Most endpoints support an `embed` query parameter that further defines and enhances related
    data. By default, if an eligible embed is not used, then the unique ID of that object will
    be given. However, by specifying an embed, you will get more in-depth information; this will
    reduce the number of requests you have to send! Here is an example:

    - `/api/v1/runs/abcd1234?embed=categories,game`: Returns information on the specific run AND
    embeds all of the metdata related to its selected category and game.

    RATE LIMITING:
    This API uses rate limits. Unauthenticated API sessions (e.g. GET) have a limit of 200/minute.
    The rate limit is increased depending on the role your API key is assigned to.

    API KEYS:
    By default, almost all GET endpoints are accessible publicly. An API Key is required for all
    non-GET HTTP methods AND in designated endpoints (e.g. `/api/v1/users/tonyhawk/preferences`).

    ERROR HANDLING:
    This section details the normal responses you will receive. Specific endpoints may have more
    response codes. Normal response codes (e.g. 2XX, 4XX, 500, etc.) are used. If more are added,
    then they will appear in this documentation.
    """),
    docs_url="/docs",
    openapi_url="/openapi.json",
    openapi_extra={
        "tags": [
            {
                "name": "Categories",
                "description": "Specific endpoints related to categories.",
            },
            {
                "name": "Games",
                "description": "Specific endpoints related to games.",
            },
            {
                "name": "Levels",
                "description": "Specific endpoints related to levels.",
            },
            {
                "name": "Platforms",
                "description": "Specific endpoints related to platforms.",
            },
            {
                "name": "Players",
                "description": "Specific endpoints related to players.",
            },
            {
                "name": "Runs",
                "description": "Specific endpoints related to runs... Which might be all lol.",
            },
            {
                "name": "Streams",
                "description": "Specific endpoints related to streams appearing in the API.",
            },
            {
                "name": "Variables",
                "description": "Specific endpoints related to variables and variable-value pairs.",
            },
            {
                "name": "Guides",
                "description": "Specific endpoints related to the Guides system of the website.",
            },
            {
                "name": "Tags",
                "description": "Specified endpoints related to the tags system.",
            },
            {
                "name": "Leaderboards",
                "description": "Specific endpoints related to the points leaderboard history.",
            },
            {
                "name": "Reference",
                "description": "Static reference data lookups that do not require authentication.",
            },
            {
                "name": "Submissions",
                "description": "Run submission and moderation workflows.",
            },
            {
                "name": "API Keys",
                "description": "Self-service endpoints for managing the "
                "authenticated user's API keys.",
            },
        ],
        "x-tagGroups": [
            {
                "name": "Resources",
                "tags": [
                    "Games",
                    "Categories",
                    "Levels",
                    "Variables",
                    "Runs",
                    "Players",
                    "Platforms",
                    "Streams",
                    "Reference",
                ],
            },
            {
                "name": "Site",
                "tags": [
                    "Leaderboards",
                    "Guides",
                    "Tags",
                ],
            },
            {
                "name": "Authenticated User",
                "tags": [
                    "Submissions",
                    "API Keys",
                ],
            },
        ],
    },
)


@ninja_api.exception_handler(ValidationError)
def validation_exception_handler(
    request: HttpRequest,
    exc: ValidationError,
) -> HttpResponse:
    """Handle Pydantic validation errors.

    This provides consistent validation error responses across all endpoints.

    Arguments:
        request: The HTTP request that caused the error.
        exc: The validation exception from Pydantic.

    Returns:
        HttpResponse: Standardized validation error response
    """
    return ninja_api.create_response(
        request,
        ValidationErrorResponse(
            error="Request validation failed",
            validation_errors=exc.errors,
        ).model_dump(),
        status=422,
    )


@ninja_api.exception_handler(InvalidEmbedsError)
def invalid_embeds_exception_handler(
    request: HttpRequest,
    exc: InvalidEmbedsError,
) -> HttpResponse:
    """Handle invalid `?embed=...` values raised from `parse_embeds`"""
    return ninja_api.create_response(
        request,
        ErrorResponse(
            error=str(exc),
            details={"valid_embeds": sorted(exc.valid)},
        ).model_dump(),
        status=400,
    )


@ninja_api.exception_handler(Exception)
def global_exception_handler(
    request: HttpRequest,
    exc: Exception,
) -> HttpResponse:
    """Handle unexpected server errors.

    Provides a consistent error response for unexpected exceptions and logs them to Sentry.

    Arguments:
        request: The HTTP request that caused the error.
        exc: The unexpected exception (e.g. server errors).

    Returns:
        HttpResponse: Object with a 500 status code denoting a server error has occurred.
    """

    with sentry_sdk.push_scope() as scope:
        scope.set_context(
            "request",
            {
                "path": request.path,
                "method": request.method,
                "user_agent": request.META.get("HTTP_USER_AGENT", "Unknown"),
                "remote_addr": client_ip(request),
            },
        )

        # Only record whether a key was present, never the key itself, so credentials
        # cannot leak into Sentry.
        api_key_header = request.headers.get("X-API-Key")
        if api_key_header:
            scope.set_tag("has_api_key", "true")
        else:
            scope.set_tag("has_api_key", "false")

        sentry_sdk.capture_exception(exc)

    logger.error(
        f"Unhandled exception in API: {exc}",
        exc_info=True,
        extra={
            "path": request.path,
            "method": request.method,
            "user_agent": request.META.get("HTTP_USER_AGENT", "Unknown"),
        },
    )

    details: dict[str, Any] | None = None
    if settings.DEBUG:
        details = {
            "exception": str(exc),
            "type": type(exc).__name__,
        }

    error_data = ErrorResponse(
        error="An unexpected error occurred",
        details=details,
    ).model_dump()

    return ninja_api.create_response(
        request,
        error_data,
        status=500,
    )


@ninja_api.get(
    "/health",
    response=dict[str, Any],
    summary="API Health Check",
    description=dedent("""A simple API endpoint that returns health information.

    This endpoint returns basic API status and versioning information. This is useful for
    monitoring and ensuring the API is accessible and is responding to requests.
    """),
)
def health_check(
    request: HttpRequest,
) -> dict[str, Any]:
    """Return a static health payload for uptime monitoring."""
    return {
        "status": "healthy",
        "version": ninja_api.version,
        "message": "thps.run API is operational and is accepting requests.",
    }


def _hide_from_schema(
    router: Router,
) -> Router:
    """Strip a router's operations from the OpenAPI docs while leaving them routable.

    Used for frontend-internal endpoints (auth flows, admin tooling, page data) that
    are not part of the public API contract documented at /docs.
    """
    for path_view in router.path_operations.values():
        for op in path_view.operations:
            op.include_in_schema = False

    return router


ninja_api.add_router("/games", games_router, tags=["Games"])
ninja_api.add_router("/games", game_audit_router, tags=["Games"])
ninja_api.add_router("/categories", categories_router, tags=["Categories"])
ninja_api.add_router("/levels", levels_router, tags=["Levels"])
ninja_api.add_router(
    "/notifications", _hide_from_schema(notifications_router), tags=["Notifications"]
)
ninja_api.add_router("/platforms", platforms_router, tags=["Platforms"])
ninja_api.add_router("/players", players_router, tags=["Players"])
ninja_api.add_router("/variables", variables_router, tags=["Variables"])
ninja_api.add_router("/runs", runs_router, tags=["Runs"])
ninja_api.add_router("/streams", streams_router, tags=["Streams"])

ninja_api.add_router("/guides", guides_router, tags=["Guides"])
ninja_api.add_router("/tags", tags_router, tags=["Tags"])

ninja_api.add_router("/website", _hide_from_schema(website_router), tags=["Website"])
ninja_api.add_router("/website", _hide_from_schema(lbs_page_router), tags=["Website"])
ninja_api.add_router(
    "/website", _hide_from_schema(leaderboard_page_router), tags=["Website"]
)
ninja_api.add_router(
    "/pointslb/history", leaderboard_history_router, tags=["Leaderboards"]
)
ninja_api.add_router("/website", _hide_from_schema(navbar_router), tags=["Website"])
ninja_api.add_router("", _hide_from_schema(history_router), tags=["Website"])

ninja_api.add_router("/countries", countries_router, tags=["Reference"])
ninja_api.add_router("/awards", awards_router, tags=["Reference"])

ninja_api.add_router("/auth", _hide_from_schema(register_router), tags=["Account"])
ninja_api.add_router("/auth", _hide_from_schema(oauth_signup_router), tags=["Account"])
ninja_api.add_router("/auth", _hide_from_schema(oauth_login_router), tags=["Account"])
ninja_api.add_router("/auth", _hide_from_schema(me_router), tags=["Profile"])
ninja_api.add_router(
    "/auth", _hide_from_schema(me_auth_router), tags=["Auth Self-Service"]
)
ninja_api.add_router(
    "/auth", _hide_from_schema(me_email_router), tags=["Email Management"]
)
ninja_api.add_router(
    "/auth", _hide_from_schema(data_export_router), tags=["Data Export"]
)
ninja_api.add_router("/auth", _hide_from_schema(pfp_router), tags=["Profile Picture"])
ninja_api.add_router(
    "/auth", _hide_from_schema(profile_bg_router), tags=["Profile Background"]
)
ninja_api.add_router("/auth", submissions_router, tags=["Submissions"])
ninja_api.add_router("/auth", api_keys_router, tags=["API Keys"])
ninja_api.add_router(
    "/auth", _hide_from_schema(admin_api_keys_router), tags=["Admin API Keys"]
)
ninja_api.add_router(
    "/auth",
    _hide_from_schema(admin_game_display_router),
    tags=["Admin Game Display"],
)
ninja_api.add_router(
    "/auth", _hide_from_schema(admin_navbar_router), tags=["Admin Navbar"]
)
ninja_api.add_router(
    "/auth", _hide_from_schema(admin_users_router), tags=["Admin Users"]
)

ninja_api.add_router("/auth", _hide_from_schema(sync_logs_router), tags=["Sync Logs"])
ninja_api.add_router("/auth", _hide_from_schema(reconcile_router), tags=["Reconcile"])
ninja_api.add_router("/auth", _hide_from_schema(src_key_router), tags=["SRC API Key"])
ninja_api.add_router(
    "/auth", _hide_from_schema(bot_session_router), tags=["SRC Sessions"]
)
