import logging

from allauth.socialaccount.signals import (
    social_account_added,
    social_account_removed,
    social_account_updated,
)
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _sync_social_to_player(sociallogin) -> None:
    user = sociallogin.user
    player = getattr(user, "player", None)
    if player is None:
        return

    provider_id = sociallogin.account.provider
    extra = sociallogin.account.extra_data or {}

    if provider_id == "discord":
        # Discord's `username` is the unique @handle in the new username system,
        # or the legacy login name for old accounts. `global_name` is the styled
        # display name (e.g., "Anastasia ☆") and is NOT what we want here.
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
        if login:
            _save_player_field(player, "twitch", f"https://twitch.tv/{login}")


def _clear_social_from_player(user, provider_id: str) -> None:
    player = getattr(user, "player", None)
    if player is None:
        return

    if provider_id == "discord":
        _save_player_field(player, "discord", None)
    elif provider_id == "twitch":
        _save_player_field(player, "twitch", None)


def _save_player_field(player, field: str, value) -> None:
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
def on_social_account_added(sender, request, sociallogin, **kwargs) -> None:
    _sync_social_to_player(sociallogin)


@receiver(social_account_updated)
def on_social_account_updated(sender, request, sociallogin, **kwargs) -> None:
    _sync_social_to_player(sociallogin)


@receiver(social_account_removed)
def on_social_account_removed(sender, request, socialaccount, **kwargs) -> None:
    _clear_social_from_player(socialaccount.user, socialaccount.provider)
