import ipaddress
import os
import socket
import time
from urllib.parse import urlparse

from curl_cffi import requests as cffi_requests
from curl_cffi.requests.exceptions import RequestException as CffiRequestException

from srl.utils import SRC_HEADERS

DEFAULT_MAX_BYTES: int = 10 * 1024 * 1024
ALLOWED_HOST_SUFFIXES: tuple[str, ...] = (
    "speedrun.com",
    "www.speedrun.com",
)
IMPERSONATE: str = "chrome120"
CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
ALLOWED_URL_EXTS: tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
)
HEADERS: dict[str, str] = {
    **SRC_HEADERS,
    "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.speedrun.com/",
}


class StaticAssetDownloadError(Exception):
    """Raised when a speedrun.com static asset cannot be fetched.

    The exception message describes the reason (SSRF rejection, HTTP status,
    request exception, byte cap exceeded, etc.).
    """


def normalize_url(
    url: str,
) -> str:
    """Upgrade http://speedrun.com URLs to https; otherwise return unchanged."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    if parsed.scheme != "http":
        return url
    host: str = (parsed.hostname or "").lower()
    if not any(host == s or host.endswith(f".{s}") for s in ALLOWED_HOST_SUFFIXES):
        return url
    return "https://" + url[len("http://") :]


def is_safe_url(
    url: str,
) -> bool:
    """Reject URLs that would allow SSRF before the network call is made."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    host: str = (parsed.hostname or "").lower()
    if not host:
        return False
    if not any(host == s or host.endswith(f".{s}") for s in ALLOWED_HOST_SUFFIXES):
        return False
    try:
        addrinfo = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for entry in addrinfo:
        try:
            ip = ipaddress.ip_address(entry[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def _ext_from_content_type(
    content_type: str | None,
) -> str | None:
    if not content_type:
        return None
    ctype: str = content_type.split(";")[0].strip().lower()
    return CONTENT_TYPE_TO_EXT.get(ctype)


def _ext_from_url(
    url: str,
) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        return ".png"
    ext: str = os.path.splitext(parsed.path)[1].lower()
    if ext == ".jpeg":
        return ".jpg"
    if ext in ALLOWED_URL_EXTS:
        return ext
    return ".png"


def _get(
    url: str,
):
    try:
        return cffi_requests.get(
            url,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True,
            stream=True,
            impersonate=IMPERSONATE,
        )
    except CffiRequestException as exc:
        raise StaticAssetDownloadError(f"request error: {exc}") from exc


def download_speedrun_asset(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[bytes, str]:
    """Download a speedrun.com static asset with curl_ccfi to help get past Cloudflare."""
    url = normalize_url(url)
    if not is_safe_url(url):
        raise StaticAssetDownloadError(f"rejected by SSRF guard: {url}")

    response = _get(url)

    retries: int = 0
    while response.status_code in (420, 503):
        retries += 1
        if retries >= 30:
            response.close()
            raise StaticAssetDownloadError(
                f"SRC rate limit exceeded after 30 retries ({response.status_code})",
            )
        response.close()
        time.sleep(60)
        response = _get(url)

    try:
        if response.status_code != 200:
            ctype: str = response.headers.get("Content-Type", "")
            raise StaticAssetDownloadError(
                f"HTTP {response.status_code} (content-type={ctype!r})",
            )
        ext: str = _ext_from_content_type(
            response.headers.get("Content-Type")
        ) or _ext_from_url(url)
        chunks: list[bytes] = []
        total: int = 0
        for chunk in response.iter_content():
            total += len(chunk)
            if total > max_bytes:
                raise StaticAssetDownloadError(
                    f"exceeded {max_bytes} byte cap",
                )

            chunks.append(chunk)
        return b"".join(chunks), ext
    finally:
        response.close()
