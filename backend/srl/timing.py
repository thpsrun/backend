from collections.abc import Iterable
from dataclasses import dataclass

from srl.models.categories import Categories
from srl.models.games import Games
from srl.models.variable_values import VariableValues


@dataclass(frozen=True)
class ResolvedTiming:
    allowed_methods: list[str]
    required_methods: list[str]
    optional_methods: list[str]
    primary_method: str


def resolve_timing(
    game: Games,
    category: Categories | None,
    is_il: bool,
    variable_values: Iterable[VariableValues],
) -> ResolvedTiming:
    """Resolve the timing tiers for a (game, category, level, variables) selection.

    Walks the VariableValue > Variable > Category > Game precedence chain to resolve
    the allowed window, the strict required subset, and the primary method.

    Arguments:
        game (Games): The game the selection belongs to (root fallback for every tier).
        category (Categories | None): The selected category, or None.
        is_il (bool): Whether the selection is an individual-level run (uses IL roots).
        variable_values (Iterable[VariableValues]): The variable values on the selection,
            most-specific first, used to narrow each tier.

    Returns:
        resolved (ResolvedTiming): The resolved allowed_methods, required_methods,
            optional_methods (allowed minus required), and primary_method.
    """
    values = list(variable_values)
    allowed: list[str] | None = None
    required: list[str] | None = None
    primary: str | None = None

    for vv in values:
        if allowed is None and vv.allowed_methods is not None:
            allowed = list(vv.allowed_methods)
        if required is None and vv.required_methods is not None:
            required = list(vv.required_methods)
        if primary is None and vv.defaulttime:
            primary = vv.defaulttime
        if allowed is not None and required is not None and primary is not None:
            break

    if allowed is None or required is None or primary is None:
        seen: set[str] = set()
        for vv in values:
            var = vv.var
            if var is None or var.pk in seen:
                continue
            seen.add(var.pk)
            if allowed is None and var.allowed_methods is not None:
                allowed = list(var.allowed_methods)
            if required is None and var.required_methods is not None:
                required = list(var.required_methods)
            if primary is None and var.defaulttime:
                primary = var.defaulttime
            if allowed is not None and required is not None and primary is not None:
                break

    if allowed is None and category and category.allowed_methods is not None:
        allowed = list(category.allowed_methods)
    if required is None and category and category.required_methods is not None:
        required = list(category.required_methods)
    if primary is None and category and category.defaulttime:
        primary = category.defaulttime

    if allowed is None:
        allowed = list(game.allowed_methods_il if is_il else game.allowed_methods_fg)
    if required is None:
        required = list(game.required_methods_il if is_il else game.required_methods_fg)
    if primary is None:
        primary = game.idefaulttime if is_il else game.defaulttime

    # Normalize the invariant primary in required subset of allowed.
    allowed_set = list(dict.fromkeys(allowed))
    required = [m for m in (required or []) if m in allowed_set]
    if primary not in required:
        required = [primary] + required
    required = [m for m in allowed_set if m in required]  # keep allowed order, dedupe
    optional = [m for m in allowed_set if m not in required]

    return ResolvedTiming(
        allowed_methods=allowed_set,
        required_methods=required,
        optional_methods=optional,
        primary_method=primary,
    )
