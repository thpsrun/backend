from typing import Annotated, Any

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils.text import slugify
from guides.models import Guides, Tags
from ninja import Query, Router, Status
from srl.models.games import Games

from api.permissions import (
    actor_game_check,
    actor_key_check,
    authed,
    public_read,
)
from api.v1.routers.utils.embeds import parse_embeds
from api.v1.routers.utils.resolvers import (
    game_from_body,
    guide_from_path,
    resolve_game_or_none,
)
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.common import CountrySchema
from api.v1.schemas.games import GameSchema
from api.v1.schemas.guides import (
    GuideAuthorSchema,
    GuideCreateSchema,
    GuideListSchema,
    GuideSchema,
    GuideUpdateSchema,
    TagSchema,
)
from api.v1.schemas.players import GradientsEmbed

router = Router()


def _author_for_user(
    user: Any,
) -> GuideAuthorSchema | None:
    if user is None:
        return None

    player = getattr(user, "player", None)
    if player is None:
        return GuideAuthorSchema(
            name=user.get_username(),
            nickname=None,
            country=None,
            gradients=None,
        )

    country: CountrySchema | None = None
    if player.countrycode_id:
        country = CountrySchema(
            id=player.countrycode.id,
            name=player.countrycode.name,
            flag=player.countrycode.flag.url if player.countrycode.flag else None,
        )

    g1: str | None = getattr(user, "gradient_1", None)
    g2: str | None = getattr(user, "gradient_2", None)
    g3: str | None = getattr(user, "gradient_3", None)
    gradients: GradientsEmbed | None = (
        GradientsEmbed(gradient_1=g1, gradient_2=g2, gradient_3=g3)
        if (g1 or g2 or g3)
        else None
    )

    return GuideAuthorSchema(
        name=player.name,
        nickname=player.nickname,
        country=country,
        gradients=gradients,
    )


_AUTHOR_SELECT_RELATED: tuple[str, ...] = (
    "owner",
    "owner__player",
    "owner__player__countrycode",
)


def _guide_slug_taken(
    game: Games,
    slug: str,
    exclude_pk: int | None = None,
) -> bool:
    """Return whether another guide in `game` already uses `slug` (case-insensitive).

    This is only a friendly pre-check; `unique_guide_slug_per_game` is the real guard.

    Arguments:
        game (Games): Game the slug must be unique within.
        slug (str): Normalized slug to look for.
        exclude_pk (int | None): Guide to ignore (the one being updated), if any.

    Returns:
        taken (bool): True when a different guide in the game has this slug.
    """
    queryset = Guides.objects.filter(game=game, slug__iexact=slug)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.exists()


def _slug_taken_response(
    slug: str,
) -> Status:
    """Build the 400 returned when `slug` is already used by another guide in the game."""
    return Status(
        400,
        ErrorResponse(
            error="Guide With Slug Already Exists",
            details={"slug": slug},
        ),
    )


@router.get(
    "/all",
    response={
        200: list[GuideListSchema],
        400: ErrorResponse,
        500: ErrorResponse,
    },
    summary="List All Guides",
    description="""\
Gets all guides within the database, with optional querying and embeds.

Query Parameters:
- `game` (str | None): Filter guides based on the game's slug or ID.
- `tag` (str | None): Filter guides based on the tag's slug or ID.
- `player_id` (str | None): Filter guides based on the author's player ID.
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
    player_id: Annotated[str | None, Query(description="Filter by player")] = None,
    embed: Annotated[
        str | None, Query(description="Comma-separated embeds (game,tags)")
    ] = None,
) -> Status:
    embed_list = parse_embeds(embed, "guides")

    queryset = Guides.objects.select_related(*_AUTHOR_SELECT_RELATED)

    if game:
        queryset = queryset.filter(
            Q(game__slug__iexact=game) | Q(game__id__iexact=game),
        )
    if tag:
        queryset = queryset.filter(
            Q(tags__slug__iexact=tag) | Q(tags__id__iexact=tag),
        )
    if player_id:
        queryset = queryset.filter(owner__player__id__iexact=player_id)

    if "game" in embed_list:
        queryset = queryset.select_related("game")
    if "tags" in embed_list:
        queryset = queryset.prefetch_related("tags")

    result = []
    for guide in queryset:
        guide_data = GuideListSchema.model_validate(guide)
        guide_data.author = _author_for_user(guide.owner)

        if "game" in embed_list and guide.game:
            guide_data.game = GameSchema.model_validate(guide.game)
        if "tags" in embed_list:
            guide_data.tags = [
                TagSchema.model_validate(tag) for tag in guide.tags.all()
            ]

        result.append(guide_data)

    return Status(200, result)


@router.get(
    "/{game_slug}/{guide_slug}",
    response={
        200: GuideSchema,
        400: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get Guide by Game and Slug",
    description="""\
Get a specific guide by its game and slug. Slugs are unique per game, so both
are required to identify a guide.

Supported Parameters:
- `game_slug` (str): Slug of the game the guide belongs to.
- `guide_slug` (str): Simplified, URL friendly name of the guide.
- `embed` (list | None): Comma-separated list of resources to embed.

Supported Embeds:
- `game`: Includes the metadata of the game the tag belongs to.
- `tags`: Include metadata of the tags belonging to this guide.
""",
    auth=public_read(),
)
def get_guide(
    request: HttpRequest,
    game_slug: str,
    guide_slug: str,
    embed: Annotated[
        str | None, Query(description="Comma-separated embeds (game,tags)")
    ] = None,
) -> Status:
    embed_list = parse_embeds(embed, "guides")

    queryset = Guides.objects.filter(
        game__slug__iexact=game_slug,
        slug__iexact=guide_slug,
    ).select_related(
        *_AUTHOR_SELECT_RELATED,
    )
    if "game" in embed_list:
        queryset = queryset.select_related("game")
    if "tags" in embed_list:
        queryset = queryset.prefetch_related("tags")

    guide = queryset.first()
    if not guide:
        return Status(
            404,
            ErrorResponse(
                error=f"Guide '{guide_slug}' not found in game '{game_slug}'",
                details=None,
            ),
        )

    guide_data = GuideSchema.model_validate(guide)
    guide_data.author = _author_for_user(guide.owner)

    if "game" in embed_list and guide.game:
        guide_data.game = GameSchema.model_validate(guide.game)
    if "tags" in embed_list:
        guide_data.tags = [TagSchema.model_validate(tag) for tag in guide.tags.all()]

    return Status(200, guide_data)


@router.post(
    "/",
    response={
        201: GuideSchema,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Create New Guide",
    description="""\
Creates a brand new guide. Any claimed player can create a guide; the new
guide is owned by the calling user.

Request Body:
- `title` (str): Name of the guide.
- `slug` (str | None): Optional URL-friendly slug (unique within the game).
- `game_id` (str): Unique game ID or slug of the game this is associated with.
- `tag_ids` (list[int] | None): List of tag IDs.
- `short_description` (str): Brief description of the guide (limit 500 characters).
- `content` (str): Full guide content (markdown supported).
""",
    auth=authed("guides.create", target_resolver=game_from_body),
)
def create_guide(
    request: HttpRequest,
    data: GuideCreateSchema,
) -> Status:
    game = resolve_game_or_none(data.game_id)
    if game is None:
        return Status(
            400,
            ErrorResponse(
                error="Game ID Doesn't Exist",
                details={"game_id": data.game_id},
            ),
        )
    if not actor_key_check(request, "guides.create", game):
        return Status(
            403,
            ErrorResponse(
                error="API key scope does not cover this game",
                details=None,
            ),
        )

    if data.tag_ids:
        existing_ids = set(
            Tags.objects.filter(id__in=data.tag_ids).values_list("id", flat=True)
        )
        missing_tags = set(data.tag_ids) - existing_ids

        if missing_tags:
            return Status(
                400,
                ErrorResponse(
                    error="Tags not found",
                    details={"missing_tags": list(missing_tags)},
                ),
            )

    # Slugs from users take precedence... if not, just derive one from the title instead.
    slug = slugify(data.slug or data.title)
    if not slug:
        return Status(
            400,
            ErrorResponse(
                error="Slug must contain at least one letter or number",
                details={"slug": data.slug or data.title},
            ),
        )
    if _guide_slug_taken(game, slug):
        return _slug_taken_response(slug)

    with transaction.atomic():
        try:
            # Savepoint around the insert only: the pre-check above can lose a race with a
            # concurrent create, and unique_guide_slug_per_game is the real guard. Other
            # errors fall through to the global handler.
            with transaction.atomic():
                guide = Guides.objects.create(
                    title=data.title,
                    slug=slug,
                    game=game,
                    owner=request.user,
                    short_description=data.short_description,
                    content=data.content,
                )
        except IntegrityError:
            return _slug_taken_response(slug)

        if data.tag_ids:
            guide.tags.set(data.tag_ids)

    guide_data = GuideSchema.model_validate(guide)
    guide_data.author = _author_for_user(request.user)
    guide_data.game = GameSchema.model_validate(guide.game)
    guide_data.tags = [TagSchema.model_validate(tag) for tag in guide.tags.all()]

    return Status(201, guide_data)


@router.put(
    "/{game_slug}/{guide_slug}",
    response={
        200: GuideSchema,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Update Guide",
    description="""\
Modifies an existing guide, identified by its game and slug.

Request Body:
- `title` (str | None): Name of the guide.
- `slug` (str | None): URL-friendly slug (unique within the guide's game).
- `game_id` (str | None): Unique game ID or slug of the game this is associated with.
- `tag_ids` (list[int] | None): List of tag IDs.
- `short_description` (str | None): Brief description of the guide (limit 500 characters).
- `content` (str | None): Full guide content (markdown supported).
""",
    auth=authed(
        ["guides.edit_own", "guides.edit_any"],
        target_resolver=guide_from_path,
    ),
)
def update_guide(
    request: HttpRequest,
    game_slug: str,
    guide_slug: str,
    data: GuideUpdateSchema,
) -> Status:
    guide = (
        Guides.objects.filter(
            game__slug__iexact=game_slug,
            slug__iexact=guide_slug,
        )
        .select_related(*_AUTHOR_SELECT_RELATED)
        .first()
    )
    if not guide:
        return Status(
            404,
            ErrorResponse(
                error=f"Guide '{guide_slug}' not found in game '{game_slug}'",
                details=None,
            ),
        )

    new_game: Games | None = None
    if data.game_id:
        new_game = resolve_game_or_none(data.game_id)
        if new_game is None:
            return Status(
                400,
                ErrorResponse(
                    error=f"Game with ID '{data.game_id}' does not exist",
                    details=None,
                ),
            )
        if new_game.pk != guide.game_id:
            if guide.owner_id == request.user.pk:
                allowed = actor_key_check(request, "guides.edit_own", new_game)
            else:
                allowed = actor_game_check(request, "guides.edit_any", new_game)
            if not allowed:
                return Status(
                    403,
                    ErrorResponse(
                        error="Permission denied for the destination game",
                        details=None,
                    ),
                )

    if data.tag_ids is not None:
        existing_ids = set(
            Tags.objects.filter(id__in=data.tag_ids).values_list("id", flat=True)
        )
        missing_tags = set(data.tag_ids) - existing_ids

        if missing_tags:
            return Status(
                400,
                ErrorResponse(
                    error="Tags not found",
                    details={"missing_tags": list(missing_tags)},
                ),
            )

    with transaction.atomic():
        if data.title is not None:
            guide.title = data.title

        if data.slug is not None:
            new_slug = slugify(data.slug)
            if not new_slug:
                return Status(
                    400,
                    ErrorResponse(
                        error="Slug must contain at least one letter or number",
                        details={"slug": data.slug},
                    ),
                )
            target_game = new_game if new_game is not None else guide.game
            if _guide_slug_taken(target_game, new_slug, exclude_pk=guide.pk):
                return _slug_taken_response(new_slug)
            guide.slug = new_slug

        if new_game is not None:
            guide.game = new_game
        if data.short_description is not None:
            guide.short_description = data.short_description
        if data.content is not None:
            guide.content = data.content

        try:
            with transaction.atomic():
                guide.save()
        except IntegrityError:
            return _slug_taken_response(guide.slug)

        if data.tag_ids is not None:
            guide.tags.set(data.tag_ids)

    guide_data = GuideSchema.model_validate(guide)
    guide_data.author = _author_for_user(guide.owner)
    guide_data.game = GameSchema.model_validate(guide.game)
    guide_data.tags = [TagSchema.model_validate(tag) for tag in guide.tags.all()]

    return Status(200, guide_data)


@router.delete(
    "/{game_slug}/{guide_slug}",
    response={
        200: dict[str, str],
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Delete Guide",
    description="""\
Deletes an existing guide, identified by its game and slug.

Supported Parameters:
- `game_slug` (str): Slug of the game the guide belongs to.
- `guide_slug` (str): Simplified, URL friendly name of the guide.
""",
    auth=authed(
        ["guides.delete_own", "guides.delete_any"],
        target_resolver=guide_from_path,
    ),
)
def delete_guide(
    request: HttpRequest,
    game_slug: str,
    guide_slug: str,
) -> Status:
    guide = Guides.objects.filter(
        game__slug__iexact=game_slug,
        slug__iexact=guide_slug,
    ).first()
    if not guide:
        return Status(
            404,
            ErrorResponse(
                error=f"Guide '{guide_slug}' not found in game '{game_slug}'",
                details=None,
            ),
        )

    title = guide.title
    guide.delete()
    return Status(200, {"message": f"Guide '{title}' deleted successfully."})
