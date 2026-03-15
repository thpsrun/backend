from django.http import HttpRequest

from api.v1.routers.utils import (
    game_leaderboard_cache_key,
    overall_leaderboard_cache_key,
)


def overall_leaderboard_adapter(
    request: HttpRequest,
) -> str:
    return overall_leaderboard_cache_key()


def game_leaderboard_adapter(
    request: HttpRequest,
    game_id: str,
) -> str:
    return game_leaderboard_cache_key(game_id)
