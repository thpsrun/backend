import logging
from datetime import timedelta
from typing import Any

from allauth.account.models import EmailAddress
from api.models import APIKey
from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from srl.models import Runs
from srl.models.games import Games
from srl.models.players import Players

from notifications import channels as channels_mod
from notifications import email as email_helpers
from notifications import kinds
from notifications.models import Notification
from notifications.services import _is_enabled_for, create_notification

logger = logging.getLogger(__name__)


@shared_task(name="notifications.dispatch_run_status_notification")
def dispatch_run_status_notification(
    run_id: str,
    expected_status: str,
    kind: str,
    title: str,
    body_override: str | None = None,
) -> dict:
    """Throws a notification to a player with the run is approved or denied."""

    run = (
        Runs.objects.filter(pk=run_id, vid_status=expected_status)
        .select_related("game", "category")
        .prefetch_related("players__user")
        .first()
    )
    if run is None:
        return {"emitted": 0, "skipped": "stale_or_missing"}

    game_name = getattr(run.game, "name", "") if run.game else ""
    category_name = getattr(run.category, "name", "") if run.category else ""
    payload: dict[str, Any] = {
        "run_id": str(run_id),
        "game_id": getattr(run, "game_id", "") or "",
        "game_name": game_name,
        "category_name": category_name,
    }

    if body_override is not None:
        body = body_override
    else:
        body = f"Your {game_name or 'run'} {category_name or ''}".strip()

    emitted = 0
    for player in run.players.all():
        user = getattr(player, "user", None)
        if user is None or getattr(user, "pk", None) is None:
            continue
        result = create_notification(
            user=user,
            kind=kind,
            title=title,
            body=body,
            target_type="run",
            target_id=str(run_id),
            payload=dict(payload),
        )
        if result is not None:
            emitted += 1
    return {"emitted": emitted}


@shared_task(name="notifications.dispatch_run_awaiting_review_notification")
def dispatch_run_awaiting_review_notification(
    run_id: str,
) -> dict:
    """Notify a game's moderators that a run is awaiting review."""

    run = (
        Runs.objects.filter(pk=run_id, vid_status="new")
        .select_related("game", "category")
        .prefetch_related("players", "game__moderators__user")
        .first()
    )
    if run is None or run.game is None:
        return {"emitted": 0, "skipped": "stale_or_missing"}

    game_name = getattr(run.game, "name", "") or ""
    category_name = getattr(run.category, "name", "") or ""
    player_names = [
        getattr(player, "name", "")
        for player in run.players.all()
        if getattr(player, "name", "")
    ]
    payload: dict[str, Any] = {
        "run_id": str(run_id),
        "game_id": getattr(run, "game_id", "") or "",
        "game_name": game_name,
        "category_name": category_name,
        "player_names": player_names,
    }

    runner = ", ".join(player_names) or "someone"
    title = "Run awaiting review"
    body = f"{game_name} {category_name} by {runner} is awaiting review.".strip()

    emitted = 0
    for moderator in run.game.moderators.all():
        user = getattr(moderator, "user", None)
        if user is None or getattr(user, "pk", None) is None:
            continue

        already_unread = Notification.objects.filter(
            user=user,
            type=kinds.RUN_AWAITING_REVIEW,
            target_id=str(run_id),
            is_read=False,
        ).exists()
        if already_unread:
            continue

        result = create_notification(
            user=user,
            kind=kinds.RUN_AWAITING_REVIEW,
            title=title,
            body=body,
            target_type="run",
            target_id=str(run_id),
            payload=dict(payload),
        )
        if result is not None:
            emitted += 1

    return {"emitted": emitted}


@shared_task(name="notifications.dispatch_mod_promoted_notification")
def dispatch_mod_promoted_notification(
    player_id: int,
    game_id: str,
    promoted_by_user_id: int | None,
    promoted_by_username: str,
) -> dict:
    player = Players.objects.filter(pk=player_id).select_related("user").first()
    if player is None:
        return {"emitted": 0, "skipped": "player_missing"}

    user = getattr(player, "user", None)
    if user is None or getattr(user, "pk", None) is None:
        return {"emitted": 0, "skipped": "no_user"}

    game = Games.objects.filter(pk=game_id).only("id", "name").first()
    if game is None:
        return {"emitted": 0, "skipped": "game_missing"}

    if not game.moderators.filter(pk=player_id).exists():
        return {"emitted": 0, "skipped": "no_longer_moderator"}

    game_name = getattr(game, "name", "") or ""

    result = create_notification(
        user=user,
        kind=kinds.MOD_PROMOTED,
        title="You were promoted to moderator",
        body=f"You are now a moderator of {game_name or 'a game'}.",
        target_type="game",
        target_id=str(game_id),
        payload={
            "game_id": str(game_id),
            "game_name": game_name,
            "promoted_by_user_id": promoted_by_user_id,
            "promoted_by_username": promoted_by_username,
        },
    )
    return {"emitted": 1 if result is not None else 0}


@shared_task(name="notifications.purge_old_notifications")
def purge_old_notifications(
    retention_days: int = 90,
) -> dict:
    """Deletes notifications after the days provided."""
    cutoff = timezone.now() - timedelta(days=retention_days)
    deleted, _ = Notification.objects.filter(created_at__lt=cutoff).delete()
    return {"deleted": deleted, "cutoff": cutoff.isoformat()}


@shared_task(name="notifications.scan_expiring_api_keys")
def scan_expiring_api_keys() -> dict:
    """Notifies the user of an API key within 3 days if their keys is to expire."""
    now = timezone.now()
    cutoff = now + timedelta(days=3)

    qs = APIKey.objects.filter(
        revoked=False,
        expiry_date__isnull=False,
        expiry_date__gt=now,
        expiry_date__lte=cutoff,
    ).select_related("user")

    emitted = 0
    skipped = 0
    for key in qs:
        recipient = getattr(key, "user", None)
        if recipient is None or getattr(recipient, "pk", None) is None:
            skipped += 1
            continue

        target_id = str(key.id)
        already = Notification.objects.filter(
            user_id=recipient.pk,
            type=kinds.API_KEY_EXPIRING,
            target_type="api_key",
            target_id=target_id,
        ).exists()
        if already:
            skipped += 1
            continue

        key_label = getattr(key, "label", "") or ""
        expiry_date = key.expiry_date
        days_left = max(0, (expiry_date - now).days)

        create_notification(
            user=recipient,
            kind=kinds.API_KEY_EXPIRING,
            title="API key expiring soon",
            body=(
                f"API key '{key_label}' expires in {days_left} day(s)."
                if key_label
                else f"One of your API keys expires in {days_left} day(s)."
            ),
            target_type="api_key",
            target_id=target_id,
            payload={
                "api_key_id": target_id,
                "key_label": key_label,
                "expiry_date": expiry_date.isoformat(),
                "days_until_expiry": days_left,
            },
        )
        emitted += 1

    return {"emitted": emitted, "skipped": skipped, "scanned": qs.count()}


@shared_task(
    name="notifications.send_notification_email",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_notification_email(
    user_id: int,
    kind: str,
    title: str,
    body: str = "",
    target_type: str = "",
    target_id: str = "",
    payload: dict | None = None,
) -> dict:
    User = get_user_model()
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return {"sent": 0, "skipped": "user_missing"}

    address = (
        EmailAddress.objects.filter(user=user, primary=True, verified=True)
        .values_list("email", flat=True)
        .first()
    )
    if not address:
        return {"sent": 0, "skipped": "no_verified_email"}

    if not _is_enabled_for(user_id, kind, channels_mod.EMAIL):
        return {"sent": 0, "skipped": "pref_disabled"}

    payload = payload or {}
    subject = email_helpers.build_subject(kind, fallback_title=title)
    cta_url = email_helpers.build_cta_url(
        kind=kind,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
    )
    message = render_to_string(
        "notifications/email/notification_message.txt",
        {
            "username": user.username,
            "title": title,
            "body": body,
            "cta_url": cta_url,
            "preferences_url": email_helpers.preferences_url(),
        },
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=None,
        recipient_list=[address],
        fail_silently=False,
    )
    return {"sent": 1}
