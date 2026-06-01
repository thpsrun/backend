from dataclasses import dataclass, field

from notifications.channels import DEFAULT_CHANNELS


@dataclass(frozen=True)
class NotificationKind:
    key: str
    label: str
    description: str
    group: str | None = None
    default_channels: dict[str, bool] = field(
        default_factory=lambda: dict(DEFAULT_CHANNELS),
    )


@dataclass(frozen=True)
class NotificationGroup:
    key: str
    label: str
    description: str
    default_channels: dict[str, bool] = field(
        default_factory=lambda: dict(DEFAULT_CHANNELS),
    )


_REGISTRY: dict[str, NotificationKind] = {}
_GROUPS: dict[str, NotificationGroup] = {}


def register(kind: NotificationKind) -> None:
    if kind.key in _REGISTRY:
        raise ValueError(f"Notification kind already registered: {kind.key}")
    if kind.key in _GROUPS:
        raise ValueError(f"Notification kind key collides with group key: {kind.key}")
    if kind.group is not None and kind.group not in _GROUPS:
        raise ValueError(
            f"Notification kind {kind.key} references unknown group: {kind.group}",
        )
    _REGISTRY[kind.key] = kind


def register_group(group: NotificationGroup) -> None:
    if group.key in _GROUPS:
        raise ValueError(f"Notification group already registered: {group.key}")
    if group.key in _REGISTRY:
        raise ValueError(f"Notification group key collides with kind key: {group.key}")
    _GROUPS[group.key] = group


def get(
    key: str,
) -> NotificationKind | None:
    return _REGISTRY.get(key)


def get_group(
    key: str,
) -> NotificationGroup | None:
    return _GROUPS.get(key)


def all_kinds() -> list[NotificationKind]:
    return list(_REGISTRY.values())


def is_registered(
    key: str,
) -> bool:
    return key in _REGISTRY


def is_group(
    key: str,
) -> bool:
    return key in _GROUPS
