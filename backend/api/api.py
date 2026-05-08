import logging
from textwrap import dedent
from typing import Any

import sentry_sdk
from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI, Redoc
from ninja.errors import ValidationError

from api.v1.routers.auth.admin_api_keys import router as admin_api_keys_router
from api.v1.routers.auth.api_keys import router as api_keys_router
from api.v1.routers.auth.bot_session import router as bot_session_router
from api.v1.routers.auth.me import router as me_router
from api.v1.routers.auth.pfp import router as pfp_router
from api.v1.routers.auth.profile_bg import router as profile_bg_router
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
from api.v1.routers.resources.categories import router as categories_router
from api.v1.routers.resources.countries import router as countries_router
from api.v1.routers.resources.games import router as games_router
from api.v1.routers.resources.levels import router as levels_router
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
        - If you want an API key, contact ThePackle on the thps.run Discord.

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
                "name": "Website",
                "description": "Specific endpoints related to how the frontend operates.",
            },
            {
                "name": "Reference",
                "description": "Static reference data lookups that do not require authentication.",
            },
            {
                "name": "Auth - Account",
                "description": "Account registration endpoints.",
            },
            {
                "name": "Auth - Profile",
                "description": "Read, update, and delete the authenticated player's profile.",
            },
            {
                "name": "Auth - Profile Picture",
                "description": "Upload the authenticated player's profile picture.",
            },
            {
                "name": "Auth - Profile Background",
                "description": "Upload and remove the authenticated player's profile background.",
            },
            {
                "name": "Auth - SRC API Key",
                "description": "Store and remove the authenticated player's Speedrun.com API key.",
            },
            {
                "name": "Auth - Submissions",
                "description": "Run submission and moderation workflows.",
            },
            {
                "name": "Auth - Sync Logs",
                "description": "Administrative sync log endpoints.",
            },
            {
                "name": "Auth - API Keys",
                "description": "Self-service endpoints for managing the "
                "authenticated user's API keys.",
            },
            {
                "name": "Auth - Admin API Keys",
                "description": "Superuser-only endpoints for inspecting and "
                "revoking any user's API keys.",
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
        HttpResponse: Standardized validation error response.
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
    """Handle invalid `?embed=...` values raised from `parse_embeds`."""
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
                "remote_addr": request.META.get("REMOTE_ADDR", "Unknown"),
            },
        )

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

    error_data = ErrorResponse(
        error="An unexpected error occurred",
        details={
            "exception": str(exc),
            "type": type(exc).__name__,
        },
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
    return {
        "status": "healthy",
        "version": ninja_api.version,
        "message": "thps.run API is operational and is accepting requests.",
    }


ninja_api.add_router("/games", games_router, tags=["Games"])
ninja_api.add_router("/categories", categories_router, tags=["Categories"])
ninja_api.add_router("/levels", levels_router, tags=["Levels"])
ninja_api.add_router("/platforms", platforms_router, tags=["Platforms"])
ninja_api.add_router("/players", players_router, tags=["Players"])
ninja_api.add_router("/variables", variables_router, tags=["Variables"])
ninja_api.add_router("/runs", runs_router, tags=["Runs"])
ninja_api.add_router("/streams", streams_router, tags=["Streams"])

ninja_api.add_router("/guides", guides_router, tags=["Guides"])
ninja_api.add_router("/tags", tags_router, tags=["Tags"])

ninja_api.add_router("/website", website_router, tags=["Website"])
ninja_api.add_router("/website", lbs_page_router, tags=["Website"])
ninja_api.add_router("/website", leaderboard_page_router, tags=["Website"])
ninja_api.add_router(
    "/pointslb/history", leaderboard_history_router, tags=["Leaderboards"]
)
ninja_api.add_router("/website", navbar_router, tags=["Website"])
ninja_api.add_router("", history_router, tags=["Website"])

ninja_api.add_router("/countries", countries_router, tags=["Reference"])

ninja_api.add_router("/auth", register_router, tags=["Auth - Account"])
ninja_api.add_router("/auth", me_router, tags=["Auth - Profile"])
ninja_api.add_router("/auth", pfp_router, tags=["Auth - Profile Picture"])
ninja_api.add_router("/auth", profile_bg_router, tags=["Auth - Profile Background"])
ninja_api.add_router("/auth", submissions_router, tags=["Auth - Submissions"])
ninja_api.add_router("/auth", api_keys_router, tags=["Auth - API Keys"])
ninja_api.add_router("/auth", admin_api_keys_router, tags=["Auth - Admin API Keys"])

ninja_api.add_router("/auth", sync_logs_router, tags=["Auth - Sync Logs"])
ninja_api.add_router("/auth", src_key_router, tags=["Auth - SRC API Key"])
ninja_api.add_router("/auth", bot_session_router, tags=["Auth - SRC Sessions"])
