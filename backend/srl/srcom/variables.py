from celery import shared_task
from django.db import transaction

from srl.models import Games, Variables, VariableValues
from srl.srcom.schema.src import SrcVariablesModel
from srl.utils import src_api


@shared_task(pydantic=True)
def sync_variables(
    variables_data: str | dict | SrcVariablesModel,
) -> None:
    """Creates or updates a `Variables` model object based on the `variables_data` argument.

    Arguments:
        variables_data (str | dict): Either the unique ID (str) of the variable or the embedded
            variable dict information.
    """
    if isinstance(variables_data, str):
        src_data: dict[dict, str] = src_api(
            f"https://speedrun.com/api/v1/variables/{variables_data}"
        )

        src_variable = SrcVariablesModel.model_validate(src_data)
    elif isinstance(variables_data, dict):
        src_variable = SrcVariablesModel.model_validate(variables_data)
    else:
        src_variable = variables_data

    with transaction.atomic():
        Variables.objects.update_or_create(
            id=src_variable.id,
            defaults={
                "name": src_variable.name,
                "game": Games.objects.only("id").get(id=src_variable.game),
                "cat": src_variable.category,
                "scope": src_variable.scope.type,
                "level": src_variable.scope.level,
            },
        )

    # Only subcategory variables have selectable values to sync
    if src_variable.is_subcategory:
        sync_values.delay(src_variable.model_dump())


@shared_task(pydantic=True)
def sync_values(
    src_variable: SrcVariablesModel | dict,
) -> None:
    if isinstance(src_variable, dict):
        src_variable = SrcVariablesModel.model_validate(src_variable)

    for value_id, value_data in src_variable.values.values.items():
        with transaction.atomic():
            VariableValues.objects.update_or_create(
                value=value_id,
                defaults={
                    "var": Variables.objects.only("id").get(id=src_variable.id),
                    "name": value_data.label,
                    "rules": value_data.rules,
                },
            )
