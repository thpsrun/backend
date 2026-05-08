from django.conf import settings


def is_v2_enabled() -> bool:
    from srl.models import BotSession

    bs = BotSession.objects.filter(pk=1).first()
    if bs is not None and bs.v2_enabled_override is not None:
        return bool(bs.v2_enabled_override)
    return bool(getattr(settings, "SRC_V2_ENABLED", False))
