from celery import shared_task
from django.db import transaction

from srl.models import Games, Levels
from srl.srcom.reconciliation import reconciliation_upsert_check
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
        src_data = src_api(f"https://speedrun.com/api/v1/levels/{levels_data}")
        assert isinstance(src_data, dict)

        src_level = SrcLevelsModel.model_validate(src_data)
    elif isinstance(levels_data, dict):
        src_level = SrcLevelsModel.model_validate(levels_data)
    else:
        src_level = levels_data

    with transaction.atomic():
        reconciliation_upsert_check(
            Levels,
            defaults={
                "name": src_level.name,
                "game": Games.objects.only("id").get(id=src_level.game),
                "url": src_level.weblink,
                "rules": src_level.rules,
            },
            record_type="level",
            id=src_level.id,
        )
