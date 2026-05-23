import os

from celery import shared_task
from django.conf import settings
from django.db import transaction

from srl.models import Games, Players
from srl.srcom._static_fetch import (
    StaticAssetDownloadError,
    download_speedrun_asset,
)
from srl.srcom.reconciliation import reconciliation_upsert_check
from srl.srcom.schema.src import SrcGamesModel
from srl.utils import src_api

BoxartDownloadError = StaticAssetDownloadError


def save_boxart_locally(
    game_id: str,
    url: str,
) -> str:
    """Download a boxart and save it under MEDIA_ROOT/boxart/."""
    data, ext = download_speedrun_asset(url)
    folder_path = os.path.join(settings.MEDIA_ROOT, "boxart")
    try:
        os.makedirs(folder_path, exist_ok=True)
    except OSError as exc:
        raise StaticAssetDownloadError(
            f"cannot create {folder_path}: {exc}",
        ) from exc

    file_path = os.path.join(folder_path, f"{game_id}{ext}")
    try:
        with open(file_path, "wb") as f:
            f.write(data)
    except OSError as exc:
        raise StaticAssetDownloadError(
            f"cannot write {file_path}: {exc}",
        ) from exc
    return f"{settings.MEDIA_URL}boxart/{game_id}{ext}"


@shared_task
def sync_game(
    game_id: str,
) -> None:
    """Creates or updates a `Games` model object based on the `game_id` argument.

    Arguments:
        game_id (str): Unique ID for an SRC game.
    """
    src_data = src_api(f"https://speedrun.com/api/v1/games/{game_id}?embed=platforms")
    assert isinstance(src_data, dict)

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

    src_boxart_url: str = src_game.assets.cover_large.uri
    try:
        boxart_value: str = save_boxart_locally(src_game.id, src_boxart_url)
    except StaticAssetDownloadError:
        boxart_value = src_boxart_url

    with transaction.atomic():
        game = reconciliation_upsert_check(
            Games,
            defaults={
                "name": src_game.names.international,
                "slug": src_game.abbreviation,
                "release": src_game.release_date,
                "defaulttime": src_game.ruleset.defaulttime,
                "boxart": boxart_value,
                "twitch": src_game.names.twitch,
                "pointsmax": points_max,
                "ipointsmax": ipoints_max,
            },
            record_type="game",
            id=src_game.id,
        )

        for plat in src_game.platforms:
            game.platforms.add(plat.id)

        game.moderators.set(
            Players.objects.filter(id__in=src_game.moderators.keys()),
        )
