import os

from api.v1.schemas.common import sanitize_social_url, sanitize_speedrun_url
from celery import shared_task
from django.conf import settings
from django.db import transaction
from langcodes import standardize_tag

from srl.models import CountryCodes, Players
from srl.srcom._static_fetch import (
    StaticAssetDownloadError,
    download_speedrun_asset,
)
from srl.srcom.reconciliation import reconciliation_upsert_check
from srl.srcom.schema.src import SrcPlayersModel
from srl.utils import src_api


def save_pfp_locally(
    player_id: str,
    url: str,
) -> str:
    """Download a pfp and save it under MEDIA_ROOT/pfp/ as `{player_id}.jpg`."""
    data, _ext = download_speedrun_asset(url)
    folder_path = os.path.join(settings.MEDIA_ROOT, "pfp")
    try:
        os.makedirs(folder_path, exist_ok=True)
    except OSError as exc:
        raise StaticAssetDownloadError(
            f"cannot create {folder_path}: {exc}",
        ) from exc

    file_path = os.path.join(folder_path, f"{player_id}.jpg")
    try:
        with open(file_path, "wb") as f:
            f.write(data)
    except OSError as exc:
        raise StaticAssetDownloadError(
            f"cannot write {file_path}: {exc}",
        ) from exc
    return f"{settings.MEDIA_URL}pfp/{player_id}.jpg"


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
        src_data = src_api(f"https://speedrun.com/api/v1/users/{players_data}")
        assert isinstance(src_data, dict)

        src_player = SrcPlayersModel.model_validate(src_data)
    else:
        src_player = SrcPlayersModel.model_validate(players_data)

    if Players.objects.filter(id=src_player.id, sync_paused=True).exists():
        return

    pfp_value: str | None = None
    if src_player.pfp is not None and download_pfp:
        try:
            pfp_value = save_pfp_locally(src_player.id, src_player.pfp)
        except StaticAssetDownloadError:
            pfp_value = None

    safe_url: str | None = sanitize_speedrun_url(src_player.weblink)
    if safe_url is None:
        return

    c_code = src_player.country_code
    cc = standardize_tag(c_code.replace("/", "_")) if c_code is not None else None

    if isinstance(cc, str) and cc.startswith("ca-"):
        cc = "ca"

    if cc is not None:
        with transaction.atomic():
            reconciliation_upsert_check(
                CountryCodes,
                defaults={"name": src_player.country_name},
                record_type="country_code",
                id=cc,
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

    if pfp_value is not None:
        defaults["pfp"] = pfp_value

    with transaction.atomic():
        reconciliation_upsert_check(
            Players,
            defaults=defaults,
            record_type="player",
            id=src_player.id,
        )
