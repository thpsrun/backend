from typing import Iterator

from srl.models import Series
from srl.srcom.categories import sync_categories
from srl.srcom.games import apply_game_record
from srl.srcom.levels import sync_levels
from srl.srcom.platforms import sync_platforms
from srl.srcom.reconciliation import reconciliation_upsert_check
from srl.srcom.schema.src import SrcGamesModel
from srl.srcom.variables import sync_variables
from srl.utils import src_api, src_api_paginate

SRC_API_BASE = "https://www.speedrun.com/api/v1"


def import_game_metadata(
    game_id: str,
) -> SrcGamesModel:
    """Synchronously import a single game's metadata in dependency order."""
    raw = src_api(
        f"{SRC_API_BASE}/games/{game_id}?embed=platforms,levels,categories,variables",
    )
    game_data = SrcGamesModel.model_validate(raw)

    for platform in game_data.platforms:
        sync_platforms(platform)

    apply_game_record(game_data)

    for category in game_data.categories or []:
        sync_categories(category, game_id=game_data.id)
    for level in game_data.levels or []:
        sync_levels(level)
    for variable in game_data.variables or []:
        sync_variables(variable)

    return game_data


def iter_series_games(
    series_id: str,
) -> Iterator[dict]:
    """Yield every game record on a Speedrun.com series, following pagination links."""
    yield from src_api_paginate(f"{SRC_API_BASE}/series/{series_id}/games")


def sync_series(
    series_id: str,
) -> tuple[Series, dict]:
    """Fetch a series from Speedrun.com and upsert the local Series record."""
    payload = src_api(f"{SRC_API_BASE}/series/{series_id}")
    assert isinstance(payload, dict)

    canonical_id: str = payload["id"]
    name: str = payload["names"]["international"]
    url: str = payload["weblink"]

    instance = reconciliation_upsert_check(
        Series,
        defaults={"name": name, "url": url},
        record_type="series",
        id=canonical_id,
    )
    return instance, payload
