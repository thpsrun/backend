from datetime import timezone as dt_tz

from django.core.cache import caches
from django.utils import timezone
from ninja import Router

from api.permissions import public_read
from api.v1.routers.utils.cache_utils import (
    get_earliest_possible,
    historical_cache_key,
    historical_cache_ttl,
)
from api.v1.routers.utils.history_query import (
    cumulative_rankings,
    monthly_rankings,
    yearly_rankings,
)
from api.v1.routers.utils.resolvers import resolve_game_or_none
from api.v1.schemas.leaderboard_history import (
    EarliestPossibleErrorSchema,
    GameNotFoundErrorSchema,
    HistoricalLeaderboardResponseSchema,
    HistoricalMetaSchema,
    TimeTravelerErrorSchema,
)

router = Router(tags=["Leaderboards"])


def _resolve_or_404(
    game_id: str,
):
    game = resolve_game_or_none(game_id)
    if game is None:
        return None, (404, {"detail": f"Game '{game_id}' not found"})
    return game, None


def _is_future(
    year: int,
    month: int,
) -> bool:
    now = timezone.now().astimezone(dt_tz.utc)
    return (year, month) > (now.year, now.month)


def _format_year_month(
    year: int,
    month: int,
) -> str:
    return f"{year:04d}-{month:02d}"


def _is_before_earliest(
    year: int,
    month: int,
    earliest: str | None,
) -> bool:
    if earliest is None:
        return True
    return _format_year_month(year, month) < earliest


def _build_meta(
    *,
    mode: str,
    year: int,
    month: int,
    scope: str,
    scope_game_id: str | None,
    earliest_possible: str | None,
) -> HistoricalMetaSchema:
    if mode == "cumulative":
        period_start = "0001-01-01T00:00:00Z"
    elif mode == "yearly":
        period_start = f"{year:04d}-01-01T00:00:00Z"
    else:
        period_start = f"{year:04d}-{month:02d}-01T00:00:00Z"

    if month == 12:
        period_end = f"{year + 1:04d}-01-01T00:00:00Z"
    else:
        period_end = f"{year:04d}-{month + 1:02d}-01T00:00:00Z"

    return HistoricalMetaSchema(
        mode=mode,
        year=year,
        month=month,
        scope=scope,
        scope_game_id=scope_game_id,
        period_start=period_start,
        period_end_exclusive=period_end,
        earliest_possible=earliest_possible,
    )


def _serve_history(
    request,
    *,
    mode: str,
    year: int,
    month: int,
    game_id: str | None,
):
    if not (1 <= month <= 12):
        return 422, {"detail": "Invalid month"}

    if _is_future(year, month):
        now = timezone.now().astimezone(dt_tz.utc)
        return 400, {
            "detail": "Are you a time traveler?",
            "current": _format_year_month(now.year, now.month),
        }

    earliest = get_earliest_possible(game_id=game_id)
    if _is_before_earliest(year, month, earliest):
        return 404, {
            "detail": "That game didn't even come out yet???",
            "earliest_possible": earliest or _format_year_month(year, month),
        }

    scope_key = "all" if game_id is None else game_id
    cache_key = historical_cache_key(
        scope=scope_key,
        mode=mode,
        year=year,
        month=month,
    )
    cache = caches["default"]

    cached = cache.get(cache_key)
    if cached is not None:
        return 200, cached

    if mode == "cumulative":
        rankings = cumulative_rankings(year=year, month=month, game_id=game_id)
    elif mode == "monthly":
        rankings = monthly_rankings(year=year, month=month, game_id=game_id)
    else:
        rankings = yearly_rankings(year=year, month=month, game_id=game_id)

    scope = "all" if game_id is None else "game"
    meta = _build_meta(
        mode=mode,
        year=year,
        month=month,
        scope=scope,
        scope_game_id=game_id,
        earliest_possible=earliest,
    )
    payload = {
        "rankings": rankings,
        "meta": meta.model_dump(),
    }
    cache.set(cache_key, payload, timeout=historical_cache_ttl(year))
    return 200, payload


@router.get(
    "/cumulative/{year}/{month}/",
    response={
        200: HistoricalLeaderboardResponseSchema,
        400: TimeTravelerErrorSchema,
        404: EarliestPossibleErrorSchema,
    },
    auth=public_read(),
)
def cumulative_series_wide(request, year: int, month: int):
    return _serve_history(
        request,
        mode="cumulative",
        year=year,
        month=month,
        game_id=None,
    )


@router.get(
    "/monthly/{year}/{month}/",
    response={
        200: HistoricalLeaderboardResponseSchema,
        400: TimeTravelerErrorSchema,
        404: EarliestPossibleErrorSchema,
    },
    auth=public_read(),
)
def monthly_series_wide(request, year: int, month: int):
    return _serve_history(
        request,
        mode="monthly",
        year=year,
        month=month,
        game_id=None,
    )


@router.get(
    "/yearly/{year}/{month}/",
    response={
        200: HistoricalLeaderboardResponseSchema,
        400: TimeTravelerErrorSchema,
        404: EarliestPossibleErrorSchema,
    },
    auth=public_read(),
)
def yearly_series_wide(request, year: int, month: int):
    return _serve_history(
        request,
        mode="yearly",
        year=year,
        month=month,
        game_id=None,
    )


@router.get(
    "/cumulative/{year}/{month}/{game_id}/",
    response={
        200: HistoricalLeaderboardResponseSchema,
        400: TimeTravelerErrorSchema,
        404: EarliestPossibleErrorSchema | GameNotFoundErrorSchema,
    },
    auth=public_read(),
)
def cumulative_per_game(request, year: int, month: int, game_id: str):
    game, err = _resolve_or_404(game_id)
    if err is not None:
        return err
    return _serve_history(
        request,
        mode="cumulative",
        year=year,
        month=month,
        game_id=game.id if game else None,
    )


@router.get(
    "/monthly/{year}/{month}/{game_id}/",
    response={
        200: HistoricalLeaderboardResponseSchema,
        400: TimeTravelerErrorSchema,
        404: EarliestPossibleErrorSchema | GameNotFoundErrorSchema,
    },
    auth=public_read(),
)
def monthly_per_game(request, year: int, month: int, game_id: str):
    game, err = _resolve_or_404(game_id)
    if err is not None:
        return err
    return _serve_history(
        request,
        mode="monthly",
        year=year,
        month=month,
        game_id=game.id if game else None,
    )


@router.get(
    "/yearly/{year}/{month}/{game_id}/",
    response={
        200: HistoricalLeaderboardResponseSchema,
        400: TimeTravelerErrorSchema,
        404: EarliestPossibleErrorSchema | GameNotFoundErrorSchema,
    },
    auth=public_read(),
)
def yearly_per_game(request, year: int, month: int, game_id: str):
    game, err = _resolve_or_404(game_id)
    if err is not None:
        return err
    return _serve_history(
        request,
        mode="yearly",
        year=year,
        month=month,
        game_id=game.id if game else None,
    )
