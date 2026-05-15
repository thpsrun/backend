from typing import Annotated, Any

from django.db.models import Q
from django.http import HttpRequest
from ninja import Query, Router, Status
from srl.models import Categories, Games, Levels

from api.permissions import public_read
from api.v1.routers.utils import (
    check_cache_query,
    lbs_game_recent_cache_key,
    lbs_game_stats_cache_key,
    lbs_il_runs_cache_key,
    lbs_il_summary_cache_key,
    lbs_runs_cache_key,
    query_lbs_il_summary,
    query_lbs_recent,
    query_lbs_runs,
    query_lbs_stats,
)
from api.v1.schemas.base import ErrorResponse

router = Router()


def _validate_embeds(
    embed: str | None,
) -> tuple[list[str], ErrorResponse | None]:
    """Parse and validate embed parameter."""
    if not embed:
        return [], None

    embed_fields = [e.strip() for e in embed.split(",") if e.strip()]
    valid_embed_types = {"stats", "recent"}
    invalid_embeds = [e for e in embed_fields if e not in valid_embed_types]
    if invalid_embeds:
        return [], ErrorResponse(
            error=f"Invalid embed type(s): {', '.join(invalid_embeds)}",
            details={"valid_embed_types": list(valid_embed_types)},
        )
    return embed_fields, None


def _apply_embeds(
    response: dict[str, Any],
    embed_fields: list[str],
    game_id: str,
) -> None:
    """Add embed data to response dict in-place."""
    if "stats" in embed_fields:
        response["stats"] = check_cache_query(
            lbs_game_stats_cache_key(game_id),
            lambda: query_lbs_stats(game_id),
        )

    if "recent" in embed_fields:
        response["recent"] = check_cache_query(
            lbs_game_recent_cache_key(game_id),
            lambda: query_lbs_recent(game_id),
        )


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


@router.get(
    "/lbs/{game_slug}/category/{category_slug}",
    response={
        200: dict[str, Any],
        400: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get Full-Game Category Leaderboard",
    description="""\
Get the leaderboard for a specific full-game category, optionally filtered by
variable value slugs (subcategory). Returns all verified, non-obsolete runs with
full run metadata and embedded player data.

Supported Embeds:
- `stats`: Game-wide run counts (full-game vs IL) and unique player count.
- `recent`: 5 most recently approved runs across the entire game.

Examples:
- `/website/lbs/thug1/category/any` - All Any% runs for THUG1
- `/website/lbs/thug1/category/any?values=beginner` - Any% Beginner runs
- `/website/lbs/thps4/category/any?embed=stats,recent` - With game-wide metadata
""",
    auth=public_read(),
)
def get_category_leaderboard(
    request: HttpRequest,
    game_slug: str,
    category_slug: str,
    values: Annotated[
        str | None,
        Query(
            description="Comma-separated variable value slugs",
            examples=["beginner"],
        ),
    ] = None,
    embed: Annotated[
        str | None,
        Query(
            description="Comma-separated embeds: stats, recent",
            examples=["stats,recent"],
        ),
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
                    "This is an IL category. Use /lbs/{game}/levels "
                    "or /lbs/{game}/level/{level}/{category}"
                ),
                details=None,
            ),
        )

    value_slugs = (
        [v.strip() for v in values.split(",") if v.strip()] if values else None
    )
    if value_slugs and len(value_slugs) > 10:
        return Status(
            400,
            ErrorResponse(
                error="Too many value slugs (max 10)",
                details=None,
            ),
        )

    embed_fields, embed_error = _validate_embeds(embed)
    if embed_error:
        return Status(400, embed_error)

    try:
        runs = check_cache_query(
            lbs_runs_cache_key(
                game.id,
                category.id,
                value_slugs,
            ),
            lambda: query_lbs_runs(
                game.id,
                category.id,
                value_slugs,
            ),
        )

        response: dict[str, Any] = {"runs": runs}
        _apply_embeds(
            response,
            embed_fields,
            game.id,
        )

        return Status(200, response)

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve leaderboard",
                details={"exception": str(e)},
            ),
        )


@router.get(
    "/lbs/{game_slug}/levels",
    response={
        200: dict[str, Any],
        400: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get IL Summary Grid",
    description="""\
Get the Individual Level summary grid for a game. Returns the top 5 runs for
each level+category combination, grouped by level then category.

Only level+category combos with actual runs are included. Optionally filter
by variable value slugs to narrow results to a specific subcategory.

Supported Embeds:
- `stats`: Game-wide run counts (full-game vs IL) and unique player count.
- `recent`: 5 most recently approved runs across the entire game.

Examples:
- `/website/lbs/thug1/levels` - IL summary grid for THUG
- `/website/lbs/thug1/levels?values=normal` - Filtered to Normal difficulty
- `/website/lbs/thug1/levels?embed=stats,recent` - With game-wide metadata
""",
    auth=public_read(),
)
def get_il_summary(
    request: HttpRequest,
    game_slug: str,
    values: Annotated[
        str | None,
        Query(
            description="Comma-separated variable value slugs",
            examples=["normal"],
        ),
    ] = None,
    embed: Annotated[
        str | None,
        Query(
            description="Comma-separated embeds: stats, recent",
            examples=["stats,recent"],
        ),
    ] = None,
) -> Status:
    game, error, code = _resolve_game(game_slug)
    if error:
        return Status(code, error)
    assert game is not None

    value_slugs = (
        [v.strip() for v in values.split(",") if v.strip()] if values else None
    )
    if value_slugs and len(value_slugs) > 10:
        return Status(
            400,
            ErrorResponse(
                error="Too many value slugs (max 10)",
                details=None,
            ),
        )

    embed_fields, embed_error = _validate_embeds(embed)
    if embed_error:
        return Status(400, embed_error)

    try:
        levels = check_cache_query(
            lbs_il_summary_cache_key(game.id, value_slugs),
            lambda: query_lbs_il_summary(game.id, value_slugs),
        )

        response: dict[str, Any] = {"levels": levels}
        _apply_embeds(
            response,
            embed_fields,
            game.id,
        )

        return Status(200, response)

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve IL summary",
                details={"exception": str(e)},
            ),
        )


@router.get(
    "/lbs/{game_slug}/level/{level_slug}/{category_slug}",
    response={
        200: dict[str, Any],
        400: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get IL Category Leaderboard",
    description="""\
Get the full leaderboard for a specific level + IL category combination,
optionally filtered by variable value slugs (subcategory).

Supported Embeds:
- `stats`: Game-wide run counts (full-game vs IL) and unique player count.
- `recent`: 5 most recently approved runs across the entire game.

Examples:
- `/website/lbs/thug1/level/foundry/any` - Foundry Any% for THUG
- `/website/lbs/thug1/level/foundry/any?values=beginner` - Filtered
- `/website/lbs/thps4/level/manhattan/any?embed=stats` - With stats
""",
    auth=public_read(),
)
def get_il_leaderboard(
    request: HttpRequest,
    game_slug: str,
    level_slug: str,
    category_slug: str,
    values: Annotated[
        str | None,
        Query(
            description="Comma-separated variable value slugs",
            examples=["beginner"],
        ),
    ] = None,
    embed: Annotated[
        str | None,
        Query(
            description="Comma-separated embeds: stats, recent",
            examples=["stats,recent"],
        ),
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
                    "/lbs/{game}/category/{category}"
                ),
                details=None,
            ),
        )

    value_slugs = (
        [v.strip() for v in values.split(",") if v.strip()] if values else None
    )
    if value_slugs and len(value_slugs) > 10:
        return Status(
            400,
            ErrorResponse(
                error="Too many value slugs (max 10)",
                details=None,
            ),
        )

    embed_fields, embed_error = _validate_embeds(embed)
    if embed_error:
        return Status(400, embed_error)

    try:
        runs = check_cache_query(
            lbs_il_runs_cache_key(
                game.id,
                level.id,
                category.id,
                value_slugs,
            ),
            lambda: query_lbs_runs(
                game.id,
                category.id,
                value_slugs,
                level_id=level.id,
            ),
        )

        response: dict[str, Any] = {"runs": runs}
        _apply_embeds(
            response,
            embed_fields,
            game.id,
        )

        return Status(200, response)

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve IL leaderboard",
                details={"exception": str(e)},
            ),
        )
