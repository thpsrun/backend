from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from datetime import timezone as dt_tz
from typing import Any

from auditlog.context import get_actor
from auditlog.models import GameAuditEvent
from auditlog.recorders import record_event
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.db import transaction
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
        "required_methods_fg",
        "required_methods_il",
    },
)
_CHILD_TIMING_FIELDS = frozenset({"defaulttime", "required_methods"})


def _actor_user_id() -> int | None:
    """Read the current actor's user primary key for Celery dispatch attribution."""

    actor = get_actor() or {}
    actor_user = actor.get("user")
    return getattr(actor_user, "pk", None)


def _record_on_commit(**kwargs: Any) -> None:
    """Wrap record_event in transaction.on_commit so audit rows aren't written inside a transaction
    that might still roll back. Safe even outside a transaction (executes immediately).
    """

    transaction.on_commit(lambda: record_event(**kwargs))


def _dispatch_rebackfill_on_commit(
    slug: str,
    *,
    triggered_by: str,
    actor_user_id: int | None,
) -> None:
    """Defer Celery dispatch until the originating transaction commits so the
    worker doesn't read stale rows."""

    transaction.on_commit(
        lambda: rebackfill_game_runs.delay(
            slug,
            triggered_by=triggered_by,
            actor_user_id=actor_user_id,
        ),
    )


def _revoke_unbackable_keys(
    users: list[Any],
) -> None:
    """Drop any live APIKey whose owner can no longer back it."""

    if not users:
        return
    keys = APIKey.objects.filter(user__in=users, revoked=False).prefetch_related(
        "scope_games",
    )
    for key in keys:
        if is_key_backable(key):
            continue
        scoped_games = list(key.scope_games.all())
        if key.revoke(APIKeyRevokedReason.PERMISSION_REVOKED):
            logger.info(
                "auto-revoked key id=%s user=%s reason=permission_revoked",
                key.pk,
                key.user_id,
            )
            for game in scoped_games:
                _record_on_commit(
                    game=game,
                    event_type=GameAuditEvent.EventType.APIKEY_REVOKED,
                    summary=f"API key revoked: {key.label or key.pk}",
                    target=key,
                    payload={
                        "key_id": key.pk,
                        "key_label": key.label,
                        "user_id": key.user_id,
                        "reason": APIKeyRevokedReason.PERMISSION_REVOKED.value,
                    },
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


@receiver(
    m2m_changed,
    sender=Games.moderators.through,
    dispatch_uid="api.signals.on_moderators_changed",
)
def on_moderators_changed(
    sender: Any,
    instance: Any,
    action: str,
    reverse: bool,
    pk_set: set[Any] | None,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw"):
        return

    if action == "pre_clear":
        if reverse:
            player = instance
            game_ids = list(player.moderated_games.values_list("pk", flat=True))
            for game_id in game_ids:
                _record_on_commit(
                    game=game_id,
                    event_type=GameAuditEvent.EventType.MODERATOR_REMOVED,
                    summary=(
                        f"Moderator remove (clear): "
                        f"{getattr(player, 'name', '') or player.pk}"
                    ),
                    target=player,
                    payload={
                        "player_id": player.pk,
                        "player_name": getattr(player, "name", None),
                        "user_id": getattr(player, "user_id", None),
                        "cause": "pre_clear",
                    },
                )
            user_id = getattr(player, "user_id", None)
            if user_id is None:
                return
            User = get_user_model()
            users = list(User.objects.filter(pk=user_id))
        else:
            game = instance
            players = list(game.moderators.all())
            for player in players:
                _record_on_commit(
                    game=game,
                    event_type=GameAuditEvent.EventType.MODERATOR_REMOVED,
                    summary=(
                        f"Moderator remove (clear): "
                        f"{getattr(player, 'name', '') or player.pk}"
                    ),
                    target=player,
                    payload={
                        "player_id": player.pk,
                        "player_name": getattr(player, "name", None),
                        "user_id": getattr(player, "user_id", None),
                        "cause": "pre_clear",
                    },
                )
            users = _users_from_player_pks({p.pk for p in players})
        _revoke_unbackable_keys(users)
        return

    if action not in ("post_add", "post_remove"):
        return
    if not pk_set:
        return

    event_type = (
        GameAuditEvent.EventType.MODERATOR_ADDED
        if action == "post_add"
        else GameAuditEvent.EventType.MODERATOR_REMOVED
    )

    if reverse:
        # Reverse-side: instance is the Player, pk_set is Game PKs.
        player = instance
        for game_id in pk_set:
            _record_on_commit(
                game=game_id,
                event_type=event_type,
                summary=(
                    f"Moderator {action[5:]}: "
                    f"{getattr(player, 'name', '') or player.pk}"
                ),
                target=player,
                payload={
                    "player_id": player.pk,
                    "player_name": getattr(player, "name", None),
                    "user_id": getattr(player, "user_id", None),
                },
            )
        user_id = getattr(player, "user_id", None)
        if user_id is None:
            return
        User = get_user_model()
        users = list(User.objects.filter(pk=user_id))
    else:
        # Forward-side: instance is the Game, pk_set is Player PKs.
        game = instance
        players = list(Players.objects.filter(pk__in=pk_set))
        for player in players:
            _record_on_commit(
                game=game,
                event_type=event_type,
                summary=(
                    f"Moderator {action[5:]}: "
                    f"{getattr(player, 'name', '') or player.pk}"
                ),
                target=player,
                payload={
                    "player_id": player.pk,
                    "player_name": getattr(player, "name", None),
                    "user_id": getattr(player, "user_id", None),
                },
            )
        users = _users_from_player_pks(pk_set)

    _revoke_unbackable_keys(users)


@receiver(
    post_save,
    sender=settings.AUTH_USER_MODEL,
    dispatch_uid="api.signals.on_user_saved",
)
def on_user_saved(
    sender: Any,
    instance: Any,
    created: bool,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw"):
        return
    if created:
        return
    _revoke_unbackable_keys([instance])


@receiver(
    pre_delete,
    sender=Games,
    dispatch_uid="api.signals.on_game_deleted",
)
def on_game_deleted(
    sender: Any,
    instance: Any,
    **kwargs: Any,
) -> None:
    """Revoke keys that scope to *only* this game."""

    try:
        for key in APIKey.objects.filter(scope_games=instance, revoked=False):
            if key.scope_games.count() != 1:
                continue
            try:
                record_event(
                    game=instance,
                    event_type=GameAuditEvent.EventType.APIKEY_REVOKED,
                    summary=(
                        f"API key revoked (last scoped game deleted): "
                        f"{key.label or key.pk}"
                    ),
                    target=key,
                    payload={
                        "key_id": key.pk,
                        "key_label": key.label,
                        "user_id": key.user_id,
                        "reason": APIKeyRevokedReason.PERMISSION_REVOKED.value,
                        "cause": "last_scope_game_deleted",
                    },
                )
            except Exception:
                logger.exception(
                    "on_game_deleted audit write failed",
                    extra={
                        "game_id": getattr(instance, "pk", None),
                        "key_id": getattr(key, "pk", None),
                    },
                )
            if key.revoke(APIKeyRevokedReason.PERMISSION_REVOKED):
                logger.info(
                    "auto-revoked key id=%s user=%s reason=permission_revoked "
                    "cause=last_scope_game_deleted game=%s",
                    key.pk,
                    key.user_id,
                    instance.pk,
                )
    except Exception:
        logger.exception(
            "Failed to revoke keys on game deletion",
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


@receiver(
    post_delete,
    sender=RunHistory,
    dispatch_uid="api.signals.on_runhistory_deleted",
)
def on_runhistory_deleted(sender, instance: RunHistory, **kwargs) -> None:
    if kwargs.get("raw"):
        return
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


@receiver(
    post_save,
    sender=RunHistory,
    dispatch_uid="api.signals.on_runhistory_saved",
)
def on_runhistory_saved(
    sender,
    instance: RunHistory,
    **kwargs,
) -> None:
    if kwargs.get("raw"):
        return
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


def _check_dirty(
    instance: Any,
    sender: type,
    fields: frozenset[str],
) -> tuple[bool, dict[str, dict[str, Any]]]:
    """Returns (any_changed, {field: {"previous": old, "new": new}, ...})."""
    if not instance.pk:
        return False, {}
    try:
        prev = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return False, {}
    diff: dict[str, dict[str, Any]] = {}
    for f in fields:
        old = getattr(prev, f, None)
        new = getattr(instance, f, None)
        if old != new:
            diff[f] = {"previous": old, "new": new}
    return bool(diff), diff


@receiver(
    pre_save,
    sender=Games,
    dispatch_uid="api.signals._capture_game_timing_change",
)
def _capture_game_timing_change(
    sender: Any,
    instance: Games,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw"):
        return
    dirty, diff = _check_dirty(instance, Games, _GAME_TIMING_FIELDS)
    instance._timing_dirty = dirty  # type: ignore
    instance._timing_diff = diff  # type: ignore


@receiver(
    post_save,
    sender=Games,
    dispatch_uid="api.signals._fire_rebackfill_game_change",
)
def _fire_rebackfill_game_change(
    sender: Any,
    instance: Games,
    created: bool,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw"):
        return
    if created:
        return
    if getattr(instance, "_timing_dirty", False):
        diff = getattr(instance, "_timing_diff", {}) or {}
        for field, change in diff.items():
            _record_on_commit(
                game=instance,
                event_type=GameAuditEvent.EventType.TIMING_CONFIG_CHANGE,
                summary=f"Games.{field} changed",
                target=instance,
                payload={
                    "model": "Games",
                    "field": field,
                    "previous": change["previous"],
                    "new": change["new"],
                    "recalc_dispatched": field in {"defaulttime", "idefaulttime"},
                    "rebackfill_dispatched": True,
                },
            )
        triggered_by = next(
            (f"Games.{field}" for field in diff),
            "Games",
        )
        _dispatch_rebackfill_on_commit(
            instance.slug,
            triggered_by=triggered_by,
            actor_user_id=_actor_user_id(),
        )


@receiver(
    pre_save,
    sender=Categories,
    dispatch_uid="api.signals._capture_category_timing_change",
)
def _capture_category_timing_change(
    sender: Any,
    instance: Categories,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw"):
        return
    dirty, diff = _check_dirty(instance, Categories, _CHILD_TIMING_FIELDS)
    instance._timing_dirty = dirty  # type: ignore
    instance._timing_diff = diff  # type: ignore


@receiver(
    post_save,
    sender=Categories,
    dispatch_uid="api.signals._fire_rebackfill_category_change",
)
def _fire_rebackfill_category_change(
    sender: Any,
    instance: Categories,
    created: bool,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw"):
        return
    if created:
        return
    if not instance.game:
        return
    if getattr(instance, "_timing_dirty", False):
        diff = getattr(instance, "_timing_diff", {}) or {}
        for field, change in diff.items():
            _record_on_commit(
                game=instance.game,
                event_type=GameAuditEvent.EventType.TIMING_CONFIG_CHANGE,
                summary=f"Categories[{instance.pk}].{field} changed",
                target=instance,
                payload={
                    "model": "Categories",
                    "field": field,
                    "previous": change["previous"],
                    "new": change["new"],
                    "recalc_dispatched": field == "defaulttime",
                    "rebackfill_dispatched": True,
                },
            )
        triggered_by = next(
            (f"Categories.{field}" for field in diff),
            "Categories",
        )
        _dispatch_rebackfill_on_commit(
            instance.game.slug,
            triggered_by=triggered_by,
            actor_user_id=_actor_user_id(),
        )


@receiver(
    pre_save,
    sender=Variables,
    dispatch_uid="api.signals._capture_variable_timing_change",
)
def _capture_variable_timing_change(
    sender: Any,
    instance: Variables,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw"):
        return
    dirty, diff = _check_dirty(instance, Variables, _CHILD_TIMING_FIELDS)
    instance._timing_dirty = dirty  # type: ignore
    instance._timing_diff = diff  # type: ignore


@receiver(
    post_save,
    sender=Variables,
    dispatch_uid="api.signals._fire_rebackfill_variable_change",
)
def _fire_rebackfill_variable_change(
    sender: Any,
    instance: Variables,
    created: bool,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw"):
        return
    if created:
        return
    if not instance.game:
        return
    if getattr(instance, "_timing_dirty", False):
        diff = getattr(instance, "_timing_diff", {}) or {}
        for field, change in diff.items():
            _record_on_commit(
                game=instance.game,
                event_type=GameAuditEvent.EventType.TIMING_CONFIG_CHANGE,
                summary=f"Variables[{instance.pk}].{field} changed",
                target=instance,
                payload={
                    "model": "Variables",
                    "field": field,
                    "previous": change["previous"],
                    "new": change["new"],
                    "recalc_dispatched": field == "defaulttime",
                    "rebackfill_dispatched": True,
                },
            )
        triggered_by = next(
            (f"Variables.{field}" for field in diff),
            "Variables",
        )
        _dispatch_rebackfill_on_commit(
            instance.game.slug,
            triggered_by=triggered_by,
            actor_user_id=_actor_user_id(),
        )


@receiver(
    pre_save,
    sender=VariableValues,
    dispatch_uid="api.signals._capture_value_timing_change",
)
def _capture_value_timing_change(
    sender: Any,
    instance: VariableValues,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw"):
        return
    dirty, diff = _check_dirty(instance, VariableValues, _CHILD_TIMING_FIELDS)
    instance._timing_dirty = dirty  # type: ignore
    instance._timing_diff = diff  # type: ignore


@receiver(
    post_save,
    sender=VariableValues,
    dispatch_uid="api.signals._fire_rebackfill_value_change",
)
def _fire_rebackfill_value_change(
    sender: Any,
    instance: VariableValues,
    created: bool,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw"):
        return
    if created:
        return
    if not instance.var or not instance.var.game:
        return
    if getattr(instance, "_timing_dirty", False):
        diff = getattr(instance, "_timing_diff", {}) or {}
        game = instance.var.game
        for field, change in diff.items():
            _record_on_commit(
                game=game,
                event_type=GameAuditEvent.EventType.TIMING_CONFIG_CHANGE,
                summary=f"VariableValues[{instance.pk}].{field} changed",
                target=instance,
                payload={
                    "model": "VariableValues",
                    "field": field,
                    "previous": change["previous"],
                    "new": change["new"],
                    "recalc_dispatched": field == "defaulttime",
                    "rebackfill_dispatched": True,
                },
            )
        triggered_by = next(
            (f"VariableValues.{field}" for field in diff),
            "VariableValues",
        )
        _dispatch_rebackfill_on_commit(
            game.slug,
            triggered_by=triggered_by,
            actor_user_id=_actor_user_id(),
        )
