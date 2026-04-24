from __future__ import annotations

from typing import Any

from srl.models.games import Games

from api.models import APIKey
from api.permissions import CAPABILITY_SCOPED

# Scopes that check if the user owns the guide or the run; if they do, then it wil give the ability
# to modify as needed.
_OWNED_SCOPES = frozenset(
    {
        "runs.edit_own",
        "guides.edit_own",
        "guides.delete_own",
    }
)


def is_key_backable(key: APIKey) -> bool:
    """Can the key's owner still do everything this key was issued to do?"""
    user = key.user
    if not user.is_active:
        return False

    caps: list[str] = list(key.scope_capabilities or [])
    games = list(key.scope_games.all())

    if not caps and not games:
        return True

    if not caps:
        # No capabilities listed means the key piggybacks on whatever the owner can do on these
        # games. If they're no longer a mod, every power is gone.
        return all(user.has_perm("games.manage", g) for g in games)

    for cap in caps:
        if not CAPABILITY_SCOPED.get(cap, False):
            if not user.has_perm(cap):
                return False
            continue
        if cap in _OWNED_SCOPES:
            if not user.has_perm("profile.edit_own"):
                return False
            continue
        if games:
            # Everything not mentioned requires game-mod powers.
            if not all(user.has_perm("games.manage", g) for g in games):
                return False
        else:
            if not _has_cap_somewhere(user, cap):
                return False
    return True


def _has_cap_somewhere(user: Any, capability: str) -> bool:
    if capability in _OWNED_SCOPES:
        return user.has_perm("profile.edit_own")
    for g in Games.objects.all().iterator():
        if user.has_perm("games.manage", g):
            return True
    return False
