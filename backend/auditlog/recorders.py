from __future__ import annotations

import logging
from typing import Any

from auditlog.context import Actor, get_actor
from auditlog.models import GameAuditEvent

logger = logging.getLogger(__name__)


def record_event(
    *,
    game: Any,
    event_type: str,
    summary: str,
    target: Any | None = None,
    payload: dict | None = None,
    actor_override: Actor | None = None,
) -> None:
    game_id: Any = None
    game_slug_snapshot: str | None = None
    if game is not None:
        game_id = getattr(game, "pk", game)
        slug = getattr(game, "slug", None)
        if slug:
            game_slug_snapshot = str(slug)[:255]

    try:
        actor: Actor = actor_override or get_actor() or {}
        user = actor.get("user")
        api_key = actor.get("api_key")
        if api_key is not None:
            kind = GameAuditEvent.ActorKind.API_KEY
        elif user is not None:
            kind = GameAuditEvent.ActorKind.USER
        else:
            kind = GameAuditEvent.ActorKind.SYSTEM

        target_app = ""
        target_model = ""
        target_id = ""
        target_repr = ""
        if target is not None:
            meta = getattr(target, "_meta", None)
            if meta is not None:
                target_app = meta.app_label
                target_model = meta.model_name
            target_id = str(getattr(target, "pk", ""))[:150]
            target_repr = str(target)[:255]

        GameAuditEvent.objects.create(
            game_id=game_id,
            game_slug_snapshot=game_slug_snapshot,
            event_type=event_type,
            actor_kind=kind,
            actor_user=user,
            actor_api_key=api_key,
            actor_label=actor.get("label", "")[:128],
            target_app=target_app,
            target_model=target_model,
            target_id=target_id,
            target_repr=target_repr,
            summary=summary[:255],
            payload=payload,
        )
    except Exception:
        logger.exception(
            "audit_record_failed",
            extra={
                "event_type": event_type,
                "game_id": game_id,
            },
        )
