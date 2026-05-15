from typing import Iterator

from srl.models import Series
from srl.srcom.categories import sync_categories
from srl.srcom.games import sync_game
from srl.srcom.leaderboards import sync_game_runs
from srl.srcom.levels import sync_levels
from srl.srcom.platforms import sync_platforms
from srl.srcom.reconciliation import (
    current_job,
    dispatch_with_recon,
    reconciliation_upsert_check,
)
from srl.srcom.schema.src import SrcGamesModel
from srl.srcom.variables import sync_variables
from srl.utils import src_api, src_api_paginate

SRC_API_BASE = "https://www.speedrun.com/api/v1"


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
        defaults={"name": name[:20], "url": url},
        record_type="series",
        id=canonical_id,
    )
    return instance, payload


def import_new_game(
    game_id: str,
    *,
    skip_runs: bool = False,
) -> dict:
    """Fetch a game's metadata from SRC and queue all per-game sync tasks."""
    raw = src_api(
        f"{SRC_API_BASE}/games/{game_id}?embed=platforms,levels,categories,variables",
    )
    game_data = SrcGamesModel.model_validate(raw)

    for platform in game_data.platforms:
        sync_platforms.delay(platform.model_dump())

    sync_game.delay(game_data.id)

    if game_data.categories:
        for category in game_data.categories:
            sync_categories.delay(category.model_dump())

    if game_data.levels:
        for level in game_data.levels:
            sync_levels.delay(level.model_dump())

    if game_data.variables:
        for variable in game_data.variables:
            sync_variables.delay(variable.model_dump())

    if not skip_runs:
        if current_job() is not None:
            dispatch_with_recon(sync_game_runs, game_data.id, 0)
        else:
            sync_game_runs.delay(game_data.id, 0)

    return {
        "name": game_data.names.international,
        "platforms": len(game_data.platforms),
        "categories": len(game_data.categories or []),
        "levels": len(game_data.levels or []),
        "variables": len(game_data.variables or []),
    }
