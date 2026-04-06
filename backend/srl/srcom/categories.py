from typing import Any

from celery import shared_task
from django.db import transaction

from srl.models import Categories, Games
from srl.srcom.schema.src import SrcCategoriesModel
from srl.utils import src_api


@shared_task(pydantic=True)
def sync_categories(
    categories_data: str | dict | SrcCategoriesModel,
) -> None:
    """Creates or updates a `Categories` model object based on the `categories_data` argument.

    Arguments:
        categories_data (str | dict): Either the unique ID (str) of the category or the embedded
            category dict information.
    """
    if isinstance(categories_data, str):
        src_data: dict[str, Any] = src_api(
            f"https://speedrun.com/api/v1/categories/{categories_data}?embed=game"
        )

        src_category = SrcCategoriesModel.model_validate(src_data)
    elif isinstance(categories_data, dict):
        src_category = SrcCategoriesModel.model_validate(categories_data)
    else:
        src_category = categories_data

    with transaction.atomic():
        Categories.objects.update_or_create(
            id=src_category.id,
            defaults={
                "name": src_category.name,
                "game": Games.objects.only("id").get(src_category.game.id),
                "type": src_category.type,
                "url": src_category.weblink,
                "rules": src_category.rules,
            },
        )
