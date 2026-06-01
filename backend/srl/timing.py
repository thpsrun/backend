from dataclasses import dataclass
from typing import Iterable

from srl.models.categories import Categories
from srl.models.games import Games
from srl.models.variable_values import VariableValues


@dataclass(frozen=True)
class ResolvedTiming:
    required_methods: list[str]
    primary_method: str


def resolve_timing(
    game: Games,
    category: Categories | None,
    is_il: bool,
    variable_values: Iterable[VariableValues],
) -> ResolvedTiming:
    # Precedence: VariableValue > Variable > Category > Game.
    values = list(variable_values)
    required: list[str] | None = None
    primary: str | None = None

    for vv in values:
        if required is None and vv.required_methods is not None:
            required = list(vv.required_methods)
        if primary is None and vv.defaulttime:
            primary = vv.defaulttime
        if required is not None and primary is not None:
            break

    if required is None or primary is None:
        seen: set[str] = set()
        for vv in values:
            var = vv.var
            if var is None or var.pk in seen:
                continue
            seen.add(var.pk)
            if required is None and var.required_methods is not None:
                required = list(var.required_methods)
            if primary is None and var.defaulttime:
                primary = var.defaulttime
            if required is not None and primary is not None:
                break

    if required is None and category and category.required_methods is not None:
        required = list(category.required_methods)
    if primary is None and category and category.defaulttime:
        primary = category.defaulttime

    if required is None:
        required = list(game.required_methods_il if is_il else game.required_methods_fg)
    if primary is None:
        primary = game.idefaulttime if is_il else game.defaulttime

    return ResolvedTiming(
        required_methods=required,
        primary_method=primary,
    )
