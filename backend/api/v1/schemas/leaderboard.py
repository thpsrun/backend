from datetime import datetime

from pydantic import ConfigDict, Field

from api.v1.schemas.base import BaseEmbedSchema
from api.v1.schemas.players import GradientsEmbed


class CountryRefEmbed(BaseEmbedSchema):
    """Slim country reference matching the shape used by /website/lbs/* run player exports."""

    id: str
    name: str


class LeaderboardPlayerEmbed(BaseEmbedSchema):
    """Player identity used by points leaderboard entries.

    Mirrors the shape exported by /website/lbs/* endpoints (see
    `_export_players`): `name` is the display name (nickname if set,
    otherwise the SRC name); `country` is a {id, name} reference;
    `gradients` is the user's three-color name palette.
    """

    name: str
    country: CountryRefEmbed | None = None
    gradients: GradientsEmbed | None = None


class LeaderboardEntrySchema(BaseEmbedSchema):
    """Schema for a single entry in a points leaderboard (series-wide or per-game).

    Attributes:
        rank (int): Position on the leaderboard (1-based).
        player (LeaderboardPlayerEmbed): Nested player identity.
        total_points (int): Combined full-game + individual level points.
        fg_points (int): Full-game category points.
        il_points (int): Individual level points.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rank": 1,
                "player": {
                    "name": "ThePackle",
                    "country": {"id": "us", "name": "United States"},
                    "gradients": {
                        "gradient_1": "#ff0000",
                        "gradient_2": "#00ff00",
                        "gradient_3": "#0000ff",
                    },
                },
                "total_points": 18200,
                "fg_points": 15000,
                "il_points": 3200,
            },
        },
    )

    rank: int = Field(..., ge=1)
    player: LeaderboardPlayerEmbed
    total_points: int = Field(..., ge=0)
    fg_points: int = Field(..., ge=0)
    il_points: int = Field(..., ge=0)


PointLeaderboardEntrySchema = LeaderboardEntrySchema
GameLeaderboardEntrySchema = LeaderboardEntrySchema


class OldestRunEntrySchema(BaseEmbedSchema):
    """Schema for a single entry in the oldest-runs embed.

    Attributes:
        player (LeaderboardPlayerEmbed): Nested player identity.
        game_name (str): Name of the game the run belongs to.
        game_slug (str): URL-friendly slug for the game.
        category_name (str | None): Category name (None for IL runs without a category).
        level_name (str | None): Level name for IL runs.
        place (int): Leaderboard placement (1-based, minimum 1).
        time (str | None): Primary timing of the run (p_time).
        date (datetime | None): Submission date of the run.
        days_held (int): Days since the run was set; -1 if date is unknown.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "player": {
                    "name": "ThePackle",
                    "country": {"id": "us", "name": "United States"},
                    "gradients": None,
                },
                "game_name": "Tony Hawk's Pro Skater 4",
                "game_slug": "thps4",
                "category_name": "Any%",
                "level_name": None,
                "place": 1,
                "time": "1m 23s",
                "date": "2018-05-12T00:00:00Z",
                "days_held": 2906,
            },
        },
    )

    player: LeaderboardPlayerEmbed
    game_name: str
    game_slug: str
    category_name: str | None = None
    level_name: str | None = None
    place: int = Field(..., ge=1)
    time: str | None = None
    date: datetime | None = None
    days_held: int = Field(..., ge=-1)
