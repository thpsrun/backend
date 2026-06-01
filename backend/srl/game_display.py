from __future__ import annotations

from typing import Any, Iterable

from django.db import transaction
from django.db.models import QuerySet

from srl.models import Categories, Games, Levels, Variables, VariableValues

INVALID_SCOPE_MESSAGE: str = "Invalid Scope Provided: {scope!r}"
MISSING_VAR_ID_MESSAGE: str = "Missing var_id for variable_value scope"
INVALID_TARGET_TYPE_MESSAGE: str = "Invalid target_type: {target_type!r}"


def _item_to_dict(
    obj: Any,
    appear_on_main: bool | None,
) -> dict[str, Any]:
    obj_id = getattr(obj, "value", None) or obj.pk
    return {
        "id": obj_id,
        "name": obj.name,
        "order": obj.order,
        "appear_on_main": appear_on_main,
    }


def _resolve_reorder_queryset(
    game: Games,
    scope: str,
    var_id: str | None,
) -> QuerySet[Any]:
    if scope == "category":
        return Categories.objects.filter(game=game, type="per-game")
    if scope == "level":
        return Levels.objects.filter(game=game)
    if scope == "variable_value":
        if not var_id:
            raise ValueError(MISSING_VAR_ID_MESSAGE)
        return VariableValues.objects.filter(var__game=game, var_id=var_id)
    raise ValueError(INVALID_SCOPE_MESSAGE.format(scope=scope))


def _resolve_target(
    game: Games,
    target_type: str,
    target_id: str,
) -> Any:
    if target_type == "category":
        return Categories.objects.get(id=target_id, game=game)
    if target_type == "variable_value":
        return VariableValues.objects.get(value=target_id, var__game=game)
    raise ValueError(INVALID_TARGET_TYPE_MESSAGE.format(target_type=target_type))


def sort_display(
    queryset: Iterable[Any],
) -> list[Any]:
    items = list(queryset)
    ordered = sorted([i for i in items if i.order > 0], key=lambda x: x.order)
    unordered = sorted([i for i in items if i.order == 0], key=lambda x: x.name)
    return ordered + unordered


def create_display(
    game: Games,
) -> dict[str, Any]:
    categories = [
        _item_to_dict(c, c.appear_on_main)
        for c in sort_display(
            Categories.objects.filter(game=game, type="per-game"),
        )
    ]
    levels = [
        _item_to_dict(level, None)
        for level in sort_display(
            Levels.objects.filter(game=game),
        )
    ]
    variable_groups: list[dict[str, Any]] = []
    for var in (
        Variables.objects.filter(game=game)
        .select_related("cat")
        .order_by("name")
        .prefetch_related("variablevalues_set")
    ):
        values = sort_display(var.variablevalues_set.all())  # type: ignore
        if not values:
            continue
        variable_groups.append(
            {
                "variable_id": var.id,
                "variable_name": var.name,
                "values": [_item_to_dict(v, v.appear_on_main) for v in values],
            },
        )

    return {
        "game_id": game.id,
        "game_name": game.name,
        "categories": categories,
        "levels": levels,
        "variable_groups": variable_groups,
    }


def apply_reorder(
    game: Games,
    scope: str,
    ordered_ids: list[str],
    var_id: str | None,
) -> None:
    """Reorders rows in the resolved queryset."""
    queryset = _resolve_reorder_queryset(game, scope, var_id)

    with transaction.atomic():
        list(queryset.select_for_update())
        for position, pk in enumerate(ordered_ids, start=1):
            queryset.filter(pk=pk).update(order=position)


def apply_visibility(
    game: Games,
    target_type: str,
    target_id: str,
    value: bool,
) -> None:
    """Sets `appear_on_main` on the resolved target."""
    obj = _resolve_target(game, target_type, target_id)
    obj.appear_on_main = value
    obj.save(update_fields=["appear_on_main", "updated_at"])
