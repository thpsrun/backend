from typing import Annotated

from django.db.models import Case, F, IntegerField, Prefetch, Q, Value, When
from django.http import HttpRequest
from ninja import Query, Router, Status
from ninja.responses import codes_4xx
from srl.models import Categories, Games, Levels, Variables, VariableValues

from api.permissions import admin_auth, moderator_auth, public_auth
from api.v1.docs.games import GAMES_ALL, GAMES_DELETE, GAMES_GET, GAMES_POST, GAMES_PUT
from api.v1.schemas.base import ErrorResponse, validate_embeds
from api.v1.schemas.games import GameCreateSchema, GameSchema, GameUpdateSchema
from api.v1.utils import get_or_generate_id

router = Router()


def _value_prefetch() -> Prefetch:
    return Prefetch(
        "variablevalues_set",
        queryset=VariableValues.objects.annotate(
            vv_sort_key=Case(
                When(order=0, then=Value(999999)),
                default=F("order"),
                output_field=IntegerField(),
            )
        ).order_by("vv_sort_key", "name"),
    )


def _game_variables_prefetch() -> Prefetch:
    """Prefetch all variables for a game (both category-linked and global)."""
    return Prefetch(
        "variables_set",
        queryset=Variables.objects.prefetch_related(
            _value_prefetch(),
        ),
    )


def game_embeds(
    queryset,
    embeds: str | None,
):
    """Add prefetches to a queryset based on embed parameter."""
    if not embeds:
        return queryset

    embed_list = [e.strip() for e in embeds.split(",")]
    needs_variables = False

    if "categories" in embed_list:
        queryset = queryset.prefetch_related(
            Prefetch(
                "categories_set",
                queryset=Categories.objects.annotate(
                    sort_key=Case(
                        When(order=0, then=Value(999999)),
                        default=F("order"),
                        output_field=IntegerField(),
                    )
                ).order_by("sort_key", "name"),
            ),
        )
        needs_variables = True

    if "levels" in embed_list:
        queryset = queryset.prefetch_related(
            Prefetch(
                "levels_set",
                queryset=Levels.objects.annotate(
                    sort_key=Case(
                        When(order=0, then=Value(999999)),
                        default=F("order"),
                        output_field=IntegerField(),
                    )
                ).order_by("sort_key", "name"),
            ),
        )
        needs_variables = True

    if needs_variables:
        queryset = queryset.prefetch_related(_game_variables_prefetch())

    if "platforms" in embed_list:
        queryset = queryset.prefetch_related("platforms")

    return queryset


_SCOPE: dict[str, str] = {
    "full-game": "per-game",
    "all-levels": "per-level",
}


def _build_cat_embed(
    game: Games,
    entity_id: str | None = None,
    entity_type: str = "cat",
    entity_cat_type: str | None = None,
) -> list[dict]:
    """Build variable dicts for an entity, including global variables (cat/level=NULL).

    Uses game.variables_set (prefetched) to avoid N+1 queries. Filters to variables
    that are either linked to the specific entity or are global (entity FK is NULL).
    Also filters by scope: full-game vars only appear on per-game categories, and
    all-levels vars only appear on per-level categories.
    """
    variables = []
    for var in game.variables_set.all():  # type: ignore
        var_entity_id = getattr(var, f"{entity_type}_id", None)
        if var_entity_id != entity_id and var_entity_id is not None:
            continue

        # Filter by scope when building for categories
        if entity_type == "cat" and entity_cat_type:
            allowed_cat_type = _SCOPE.get(var.scope)
            if allowed_cat_type and allowed_cat_type != entity_cat_type:
                continue
            # single-level scoped vars don't belong on categories
            if var.scope == "single-level":
                continue
        values = [
            {
                "value": val.value,
                "name": val.name,
                "slug": val.slug,
                "appear_on_main": val.appear_on_main,
                "order": val.order,
                "archive": val.archive,
                "rules": val.rules,
            }
            for val in var.variablevalues_set.all()  # type: ignore
        ]
        variables.append(
            {
                "id": var.id,
                "name": var.name,
                "slug": var.slug,
                "scope": var.scope,
                "archive": var.archive,
                "values": values,
            }
        )
    return variables


def _build_categories_embed(
    game: Games,
) -> list[dict]:
    result = []
    for cat in game.categories_set.all():  # type: ignore
        result.append(
            {
                "id": cat.id,
                "name": cat.name,
                "slug": cat.slug,
                "type": cat.type,
                "players": cat.players,
                "url": cat.url,
                "rules": cat.rules,
                "appear_on_main": cat.appear_on_main,
                "archive": cat.archive,
                "variables": _build_cat_embed(
                    game,
                    cat.id,
                    "cat",
                    cat.type,
                ),
            }
        )
    return result


def _build_levels_embed(
    game: Games,
) -> list[dict]:
    result = []
    for level in game.levels_set.all():  # type: ignore
        result.append(
            {
                "id": level.id,
                "name": level.name,
                "slug": level.slug,
                "url": level.url,
                "rules": level.rules,
                "variables": _build_cat_embed(game, level.id, "level"),
            }
        )
    return result


def _build_platforms_embed(
    game: Games,
) -> list[dict]:
    return [
        {
            "id": platform.id,
            "name": platform.name,
            "slug": platform.slug,
        }
        for platform in game.platforms.all()  # type: ignore
    ]


@router.get(
    "/all",
    response={200: list[GameSchema], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get All Games",
    description="""\
Retrieves all games within the `Games` object, including optional embedding and
pagination.

Supported Parameters:
- `limit` (int | None): Results per page (default 50, max 100).
- `offset` (int | None): Results to skip (default 0).
- `embed` (list | None): Comma-separated list of resources to embed,

Supported Embeds:
- `categories`: Include metadata related to the game's categories.
- `levels`: Include metadata related to the game's levels.
- `platforms`: Include metadata related to the game's available platforms.

Examples:
- `/games/all` - Get all games.
- `/games/all?limit=20` - Get first 20 games.
- `/games/all?embed=categories,platforms` - Get games with categories and platforms.
""",
    auth=public_auth,
    openapi_extra=GAMES_ALL,
)
def get_all_games(
    request: HttpRequest,
    embed: Annotated[
        str | None, Query(description="Comma-separated embeds")
    ] = None,
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
    # Checks to see what embeds are being used versus what is allowed
    # via this endpoint. It will return an error to the client if they
    # have an embed type not supported.
    embed_fields = []
    if embed:
        embed_fields = [field.strip() for field in embed.split(",") if field.strip()]
        invalid_embeds = validate_embeds("games", embed_fields)
        if invalid_embeds:
            return Status(
                400,
                ErrorResponse(
                    error=f"Invalid embed(s): {', '.join(invalid_embeds)}",
                    details={"valid_embeds": ["categories", "levels", "platforms"]},
                ),
            )

    try:
        queryset = Games.objects.all().order_by("release")
        queryset = game_embeds(queryset, embed)
        games = queryset[offset : offset + limit]

        # Simple model validate on the game date received before putting it into
        # an array that is then sent back to the client.
        game_schemas = []
        for game in games:
            game_data = GameSchema.model_validate(game)
            if "categories" in embed_fields:
                game_data.categories = _build_categories_embed(game)
            if "levels" in embed_fields:
                game_data.levels = _build_levels_embed(game)
            if "platforms" in embed_fields:
                game_data.platforms = _build_platforms_embed(game)
            game_schemas.append(game_data)

        return Status(200, game_schemas)
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve games",
                details={"exception": str(e)},
            ),
        )


@router.get(
    "/{id}",
    response={200: GameSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get Game by ID",
    description="""\
Retrieves a single game by its ID or its slug, including optional embedding.

Supported Embeds:
- `categories`: Include metadata related to the game's categories
- `levels`: Include metadata related to the game's levels
- `platforms`: Include metadata related to the game's available platforms

Examples:
- `/games/thps4` - Get game by slug
- `/games/n2680o1p` - Get game by ID
- `/games/thps4?embed=categories,levels` - Get game with categories and levels
""",
    auth=public_auth,
    openapi_extra=GAMES_GET,
)
def get_game(
    request: HttpRequest,
    id: str,
    embed: Annotated[
        str | None, Query(description="Comma-separated embeds")
    ] = None,
) -> Status:
    if len(id) > 15:
        return Status(
            400,
            ErrorResponse(
                error="ID must be 15 characters or less",
                details=None,
            ),
        )

    # Checks to see what embeds are being used versus what is allowed
    # via this endpoint. It will return an error to the client if they
    # have an embed type not supported.
    embed_fields = []
    if embed:
        embed_fields = [field.strip() for field in embed.split(",") if field.strip()]
        invalid_embeds = validate_embeds("games", embed_fields)
        if invalid_embeds:
            return Status(
                400,
                ErrorResponse(
                    error=f"Invalid embed(s): {', '.join(invalid_embeds)}",
                    details={"valid_embeds": ["categories", "levels", "platforms"]},
                ),
            )

    try:
        queryset = Games.objects.all()
        queryset = game_embeds(queryset, embed)

        game = queryset.filter(Q(id__iexact=id) | Q(slug__iexact=id)).first()
        if not game:
            return Status(
                404,
                ErrorResponse(
                    error="Game does not exist",
                    details=None,
                ),
            )

        game_data = GameSchema.model_validate(game)
        if "categories" in embed_fields:
            game_data.categories = _build_categories_embed(game)
        if "levels" in embed_fields:
            game_data.levels = _build_levels_embed(game)
        if "platforms" in embed_fields:
            game_data.platforms = _build_platforms_embed(game)
        return Status(200, game_data)
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve game",
                details={"exception": str(e)},
            ),
        )


@router.post(
    "/",
    response={201: GameSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Create Game",
    description="""\
Creates a brand new game.

REQUIRES MODERATOR ACCESS OR HIGHER.

Request Body:
- `id` (str | None): The game ID; if one is not given, it will auto-generate.
- `name` (str): Game name.
- `slug` (str): URL-friendly game abbreviation.
- `twitch` (str | None): Game name as it appears on Twitch.
- `release` (date): Game release date (ISO format).
- `boxart` (str): URL to game box art/cover image.
- `defaulttime` (str): Default timing method for full-game runs.
- `idefaulttime` (str): Default timing method for individual level runs.
- `pointsmax` (int): Maximum points for world record full-game runs.
- `ipointsmax` (int): Maximum points for world record individual level runs.
""",
    auth=moderator_auth,
    openapi_extra=GAMES_POST,
)
def create_game(
    request: HttpRequest,
    game_data: GameCreateSchema,
) -> Status:
    try:
        game_check = Games.objects.filter(
            Q(name__iexact=game_data.name) | Q(slug__iexact=game_data.slug)
        ).first()
        if game_check:
            return Status(
                400,
                ErrorResponse(
                    error="Game Already Exists",
                    details={
                        "exception": "Either the name of the game or its slug already exists."
                    },
                ),
            )

        try:
            game_id = get_or_generate_id(
                game_data.id,
                lambda id: Games.objects.filter(id=id).exists(),
            )
        except ValueError as e:
            return Status(
                400,
                ErrorResponse(
                    error="ID Already Exists",
                    details={"exception": str(e)},
                ),
            )

        create_data = game_data.model_dump()
        create_data["id"] = game_id
        game = Games.objects.create(**create_data)

        return Status(201, GameSchema.model_validate(game))
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Game Creation Failed",
                details={"exception": str(e)},
            ),
        )


@router.put(
    "/{id}",
    response={200: GameSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Update Game",
    description="""\
Updates the game based on its unique ID or slug.

REQUIRES MODERATOR ACCESS OR HIGHER.

Request Body:
- `name` (str | None): Game name.
- `slug` (str | None): URL-friendly game abbreviation.
- `twitch` (str | None): Game name as it appears on Twitch.
- `release` (date | None): Game release date (ISO format).
- `boxart` (str | None): URL to game box art/cover image.
- `defaulttime` (str | None): Default timing method for full-game runs.
- `idefaulttime` (str | None): Default timing method for individual level runs.
- `pointsmax` (int | None): Maximum points for world record full-game runs.
- `ipointsmax` (int | None): Maximum points for world record individual level runs.
""",
    auth=moderator_auth,
    openapi_extra=GAMES_PUT,
)
def update_game(
    request: HttpRequest,
    id: str,
    game_data: GameUpdateSchema,
) -> Status:
    try:
        game = Games.objects.filter(Q(id__iexact=id) | Q(slug__iexact=id)).first()
        if not game:
            return Status(
                404,
                ErrorResponse(
                    error="Game does not exist",
                    details=None,
                ),
            )

        for attr, value in game_data.model_dump(exclude_unset=True).items():
            setattr(game, attr, value)

        game.save()
        return Status(200, GameSchema.model_validate(game))
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to update game",
                details={"exception": str(e)},
            ),
        )


@router.delete(
    "/{id}",
    response={200: dict[str, str], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Delete Game",
    description="""\
Deletes the selected game.

REQUIRES ADMIN ACCESS.

Supported Parameters:
- id (str): Unique ID or slug of the specified game
""",
    auth=admin_auth,
    openapi_extra=GAMES_DELETE,
)
def delete_game(
    request: HttpRequest,
    id: str,
) -> Status:
    try:
        game = Games.objects.filter(Q(id__iexact=id) | Q(slug__iexact=id)).first()
        if not game:
            return Status(
                404,
                ErrorResponse(
                    error="Game does not exist",
                    details=None,
                ),
            )

        name = game.name
        game.delete()
        return Status(200, {"message": f"Game '{name}' deleted successfully"})
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to delete game",
                details={"exception": str(e)},
            ),
        )
