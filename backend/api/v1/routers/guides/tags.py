from textwrap import dedent

from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from guides.models import Tags
from ninja import Router, Status
from ninja.responses import codes_4xx

from api.permissions import contributor_auth, public_auth
from api.v1.docs.tags import TAGS_ALL, TAGS_DELETE, TAGS_GET, TAGS_POST, TAGS_PUT
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.guides import (
    TagCreateSchema,
    TagListSchema,
    TagSchema,
    TagUpdateSchema,
)

router = Router()


@router.get(
    "/all",
    response={200: list[TagListSchema], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="List All Tags",
    description=dedent(
        """Returns a list of all available tags to categorize guides.

    Examples:
    - `/tags/all` - Get all tags
    """
    ),
    auth=public_auth,
    openapi_extra=TAGS_ALL,
)
def list_tags(
    request: HttpRequest,
) -> Status:
    tags = Tags.objects.all().order_by("name")
    return Status(200, [TagListSchema.model_validate(tag) for tag in tags])


@router.get(
    "/{slug}",
    response={200: TagSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get Tag by Slug",
    description=dedent(
        """Get a specific tag by its slug.

    Supported Parameters:
    - `slug` (str): URL-friendly tag identifier

    Examples:
    - `/tags/tricks` - Get the "Tricks" tag
    - `/tags/glitches` - Get the "Glitches" tag
    """
    ),
    auth=public_auth,
    openapi_extra=TAGS_GET,
)
def get_tag(
    request: HttpRequest,
    slug: str,
) -> Status:
    tag = Tags.objects.filter(slug__iexact=slug).first()
    if not tag:
        return Status(404, ErrorResponse(
            error=f"Tag with slug '{slug}' not found",
            details=None,
        ))

    return Status(200, TagSchema.model_validate(tag))


@router.post(
    "/",
    response={200: TagSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Create Tag",
    description=dedent(
        """Creates a brand new tag for categorizing guides.

    REQUIRES CONTRIBUTOR ACCESS OR HIGHER.

    Request Body:
    - `name` (str): Name of the tag
    - `description` (str): Description of what this tag represents
    """
    ),
    auth=contributor_auth,
    openapi_extra=TAGS_POST,
)
def create_tag(
    request: HttpRequest,
    data: TagCreateSchema,
) -> Status:
    existing_tag = Tags.objects.filter(name__iexact=data.name).first()
    if existing_tag:
        return Status(400, ErrorResponse(
            error="Tag With Slug Already Exists",
            details={"slug": existing_tag.slug},
        ))

    try:
        tag = Tags.objects.create(
            name=data.name,
            description=data.description,
        )
        return Status(200, TagSchema.model_validate(tag))
    except Exception as e:
        return Status(500, ErrorResponse(
            error="Tag Creation Failed",
            details={"exception": str(e)},
        ))


@router.put(
    "/{slug}",
    response={200: TagSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Update Tag",
    description=dedent(
        """Update an existing tag.

    REQUIRES CONTRIBUTOR ACCESS OR HIGHER.

    Supported Parameters:
    - `slug` (str): Tag slug to update

    Request Body:
    - `name` (str | None): Updated tag name
    - `slug` (str | None): Updated URL-friendly slug
    - `description` (str | None): Updated tag description
    """
    ),
    auth=contributor_auth,
    openapi_extra=TAGS_PUT,
)
def update_tag(
    request: HttpRequest,
    slug: str,
    data: TagUpdateSchema,
) -> Status:
    tag = Tags.objects.filter(slug__iexact=slug).first()
    if not tag:
        return Status(404, ErrorResponse(
            error=f"Tag with slug '{slug}' not found",
            details=None,
        ))

    try:
        with transaction.atomic():
            if data.name is not None:
                tag.name = data.name

            if data.slug is not None:
                existing_tag = (
                    Tags.objects.filter(slug__iexact=data.slug)
                    .exclude(pk=tag.pk)
                    .first()
                )
                if existing_tag:
                    return Status(400, ErrorResponse(
                        error=f"A tag with slug '{data.slug}' already exists",
                        details={"slug": data.slug},
                    ))
                tag.slug = data.slug

            if data.description is not None:
                tag.description = data.description

            tag.save()
            return Status(200, TagSchema.model_validate(tag))

    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to update tag",
            details={"exception": str(e)},
        ))


@router.delete(
    "/{slug}",
    response={200: dict[str, str], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Delete Tag",
    description=dedent(
        """Delete a tag.

    REQUIRES CONTRIBUTOR ACCESS OR HIGHER.

    Supported Parameters:
    - `slug` (str): Unique ID or the slug of the tag to remove.
    """
    ),
    auth=contributor_auth,
    openapi_extra=TAGS_DELETE,
)
def delete_tag(
    request: HttpRequest,
    slug: str,
) -> Status:
    tag = Tags.objects.filter(Q(slug__iexact=slug) | Q(pk__iexact=slug)).first()
    if not tag:
        return Status(404, ErrorResponse(
            error=f"Tag with ID/slug '{slug}' not found",
            details=None,
        ))

    try:
        name = tag.name
        tag.delete()
        return Status(200, {"message": f"Tag '{name}' deleted successfully"})
    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to delete tag",
            details={"exception": str(e)},
        ))
