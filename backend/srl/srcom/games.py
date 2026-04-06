from typing import Any

from celery import shared_task
from django.conf import settings
from django.db import transaction
from srl.models import Games
from srl.srcom.schema.src import SrcGamesModel
from srl.utils import src_api


@shared_task
def sync_game(
    game_id: str,
) -> None:
    """Creates or updates a `Games` model object based on the `game_id` argument.

    Arguments:
        game_id (str): Unique ID for an SRC game.
    """
    src_data: dict[str, Any] = src_api(
        f"https://speedrun.com/api/v1/games/{game_id}?embed=platforms"
    )

    src_game = SrcGamesModel.model_validate(src_data)

    # Category Extensions games cap at a lower max (e.g. 50) vs standard FG/IL
    points_max = (
        settings.POINTS_MAX_FG
        if "category extensions" not in src_game.names.international.lower()
        else settings.POINTS_MAX_CE
    )

    ipoints_max = (
        settings.POINTS_MAX_IL
        if "category extensions" not in src_game.names.international.lower()
        else settings.POINTS_MAX_CE
    )

    with transaction.atomic():
        game, _ = Games.objects.update_or_create(
            id=src_game.id,
            defaults={
                "name": src_game.names.international,
                "slug": src_game.abbreviation,
                "release": src_game.release_date,
                "defaulttime": src_game.ruleset.defaulttime,
                "boxart": src_game.assets.cover_large.uri,
                "twitch": src_game.names.twitch,
                "pointsmax": points_max,
                "ipointsmax": ipoints_max,
            },
        )

        for plat in src_game.platforms:
            game.platforms.add(plat.id)
