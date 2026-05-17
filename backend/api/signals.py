from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from datetime import timezone as dt_tz
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.db.models.signals import (
    m2m_changed,
    post_delete,
    post_save,
    pre_delete,
    pre_save,
)
from django.dispatch import receiver
from django.utils import timezone
from srl.models import Categories, RunHistory, Variables, VariableValues
from srl.models.games import Games
from srl.models.players import Players
from srl.tasks import rebackfill_game_runs

from api.backability import is_key_backable
from api.models import APIKey, APIKeyRevokedReason
from api.v1.routers.utils.cache_utils import _HISTORY_CACHE_PREFIX

logger = logging.getLogger(__name__)

_GAME_TIMING_FIELDS = frozenset(
    {
        "defaulttime",
        "idefaulttime",
        "allowed_methods_fg",
        "allowed_methods_il",
    }
)


def _revoke_unbackable_keys(
    users: list[Any],
) -> None:
    """Drop any live APIKey whose owner can no longer back it.

    Touches APIKey rows only - never auth_user or Games.moderators - so the
    handlers that call this can't recurse into themselves.
    """
    if not users:
        return
    keys = APIKey.objects.filter(user__in=users, revoked=False)
    for key in keys:
        if is_key_backable(key):
            continue
        if key.revoke(APIKeyRevokedReason.PERMISSION_REVOKED):
            logger.info(
                "auto-revoked key id=%s user=%s reason=permission_revoked",
                key.pk,
                key.user_id,
            )


def _users_from_player_pks(
    pk_set: set[Any],
) -> list[Any]:
    user_ids = list(
        Players.objects.filter(pk__in=pk_set)
        .exclude(user__isnull=True)
        .values_list("user_id", flat=True),
    )
    if not user_ids:
        return []
    User = get_user_model()
    return list(User.objects.filter(pk__in=user_ids))


@receiver(m2m_changed, sender=Games.moderators.through)
def on_moderators_changed(
    sender: Any,
    instance: Any,
    action: str,
    reverse: bool,
    pk_set: set[Any] | None,
    **kwargs: Any,
) -> None:
    if action not in ("post_add", "post_remove"):
        return
    if not pk_set:
        return

    if reverse:
        # Reverse-side: `player.games_moderated.add(game)` or similar. instance is the
        # Player, pk_set is Game PKs. Only the player's owning user needs checking.
        user_id = getattr(instance, "user_id", None)
        if user_id is None:
            return
        User = get_user_model()
        users = list(User.objects.filter(pk=user_id))
    else:
        # Forward-side: `game.moderators.add(player)`. instance is the Game, pk_set is
        # Player PKs. Fan out to each affected player's owning user.
        users = _users_from_player_pks(pk_set)

    _revoke_unbackable_keys(users)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def on_user_saved(
    sender: Any,
    instance: Any,
    created: bool,
    **kwargs: Any,
) -> None:
    if created:
        return
    _revoke_unbackable_keys([instance])


@receiver(pre_delete, sender=Games)
def on_game_deleted(
    sender: Any,
    instance: Any,
    **kwargs: Any,
) -> None:
    """Revoke keys that scope to *only* this game. Without this, the M2M cascade
    silently empties their scope_games and the key's game restriction vanishes
    (effectively broadening the key beyond what the owner asked for).
    """
    try:
        for key in APIKey.objects.filter(scope_games=instance, revoked=False):
            if key.scope_games.count() != 1:
                continue
            if key.revoke(APIKeyRevokedReason.PERMISSION_REVOKED):
                logger.info(
                    "auto-revoked key id=%s user=%s reason=permission_revoked "
                    "cause=last_scope_game_deleted game=%s",
                    key.pk,
                    key.user_id,
                    instance.pk,
                )
    except Exception:
        logger.warning(
            "Failed to revoke keys on game deletion",
            exc_info=True,
            extra={"game_id": getattr(instance, "pk", None)},
        )


def _months_between(
    start: datetime,
    end: datetime,
) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    y, m = start.year, start.month
    end_y, end_m = end.year, end.month
    while (y, m) <= (end_y, end_m):
        months.append((y, m))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return months


def _invalidate_overall(
    scopes: list[str],
    months: list[tuple[int, int]],
) -> None:
    cache = caches["default"]
    keys = [
        f"{_HISTORY_CACHE_PREFIX}:{scope}:cumulative:{y:04d}-{m:02d}"
        for scope in scopes
        for (y, m) in months
    ]
    if keys:
        cache.delete_many(keys)


def _invalidate_earliest(
    scopes: list[str],
) -> None:
    cache = caches["default"]
    cache.delete_many(
        [f"{_HISTORY_CACHE_PREFIX}:earliest:{scope}" for scope in scopes],
    )


def _is_first(
    row: RunHistory,
) -> bool:
    earliest = (
        RunHistory.objects.filter(run=row.run)
        .order_by("start_date")
        .values_list("id", flat=True)
        .first()
    )
    return earliest == row.id  # type: ignore


def _yearly_periods(
    year: int,
    start_month: int,
) -> list[tuple[int, int]]:
    return [(year, m) for m in range(start_month, 13)]


def _invalidate_monthly(
    scopes: list[str],
    months: list[tuple[int, int]],
) -> None:
    cache = caches["default"]
    keys = [
        f"{_HISTORY_CACHE_PREFIX}:{scope}:monthly:{y:04d}-{m:02d}"
        for scope in scopes
        for (y, m) in months
    ]
    if keys:
        cache.delete_many(keys)


def _invalidate_yearly(
    scopes: list[str],
    months: list[tuple[int, int]],
) -> None:
    cache = caches["default"]
    keys = [
        f"{_HISTORY_CACHE_PREFIX}:{scope}:yearly:{y:04d}-{m:02d}"
        for scope in scopes
        for (y, m) in months
    ]
    if keys:
        cache.delete_many(keys)


@receiver(post_delete, sender=RunHistory)
def on_runhistory_deleted(sender, instance: RunHistory, **kwargs) -> None:
    scopes = ["all", instance.run.game.id]

    end = instance.end_date or timezone.now().astimezone(dt_tz.utc)
    cumulative_months = _months_between(instance.start_date, end)
    _invalidate_overall(scopes, cumulative_months)

    # On delete we cannot tell whether this row WAS the first entry, so invalidate
    # monthly/yearly for the row's start_date period unconditionally.
    deleted_month = (instance.start_date.year, instance.start_date.month)
    _invalidate_monthly(scopes, [deleted_month])
    _invalidate_yearly(
        scopes,
        _yearly_periods(instance.start_date.year, instance.start_date.month),
    )

    _invalidate_earliest(scopes)


@receiver(post_save, sender=RunHistory)
def on_runhistory_saved(
    sender,
    instance: RunHistory,
    **kwargs,
) -> None:
    scopes = ["all", instance.run.game.id]

    end = instance.end_date or timezone.now().astimezone(dt_tz.utc)
    cumulative_months = _months_between(instance.start_date, end)
    _invalidate_overall(scopes, cumulative_months)

    if _is_first(instance):
        first_month = (instance.start_date.year, instance.start_date.month)
        _invalidate_monthly(scopes, [first_month])
        _invalidate_yearly(
            scopes,
            _yearly_periods(instance.start_date.year, instance.start_date.month),
        )

    _invalidate_earliest(scopes)


@contextlib.contextmanager
def disable_history_signals():
    post_save.disconnect(on_runhistory_saved, sender=RunHistory)
    post_delete.disconnect(on_runhistory_deleted, sender=RunHistory)
    try:
        yield
    finally:
        post_save.connect(on_runhistory_saved, sender=RunHistory)
        post_delete.connect(on_runhistory_deleted, sender=RunHistory)


# Any timing-shape change on Game/Category/Variable/VariableValue fires
# rebackfill_game_runs, which internally chains recalculate_game_boards.
# One signal, one task, one source of truth.
_CHILD_TIMING_FIELDS = frozenset({"defaulttime", "allowed_methods"})


def _check_dirty(
    instance: Any,
    sender: type,
    fields: frozenset[str],
) -> bool:
    if not instance.pk:
        return False
    try:
        prev = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return False
    return any(getattr(prev, f, None) != getattr(instance, f, None) for f in fields)


@receiver(pre_save, sender=Games)
def _capture_game_timing_change(
    sender: Any,
    instance: Games,
    **kwargs: Any,
) -> None:
    instance._timing_dirty = _check_dirty(instance, Games, _GAME_TIMING_FIELDS)  # type: ignore


@receiver(post_save, sender=Games)
def _fire_rebackfill_on_game_timing_change(
    sender: Any,
    instance: Games,
    created: bool,
    **kwargs: Any,
) -> None:
    if created:
        return
    if getattr(instance, "_timing_dirty", False):
        rebackfill_game_runs.delay(instance.slug)


@receiver(pre_save, sender=Categories)
def _capture_category_timing_change(
    sender: Any,
    instance: Categories,
    **kwargs: Any,
) -> None:
    instance._timing_dirty = _check_dirty(  # type: ignore
        instance,
        Categories,
        _CHILD_TIMING_FIELDS,
    )


@receiver(post_save, sender=Categories)
def _fire_rebackfill_on_category_timing_change(
    sender: Any,
    instance: Categories,
    created: bool,
    **kwargs: Any,
) -> None:
    if created:
        return
    if not instance.game:
        return
    if getattr(instance, "_timing_dirty", False):
        rebackfill_game_runs.delay(instance.game.slug)


@receiver(pre_save, sender=Variables)
def _capture_variable_timing_change(
    sender: Any,
    instance: Variables,
    **kwargs: Any,
) -> None:
    instance._timing_dirty = _check_dirty(  # type: ignore
        instance,
        Variables,
        _CHILD_TIMING_FIELDS,
    )


@receiver(post_save, sender=Variables)
def _fire_rebackfill_on_variable_timing_change(
    sender: Any,
    instance: Variables,
    created: bool,
    **kwargs: Any,
) -> None:
    if created:
        return
    if not instance.game:
        return
    if getattr(instance, "_timing_dirty", False):
        rebackfill_game_runs.delay(instance.game.slug)


@receiver(pre_save, sender=VariableValues)
def _capture_value_timing_change(
    sender: Any,
    instance: VariableValues,
    **kwargs: Any,
) -> None:
    instance._timing_dirty = _check_dirty(  # type: ignore
        instance,
        VariableValues,
        _CHILD_TIMING_FIELDS,
    )


@receiver(post_save, sender=VariableValues)
def _fire_rebackfill_on_value_timing_change(
    sender: Any,
    instance: VariableValues,
    created: bool,
    **kwargs: Any,
) -> None:
    if created:
        return
    if not instance.var or not instance.var.game:
        return
    if getattr(instance, "_timing_dirty", False):
        rebackfill_game_runs.delay(instance.var.game.slug)
