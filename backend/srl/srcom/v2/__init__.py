from django.conf import settings
from django.core.cache import cache

from srl.models import BotSession

_V2_ENABLED_CACHE_KEY = "src_v2_enabled"
_V2_ENABLED_CACHE_TTL = 30


def is_v2_enabled() -> bool:
    cached = cache.get(_V2_ENABLED_CACHE_KEY)
    if cached is not None:
        return bool(cached)

    bs = BotSession.objects.filter(pk=1).first()
    if bs is not None and bs.v2_enabled_override is not None:
        enabled = bool(bs.v2_enabled_override)
    else:
        enabled = bool(getattr(settings, "SRC_V2_ENABLED", False))

    cache.set(_V2_ENABLED_CACHE_KEY, enabled, _V2_ENABLED_CACHE_TTL)
    return enabled


def invalidate_v2_enabled_cache() -> None:
    cache.delete(_V2_ENABLED_CACHE_KEY)
