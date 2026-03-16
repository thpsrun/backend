from textwrap import dedent
from typing import Annotated, Any

from django.db.models import Q
from django.http import HttpRequest
from ninja import Query, Router, Status
from ninja.responses import codes_4xx
from pydantic import Field
from srl.models import Games

from api.permissions import public_auth
from api.v1.routers.utils import (
    check_cache_query,
    game_leaderboard_cache_key,
    overall_leaderboard_cache_key,
)
from api.v1.routers.utils.query_utils import (
    query_game_leaderboard,
    query_overall_leaderboard,
    query_thps4_oldest_runs,
)
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.leaderboard import (
    GameLeaderboardEntrySchema,
    OldestRunEntrySchema,
    PointLeaderboardEntrySchema,
)

router = Router()


@router.get(
    "/pointslb",
    response={
        200: list[PointLeaderboardEntrySchema],
        codes_4xx: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get Overall Series Point Leaderboard",
    description=dedent(
        """
    Get the series-wide points leaderboard, ranking all runners across every game.

    Only non-obsolete, verified runs are counted toward point totals.

    Players are ranked by total_points in descending order.
    """
    ),
    auth=public_auth,
)
def get_overall_leaderboard(
    request: HttpRequest,
) -> Status:
    """Get series-wide points leaderboard across all games."""
    try:
        data = check_cache_query(
            overall_leaderboard_cache_key(),
            query_overall_leaderboard,
        )
        return Status(200, [PointLeaderboardEntrySchema(**entry) for entry in data])
    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to retrieve overall leaderboard",
            details={"exception": str(e)},
        ))


@router.get(
    "/pointslb/{game_id}",
    response={200: dict[str, Any], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get Per-Game Leaderboard",
    description=dedent(
        """
    Get the points leaderboard for a specific game, ranking all runners by their
    combined full-game and individual level points for that game only.

    Only non-obsolete, verified runs are counted toward point totals.

    **THPS4 note:** The level "Zoo - Feed the Hippos" is automatically excluded
    from point calculations.

    **Supported Embeds:**
    - `oldest-runs` (THPS4 only): Adds an `oldest_runs` key to the response containing
      each runner's personal best sorted by longest-held time (days since the run was set).
      Returns -1 for days_held when the submission date is unknown.

    **Examples:**
    - `/website/game/thps4/pointslb` - THPS4 leaderboard
    - `/website/game/thps4/pointslb?embed=oldest-runs` - THPS4 leaderboard with oldest PBs
    - `/website/game/n2680o1p/pointslb` - Leaderboard by game ID
    """
    ),
    auth=public_auth,
)
def get_game_leaderboard(
    request: HttpRequest,
    game_id: str,
    embed: Annotated[
        str | None,
        Query,
        Field(description="Optional: 'oldest-runs' for THPS4 oldest PBs embed"),
    ] = None,
) -> Status:
    """Get per-game points leaderboard with optional oldest-runs embed for THPS4."""
    if len(game_id) > 15:
        return Status(400, ErrorResponse(
            error="ID must be 15 characters or less",
            details=None,
        ))

    try:
        game = Games.objects.filter(
            Q(id__iexact=game_id) | Q(slug__iexact=game_id)
        ).first()
        if not game:
            return Status(404, ErrorResponse(
                error="Game not found",
                details=None,
            ))

        embed_fields = [e.strip() for e in embed.split(",")] if embed else []

        valid_embed_types = {"oldest-runs"}
        invalid_embeds = [e for e in embed_fields if e not in valid_embed_types]
        if invalid_embeds:
            return Status(400, ErrorResponse(
                error=f"Invalid embed type(s): {', '.join(invalid_embeds)}",
                details={"valid_embed_types": list(valid_embed_types)},
            ))

        leaderboard_data = check_cache_query(
            game_leaderboard_cache_key(game.id),
            lambda: query_game_leaderboard(game.id, game.slug),
        )

        response: dict[str, Any] = {
            "leaderboard": [
                GameLeaderboardEntrySchema(**entry).model_dump()
                for entry in leaderboard_data
            ],
        }

        if game.slug == "thps4" and "oldest-runs" in embed_fields:
            oldest_data = check_cache_query(
                game_leaderboard_cache_key(game.id) + ":oldest",
                lambda: query_thps4_oldest_runs(game.id),
            )
            response["oldest_runs"] = [
                OldestRunEntrySchema(**entry).model_dump() for entry in oldest_data
            ]

        return Status(200, response)

    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to retrieve game leaderboard",
            details={"exception": str(e)},
        ))
