from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from nav.models import NavItem, SocialLink

HAS_CHILDREN_MESSAGE: str = (
    "Cannot delete a NavItem with children. Remove or reparent them first."
)
SELF_PARENT_MESSAGE: str = "A NavItem cannot be its own parent."
CYCLE_MESSAGE: str = "Cannot set parent to a descendant (would create a cycle)."
MAX_DEPTH_MESSAGE: str = "Resulting subtree would exceed the 4-level nesting limit."
UNKNOWN_IDS_MESSAGE: str = (
    "ordered_ids do not match the siblings under the given parent."
)

MAX_DEPTH: int = 4


def _sorted_for_display(
    items: list,
    key: str = "name",
) -> list:
    ordered = sorted([i for i in items if i.order > 0], key=lambda x: x.order)
    unordered = sorted(
        [i for i in items if i.order == 0],
        key=lambda x: getattr(x, key),
    )
    return ordered + unordered


def _build_nav_tree() -> list[dict[str, Any]]:
    all_items = list(NavItem.objects.all())
    children_map: dict[int | None, list[NavItem]] = {}
    for item in all_items:
        children_map.setdefault(item.parent_id, []).append(item)

    def build(
        parent_id: int | None,
    ) -> list[dict[str, Any]]:
        items = children_map.get(parent_id, [])
        return [
            {
                "id": item.pk,
                "name": item.name,
                "url": item.url,
                "parent_id": item.parent_id,
                "order": item.order,
                "is_visible": item.is_visible,
                "children": build(item.pk),
            }
            for item in _sorted_for_display(items, key="name")
        ]

    return build(None)


def _build_social_list() -> list[dict[str, Any]]:
    items = list(SocialLink.objects.all())
    return [
        {
            "id": item.pk,
            "platform": item.platform,
            "url": item.url,
            "order": item.order,
            "is_visible": item.is_visible,
        }
        for item in _sorted_for_display(items, key="platform")
    ]


def get_navbar_state() -> dict[str, Any]:
    return {
        "items": _build_nav_tree(),
        "social": _build_social_list(),
    }


def _depth_of(
    item_id: int | None,
) -> int:
    """Returns the 1-indexed depth of the node with given id; 0 if id is None."""
    if item_id is None:
        return 0
    depth = 1
    parent_id = (
        NavItem.objects.filter(pk=item_id)
        .values_list(
            "parent_id",
            flat=True,
        )
        .first()
    )
    while parent_id is not None:
        depth += 1
        parent_id = (
            NavItem.objects.filter(pk=parent_id)
            .values_list(
                "parent_id",
                flat=True,
            )
            .first()
        )
    return depth


def _ancestor_ids(
    item_id: int | None,
) -> list[int]:
    if item_id is None:
        return []
    ancestors: list[int] = []
    parent_id = (
        NavItem.objects.filter(pk=item_id)
        .values_list(
            "parent_id",
            flat=True,
        )
        .first()
    )
    while parent_id is not None:
        ancestors.append(parent_id)
        parent_id = (
            NavItem.objects.filter(pk=parent_id)
            .values_list(
                "parent_id",
                flat=True,
            )
            .first()
        )
    return ancestors


def _subtree_depth(
    root_id: int | None,
) -> int:
    """Max depth of subtree rooted at root_id, with root counting as 1."""
    if root_id is None:
        return 0
    children = list(
        NavItem.objects.filter(parent_id=root_id).values_list("pk", flat=True)
    )
    if not children:
        return 1
    return 1 + max(_subtree_depth(c) for c in children)


def _validate_parent_assignment(
    item_id: int | None,
    new_parent_id: int | None,
) -> None:
    """Validate that setting `item_id`'s parent to `new_parent_id` is allowed.

    Checks: not self-parent, no cycle, total resulting subtree depth <= MAX_DEPTH.
    """
    new_parent_depth = _depth_of(new_parent_id)

    if item_id is None:
        if new_parent_depth + 1 > MAX_DEPTH:
            raise ValueError(MAX_DEPTH_MESSAGE)
        return

    if new_parent_id is not None and item_id == new_parent_id:
        raise ValueError(SELF_PARENT_MESSAGE)

    if new_parent_id is not None and item_id in _ancestor_ids(new_parent_id):
        raise ValueError(CYCLE_MESSAGE)

    subtree_depth = _subtree_depth(item_id)
    if new_parent_depth + subtree_depth > MAX_DEPTH:
        raise ValueError(MAX_DEPTH_MESSAGE)


def create_nav_item(
    data: dict[str, Any],
) -> NavItem:
    parent_id = data.get("parent_id")
    _validate_parent_assignment(item_id=None, new_parent_id=parent_id)
    item = NavItem(
        name=data["name"],
        url=data.get("url"),
        parent_id=parent_id,
        order=data.get("order", 0),
        is_visible=data.get("is_visible", True),
    )
    item.full_clean(exclude=("parent",))
    item.save()
    return item


def update_nav_item(
    item: NavItem,
    data: dict[str, Any],
) -> NavItem:
    """Applies partial update; only keys present in `data` are touched."""
    if "parent_id" in data:
        _validate_parent_assignment(item_id=item.pk, new_parent_id=data["parent_id"])
        item.parent_id = data["parent_id"]
    for field in ("name", "url", "order", "is_visible"):
        if field in data:
            setattr(item, field, data[field])
    item.full_clean(exclude=("parent",))
    item.save()
    return item


def delete_nav_item(
    item: NavItem,
) -> None:
    if item.children.exists():
        raise ValueError(HAS_CHILDREN_MESSAGE)
    item.delete()


def reorder_nav_items(
    parent_id: int | None,
    ordered_ids: list[int],
) -> None:
    siblings_qs = NavItem.objects.filter(parent_id=parent_id)
    existing_ids = set(siblings_qs.values_list("pk", flat=True))
    if set(ordered_ids) != existing_ids:
        raise ValueError(UNKNOWN_IDS_MESSAGE)

    with transaction.atomic():
        list(siblings_qs.select_for_update())
        now = timezone.now()
        for position, pk in enumerate(ordered_ids, start=1):
            NavItem.objects.filter(pk=pk).update(order=position, updated_at=now)

    _invalidate_navbar_cache()


def create_social_link(
    data: dict[str, Any],
) -> SocialLink:
    link = SocialLink(
        platform=data["platform"],
        url=data["url"],
        order=data.get("order", 0),
        is_visible=data.get("is_visible", True),
    )
    link.full_clean()
    link.save()
    return link


def update_social_link(
    link: SocialLink,
    data: dict[str, Any],
) -> SocialLink:
    for field in ("platform", "url", "order", "is_visible"):
        if field in data:
            setattr(link, field, data[field])
    link.full_clean()
    link.save()
    return link


def delete_social_link(
    link: SocialLink,
) -> None:
    link.delete()


def reorder_social_links(
    ordered_ids: list[int],
) -> None:
    qs = SocialLink.objects.all()
    existing_ids = set(qs.values_list("pk", flat=True))
    if set(ordered_ids) != existing_ids:
        raise ValueError(UNKNOWN_IDS_MESSAGE)

    with transaction.atomic():
        list(qs.select_for_update())
        now = timezone.now()
        for position, pk in enumerate(ordered_ids, start=1):
            SocialLink.objects.filter(pk=pk).update(order=position, updated_at=now)

    _invalidate_navbar_cache()


def _invalidate_navbar_cache() -> None:
    """Force a cache flush since bulk updates bypass post_save signals."""
    from nav.signals import _invalidate_navbar_cache as _flush

    _flush()
