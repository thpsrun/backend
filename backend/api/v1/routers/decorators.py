from django.http import HttpRequest

from api.v1.routers.utils import (
    game_categories_cache_key,
    game_leaderboard_cache_key,
    game_levels_cache_key,
    overall_leaderboard_cache_key,
)


def categories_adapter(
    request: HttpRequest,
    game_id: str,
) -> str:
    return game_categories_cache_key(game_id)


def levels_adapter(
    request: HttpRequest,
    level_id: str,
) -> str:
    return game_levels_cache_key(level_id)


def overall_leaderboard_adapter(
    request: HttpRequest,
) -> str:
    return overall_leaderboard_cache_key()


def game_leaderboard_adapter(
    request: HttpRequest,
    game_id: str,
) -> str:
    return game_leaderboard_cache_key(game_id)
