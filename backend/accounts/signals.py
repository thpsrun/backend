import logging

from allauth.account.signals import user_logged_in, user_signed_up
from allauth.mfa.models import Authenticator
from allauth.socialaccount.signals import (
    social_account_added,
    social_account_removed,
    social_account_updated,
)
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from srl.models.games import Games
from srl.models.players import Players

from accounts.adapters import TWITCH_LOGIN_RE
from accounts.privileges import invalidate_has_required_factor, invalidate_privileged

logger = logging.getLogger(__name__)

REMEMBER_AGE = getattr(settings, "REMEMBER_AGE", 60 * 60 * 24 * 30)


def _sync_social_to_player(
    sociallogin,
) -> None:
    user = sociallogin.user
    player = getattr(user, "player", None)
    if player is None:
        return

    provider_id = sociallogin.account.provider
    extra = sociallogin.account.extra_data or {}

    if provider_id == "discord":
        username = extra.get("username") or ""
        logger.info(
            "Discord connect for user_id=%s username=%r global_name=%r discriminator=%r",
            user.pk,
            username,
            extra.get("global_name"),
            extra.get("discriminator"),
        )
        if username:
            _save_player_field(player, "discord", username[:32])
    elif provider_id == "twitch":
        login = extra.get("login")
        if not login or not TWITCH_LOGIN_RE.match(login):
            logger.warning(
                "Skipping twitch sync for user_id=%s: unexpected login %r",
                user.pk,
                login,
            )
            return
        _save_player_field(player, "twitch", f"https://twitch.tv/{login}")


def _clear_social_from_player(
    user,
    provider_id: str,
) -> None:
    player = getattr(user, "player", None)
    if player is None:
        return

    if provider_id == "discord":
        _save_player_field(player, "discord", None)
    elif provider_id == "twitch":
        _save_player_field(player, "twitch", None)


def _save_player_field(
    player,
    field: str,
    value,
) -> None:
    setattr(player, field, value)
    try:
        player.save(update_fields=[field])
    except Exception:
        logger.exception(
            "Failed to sync %s to Players for user_id=%s",
            field,
            player.user_id,
        )


@receiver(social_account_added)
def on_social_account_added(
    sender,
    request,
    sociallogin,
    **kwargs,
) -> None:
    _sync_social_to_player(sociallogin)


@receiver(social_account_updated)
def on_social_account_updated(
    sender,
    request,
    sociallogin,
    **kwargs,
) -> None:
    _sync_social_to_player(sociallogin)


@receiver(social_account_removed)
def on_social_account_removed(
    sender,
    request,
    socialaccount,
    **kwargs,
) -> None:
    _clear_social_from_player(socialaccount.user, socialaccount.provider)


@receiver(user_signed_up)
def on_user_signed_up(
    sender,
    request,
    user,
    sociallogin=None,
    **kwargs,
) -> None:
    if sociallogin is not None:
        _sync_social_to_player(sociallogin)


@receiver(user_logged_in)
def apply_remember_me(
    sender,
    request,
    user,
    **kwargs,
) -> None:
    if request is None:
        return
    remember = request.headers.get("X-Remember-Me", "").strip().lower()
    if remember in {"1", "true", "yes"}:
        request.session.set_expiry(REMEMBER_AGE)


@receiver(post_save, sender=Authenticator)
@receiver(post_delete, sender=Authenticator)
def invalidate_mfa_factor_cache(
    sender,
    instance,
    **kwargs,
) -> None:
    invalidate_has_required_factor(instance.user_id)


@receiver(m2m_changed, sender=Games.moderators.through)
def invalidate_mfa_privileged_on_moderators(
    sender,
    instance,
    action,
    reverse,
    pk_set,
    **kwargs,
) -> None:
    if action not in {"post_add", "post_remove"}:
        return
    if reverse:
        user_id = getattr(instance, "user_id", None)
        if user_id is not None:
            invalidate_privileged(user_id)
        return
    if not pk_set:
        return
    user_ids = (
        Players.objects.filter(pk__in=pk_set)
        .exclude(user__isnull=True)
        .values_list("user_id", flat=True)
    )
    for user_id in user_ids:
        invalidate_privileged(user_id)


@receiver(post_save, sender=get_user_model())
def invalidate_mfa_privileged_on_user_save(
    sender,
    instance,
    **kwargs,
) -> None:
    invalidate_privileged(instance.pk)
