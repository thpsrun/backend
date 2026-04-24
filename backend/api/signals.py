from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from srl.models.games import Games
from srl.models.players import Players

from api.backability import is_key_backable
from api.models import APIKey, APIKeyRevokedReason

logger = logging.getLogger(__name__)


def _revoke_unbackable_keys(users: list[Any]) -> None:
    """Drop any live APIKey whose owner can no longer back it.

    Touches APIKey rows only - never auth_user or Games.moderators - so the
    handlers that call this can't recurse into themselves.
    """
    if not users:
        return
    keys = APIKey.objects.filter(user__in=users, revoked=False)
    for key in keys:
        if not is_key_backable(key):
            key.revoked = True
            key.revoked_reason = APIKeyRevokedReason.PERMISSION_REVOKED
            key.save(update_fields=["revoked", "revoked_reason"])
            logger.info(
                "auto-revoked key id=%s user=%s reason=permission_revoked",
                key.pk,
                key.user_id,
            )


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
    if not pk_set or reverse:
        return

    user_ids = list(
        Players.objects.filter(pk__in=pk_set)
        .exclude(user__isnull=True)
        .values_list("user_id", flat=True),
    )
    if not user_ids:
        return

    User = get_user_model()
    users = list(User.objects.filter(pk__in=user_ids))
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
