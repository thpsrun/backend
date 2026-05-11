from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from django.db import models, transaction
from django.db.models import QuerySet
from django.utils import timezone

from srl.models import Categories, Games, Levels, Variables, VariableValues

STALE_MESSAGE: str = "Page data is stale! Please reload and try again!"
INVALID_SCOPE_MESSAGE: str = "Invalid Scope Provided: {scope!r}"
MISSING_VAR_ID_MESSAGE: str = "Missing var_id for variable_value scope"
INVALID_TARGET_TYPE_MESSAGE: str = "Invalid target_type: {target_type!r}"


class StaleStateError(Exception):
    """Raised when a write is attempted against data the caller has not refreshed."""


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
) -> tuple[Any, QuerySet[Any]]:
    if target_type == "category":
        obj = Categories.objects.get(id=target_id, game=game)
        return obj, Categories.objects.filter(id=target_id)
    if target_type == "variable_value":
        obj = VariableValues.objects.get(value=target_id, var__game=game)
        return obj, VariableValues.objects.filter(value=target_id)
    raise ValueError(INVALID_TARGET_TYPE_MESSAGE.format(target_type=target_type))


def sorted_for_display(
    queryset: Iterable[Any],
) -> list[Any]:
    items = list(queryset)
    ordered = sorted([i for i in items if i.order > 0], key=lambda x: x.order)
    unordered = sorted([i for i in items if i.order == 0], key=lambda x: x.name)
    return ordered + unordered


def parse_page_loaded_at(
    raw: str | None,
) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = timezone.make_aware(parsed)
    return parsed


def is_stale_against(
    page_loaded_at: datetime | None,
    queryset: QuerySet[Any],
) -> bool:
    if page_loaded_at is None:
        return False
    latest = queryset.aggregate(latest=models.Max("updated_at"))["latest"]
    if latest is None:
        return False
    return latest > page_loaded_at


def create_display(
    game: Games,
) -> dict[str, Any]:
    categories = [
        _item_to_dict(c, c.appear_on_main)
        for c in sorted_for_display(
            Categories.objects.filter(game=game, type="per-game"),
        )
    ]
    levels = [
        _item_to_dict(level, None)
        for level in sorted_for_display(
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
        values = sorted_for_display(var.variablevalues_set.all())  # type: ignore
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
        "page_loaded_at": timezone.now().isoformat(),
    }


def apply_reorder(
    game: Games,
    scope: str,
    ordered_ids: list[str],
    var_id: str | None,
    page_loaded_at: datetime | None,
) -> datetime:
    """Reorders rows in the resolved queryset. Returns the new page-loaded-at stamp."""
    queryset = _resolve_reorder_queryset(game, scope, var_id)
    if is_stale_against(page_loaded_at, queryset):
        raise StaleStateError(STALE_MESSAGE)

    with transaction.atomic():
        list(queryset.select_for_update())
        now = timezone.now()
        for position, pk in enumerate(ordered_ids, start=1):
            queryset.filter(pk=pk).update(
                order=position,
                updated_at=now,
            )
    return timezone.now()


def apply_visibility(
    game: Games,
    target_type: str,
    target_id: str,
    value: bool,
    page_loaded_at: datetime | None,
) -> datetime:
    """Sets `appear_on_main` on the resolved target."""
    obj, stale_qs = _resolve_target(game, target_type, target_id)
    if is_stale_against(page_loaded_at, stale_qs):
        raise StaleStateError(STALE_MESSAGE)
    obj.appear_on_main = value
    obj.save(update_fields=["appear_on_main", "updated_at"])
    return timezone.now()
