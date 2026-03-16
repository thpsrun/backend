from textwrap import dedent
from typing import Annotated, Any

from django.http import HttpRequest
from ninja import Query, Router, Status
from ninja.responses import codes_4xx
from pydantic import Field

from api.permissions import public_auth
from api.v1.docs.website import MAIN_PAGE_GET
from api.v1.routers.utils import get_cached_embed
from api.v1.schemas.base import ErrorResponse

router = Router()


@router.get(
    "/main",
    response={200: dict[str, Any], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get Main Page Data",
    description=dedent(
        """
    Get aggregated data for the website main page including latest world records,
    personal bests, and current records for featured categories.

    **Supported Embeds:**
    - `latest-wrs`: Latest 5 world records within the database.
    - `latest-pbs`: Latest 5 personal bests (excluding WRs) within the database.
    - `records`: Current WRs for featured categories.

    **Supported Parameters:**
    - `embed`: Comma-separated list of data types to include (required)

    **Examples:**
    - `/website/main?embed=latest-wrs,latest-pbs` - Recent activity
    - `/website/main?embed=records` - Current world records
    - `/website/main?embed=latest-wrs,latest-pbs,records` - All data
    """
    ),
    auth=public_auth,
    openapi_extra=MAIN_PAGE_GET,
)
def get_main_page_data(
    request: HttpRequest,
    embed: Annotated[
        str | None,
        Query,
        Field(description="Comma-separated embed types"),
    ] = None,
) -> Status:
    if not embed:
        return Status(400, ErrorResponse(
            error="Must specify embed types to retrieve",
            details={"valid_embed_types": ["latest-wrs", "latest-pbs", "records"]},
        ))

    embed_fields = [field.strip() for field in embed.split(",") if field.strip()]
    valid_embed_types = {"latest-wrs", "latest-pbs", "records"}
    invalid_embeds = [field for field in embed_fields if field not in valid_embed_types]

    if invalid_embeds:
        return Status(400, ErrorResponse(
            error=f"Invalid embed type(s): {', '.join(invalid_embeds)}",
            details={"valid_embed_types": list(valid_embed_types)},
        ))

    try:
        response_data = {}

        if "latest-wrs" in embed_fields:
            response_data["latest_wrs"] = get_cached_embed("latest-wrs")

        if "latest-pbs" in embed_fields:
            response_data["latest_pbs"] = get_cached_embed("latest-pbs")

        if "records" in embed_fields:
            response_data["records"] = get_cached_embed("records")

        return Status(200, response_data)
    except Exception as e:
        return Status(500, ErrorResponse(
            error="Server error!",
            details={"exception": str(e)},
        ))
