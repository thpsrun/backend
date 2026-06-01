from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from allauth.socialaccount.models import SocialAccount
from api.models import APIActivityLog, APIKey
from auditlog.models import GameAuditEvent
from guides.models import Guides
from notifications.models import Notification, NotificationPreference
from srl.models import Players, RunHistory, Runs


def _isoformat(
    value: Any,
) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def serialize_account(
    user: Any,
) -> Iterator[dict]:
    yield {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "date_joined": _isoformat(user.date_joined),
        "last_login": _isoformat(user.last_login),
        "bio": user.bio,
        "short_bio": user.short_bio,
        "therun_gg": user.therun_gg,
        "gradient_1": user.gradient_1,
        "gradient_2": user.gradient_2,
        "gradient_3": user.gradient_3,
    }


def serialize_player(
    user: Any,
) -> Iterator[dict]:
    player = Players.objects.filter(user=user).first()
    if player is None:
        return
    yield {
        "id": player.pk,
        "name": player.name,
        "nickname": player.nickname,
        "url": player.url,
        "countrycode": player.countrycode.id if player.countrycode else None,
        "pfp": player.pfp,
        "pronouns": player.pronouns,
        "twitch": player.twitch,
        "youtube": player.youtube,
        "twitter": player.twitter,
        "bluesky": player.bluesky,
        "discord": player.discord,
        "ex_stream": player.ex_stream,
        "claim_status": player.claim_status,
        "sync_paused": player.sync_paused,
        "joined": _isoformat(player.joined),
        "created_at": _isoformat(player.created_at),
        "updated_at": _isoformat(player.updated_at),
    }


def serialize_runs(
    user: Any,
) -> Iterator[dict]:
    player = Players.objects.filter(user=user).first()
    if player is None:
        return
    qs = Runs.objects.filter(players=player).distinct().iterator(chunk_size=500)
    for run in qs:
        yield {
            "id": run.pk,
            "runtype": run.runtype,
            "game": run.game.id,
            "category": run.category.id if run.category else None,
            "level": run.level.id if run.level else None,
            "platform": run.platform.id if run.platform else None,
            "place": run.place,
            "url": run.url,
            "video": run.video,
            "arch_video": run.arch_video,
            "date": _isoformat(run.date),
            "v_date": _isoformat(run.v_date),
            "time": run.time,
            "time_secs": run.time_secs,
            "timenl": run.timenl,
            "timenl_secs": run.timenl_secs,
            "timeigt": run.timeigt,
            "timeigt_secs": run.timeigt_secs,
            "points": run.points,
            "bonus": run.bonus,
            "emulated": run.emulated,
            "vid_status": run.vid_status,
            "obsolete": run.obsolete,
            "obsoleted_at": _isoformat(run.obsoleted_at),
            "review_notes": run.review_notes,
            "description": run.description,
            "approver": run.approver.id if run.approver else None,
            "created_at": _isoformat(run.created_at),
            "updated_at": _isoformat(run.updated_at),
        }


def serialize_run_history(
    user: Any,
) -> Iterator[dict]:
    player = Players.objects.filter(user=user).first()
    if player is None:
        return
    qs = (
        RunHistory.objects.filter(run__players=player)
        .distinct()
        .iterator(chunk_size=500)
    )
    for hist in qs:
        yield {
            "id": hist.pk,
            "run": hist.run.id,
            "points": hist.points,
            "end_reason": hist.end_reason,
            "start_date": _isoformat(hist.start_date),
            "end_date": _isoformat(hist.end_date),
            "streak_start_date": _isoformat(hist.streak_start_date),
            "created_at": _isoformat(hist.created_at),
        }


def serialize_guides(
    user: Any,
) -> Iterator[dict]:
    qs = Guides.objects.filter(owner=user).iterator(chunk_size=500)
    for guide in qs:
        yield {
            "id": guide.pk,
            "title": guide.title,
            "slug": guide.slug,
            "short_description": guide.short_description,
            "content": guide.content,
            "game": guide.game.id,
            "tags": list(guide.tags.values_list("name", flat=True)),
            "created_at": _isoformat(guide.created_at),
            "updated_at": _isoformat(guide.updated_at),
        }


def serialize_submissions(
    user: Any,
) -> Iterator[dict]:
    player = Players.objects.filter(user=user).first()
    if player is None:
        return
    qs = (
        Runs.objects.filter(players=player, vid_status__in=("new", "review"))
        .distinct()
        .iterator(chunk_size=500)
    )
    for run in qs:
        yield {
            "id": run.pk,
            "game": run.game.id,
            "category": run.category.id if run.category else None,
            "vid_status": run.vid_status,
            "review_notes": run.review_notes,
            "date": _isoformat(run.date),
        }


def serialize_api_keys(
    user: Any,
) -> Iterator[dict]:
    qs = APIKey.objects.filter(user=user).iterator(chunk_size=500)
    for key in qs:
        yield {
            "label": key.label,
            "description": key.description,
            "scope_capabilities": list(key.scope_capabilities or []),
            "scope_games": list(key.scope_games.values_list("pk", flat=True)),
            "created": _isoformat(getattr(key, "created", None)),
            "expiry_date": _isoformat(getattr(key, "expiry_date", None)),
            "last_used": _isoformat(key.last_used),
            "last_used_ip": key.last_used_ip,
            "revoked": getattr(key, "revoked", False),
            "revoked_at": _isoformat(key.revoked_at),
            "revoked_reason": key.revoked_reason,
        }


def serialize_api_activity(
    user: Any,
) -> Iterator[dict]:
    qs = APIActivityLog.objects.filter(user=user).iterator(chunk_size=500)
    for row in qs:
        yield {
            "created_at": _isoformat(row.created_at),
            "api_key_label": row.key_label_snapshot,
            "auth_method": row.auth_method,
            "method": row.method,
            "path": row.path,
            "action": row.action,
            "status_code": row.status_code,
            "ip": row.ip,
            "user_agent": row.user_agent,
            "target_app": row.target_app,
            "target_model": row.target_model,
            "target_id": row.target_id,
            "target_repr": row.target_repr,
            "change_summary": row.change_summary,
        }


def serialize_notifications(
    user: Any,
) -> Iterator[dict]:
    qs = Notification.objects.filter(user=user).iterator(chunk_size=500)
    for n in qs:
        yield {
            "id": n.pk,
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "payload": n.payload,
            "target_type": n.target_type,
            "target_id": n.target_id,
            "is_read": n.is_read,
            "read_at": _isoformat(n.read_at),
            "created_at": _isoformat(n.created_at),
        }


def serialize_notification_prefs(
    user: Any,
) -> Iterator[dict]:
    qs = NotificationPreference.objects.filter(user=user).iterator(chunk_size=500)
    for p in qs:
        yield {
            "type": p.type,
            "enabled": p.enabled,
        }


def serialize_social_accounts(
    user: Any,
) -> Iterator[dict]:
    qs = SocialAccount.objects.filter(user=user).iterator(chunk_size=500)
    for sa in qs:
        yield {
            "provider": sa.provider,
            "uid": sa.uid,
            "date_joined": _isoformat(sa.date_joined),
            "last_login": _isoformat(sa.last_login),
        }


def serialize_audit_events(
    user: Any,
) -> Iterator[dict]:
    qs = GameAuditEvent.objects.filter(actor_user=user).iterator(chunk_size=500)
    for evt in qs:
        yield {
            "id": evt.pk,
            "game": evt.game.id if evt.game else None,
            "game_slug_snapshot": evt.game_slug_snapshot,
            "event_type": evt.event_type,
            "actor_kind": evt.actor_kind,
            "actor_label": evt.actor_label,
            "target_app": evt.target_app,
            "target_model": evt.target_model,
            "target_id": evt.target_id,
            "target_repr": evt.target_repr,
            "summary": evt.summary,
            "payload": evt.payload,
            "created_at": _isoformat(evt.created_at),
        }


def collect_exports(
    user: Any,
) -> Iterator[tuple[str, Iterator[dict]]]:
    yield "account", serialize_account(user)
    yield "player", serialize_player(user)
    yield "runs", serialize_runs(user)
    yield "run_history", serialize_run_history(user)
    yield "guides", serialize_guides(user)
    yield "submissions", serialize_submissions(user)
    yield "api_keys", serialize_api_keys(user)
    yield "api_activity_log", serialize_api_activity(user)
    yield "notifications", serialize_notifications(user)
    yield "notification_preferences", serialize_notification_prefs(user)
    yield "social_accounts", serialize_social_accounts(user)
    yield "game_audit_events", serialize_audit_events(user)
