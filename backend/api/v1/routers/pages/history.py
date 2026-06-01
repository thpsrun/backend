from typing import Annotated, Any

from django.db.models import Q
from django.http import HttpRequest
from ninja import Query, Router, Status
from srl.models import Categories, Games, Levels

from api.permissions import public_read
from api.v1.routers.utils import check_cache_query, history_cache_key, query_wr_history
from api.v1.schemas.base import ErrorResponse

router = Router()

CACHE_TIMEOUT = 604800  # 7 days


def _resolve_game(
    game_slug: str,
) -> tuple[Games | None, ErrorResponse | None, int]:
    """Resolve game by slug/ID. Returns (game, error, status_code)."""
    if len(game_slug) > 15:
        return (
            None,
            ErrorResponse(
                error="Game slug must be 15 characters or less",
                details=None,
            ),
            400,
        )

    game = Games.objects.filter(
        Q(slug__iexact=game_slug) | Q(id__iexact=game_slug)
    ).first()

    if not game:
        return None, ErrorResponse(error="Game not found", details=None), 404

    return game, None, 200


def _parse_value_slugs(
    values: str | None,
) -> tuple[list[str] | None, ErrorResponse | None]:
    """Parse and validate value slugs query param."""
    if not values:
        return None, None

    value_slugs = [v.strip() for v in values.split(",") if v.strip()]
    if len(value_slugs) > 10:
        return None, ErrorResponse(
            error="Too many value slugs (max 10)",
            details=None,
        )

    return value_slugs, None


@router.get(
    "/history/{game_slug}/category/{category_slug}",
    response={
        200: dict[str, Any],
        400: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get Full-Game WR History",
    description="""\
Get the complete world record history for a full-game category,
optionally filtered by variable value slugs (subcategory). Returns
every WR from first to current with timing deltas.

Examples:
- `/history/thug1/category/any` - Any% WR history for THUG1
- `/history/thug1/category/any?values=beginner` - Any% Beginner
""",
    auth=public_read(),
)
def get_fg_wr_history(
    request: HttpRequest,
    game_slug: str,
    category_slug: str,
    values: Annotated[
        str | None,
        Query(description="Comma-separated variable value slugs"),
    ] = None,
) -> Status:
    game, error, code = _resolve_game(game_slug)
    if error:
        return Status(code, error)
    assert game is not None

    if len(category_slug) > 50:
        return Status(
            400,
            ErrorResponse(
                error="Category slug must be 50 characters or less",
                details=None,
            ),
        )

    category = Categories.objects.filter(
        game=game,
        slug__iexact=category_slug,
    ).first()
    if not category:
        return Status(
            404,
            ErrorResponse(error="Category not found", details=None),
        )

    if category.type == "per-level":
        return Status(
            400,
            ErrorResponse(
                error=(
                    "This is an IL category. Use "
                    "/history/{game}/level/{level}/{category}"
                ),
                details=None,
            ),
        )

    value_slugs, val_error = _parse_value_slugs(values)
    if val_error:
        return Status(400, val_error)

    try:
        result = check_cache_query(
            history_cache_key(
                game.id,
                category.id,
                value_slugs=value_slugs,
            ),
            lambda: query_wr_history(
                game.id,
                category.id,
                value_slugs=value_slugs,
            ),
            timeout=CACHE_TIMEOUT,
        )

        return Status(
            200,
            {
                "game": game.name,
                "category": category.name,
                "subcategory": result["subcategory"] or category.name,
                "level": None,
                "entries": result["entries"],
            },
        )

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve WR history",
                details={"exception": str(e)},
            ),
        )


@router.get(
    "/history/{game_slug}/level/{level_slug}/{category_slug}",
    response={
        200: dict[str, Any],
        400: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get IL WR History",
    description="""\
Get the complete world record history for an individual level
category, optionally filtered by variable value slugs.

Examples:
- `/history/thps1/level/warehouse/agg` - Warehouse AG&G WR history
- `/history/thps1/level/warehouse/agg?values=console,igt`
""",
    auth=public_read(),
)
def get_il_wr_history(
    request: HttpRequest,
    game_slug: str,
    level_slug: str,
    category_slug: str,
    values: Annotated[
        str | None,
        Query(description="Comma-separated variable value slugs"),
    ] = None,
) -> Status:
    game, error, code = _resolve_game(game_slug)
    if error:
        return Status(code, error)
    assert game is not None

    if len(level_slug) > 75:
        return Status(
            400,
            ErrorResponse(
                error="Level slug must be 75 characters or less",
                details=None,
            ),
        )

    if len(category_slug) > 50:
        return Status(
            400,
            ErrorResponse(
                error="Category slug must be 50 characters or less",
                details=None,
            ),
        )

    level = Levels.objects.filter(
        game=game,
        slug__iexact=level_slug,
    ).first()
    if not level:
        return Status(
            404,
            ErrorResponse(error="Level not found", details=None),
        )

    category = Categories.objects.filter(
        game=game,
        slug__iexact=category_slug,
    ).first()
    if not category:
        return Status(
            404,
            ErrorResponse(error="Category not found", details=None),
        )

    if category.type == "per-game":
        return Status(
            400,
            ErrorResponse(
                error=(
                    "This is a full-game category. Use "
                    "/history/{game}/category/{category}"
                ),
                details=None,
            ),
        )

    value_slugs, val_error = _parse_value_slugs(values)
    if val_error:
        return Status(400, val_error)

    try:
        result = check_cache_query(
            history_cache_key(
                game.id,
                category.id,
                level_id=level.id,
                value_slugs=value_slugs,
            ),
            lambda: query_wr_history(
                game.id,
                category.id,
                level_id=level.id,
                value_slugs=value_slugs,
            ),
            timeout=CACHE_TIMEOUT,
        )

        return Status(
            200,
            {
                "game": game.name,
                "category": category.name,
                "subcategory": result["subcategory"] or level.name,
                "level": level.name,
                "entries": result["entries"],
            },
        )

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve WR history",
                details={"exception": str(e)},
            ),
        )
