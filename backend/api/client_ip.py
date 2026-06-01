from functools import lru_cache
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_address,
    ip_network,
)

from django.conf import settings
from django.http import HttpRequest

TrustedEntry = IPv4Address | IPv6Address | IPv4Network | IPv6Network


@lru_cache(maxsize=1)
def _get_trusted_proxies() -> tuple[TrustedEntry, ...]:
    raw: str = getattr(settings, "TRUSTED_PROXIES", "") or ""
    parsed: list[TrustedEntry] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                parsed.append(ip_network(entry, strict=False))
            else:
                parsed.append(ip_address(entry))
        except ValueError:
            continue
    return tuple(parsed)


def _is_trusted(
    addr: IPv4Address | IPv6Address,
    proxies: tuple[TrustedEntry, ...],
) -> bool:
    for p in proxies:
        if isinstance(p, (IPv4Network, IPv6Network)):
            if addr in p:
                return True
        elif addr == p:
            return True
    return False


def client_ip(
    request: HttpRequest,
) -> str:
    remote: str = request.META.get("REMOTE_ADDR", "") or "unknown"

    if settings.DEBUG:
        return remote

    proxies = _get_trusted_proxies()
    if not proxies or remote == "unknown":
        return remote

    try:
        addr = ip_address(remote)
    except ValueError:
        return remote

    if not _is_trusted(addr, proxies):
        return remote

    xff: str = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first

    return remote
