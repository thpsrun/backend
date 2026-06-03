from __future__ import annotations

from typing import Any

from allauth.mfa.models import Authenticator
from django.core.cache import cache
from srl.models.games import Games

PRIVILEGED_CACHE_KEY = "mfa:privileged:{user_id}"
HASFACTOR_CACHE_KEY = "mfa:hasfactor:{user_id}"
CACHE_TTL = 300


def compute_privileged(
    user: Any,
) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    player = getattr(user, "player", None)
    if player is None:
        return False

    return Games.objects.filter(moderators=player).exists()


def is_privileged_user(
    user: Any,
) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    key = PRIVILEGED_CACHE_KEY.format(user_id=user.pk)
    cached = cache.get(key)
    if cached is not None:
        return cached
    value = compute_privileged(user)
    cache.set(key, value, CACHE_TTL)
    return value


def compute_has_required_factor(
    user: Any,
) -> bool:
    return Authenticator.objects.filter(
        user=user,
        type__in=[
            Authenticator.Type.TOTP,
            Authenticator.Type.WEBAUTHN,
        ],
    ).exists()


def has_required_factor(
    user: Any,
) -> bool:
    key = HASFACTOR_CACHE_KEY.format(user_id=user.pk)
    cached = cache.get(key)
    if cached is not None:
        return cached
    value = compute_has_required_factor(user)
    cache.set(key, value, CACHE_TTL)
    return value


def is_gated(
    user: Any,
) -> bool:
    return is_privileged_user(user) and not has_required_factor(user)


def social_login_requires_mfa(
    user: Any,
) -> bool:
    has_totp = Authenticator.objects.filter(
        user=user,
        type=Authenticator.Type.TOTP,
    ).exists()
    if not has_totp:
        return False
    has_passkey = Authenticator.objects.filter(
        user=user,
        type=Authenticator.Type.WEBAUTHN,
    ).exists()
    return not has_passkey


def invalidate_privileged(
    user_id: int,
) -> None:
    cache.delete(PRIVILEGED_CACHE_KEY.format(user_id=user_id))


def invalidate_has_required_factor(
    user_id: int,
) -> None:
    cache.delete(HASFACTOR_CACHE_KEY.format(user_id=user_id))
