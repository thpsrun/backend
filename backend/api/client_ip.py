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
    """Parse TRUSTED_PROXIES once per process; the setting is env-fixed at startup."""
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
            # A malformed entry must not break IP resolution for every request;
            # dropping it just means that proxy is treated as untrusted.
            continue
    return tuple(parsed)


def _is_trusted(
    addr: IPv4Address | IPv6Address,
    proxies: tuple[TrustedEntry, ...],
) -> bool:
    """Check an address against the trusted proxy list (exact IPs and CIDR ranges)."""
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
    """Resolve the real client IP, trusting X-Forwarded-For only behind a trusted proxy.

    Arguments:
        request (HttpRequest): The incoming request.

    Returns:
        ip (str): The resolved client IP, or REMOTE_ADDR ("unknown" if absent) when the
            peer is untrusted, no proxies are configured, or the chain yields no
            non-proxy address.
    """
    remote: str = request.META.get("REMOTE_ADDR", "") or "unknown"

    # Dev runserver has no proxy in front; never honor XFF locally so it can't be spoofed.
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
    if not xff:
        return remote

    # Walks right-to-left, peeling off any trusted proxies. This is mainly to figure out what the
    # real client IP is to prevent forged IP addresses from targeing the site.
    for entry in reversed(xff.split(",")):
        candidate = entry.strip()
        if not candidate:
            continue
        try:
            candidate_addr = ip_address(candidate)
        except ValueError:
            continue
        if not _is_trusted(candidate_addr, proxies):
            return candidate

    # Every XFF hop was itself a trusted proxy; fall back to the direct peer.
    return remote
