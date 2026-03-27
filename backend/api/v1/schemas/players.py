from datetime import date
from typing import Any

from pydantic import Field, field_validator

from api.v1.schemas.base import BaseEmbedSchema


class PlayerBaseSchema(BaseEmbedSchema):
    """Base schema for `Players` data without embeds.

    Attributes:
        id (str): Unique ID (usually based on SRC) of the player.
        name (str): Player name on Speedrun.com.
        nickname (str | None): Custom nickname override (displayed instead of name).
        url (str): Speedrun.com profile URL.
        pfp (str | None): Profile picture URL.
        pronouns (str | None): Player pronouns.
        twitch (str | None): Twitch channel URL.
        youtube (str | None): YouTube channel URL.
        twitter (str | None): Twitter profile URL.
        bluesky (str | None): Bluesky profile URL.
        discord (str | None): Discord username.
        ex_stream (bool): Whether player is excluded from streaming features.
        joined (date | None): Date of the player's first verified speedrun.
    """

    id: str = Field(..., max_length=15)
    name: str = Field(..., max_length=30)
    nickname: str | None = Field(
        default=None,
        max_length=30,
        description="Displayed instead of name if set",
    )
    url: str
    pfp: str | None = Field(
        default=None, max_length=100, description="Profile picture URL"
    )
    pronouns: str | None = Field(default=None, max_length=50)
    twitch: str | None = None
    youtube: str | None = None
    twitter: str | None = None
    bluesky: str | None = None
    discord: str | None = None
    ex_stream: bool = Field(default=False, description="Exclude from streaming bots")
    joined: date | None = Field(
        default=None, description="Date of first verified speedrun"
    )


class CountrySchema(BaseEmbedSchema):
    """Simple schema for country codes.

    Attributes:
        id (str): Country code ID.
        name (str): Country name.
    """

    id: str
    name: str


class StatsSchema(BaseEmbedSchema):
    """Simple schema for player stats.

    Attributes:
        total_runs (int): Number of runs (including obsolete) for a player.
        fg_points (float | None): Number of points a player has for all full-game runs together.
        il_points (float | None): Number of points a player has for all IL runs together.
    """

    total_runs: int
    fg_points: float | None = 0
    il_points: float | None = 0


class AwardSchema(BaseEmbedSchema):
    """Simple schema for awards.

    Attributes:
        name (str): Award name.
        description (str | None): Award description.
        image (str | None): Award image URL.
    """

    name: str
    description: str | None = None
    image: str | None = None


class ModeratedGameEmbedSchema(BaseEmbedSchema):
    """Schema for games a player moderates.

    Attributes:
        id (str): Game ID.
        name (str): Game name.
        slug (str): Game slug/abbreviation.
    """

    id: str
    name: str
    slug: str


class PlayerRunSchema(BaseEmbedSchema):
    """Schema for run data embedded in player responses.

    Attributes:
        id (str): Run ID.
        game (str | None): Game name.
        category (str | None): Category name.
        level (str | None): Level name (for IL runs).
        place (int | None): Placement on leaderboard.
        time (str | None): Run time.
        date (str | None): Run date (ISO format).
        url (str): URL to the run on SRC.
        video (str | None): Twitch or YouTube video URL.
        arch_video (str | None): Archived video URL.
    """

    id: str
    game: str | None = None
    category: str | None = None
    level: str | None = Field(default=None, description="For IL runs")
    place: int | None = None
    time: str | None = None
    date: str | None = None
    url: str
    video: str | None = None
    arch_video: str | None = None


class PlayerSchema(PlayerBaseSchema):
    """Complete player schema with optional embedded data.

    Attributes:
        country (CountrySchema | None): Country information - included with ?embed=country.
        awards (list[AwardSchema] | None): Player earned awards - included with ?embed=awards.
        runs (list[PlayerRunSchema] | None): Recent player runs (limited to 20) - included with
            ?embed=runs.
    """

    country: CountrySchema | None = Field(
        None, description="Shows full information on the player's country."
    )
    stats: StatsSchema | None = Field(None, description="Shows the player's points.")
    awards: list[AwardSchema] | None = Field(
        None, description="Shows full information on the player's awards."
    )
    runs: list[PlayerRunSchema] | None = Field(
        None,
        description="Limited to showing the last 25 approved, non-obsolete runs.",
    )
    fg: list[PlayerRunSchema] | None = Field(
        None, description="Shows all of the full-game runs from the player."
    )
    il: list[PlayerRunSchema] | None = Field(
        None, description="Shows all of the individual level runs from the player."
    )
    moderated_games: list[ModeratedGameEmbedSchema] | None = Field(
        None,
        description="Games this player moderates. Null if not a moderator.",
    )

    @field_validator("country", mode="before")
    @classmethod
    def convert_country_to_none(cls, v: Any) -> dict | None:
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        return None

    @field_validator("awards", "runs", "moderated_games", mode="before")
    @classmethod
    def convert_manager_to_none(cls, v: Any) -> list[dict] | None:
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if hasattr(v, "all"):
            return None
        return v


class PlayerCreateSchema(BaseEmbedSchema):
    """Schema for creating new players.

    Attributes:
        id (str | None): The player ID; if one is not given, it will auto-generate.
        name (str): Player name.
        nickname (str | None): Custom nickname.
        url (str): Speedrun.com profile URL.
        country_id (str | None): Country code ID.
        pfp (str | None): Profile picture URL.
        pronouns (str | None): Player pronouns.
        twitch (str | None): Twitch channel URL.
        youtube (str | None): YouTube channel URL.
        twitter (str | None): Twitter profile URL.
        bluesky (str | None): Bluesky profile URL.
        discord (str | None): Discord username.
        ex_stream (bool): Whether to exclude from streaming features.
    """

    id: str | None = Field(
        default=None, max_length=12, description="Auto-generates if omitted"
    )
    name: str = Field(..., max_length=30)
    nickname: str | None = Field(
        default=None, max_length=30, description="Displayed instead of name if set"
    )
    url: str
    country_id: str | None = None
    pfp: str | None = Field(
        default=None, max_length=100, description="Profile picture URL"
    )
    pronouns: str | None = Field(default=None, max_length=20)
    twitch: str | None = None
    youtube: str | None = None
    twitter: str | None = None
    bluesky: str | None = None
    discord: str | None = None
    ex_stream: bool = Field(default=False, description="Exclude from streaming bots")


class PlayerUpdateSchema(BaseEmbedSchema):
    """Schema for updating players.

    Attributes:
        name (str | None): Updated player name.
        nickname (str | None): Updated nickname.
        url (str | None): Updated Speedrun.com profile URL.
        country_id (str | None): Updated country code ID.
        pfp (str | None): Updated profile picture URL.
        pronouns (str | None): Updated pronouns.
        twitch (str | None): Updated Twitch channel URL.
        youtube (str | None): Updated YouTube channel URL.
        twitter (str | None): Updated Twitter profile URL.
        bluesky (str | None): Updated Bluesky profile URL.
        discord (str | None): Updated Discord username.
        ex_stream (bool | None): Updated streaming exclusion flag.
    """

    name: str | None = Field(default=None, max_length=30)
    nickname: str | None = Field(default=None, max_length=30)
    url: str | None = None
    country_id: str | None = None
    pfp: str | None = Field(default=None, max_length=100)
    pronouns: str | None = Field(default=None, max_length=20)
    twitch: str | None = None
    youtube: str | None = None
    twitter: str | None = None
    bluesky: str | None = None
    discord: str | None = None
    ex_stream: bool | None = None
