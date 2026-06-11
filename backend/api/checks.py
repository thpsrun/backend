from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security)
def trusted_proxies_configured(
    app_configs,
    **kwargs,
) -> list[Warning]:
    """Warn when production runs without TRUSTED_PROXIES configured.

    Arguments:
        app_configs: App configs Django passes to system checks (unused).

    Returns:
        warnings (list[Warning]): One warning when misconfigured, else empty.
    """
    if settings.DEBUG or settings.TRUSTED_PROXIES:
        return []
    return [
        Warning(
            "TRUSTED_PROXIES is empty while DEBUG is off. If the app runs "
            "behind a reverse proxy or CDN, per-IP rate limiting and request "
            "logging will treat every client as the proxy's IP.",
            hint="Set TRUSTED_PROXIES to the proxy's IPs/CIDR ranges in the environment.",
            id="api.W001",
        ),
    ]
