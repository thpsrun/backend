from __future__ import annotations

from typing import Any

from api.models import APIKey
from api.permissions import CAPABILITY_SCOPED, MOD_SCOPES, PLAYER_SCOPES, SU_ONLY_SCOPES


def is_key_backable(
    key: APIKey,
) -> bool:
    """Used to determine if the keys owner can still do everything or not."""
    user = key.user
    if not user.is_active:
        return False

    caps: list[str] = list(key.scope_capabilities or [])
    games = list(key.scope_games.all())

    if not caps and not games:
        return True

    if not caps:
        return all(user.has_perm("games.manage", g) for g in games)

    for cap in caps:
        if not CAPABILITY_SCOPED.get(cap, False):
            if not user.has_perm(cap):
                return False
            continue
        if cap in PLAYER_SCOPES:
            if not user.has_perm("profile.edit_own"):
                return False
            continue
        if cap in SU_ONLY_SCOPES:
            if not user.is_superuser:
                return False
            continue
        if cap in MOD_SCOPES:
            if games:
                if not all(user.has_perm("games.manage", g) for g in games):
                    return False
            else:
                if not _user_moderates_any_game(user):
                    return False
            continue
    return True


def _user_moderates_any_game(
    user: Any,
) -> bool:
    from accounts.privileges import compute_privileged
    return compute_privileged(user)
