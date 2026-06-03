from datetime import datetime, timedelta
from typing import Any

from auditlog.context import get_actor
from django.conf import settings
from django.db import transaction
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from srl.models import Runs
from srl.models.games import Games

from notifications import kinds
from notifications.tasks import (
    dispatch_mod_promoted_notification,
    dispatch_run_awaiting_review_notification,
    dispatch_run_status_notification,
)


@receiver(
    pre_save,
    sender=Runs,
    dispatch_uid="notifications.signals.runs_capture_previous_status",
)
def runs_capture_previous_status(
    sender: Any,
    instance: Any,
    raw: bool = False,
    **kwargs: Any,
) -> None:
    if raw:
        return
    if instance.pk is None:
        instance._previous_vid_status = None
        instance._previous_review_notes = ""
        return
    try:
        previous = sender.objects.only(
            "vid_status",
            "review_notes",
        ).get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._previous_vid_status = None
        instance._previous_review_notes = ""
        return
    instance._previous_vid_status = previous.vid_status
    instance._previous_review_notes = previous.review_notes


@receiver(
    post_save,
    sender=Runs,
    dispatch_uid="notifications.signals.runs_trigger_status_notification",
)
def runs_trigger_status_notification(
    sender: Any,
    instance: Any,
    created: bool,
    raw: bool = False,
    **kwargs: Any,
) -> None:
    if raw:
        return
    if created:
        return

    previous = getattr(instance, "_previous_vid_status", None)
    current = instance.vid_status
    previous_notes = getattr(instance, "_previous_review_notes", "")
    current_notes = getattr(instance, "review_notes", "") or ""

    transitioned_to_verified = previous != "verified" and current == "verified"
    transitioned_to_rejected = previous != "rejected" and current == "rejected"
    transitioned_to_review = previous != "review" and current == "review"
    notes_changed_in_review = (
        previous == "review" and current == "review" and previous_notes != current_notes
    )

    if transitioned_to_verified:
        kind = kinds.RUN_APPROVED
        title = "Run Approved"
        body_override: str | None = None
    elif transitioned_to_rejected:
        kind = kinds.RUN_DENIED
        title = "Run Denied"
        body_override = None
    elif transitioned_to_review or notes_changed_in_review:
        kind = kinds.RUN_REVIEW
        title = "Your run was sent back for review!"
        body_override = current_notes
    else:
        return

    run_id = str(instance.pk)
    expected_status = current

    transaction.on_commit(
        lambda: dispatch_run_status_notification.delay(
            run_id=run_id,
            expected_status=expected_status,
            kind=kind,
            title=title,
            body_override=body_override,
        ),
    )


@receiver(
    post_save,
    sender=Runs,
    dispatch_uid="notifications.signals.runs_trigger_review_notification",
)
def runs_trigger_review_notification(
    sender: Any,
    instance: Any,
    created: bool,
    raw: bool = False,
    **kwargs: Any,
) -> None:
    if raw:
        return

    previous = getattr(instance, "_previous_vid_status", None)
    current = instance.vid_status

    entered_new = (created and current == "new") or (
        previous != "new" and current == "new"
    )
    if not entered_new:
        return

    max_age_days = getattr(settings, "AWAITING_REVIEW_NOTIFY_MAX_AGE_DAYS", 7)
    run_date = getattr(instance, "date", None)
    if isinstance(run_date, datetime):
        cutoff = timezone.now() - timedelta(days=max_age_days)
        if timezone.is_aware(cutoff) and timezone.is_naive(run_date):
            run_date = timezone.make_aware(run_date)
        elif timezone.is_naive(cutoff) and timezone.is_aware(run_date):
            run_date = timezone.make_naive(run_date)
        if run_date < cutoff:
            return

    run_id = str(instance.pk)
    transaction.on_commit(
        lambda: dispatch_run_awaiting_review_notification.delay(run_id=run_id),
    )


@receiver(
    m2m_changed,
    sender=Games.moderators.through,
    dispatch_uid="notifications.signals.mods_trigger_promoted_notification",
)
def mods_trigger_promoted_notification(
    sender: Any,
    instance: Any,
    action: str,
    reverse: bool,
    pk_set: set[Any] | None,
    **kwargs: Any,
) -> None:
    """Throws a notification when a user is promoted to a moderator."""

    if kwargs.get("raw"):
        return
    if action != "post_add":
        return
    if not pk_set:
        return

    actor = get_actor() or {}
    promoted_by_user = actor.get("user")
    promoted_by_user_id = (
        getattr(promoted_by_user, "pk", None) if promoted_by_user is not None else None
    )
    promoted_by_username = (
        getattr(promoted_by_user, "username", None)
        if promoted_by_user is not None
        else None
    ) or "system"

    if reverse:
        player_pk = instance.pk
        pairs = [(player_pk, game_pk) for game_pk in pk_set]
    else:
        game_pk = instance.pk
        pairs = [(player_pk, game_pk) for player_pk in pk_set]

    for player_pk, game_pk in pairs:
        transaction.on_commit(
            lambda p=player_pk, g=game_pk: dispatch_mod_promoted_notification.delay(
                player_id=p,
                game_id=str(g),
                promoted_by_user_id=promoted_by_user_id,
                promoted_by_username=promoted_by_username,
            ),
        )
