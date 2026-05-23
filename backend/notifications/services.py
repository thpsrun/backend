from typing import Any

from django.db import transaction

from notifications import registry
from notifications.models import Notification, NotificationPreference


def _is_enabled_for(
    user_id: int,
    kind_key: str,
) -> bool:
    """Return True if the user has the kind (or its group) enabled."""
    kind = registry.get(kind_key)
    if kind is None:
        return False

    if kind.group is not None:
        pref_key = kind.group
        group = registry.get_group(kind.group)
        assert group is not None
        default_enabled = group.default_enabled
    else:
        pref_key = kind.key
        default_enabled = kind.default_enabled

    pref = (
        NotificationPreference.objects.filter(user_id=user_id, type=pref_key)
        .values_list("enabled", flat=True)
        .first()
    )
    if pref is None:
        return default_enabled
    return bool(pref)


def create_notification(
    *,
    user: Any,
    kind: str,
    title: str,
    body: str = "",
    target_type: str = "",
    target_id: str = "",
    payload: dict | None = None,
) -> Notification | None:
    if not registry.is_registered(kind):
        raise ValueError(f"Unknown notification kind: {kind}")
    if user is None or getattr(user, "pk", None) is None:
        return None

    user_id = user.pk
    if not _is_enabled_for(user_id, kind):
        return None

    pending = Notification(
        user_id=user_id,
        type=kind,
        title=title[:255],
        body=body,
        target_type=target_type[:50],
        target_id=target_id[:100],
        payload=payload or {},
    )

    def _write() -> None:
        pending.save()

    transaction.on_commit(_write)
    return pending
