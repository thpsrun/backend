import ipaddress
import logging
import os
import socket
import time
from typing import Any
from urllib.parse import urlparse

import requests
from api.v1.schemas.common import sanitize_social_url, sanitize_speedrun_url
from celery import shared_task
from django.conf import settings
from django.db import transaction
from langcodes import standardize_tag

from srl.models import CountryCodes, Players
from srl.srcom.schema.src import SrcPlayersModel
from srl.utils import src_api

logger = logging.getLogger(__name__)

MAX_PFP_BYTES: int = 10 * 1024 * 1024
ALLOWED_PFP_HOST_SUFFIXES: tuple[str, ...] = ("speedrun.com",)


def _is_safe_pfp_url(
    url: str,
) -> bool:
    """Reject URLs that would allow SSRF before requests.get is called."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    host: str = (parsed.hostname or "").lower()
    if not host:
        return False
    if not any(host == s or host.endswith(f".{s}") for s in ALLOWED_PFP_HOST_SUFFIXES):
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


def _download_pfp_bytes(
    url: str,
) -> bytes | None:
    """Fetch a PFP after SSRF validation. Returns None on any failure."""
    if not _is_safe_pfp_url(url):
        logger.warning("Refusing to fetch unsafe PFP URL: %s", url)
        return None

    response = requests.get(
        url,
        timeout=30,
        allow_redirects=False,
        stream=True,
    )

    retries: int = 0
    while response.status_code in (420, 503):
        retries += 1
        if retries >= 30:
            response.close()
            raise ValueError(
                f"SRC API rate limit exceeded after 30 retries (pfp: {url})",
            )
        response.close()
        time.sleep(60)
        response = requests.get(
            url,
            timeout=30,
            allow_redirects=False,
            stream=True,
        )

    try:
        if response.status_code != 200:
            return None
        chunks: list[bytes] = []
        total: int = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            total += len(chunk)
            if total > MAX_PFP_BYTES:
                logger.warning("PFP exceeds %d bytes, dropping: %s", MAX_PFP_BYTES, url)
                return None
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        response.close()


@shared_task
def sync_players(
    players_data: str | dict,
    download_pfp: bool = False,
) -> None:
    """Creates or updates a `Players` model object based on the `players_data` argument.

    Arguments:
        players_data (str | dict): Either the unique ID (str) of the player or the embedded
            player dict information.
    """
    if isinstance(players_data, str):
        src_data: dict[str, Any] = src_api(
            f"https://speedrun.com/api/v1/users/{players_data}"
        )

        src_player = SrcPlayersModel.model_validate(src_data)
    else:
        src_player = SrcPlayersModel.model_validate(players_data)

    if Players.objects.filter(id=src_player.id, sync_paused=True).exists():
        return

    pfp_written: bool = False
    if src_player.pfp is not None and download_pfp:
        pfp_bytes: bytes | None = _download_pfp_bytes(src_player.pfp)
        if pfp_bytes is not None:
            folder_path = os.path.join(settings.MEDIA_ROOT, "pfp")
            os.makedirs(folder_path, exist_ok=True)
            file_path = os.path.join(folder_path, f"{src_player.id}.jpg")
            with open(file_path, "wb") as f:
                f.write(pfp_bytes)
            pfp_written = True

    safe_url: str | None = sanitize_speedrun_url(src_player.weblink)
    if safe_url is None:
        logger.warning(
            "Refusing to sync player %s: invalid weblink %r",
            src_player.id,
            src_player.weblink,
        )
        return

    c_code = src_player.country_code
    cc = standardize_tag(c_code.replace("/", "_")) if c_code is not None else None

    if isinstance(cc, str) and cc.startswith("ca-"):
        cc = "ca"

    if cc is not None:
        with transaction.atomic():
            CountryCodes.objects.update_or_create(
                id=cc,
                defaults={
                    "name": src_player.country_name,
                },
            )

    try:
        cc_get = CountryCodes.objects.only("id").get(id=cc)
    except CountryCodes.DoesNotExist:
        cc_get = None

    defaults = {
        "name": src_player.names.international,
        "url": safe_url,
        "countrycode": cc_get,
        "pronouns": src_player.pronouns,
        "twitch": sanitize_social_url("twitch", src_player.twitch_url),
        "youtube": sanitize_social_url("youtube", src_player.youtube_url),
    }

    if pfp_written:
        defaults["pfp"] = f"{settings.MEDIA_URL}pfp/{src_player.id}.jpg"

    with transaction.atomic():
        Players.objects.update_or_create(
            id=src_player.id,
            defaults=defaults,
        )
