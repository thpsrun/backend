from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationKind:
    key: str
    label: str
    description: str
    default_enabled: bool = True


_REGISTRY: dict[str, NotificationKind] = {}


def register(kind: NotificationKind) -> None:
    if kind.key in _REGISTRY:
        raise ValueError(f"Notification kind already registered: {kind.key}")
    _REGISTRY[kind.key] = kind


def get(
    key: str,
) -> NotificationKind | None:
    return _REGISTRY.get(key)


def all_kinds() -> list[NotificationKind]:
    return list(_REGISTRY.values())


def is_registered(
    key: str,
) -> bool:
    return key in _REGISTRY
