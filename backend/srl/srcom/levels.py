from typing import Any

from celery import shared_task
from django.db import transaction

from srl.models import Games, Levels
from srl.srcom.schema.src import SrcLevelsModel
from srl.utils import src_api


@shared_task(pydantic=True)
def sync_levels(
    levels_data: str | dict | SrcLevelsModel,
) -> None:
    """Creates or updates a `Levels` model object based on the `levels_data` argument.

    Arguments:
        levels_data (str | dict): Either the unique ID (str) of the level or the embedded
            level dict information.
    """
    if isinstance(levels_data, str):
        src_data: dict[str, Any] = src_api(
            f"https://speedrun.com/api/v1/levels/{levels_data}"
        )

        src_level = SrcLevelsModel.model_validate(src_data)
    elif isinstance(levels_data, dict):
        src_level = SrcLevelsModel.model_validate(levels_data)
    else:
        src_level = levels_data

    with transaction.atomic():
        Levels.objects.update_or_create(
            id=src_level.id,
            defaults={
                "name": src_level.name,
                "game": Games.objects.only("id").get(src_level.game),
                "url": src_level.weblink,
                "rules": src_level.rules,
            },
        )
