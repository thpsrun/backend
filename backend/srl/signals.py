from __future__ import annotations

import datetime

from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from srl.models.players import Players
from srl.models.run_players import RunPlayers
from srl.models.runs import Runs


def _effective_date(
    run: Runs,
) -> datetime.date | None:
    """Return the date portion of v_date (primary) or date (fallback)."""
    dt = run.v_date or run.date
    if dt is None:
        return None
    return dt.date()


def _update_player_joined(
    player: Players,
    run_date: datetime.date,
) -> bool:
    """Set player.joined if run_date is earlier (or joined is unset). Returns True if changed."""
    if player.joined is None or run_date < player.joined:
        player.joined = run_date
        player.save(update_fields=["joined"])
        return True
    return False


@receiver(
    m2m_changed,
    sender=Runs.players.through,
    dispatch_uid="set_joined_on_player_add",
)
def set_joined_on_player_add(
    sender: type,
    instance: Runs,
    action: str,
    pk_set: set[str] | None,
    **kwargs: object,
) -> None:
    """When players are added to a verified run, update their joined date."""
    if action != "post_add" or not pk_set:
        return
    # Only handle forward direction (run.players.add); reverse is not used by import
    if not isinstance(instance, Runs):
        return
    if instance.vid_status != "verified":
        return

    run_date = _effective_date(instance)
    if run_date is None:
        return

    for player in Players.objects.filter(pk__in=pk_set):
        _update_player_joined(player, run_date)


@receiver(
    post_save,
    sender=Runs,
    dispatch_uid="set_joined_on_run_verified",
)
def set_joined_on_run_verified(
    sender: type,
    instance: Runs,
    **kwargs: object,
) -> None:
    """When a run becomes verified, update joined for all its players."""
    update_fields = kwargs.get("update_fields")
    # Skip if save() specified fields and vid_status is not among them
    if update_fields is not None and "vid_status" not in update_fields:
        return
    if instance.vid_status != "verified":
        return

    run_date = _effective_date(instance)
    if run_date is None:
        return

    for player in instance.players.all():
        _update_player_joined(player, run_date)


@receiver(
    post_save,
    sender=RunPlayers,
    dispatch_uid="set_joined_on_runplayer_create",
)
def set_joined_on_runplayer_create(
    sender: type,
    instance: RunPlayers,
    created: bool,
    **kwargs: object,
) -> None:
    """When a RunPlayers entry is created for a verified run, update joined.

    Covers the SRC import path which uses RunPlayers.objects.create() directly
    instead of run.players.add(), bypassing m2m_changed.
    """
    if not created:
        return
    run = instance.run
    if run.vid_status != "verified":
        return
    run_date = _effective_date(run)
    if run_date is None:
        return
    _update_player_joined(instance.player, run_date)
