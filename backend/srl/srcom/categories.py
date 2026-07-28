from celery import shared_task
from django.db import transaction
from srl.models import Categories, Games
from srl.srcom.reconciliation import reconciliation_upsert_check
from srl.srcom.schema.src import SrcCategoriesModel
from srl.utils import src_api


@shared_task(pydantic=True)
def sync_categories(
    categories_data: str | dict | SrcCategoriesModel,
    game_id: str | None = None,
) -> None:
    """Creates or updates a `Categories` model object based on the `categories_data` argument.

    Arguments:
        categories_data (str | dict | SrcCategoriesModel): Either the unique ID (str) of the
            category or the embedded category dict/model.
        game_id (str | None): Owning game id. Callers that pass an embedded category dict (which
            omits the game) supply this so the game FK is set directly, instead of issuing a
            redundant SRC re-fetch just to resolve it.
    """
    if isinstance(categories_data, str):
        src_data = src_api(
            f"https://speedrun.com/api/v1/categories/{categories_data}?embed=game"
        )
        assert isinstance(src_data, dict)

        src_category = SrcCategoriesModel.model_validate(src_data)
    elif isinstance(categories_data, dict):
        src_category = SrcCategoriesModel.model_validate(categories_data)
    else:
        src_category = categories_data

    resolved_game_id = src_category.game.id if src_category.game else game_id
    if resolved_game_id is None:
        # Neither an embedded game nor a caller-supplied id: fall back to a single SRC re-fetch.
        src_data = src_api(
            f"https://speedrun.com/api/v1/categories/{src_category.id}?embed=game"
        )
        assert isinstance(src_data, dict)
        src_category = SrcCategoriesModel.model_validate(src_data)
        resolved_game_id = src_category.game.id if src_category.game else None

    with transaction.atomic():
        reconciliation_upsert_check(
            Categories,
            defaults={
                "name": src_category.name,
                "game": Games.objects.only("id").get(id=resolved_game_id),
                "type": src_category.type,
                "url": src_category.weblink,
                "rules": src_category.rules,
            },
            record_type="category",
            id=src_category.id,
        )
