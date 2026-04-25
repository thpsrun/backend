from datetime import date
from typing import Any

from django.conf import settings
from pydantic import ConfigDict, Field, field_validator

from api.v1.schemas.base import BaseEmbedSchema, SlugMixin, TimingMethodType


class GameBaseSchema(SlugMixin, BaseEmbedSchema):
    """Base schema for `Game` data without embeds.

    Attributes:
        id (str): Unique ID (usually based on SRC) of the game.
        name (str): Full game name (e.g., "Tony Hawk's Pro Skater 4").
        slug (str): URL-friendly abbreviation (e.g., "thps4").
        twitch (str | None): Game name as it appears on Twitch.
        release (date): Game release date.
        boxart (str): URL to game cover art.
        defaulttime (str): Default timing method for full-game runs.
        idefaulttime (str): Default timing method for individual level runs.
        pointsmax (int): Maximum points for world record full-game runs.
        ipointsmax (int): Maximum points for world record IL runs.
        rules (str | None): Game-level rules text.
    """

    id: str = Field(..., max_length=10)
    name: str = Field(..., max_length=55)
    slug: str = Field(..., max_length=20, description="URL-friendly slug")
    twitch: str | None = Field(
        default=None, max_length=55, description="Game name on Twitch"
    )
    rules: str | None = Field(
        default=None, max_length=5000, description="Game-level rules"
    )
    release: date
    boxart: str
    defaulttime: TimingMethodType = Field(
        ...,
        description="Timing for full-game runs",
    )
    idefaulttime: TimingMethodType = Field(
        ...,
        description="Timing for IL runs",
    )
    pointsmax: int = Field(
        settings.POINTS_MAX_FG, ge=1, description="WR points for full-game runs"
    )
    ipointsmax: int = Field(
        settings.POINTS_MAX_IL, ge=1, description="WR points for IL runs"
    )


class GameSchema(GameBaseSchema):
    """Complete game schema with optional embedded data.

    Attributes:
        categories (List[dict] | None): Game categories - included with ?embed=categories.
        levels (List[dict] | None): Individual levels - included with ?embed=levels.
        platforms (List[dict] | None): Supported platforms - included with ?embed=platforms.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "n2680o1p",
                "name": "Tony Hawk's Pro Skater 4",
                "slug": "thps4",
                "twitch": "Tony Hawk's Pro Skater 4",
                "rules": "Timing starts on first input and ends on final input.",
                "release": "2002-10-23",
                "boxart": "https://example.com/boxart.jpg",
                "defaulttime": "realtime",
                "idefaulttime": "realtime",
                "pointsmax": 1000,
                "ipointsmax": 100,
            },
        },
    )

    categories: list[dict] | None = Field(
        None, description="Included with ?embed=categories"
    )
    levels: list[dict] | None = Field(None, description="Included with ?embed=levels")
    platforms: list[dict] | None = Field(
        None, description="Included with ?embed=platforms"
    )

    @field_validator("platforms", "categories", "levels", mode="before")
    @classmethod
    def convert_manager_to_list(
        cls,
        v: Any,
    ) -> list[dict] | None:
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if hasattr(v, "all"):
            return None
        return v


class GameListSchema(BaseEmbedSchema):
    """Schema for paginated game list responses.

    Attributes:
        count (int): Total number of games.
        results (List[GameSchema]): Games for this page.
    """

    count: int
    results: list[GameSchema]


class GameCreateSchema(SlugMixin, BaseEmbedSchema):
    """Schema for creating new games.

    Attributes:
        id (str | None): The game ID; if one is not given, it will auto-generate.
        name (str): Game name.
        slug (str): URL-friendly game abbreviation.
        twitch (str | None): Game name as it appears on Twitch.
        release (date): Game release date.
        boxart (str): URL to game box art/cover image.
        defaulttime (str): Default timing method for full-game runs.
        idefaulttime (str): Default timing method for individual level runs.
        pointsmax (int): Maximum points for world record full-game runs.
        ipointsmax (int): Maximum points for world record individual level runs.
        rules (str | None): Game-level rules text.
    """

    id: str | None = Field(
        default=None, max_length=10, description="Auto-generates if omitted"
    )
    name: str = Field(..., max_length=55)
    slug: str = Field(..., max_length=20, description="URL-friendly slug")
    twitch: str | None = Field(
        default=None, max_length=55, description="Game name on Twitch"
    )
    rules: str | None = Field(
        default=None, max_length=5000, description="Game-level rules"
    )
    release: date
    boxart: str
    defaulttime: TimingMethodType = Field(default="realtime")
    idefaulttime: TimingMethodType = Field(default="realtime")
    pointsmax: int = Field(
        settings.POINTS_MAX_FG, ge=1, description="WR points for full-game runs"
    )
    ipointsmax: int = Field(
        settings.POINTS_MAX_IL, ge=1, description="WR points for IL runs"
    )


class GameUpdateSchema(BaseEmbedSchema):
    """Schema for updating existing games.

    Attributes:
        name (str | None): Updated game name.
        slug (str | None): Updated URL-friendly game abbreviation.
        twitch (str | None): Updated Twitch name.
        release (date | None): Updated release date.
        boxart (str | None): Updated box art URL.
        defaulttime (str | None): Updated default timing method for full-game runs.
        idefaulttime (str | None): Updated default timing method for IL runs.
        pointsmax (int | None): Updated max points for full-game runs.
        ipointsmax (int | None): Updated max points for IL runs.
        rules (str | None): Updated game-level rules text.
    """

    name: str | None = Field(default=None, max_length=55)
    slug: str | None = Field(
        default=None, min_length=1, max_length=20, description="URL-friendly slug"
    )
    twitch: str | None = Field(default=None, max_length=55)
    rules: str | None = Field(
        default=None, max_length=5000, description="Game-level rules"
    )
    release: date | None = None
    boxart: str | None = None
    defaulttime: TimingMethodType | None = None
    idefaulttime: TimingMethodType | None = None
    pointsmax: int | None = Field(default=None, ge=1)
    ipointsmax: int | None = Field(default=None, ge=1)


GameSchema.model_rebuild()
