import logging
from typing import Annotated

from django.http import HttpRequest
from ninja import Query, Router, Status
from ninja.errors import HttpError
from srl.models import Awards

from api.permissions import public_read
from api.v1.schemas.awards import AwardListSchema
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()


@router.get(
    "/all",
    response={200: list[AwardListSchema], 500: ErrorResponse},
    summary="Get All Awards",
    description="""\
Retrieve all awards within the `Awards` object, ordered by name.

Supported Parameters:
- `limit` (int | None): Results per page (default 50, max 100)
- `offset` (int | None): Results to skip (default 0)

Examples:
- `/awards/all` - Get all awards
- `/awards/all?limit=20` - Get first 20 awards
- `/awards/all?limit=10&offset=10` - Get awards 11-20
""",
    auth=public_read(),
)
def get_all_awards(
    request: HttpRequest,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of returned objects (default 50, less than 100)",
        ),
    ] = 50,
    offset: Annotated[int, Query(ge=0, description="Offset from 0")] = 0,
) -> Status:
    try:
        awards = Awards.objects.all().order_by("name")[offset : offset + limit]
        return Status(
            200,
            [
                AwardListSchema(
                    id=award.id,
                    name=award.name,
                    description=award.description,
                    image=award.image.url if award.image else None,
                )
                for award in awards
            ],
        )
    except Exception:
        logger.exception("awards_list_failed")
        raise HttpError(500, "Internal Server Error")
