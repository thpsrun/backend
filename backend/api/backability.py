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

    # Fully unscoped key: it can only ever do what the user can do right now, so it
    # stays backable for as long as the account is active.
    if not caps and not games:
        return True

    # Game-scoped but capability-unscoped: treated as a mod key, so the owner must
    # still moderate (or be superuser over) every scoped game.
    if not caps:
        return all(user.has_perm("games.manage", g) for g in games)

    for cap in caps:
        # User-scoped caps: re-run the registered predicate directly.
        if not CAPABILITY_SCOPED.get(cap, False):
            if not user.has_perm(cap):
                return False
            continue
        # profile.edit_own is the registered proxy for "has a claimed player", the
        # only natural power the player-tier caps require.
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
                # Game-unrestricted mod cap: valid for any game the user moderates,
                # so moderating anywhere (or superuser) keeps the key backable.
                if not _user_moderates_any_game(user):
                    return False
            continue
    return True


def _user_moderates_any_game(
    user: Any,
) -> bool:
    """True when the user is a superuser or moderates at least one game."""
    # Deferred import keeps this module importable without pulling accounts (and its
    # allauth deps) in at app-registry time.
    from accounts.privileges import compute_privileged
    return compute_privileged(user)
