from django.core.cache import caches
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from nav.models import NavItem, SocialLink

_NAVBAR_CACHE_PREFIX = "navbar:"


def _invalidate_navbar_cache() -> None:
    """Delete all navbar cache entries."""
    cache = caches["default"]
    cache.delete_pattern(f"{_NAVBAR_CACHE_PREFIX}*")


@receiver(
    post_save,
    sender=NavItem,
    dispatch_uid="navbar_invalidate_navitem_save",
)
def invalidate_on_navitem_save(
    sender: type,
    **kwargs: object,
) -> None:
    _invalidate_navbar_cache()


@receiver(
    post_delete,
    sender=NavItem,
    dispatch_uid="navbar_invalidate_navitem_delete",
)
def invalidate_on_navitem_delete(
    sender: type,
    **kwargs: object,
) -> None:
    _invalidate_navbar_cache()


@receiver(
    post_save,
    sender=SocialLink,
    dispatch_uid="navbar_invalidate_sociallink_save",
)
def invalidate_on_sociallink_save(
    sender: type,
    **kwargs: object,
) -> None:
    _invalidate_navbar_cache()


@receiver(
    post_delete,
    sender=SocialLink,
    dispatch_uid="navbar_invalidate_sociallink_delete",
)
def invalidate_on_sociallink_delete(
    sender: type,
    **kwargs: object,
) -> None:
    _invalidate_navbar_cache()
