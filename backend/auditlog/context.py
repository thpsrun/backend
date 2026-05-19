from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from accounts.models import CustomUser
    from api.models import APIKey


class Actor(TypedDict, total=False):
    user: "CustomUser | None"
    api_key: "APIKey | None"
    label: str


_actor: contextvars.ContextVar[Actor | None] = contextvars.ContextVar(
    "audit_actor",
    default=None,
)


def set_actor(
    *,
    user: "CustomUser | None" = None,
    api_key: "APIKey | None" = None,
    label: str = "",
) -> None:
    _actor.set({"user": user, "api_key": api_key, "label": label})


def get_actor() -> Actor | None:
    return _actor.get()


def clear_actor() -> None:
    _actor.set(None)
