from typing import Annotated, Any

from django.db.models import Q
from django.http import HttpRequest
from ninja import Query, Router, Status
from ninja.responses import codes_4xx
from srl.models import Games

from api.permissions import public_read
from api.v1.routers.utils import (
    check_cache_query,
    game_leaderboard_cache_key,
    overall_leaderboard_cache_key,
)
from api.v1.routers.utils.query_utils import (
    OLDEST_RUNS_LIMITS,
    query_game_leaderboard,
    query_oldest_il_runs,
    query_overall_leaderboard,
    query_wr_count,
)
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.leaderboard import (
    GameLeaderboardEntrySchema,
    OldestRunEntrySchema,
    PointLeaderboardEntrySchema,
    WRCountEntrySchema,
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
    description="""\
Get the series-wide points leaderboard, ranking all runners across every game.

Only non-obsolete, verified runs are counted toward point totals.

Players are ranked by total_points in descending order.
""",
    auth=public_read(),
)
def get_overall_leaderboard(
    request: HttpRequest,
) -> Status:
    try:
        data = check_cache_query(
            overall_leaderboard_cache_key(),
            query_overall_leaderboard,
        )
        return Status(200, [PointLeaderboardEntrySchema(**entry) for entry in data])
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve overall leaderboard",
                details={"exception": str(e)},
            ),
        )


@router.get(
    "/pointslb/{game_id}",
    response={200: dict[str, Any], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get Per-Game Leaderboard",
    description="""\
Get the points leaderboard for a specific game, ranking all runners by their
combined full-game and individual level points for that game only.

Only non-obsolete, verified runs are counted toward point totals.

THPS4 Note: The level "Zoo - Feed the Hippos" is automatically excluded
from point calculations.

Supported Embeds:
- `oldest-runs` (THPS4, THPS12, THPS34 only): Adds an `oldest_runs` key to the
  response containing the longest-held IL world records (full-game runs are
  excluded). THPS4 returns 10 entries; THPS12 and THPS34 return 5 each.
  Entries are sorted oldest-first by submission date; `days_held` is -1 when
  the submission date is unknown.
- `wr-count` (THPS4, THPS12, THPS34 only): Adds a `wr_count` key listing every
  player who currently holds at least one IL world record for the game,
  ranked by trophy count descending (case-insensitive name as tiebreaker).
  THPS4 excludes `zoo-feed-the-hippos`. Each (level, category, variable)
  WR row counts independently; co-op runs credit every attached player.

Examples:
- `/website/game/thps4/pointslb` - THPS4 leaderboard
- `/website/game/thps4/pointslb?embed=oldest-runs` - THPS4 leaderboard with oldest IL WRs
- `/website/game/thps4/pointslb?embed=wr-count` - THPS4 leaderboard with IL WR trophy counts
- `/website/game/thps4/pointslb?embed=oldest-runs,wr-count` - THPS4 with both embeds
- `/website/game/thps12/pointslb?embed=oldest-runs` - THPS1+2 with oldest IL WRs
- `/website/game/n2680o1p/pointslb` - Leaderboard by game ID
""",
    auth=public_read(),
)
def get_game_leaderboard(
    request: HttpRequest,
    game_id: str,
    embed: Annotated[
        str | None,
        Query(
            description=(
                "Optional comma-separated embeds (THPS4/12/34): "
                "'oldest-runs' for oldest IL WRs, 'wr-count' for IL WR trophy counts."
            ),
        ),
    ] = None,
) -> Status:
    if len(game_id) > 15:
        return Status(
            400,
            ErrorResponse(
                error="ID must be 15 characters or less",
                details=None,
            ),
        )

    try:
        game = Games.objects.filter(
            Q(id__iexact=game_id) | Q(slug__iexact=game_id)
        ).first()
        if not game:
            return Status(
                404,
                ErrorResponse(
                    error="Game not found",
                    details=None,
                ),
            )

        embed_fields = [e.strip() for e in embed.split(",")] if embed else []

        valid_embed_types = {"oldest-runs", "wr-count"}
        invalid_embeds = [e for e in embed_fields if e not in valid_embed_types]
        if invalid_embeds:
            return Status(
                400,
                ErrorResponse(
                    error=f"Invalid embed type(s): {', '.join(invalid_embeds)}",
                    details={"valid_embed_types": list(valid_embed_types)},
                ),
            )

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

        if game.slug in OLDEST_RUNS_LIMITS and "oldest-runs" in embed_fields:
            oldest_data = check_cache_query(
                game_leaderboard_cache_key(game.id) + ":oldest",
                lambda: query_oldest_il_runs(game.id, game.slug),
            )
            response["oldest_runs"] = [
                OldestRunEntrySchema(**entry).model_dump() for entry in oldest_data
            ]

        if game.slug in OLDEST_RUNS_LIMITS and "wr-count" in embed_fields:
            wr_count_data = check_cache_query(
                game_leaderboard_cache_key(game.id) + ":wr_count",
                lambda: query_wr_count(game.id, game.slug),
            )
            response["wr_count"] = [
                WRCountEntrySchema(**entry).model_dump() for entry in wr_count_data
            ]

        return Status(200, response)

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve game leaderboard",
                details={"exception": str(e)},
            ),
        )
