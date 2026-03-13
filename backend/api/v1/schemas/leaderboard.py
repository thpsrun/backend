from datetime import datetime

from pydantic import Field

from api.v1.schemas.base import BaseEmbedSchema


class LeaderboardEntrySchema(BaseEmbedSchema):
    """Schema for a single entry in the series-wide points leaderboard.

    Attributes:
        rank (int): Position on the leaderboard (1-based).
        player_id (str): Unique player ID.
        player_name (str): Display name; nickname if set, otherwise SRC name.
        player_url (str): Speedrun.com profile URL.
        player_pfp (str | None): Profile picture URL.
        total_points (int): Combined full-game + individual level points.
        fg_points (int): Full-game category points only.
        il_points (int): Individual level points only.
    """

    rank: int
    player_id: str = Field(..., max_length=15)
    player_name: str
    player_url: str
    player_pfp: str | None = None
    total_points: int = Field(..., ge=0)
    fg_points: int = Field(..., ge=0)
    il_points: int = Field(..., ge=0)


class GameLeaderboardEntrySchema(BaseEmbedSchema):
    """Schema for a single entry in a per-game points leaderboard.

    Attributes:
        rank (int): Position on the leaderboard (1-based).
        player_id (str): Unique player ID.
        player_name (str): Display name; nickname if set, otherwise SRC name.
        player_url (str): Speedrun.com profile URL.
        player_pfp (str | None): Profile picture URL.
        total_points (int): Combined full-game + individual level points for this game.
        fg_points (int): Full-game category points for this game only.
        il_points (int): Individual level points for this game only.
    """

    rank: int
    player_id: str = Field(..., max_length=15)
    player_name: str
    player_url: str
    player_pfp: str | None = None
    total_points: int = Field(..., ge=0)
    fg_points: int = Field(..., ge=0)
    il_points: int = Field(..., ge=0)


class OldestRunEntrySchema(BaseEmbedSchema):
    """Schema for a single entry in the THPS4 oldest-runs embed.

    Attributes:
        player_id (str): Unique player ID.
        player_name (str): Display name of the player.
        game_name (str): Name of the game the run belongs to.
        game_slug (str): URL-friendly slug for the game.
        category_name (str | None): Category name (None for IL runs without a category).
        level_name (str | None): Level name for IL runs; None for full-game runs.
        place (int): Leaderboard placement (1-based, minimum 1).
        time (str | None): Primary timing of the run (p_time).
        date (datetime | None): Submission date of the run.
        days_held (int): Days since the run was set; -1 if date is unknown.
    """

    player_id: str = Field(..., max_length=15)
    player_name: str
    game_name: str
    game_slug: str
    category_name: str | None = None
    level_name: str | None = None
    place: int = Field(..., ge=1)
    time: str | None = None
    date: datetime | None = None
    days_held: int = Field(..., ge=-1)
