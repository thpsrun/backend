import logging

from allauth.account.signals import user_logged_in
from allauth.socialaccount.signals import (
    social_account_added,
    social_account_removed,
    social_account_updated,
)
from django.conf import settings
from django.dispatch import receiver

from accounts.adapters import TWITCH_LOGIN_RE

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
