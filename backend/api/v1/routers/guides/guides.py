from typing import Annotated

from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from guides.models import Guides, Tags
from ninja import Query, Router, Status
from ninja.responses import codes_4xx
from srl.models.games import Games

from api.permissions import authed, public_read
from api.v1.routers.utils.resolvers import game_from_body, guide_from_path
from api.v1.routers.utils.embeds import parse_embeds
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.games import GameSchema
from api.v1.schemas.guides import (
    GuideCreateSchema,
    GuideListSchema,
    GuideSchema,
    GuideUpdateSchema,
    TagSchema,
)

router = Router()


@router.get(
    "/all",
    response={200: list[GuideListSchema], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="List All Guides",
    description="""\
Gets all guides within the database, with optional querying and embeds.

Query Parameters:
- `game` (str | None): Filter guides based on the game's slug or ID.
- `tag` (str | None): Filter guides based on the tag's slug or ID.
- `embed` (list | None): Comma-separated list of resources to embed.

Supported Embeds:
- `game`: Includes the metadata of the game the tag belongs to.
- `tags`: Include metadata of the tags belonging to this guide.
""",
    auth=public_read(),
)
def list_guides(
    request: HttpRequest,
    game: Annotated[str | None, Query(description="Filter by game slug")] = None,
    tag: Annotated[str | None, Query(description="Filter by tag slug")] = None,
    embed: Annotated[
        str | None, Query(description="Comma-separated embeds (game,tags)")
    ] = None,
) -> Status:
    embed_list = parse_embeds(embed, "guides")

    queryset = Guides.objects.all()

    if game:
        queryset = queryset.filter(
            Q(game__slug__iexact=game) | Q(game__id__iexact=game),
        )
    if tag:
        queryset = queryset.filter(
            Q(tags__slug__iexact=tag) | Q(tags__id__iexact=tag),
        )

    if "game" in embed_list:
        queryset = queryset.select_related("game")
    if "tags" in embed_list:
        queryset = queryset.prefetch_related("tags")

    result = []
    for guide in queryset:
        guide_data = GuideListSchema.model_validate(guide)

        if "game" in embed_list and guide.game:
            guide_data.game = GameSchema.model_validate(guide.game)
        if "tags" in embed_list:
            guide_data.tags = [
                TagSchema.model_validate(tag) for tag in guide.tags.all()
            ]

        result.append(guide_data)

    return Status(200, result)


@router.get(
    "/{slug}",
    response={200: GuideSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get Guide by Slug",
    description="""\
Get a specific guide by its slug.

Supported Parameters:
- `slug` (str): Simplified, URL friendly name of the guide.
- `embed` (list | None): Comma-separated list of resources to embed.

Supported Embeds:
- `game`: Includes the metadata of the game the tag belongs to.
- `tags`: Include metadata of the tags belonging to this guide.
""",
    auth=public_read(),
)
def get_guide(
    request: HttpRequest,
    slug: str,
    embed: Annotated[
        str | None, Query(description="Comma-separated embeds (game,tags)")
    ] = None,
) -> Status:
    embed_list = parse_embeds(embed, "guides")

    queryset = Guides.objects.filter(slug__iexact=slug)
    if "game" in embed_list:
        queryset = queryset.select_related("game")
    if "tags" in embed_list:
        queryset = queryset.prefetch_related("tags")

    guide = queryset.first()
    if not guide:
        return Status(
            404,
            ErrorResponse(
                error=f"Guide with slug '{slug}' not found",
                details=None,
            ),
        )

    return Status(200, GuideSchema.model_validate(guide))


@router.post(
    "/",
    response={200: GuideSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Create New Guide",
    description="""\
Creates a brand new guide.

REQUIRES CONTRIBUTOR ACCESS OR HIGHER.

Request Body:
- `title` (str): Name of the guide.
- `game_id` (str): Unique game ID or slug of the game this is associated with.
- `tag_ids` (list | None): List of tag IDs or their slug.
- `short_description` (str): Brief description of the guide (limit 500 characters).
- `content` (str): Full guide content (markdown supported).
""",
    auth=authed("games.manage", target_resolver=game_from_body),
)
def create_guide(
    request: HttpRequest,
    data: GuideCreateSchema,
) -> Status:
    try:
        game = Games.objects.get(id=data.game_id)
    except Games.DoesNotExist:
        return Status(
            400,
            ErrorResponse(
                error="Game ID Doesn't Exist",
                details={"games": {data.game_id}},
            ),
        )

    if data.tag_ids:
        existing_tags = Tags.objects.filter(
            Q(id__in=data.tag_ids) | Q(slug__in=data.tag_ids)
        )

        found_identifiers = set(existing_tags.values_list("id", flat=True)).union(
            existing_tags.values_list("slug", flat=True)
        )

        provided_tags = set(data.tag_ids)
        missing_tags = provided_tags - found_identifiers

        if missing_tags:
            return Status(
                400,
                ErrorResponse(
                    error="Tags not found",
                    details={"missing_tags": list(missing_tags)},
                ),
            )

    try:
        with transaction.atomic():
            guide = Guides.objects.create(
                title=data.title,
                game=game,
                short_description=data.short_description,
                content=data.content,
            )

            if data.tag_ids:
                guide.tags.set(data.tag_ids)

            guide_data = GuideSchema.model_validate(guide)
            guide_data.game = GameSchema.model_validate(guide.game)
            guide_data.tags = [
                TagSchema.model_validate(tag) for tag in guide.tags.all()
            ]

            return Status(200, guide_data)
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Guide Creation Failed",
                details={"exception": str(e)},
            ),
        )


@router.put(
    "/{slug}",
    response={200: GuideSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Update Guide",
    description="""\
Modifies an existing guide.

REQUIRES CONTRIBUTOR ACCESS OR HIGHER.

Request Body:
- `title` (str | None): Name of the guide.
- `game_id` (str | None): Unique game ID or slug of the game this is associated with.
- `tag_ids` (list | None): List of tag IDs or their slug.
- `short_description` (str | None): Brief description of the guide (limit 500 characters).
- `content` (str | None): Full guide content (markdown supported).
""",
    auth=authed("guides.edit_any", target_resolver=guide_from_path),
)
def update_guide(
    request: HttpRequest,
    slug: str,
    data: GuideUpdateSchema,
) -> Status:
    guide = Guides.objects.filter(slug__iexact=slug).first()
    if not guide:
        return Status(
            404,
            ErrorResponse(
                error=f"Guide with slug '{slug}' not found",
                details=None,
            ),
        )

    if data.game_id:
        try:
            Games.objects.get(id=data.game_id)
        except Games.DoesNotExist:
            return Status(
                400,
                ErrorResponse(
                    error=f"Game with ID '{data.game_id}' does not exist",
                    details=None,
                ),
            )

    if data.tag_ids is not None:
        existing_tags = Tags.objects.filter(
            Q(id__in=data.tag_ids) | Q(slug__in=data.tag_ids)
        )

        found_identifiers = set(existing_tags.values_list("id", flat=True)).union(
            existing_tags.values_list("slug", flat=True)
        )

        provided_tags = set(data.tag_ids)
        missing_tags = provided_tags - found_identifiers

        if missing_tags:
            return Status(
                400,
                ErrorResponse(
                    error="Tags not found",
                    details={"missing_tags": list(missing_tags)},
                ),
            )

    try:
        with transaction.atomic():
            if data.title is not None:
                guide.title = data.title

            if data.slug is not None:
                existing_guide = (
                    Guides.objects.filter(slug__iexact=data.slug)
                    .exclude(id=guide.pk)
                    .first()
                )
                if existing_guide:
                    return Status(
                        400,
                        ErrorResponse(
                            error="Guide With Slug Already Exists",
                            details={"slug": data.slug},
                        ),
                    )
                guide.slug = data.slug

            if data.game_id:
                guide.game = Games.objects.get(id=data.game_id)
            if data.short_description is not None:
                guide.short_description = data.short_description
            if data.content is not None:
                guide.content = data.content

            guide.save()

            if data.tag_ids is not None:
                guide.tags.set(data.tag_ids)

            return Status(200, GuideSchema.model_validate(guide))
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Guide Update Failed",
                details={"exception": str(e)},
            ),
        )


@router.delete(
    "/{slug}",
    response={200: dict[str, str], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Delete Guide",
    description="""\
Deletes an existing guide.

REQUIRES ADMIN ACCESS OR HIGHER.

Supported Parameters:
- `slug` (str): Simplified, URL friendly name of the guide.
""",
    auth=authed("guides.delete_any", target_resolver=guide_from_path),
)
def delete_guide(
    request: HttpRequest,
    slug: str,
) -> Status:
    guide = Guides.objects.filter(slug__iexact=slug).first()
    if not guide:
        return Status(
            404,
            ErrorResponse(
                error=f"Guide with slug '{slug}' not found",
                details=None,
            ),
        )

    try:
        title = guide.title
        guide.delete()
        return Status(200, {"message": f"Guide '{title} deleted successfully."})
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Guide Delete Failed",
                details={"exception": str(e)},
            ),
        )
