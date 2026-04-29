from datetime import datetime

from pydantic import ConfigDict, Field

from api.v1.schemas.base import BaseEmbedSchema
from api.v1.schemas.common import CountrySchema
from api.v1.schemas.players import GradientsEmbed


class LeaderboardPlayerEmbed(BaseEmbedSchema):
    """Nested player identity for leaderboard entries.

    Attributes:
        id (str): Unique player ID.
        name (str): Player name on Speedrun.com.
        nickname (str | None): Custom nickname override.
        url (str): Speedrun.com profile URL.
        pfp (str | None): Profile picture URL.
        country (CountrySchema | None): Country code reference; None if unset.
        gradients (GradientsEmbed | None): Player gradient colors; None if unclaimed
            or no colors set.
    """

    id: str = Field(..., max_length=15)
    name: str
    nickname: str | None = None
    url: str
    pfp: str | None = None
    country: CountrySchema | None = None
    gradients: GradientsEmbed | None = None


class LeaderboardEntrySchema(BaseEmbedSchema):
    """Schema for a single entry in a points leaderboard (series-wide or per-game).

    Attributes:
        rank (int): Position on the leaderboard.
        total_points (int): Combined full-game + individual level points.
        fg_points (int): Full-game category points.
        il_points (int): Individual level points.
        player (LeaderboardPlayerEmbed): Nested player information.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rank": 1,
                "total_points": 4250,
                "fg_points": 3100,
                "il_points": 1150,
                "player": {
                    "id": "v8lponvj",
                    "name": "PlayerOne",
                    "nickname": None,
                    "url": "https://speedrun.com/user/PlayerOne",
                    "pfp": None,
                    "country": {"id": "us", "name": "United States", "flag": None},
                    "gradients": {
                        "gradient_1": "#ff0000",
                        "gradient_2": "#00ff00",
                        "gradient_3": "#0000ff",
                    },
                },
            },
        },
    )

    rank: int = Field(..., ge=1)
    total_points: int = Field(..., ge=0)
    fg_points: int = Field(..., ge=0)
    il_points: int = Field(..., ge=0)
    player: LeaderboardPlayerEmbed


PointLeaderboardEntrySchema = LeaderboardEntrySchema
GameLeaderboardEntrySchema = LeaderboardEntrySchema


class OldestRunEntrySchema(BaseEmbedSchema):
    """Schema for a single entry in the THPS4 oldest-runs embed.

    Attributes:
        player (LeaderboardPlayerEmbed): Nested player identity.
        game_name (str): Name of the game the run belongs to.
        game_slug (str): URL-friendly slug for the game.
        category_name (str | None): Category name (None for IL runs without a category).
        level_name (str | None): Level name for IL runs; None for full-game runs.
        place (int): Leaderboard placement (1-based, minimum 1).
        time (str | None): Primary timing of the run (p_time).
        date (datetime | None): Submission date of the run.
        days_held (int): Days since the run was set; -1 if date is unknown.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "player": {
                    "id": "v8lponvj",
                    "name": "PlayerOne",
                    "nickname": None,
                    "url": "https://speedrun.com/user/PlayerOne",
                    "pfp": None,
                    "country": {"id": "us", "name": "United States", "flag": None},
                    "gradients": None,
                },
                "game_name": "THPS4",
                "game_slug": "thps4",
                "category_name": "Any%",
                "level_name": "Manhattan",
                "place": 1,
                "time": "1:23.456",
                "date": "2018-06-01T00:00:00Z",
                "days_held": 2856,
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
