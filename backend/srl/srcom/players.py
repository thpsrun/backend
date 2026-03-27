import os
import time
from typing import Any

import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction
from langcodes import standardize_tag

from srl.models import CountryCodes, Players
from srl.srcom.schema.src import SrcPlayersModel
from srl.utils import src_api


@shared_task
def sync_players(
    players_data: str | dict,
    download_pfp: bool = False,
) -> None:
    """Creates or updates a `Players` model object based on the `players_data` argument.

    Arguments:
        players_data (str | dict): Either the unique ID (str) of the player or the embedded
            player dict information.
    """
    if isinstance(players_data, str):
        src_data: dict[str, Any] = src_api(
            f"https://speedrun.com/api/v1/users/{players_data}"
        )

        src_player = SrcPlayersModel.model_validate(src_data)
    else:
        src_player = SrcPlayersModel.model_validate(players_data)

    # Early-return guard: skip sync for players with sync_paused=True
    if Players.objects.filter(id=src_player.id, sync_paused=True).exists():
        return  # Player has claimed their account; skip SRC sync

    if src_player.pfp is not None and download_pfp:
        response = requests.get(src_player.pfp)

        while response.status_code == 420 or response.status_code == 503:
            time.sleep(60)
            response = requests.get(src_player.pfp)

        folder_path = os.path.join(settings.STATIC_ROOT, "pfp")
        os.makedirs(folder_path, exist_ok=True)

        file_name = f"{src_player.id}.jpg"
        file_path = os.path.join(folder_path, file_name)

        with open(file_path, "wb") as f:
            f.write(response.content)
    else:
        file_path = None

    c_code = src_player.country_code
    cc = standardize_tag(c_code.replace("/", "_")) if c_code is not None else None

    if isinstance(cc, str) and cc.startswith("ca-"):
        cc = "ca"

    if cc is not None:
        with transaction.atomic():
            CountryCodes.objects.update_or_create(
                id=cc,
                defaults={
                    "name": src_player.country_name,
                },
            )

    try:
        cc_get = CountryCodes.objects.only("id").get(id=cc)
    except CountryCodes.DoesNotExist:
        cc_get = None

    with transaction.atomic():
        Players.objects.update_or_create(
            id=src_player.id,
            defaults={
                "name": src_player.names.international,
                "url": src_player.weblink,
                "countrycode": cc_get,
                "pfp": f"{settings.STATIC_URL}pfp/{src_player.id}.jpg" if download_pfp else None,
                "pronouns": src_player.pronouns,
                "twitch": src_player.twitch_url,
                "youtube": src_player.youtube_url,
            },
        )
