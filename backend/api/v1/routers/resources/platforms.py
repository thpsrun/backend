from textwrap import dedent
from typing import Annotated

from django.db.models import Q
from django.http import HttpRequest
from ninja import Query, Router, Status
from ninja.responses import codes_4xx
from pydantic import Field
from srl.models import Platforms

from api.permissions import admin_auth, moderator_auth, public_auth
from api.v1.docs.platforms import (
    PLATFORMS_ALL,
    PLATFORMS_DELETE,
    PLATFORMS_GET,
    PLATFORMS_POST,
    PLATFORMS_PUT,
)
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.platforms import (
    PlatformCreateSchema,
    PlatformSchema,
    PlatformUpdateSchema,
)
from api.v1.utils import get_or_generate_id

router = Router()


@router.get(
    "/all",
    response={200: list[PlatformSchema], 500: ErrorResponse},
    summary="Get All Platforms",
    description=dedent(
        """Retrieve all platforms within the `Platforms` object, ordered by name.

    **Supported Parameters:**
    - `limit` (int | None): Results per page (default 50, max 100)
    - `offset`(int | None): Results to skip (default 0)

    **Examples:**
    - `/platforms/all` - Get all platforms
    - `/platforms/all?limit=20` - Get first 20 platforms
    - `/platforms/all?limit=10&offset=10` - Get platforms 11-20
    """
    ),
    auth=public_auth,
    openapi_extra=PLATFORMS_ALL,
)
def get_all_platforms(
    request: HttpRequest,
    limit: Annotated[
        int,
        Query,
        Field(
            ge=1,
            le=100,
            description="Maximum number of returned objects (default 50, less than 100)",
        ),
    ] = 50,
    offset: Annotated[int, Query, Field(ge=0, description="Offset from 0")] = 0,
) -> Status:
    try:
        platforms = Platforms.objects.all().order_by("name")[offset : offset + limit]
        return Status(200, [PlatformSchema.model_validate(platform) for platform in platforms])
    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to retrieve platforms",
            details={"exception": str(e)},
        ))


@router.get(
    "/{id}",
    response={200: PlatformSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get Platform by ID",
    description=dedent(
        """Retrieve a single platform by its ID or its slug.

    **Supported Parameters:**
    - `id` (str): Unique ID of the platform being queried.

    **Examples:**
    - `/platforms/8gej2n3z` - Get platform by ID
    - `/platforms/pc` - Get platform by slug
    """
    ),
    auth=public_auth,
    openapi_extra=PLATFORMS_GET,
)
def get_platform(
    request: HttpRequest,
    id: str,
) -> Status:
    if len(id) > 15:
        return Status(400, ErrorResponse(
            error="ID must be 15 characters or less",
            details=None,
        ))

    try:
        platform = Platforms.objects.filter(
            Q(id__iexact=id) | Q(slug__iexact=id)
        ).first()
        if not platform:
            return Status(404, ErrorResponse(
                error="Platform ID does not exist",
                details=None,
            ))

        return Status(200, PlatformSchema.model_validate(platform))

    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to retrieve platform",
            details={"exception": str(e)},
        ))


@router.post(
    "/",
    response={201: PlatformSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Create Platform",
    description=dedent(
        """Creates a brand new platform.

    **REQUIRES MODERATOR ACCESS OR HIGHER.**

    **Request Body:**
    - `id` (str): Unique ID (usually based on SRC) of the platform being created.
    - `name` (str): Platform name (e.g., "PlayStation 2") being created.
    - `slug` (str): URL-friendly version (e.g., "playstation-2").
    """
    ),
    auth=moderator_auth,
    openapi_extra=PLATFORMS_POST,
)
def create_platform(
    request: HttpRequest,
    platform_data: PlatformCreateSchema,
) -> Status:
    try:
        try:
            platform_id = get_or_generate_id(
                platform_data.id,
                lambda id: Platforms.objects.filter(id=id).exists(),
            )
        except ValueError as e:
            return Status(400, ErrorResponse(
                error="ID Already Exists",
                details={"exception": str(e)},
            ))

        create_data = platform_data.model_dump()
        create_data["id"] = platform_id
        platform = Platforms.objects.create(**create_data)
        return Status(201, PlatformSchema.model_validate(platform))

    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to create platform",
            details={"exception": str(e)},
        ))


@router.put(
    "/{id}",
    response={200: PlatformSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Update Platform",
    description=dedent(
        """Updates the platform based on its unique ID.

    **REQUIRES MODERATOR ACCESS OR HIGHER.**

    **Supported Parameters:**
    - `id (str): Unique ID (usually based on SRC) of the platform.

    **Request Body:**
    - `name` (str | None): Platform name (e.g., "PlayStation 2") being created.
    - `slug` (str | None): URL-friendly version (e.g., "playstation-2").
    """
    ),
    auth=moderator_auth,
    openapi_extra=PLATFORMS_PUT,
)
def update_platform(
    request: HttpRequest,
    id: str,
    platform_data: PlatformUpdateSchema,
) -> Status:
    try:
        platform = Platforms.objects.filter(id__iexact=id).first()
        if not platform:
            return Status(404, ErrorResponse(
                error="Platform does not exist",
                details=None,
            ))

        update_data = platform_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(platform, field, value)

        platform.save()
        return Status(200, PlatformSchema.model_validate(platform))

    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to update platform",
            details={"exception": str(e)},
        ))


@router.delete(
    "/{id}",
    response={200: dict[str, str], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Delete Platform",
    description=dedent(
        """Deletes the selected platform based on its ID.

    **REQUIRES ADMIN ACCESS.**

    **Supported Parameters:**
    - `id (str): Unique ID (usually based on SRC) of the platform being deleted.
    """
    ),
    auth=admin_auth,
    openapi_extra=PLATFORMS_DELETE,
)
def delete_platform(
    request: HttpRequest,
    id: str,
) -> Status:
    try:
        platform = Platforms.objects.filter(id__iexact=id).first()
        if not platform:
            return Status(404, ErrorResponse(
                error="Platform does not exist",
                details=None,
            ))

        name = platform.name
        platform.delete()
        return Status(200, {"message": f"Platform '{name}' deleted successfully"})

    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to delete platform",
            details={"exception": str(e)},
        ))
