from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.utils import timezone
from ninja import Query, Router, Status
from notifications import registry
from notifications.models import Notification, NotificationPreference
from notifications.registry import NotificationGroup, NotificationKind

from api.permissions import session_only
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.notifications import (
    NotificationKindOut,
    NotificationKindsOut,
    NotificationListOut,
    NotificationOut,
    PreferenceOut,
    PreferencesOut,
    PreferencesUpdateIn,
    ReadByTargetIn,
    ReadCountOut,
    UnreadCountOut,
)

router = Router()


@router.get(
    "",
    auth=session_only("notifications.read_own"),
    response={
        200: NotificationListOut,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="List Notifications",
)
def list_notifications(
    request: HttpRequest,
    unread_only: bool = Query(False),
    type: str | None = Query(None, description="Comma-separated kind keys"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Any:
    qs = Notification.objects.filter(user=request.user)
    if unread_only:
        qs = qs.filter(is_read=False)
    if type:
        keys = [t.strip() for t in type.split(",") if t.strip()]
        if keys:
            qs = qs.filter(type__in=keys)
    total = qs.count()
    page = list(qs.order_by("-created_at")[offset : offset + limit])
    return {
        "count": total,
        "limit": limit,
        "offset": offset,
        "items": [NotificationOut.model_validate(n) for n in page],
    }


@router.get(
    "/unread-count",
    auth=session_only("notifications.read_own"),
    response={
        200: UnreadCountOut,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Unread Notification Count",
)
def unread_count(
    request: HttpRequest,
) -> Any:
    n = Notification.objects.filter(user=request.user, is_read=False).count()
    return {"count": n}


@router.post(
    "/read-all",
    auth=session_only("notifications.manage_own"),
    response={
        200: ReadCountOut,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Mark All Notifications As Read",
)
def mark_all_read(
    request: HttpRequest,
) -> Any:
    now = timezone.now()
    updated = Notification.objects.filter(user=request.user, is_read=False).update(
        is_read=True, read_at=now
    )
    return {"updated": updated}


@router.post(
    "/read-by-target",
    auth=session_only("notifications.manage_own"),
    response={
        200: ReadCountOut,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Mark Notifications as Read",
)
def mark_read_by_target(request: HttpRequest, payload: ReadByTargetIn) -> Any:
    now = timezone.now()
    updated = Notification.objects.filter(
        user=request.user,
        is_read=False,
        target_type=payload.target_type,
        target_id=payload.target_id,
    ).update(is_read=True, read_at=now)
    return {"updated": updated}


def _preference_entries() -> list[NotificationKind | NotificationGroup]:
    """Returns the user-facing preference entries."""
    seen_groups: set[str] = set()
    out: list[NotificationKind | NotificationGroup] = []
    for kind in registry.all_kinds():
        if kind.group is None:
            out.append(kind)
            continue
        if kind.group in seen_groups:
            continue
        group = registry.get_group(kind.group)
        assert group is not None
        out.append(group)
        seen_groups.add(kind.group)
    return out


def _is_valid_preference_key(
    key: str,
) -> bool:
    if registry.is_group(key):
        return True
    kind = registry.get(key)
    if kind is None:
        return False
    return kind.group is None


@router.get(
    "/preferences",
    auth=session_only("notifications.read_own"),
    response={
        200: PreferencesOut,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Get notification preferences",
)
def get_preferences(
    request: HttpRequest,
) -> Any:
    stored = dict(
        NotificationPreference.objects.filter(user=request.user).values_list(
            "type", "enabled"
        ),
    )
    out: list[PreferenceOut] = []
    for entry in _preference_entries():
        enabled = stored.get(entry.key, entry.default_enabled)
        out.append(
            PreferenceOut(
                kind=entry.key,
                label=entry.label,
                description=entry.description,
                enabled=enabled,
            ),
        )
    return {"preferences": out}


@router.put(
    "/preferences",
    auth=session_only("notifications.manage_own"),
    response={
        200: PreferencesOut,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Update Notification Preferences",
)
def put_preferences(
    request: HttpRequest,
    payload: PreferencesUpdateIn,
) -> Any:
    unknown = [k for k in payload.preferences.keys() if not _is_valid_preference_key(k)]
    if unknown:
        return Status(
            400,
            ErrorResponse(
                error="unknown_notification_kind",
                details={"kinds": sorted(unknown)},
            ),
        )

    for pref_key, enabled in payload.preferences.items():
        NotificationPreference.objects.update_or_create(
            user=request.user,
            type=pref_key,
            defaults={"enabled": bool(enabled)},
        )
    return get_preferences(request)


@router.get(
    "/kinds",
    auth=session_only("notifications.read_own"),
    response={
        200: NotificationKindsOut,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="List All Registered Notification Types",
)
def list_kinds(
    request: HttpRequest,
) -> Any:
    return {
        "kinds": [
            NotificationKindOut(
                kind=entry.key,
                label=entry.label,
                description=entry.description,
                default_enabled=entry.default_enabled,
            )
            for entry in _preference_entries()
        ],
    }


@router.post(
    "/{notification_id}/read",
    auth=session_only("notifications.manage_own"),
    response={
        200: NotificationOut,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Mark notification as read",
)
def mark_read(
    request: HttpRequest,
    notification_id: int,
) -> Any:
    try:
        notif = Notification.objects.get(
            pk=notification_id,
            user=request.user,
        )
    except Notification.DoesNotExist:
        return Status(
            404,
            ErrorResponse(error="notification_not_found", details=None),
        )
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save(update_fields=["is_read", "read_at"])
    return notif


@router.delete(
    "/{notification_id}",
    auth=session_only("notifications.manage_own"),
    response={
        200: dict[str, str],
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Delete a notification",
)
def delete_notification(
    request: HttpRequest,
    notification_id: int,
) -> Any:
    try:
        notif = Notification.objects.get(
            pk=notification_id,
            user=request.user,
        )
    except Notification.DoesNotExist:
        return Status(
            404,
            ErrorResponse(error="notification_not_found", details=None),
        )
    notif.delete()
    return {"detail": "deleted"}
