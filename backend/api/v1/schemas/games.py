from datetime import date
from typing import Any

from django.conf import settings
from pydantic import ConfigDict, Field, field_validator

from api.v1.schemas.base import BaseEmbedSchema, SlugMixin, TimingMethodType
from api.v1.schemas.players import GradientsEmbed
from api.v1.schemas.sanitization import sanitize_optional_markdown


class GameModeratorEmbedSchema(BaseEmbedSchema):
    """Player summary used in a game's moderator list.

    Attributes:
        id (str): Player ID.
        name (str): Player name.
        nickname (str | None): Player nickname override, if any.
        url (str): Player profile URL.
        country_id (str | None): Country code ID.
        pfp (str | None): Profile picture URL.
        gradients (GradientsEmbed | None): Player's name gradient colors; None if unclaimed or
            no colors set.
    """

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
        json_schema_extra={
            "example": {
                "id": "v8lponvj",
                "name": "ThePackle",
                "nickname": None,
                "url": "https://speedrun.com/user/ThePackle",
                "country_id": "us",
                "pfp": None,
                "gradients": {
                    "gradient_1": "#ff0000",
                    "gradient_2": "#00ff00",
                    "gradient_3": "#0000ff",
                },
            },
        },
    )

    id: str = Field(..., max_length=10)
    name: str
    nickname: str | None = None
    url: str
    country_id: str | None = None
    pfp: str | None = None
    gradients: GradientsEmbed | None = None


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
        required_methods_fg (list[TimingMethodType]): Timing methods allowed for full-game runs.
        required_methods_il (list[TimingMethodType]): Timing methods allowed for IL runs.
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
    required_methods_fg: list[TimingMethodType] = Field(
        default_factory=list,
        description="Timing methods allowed for full-game runs",
    )
    required_methods_il: list[TimingMethodType] = Field(
        default_factory=list,
        description="Timing methods allowed for individual-level runs",
    )


class GameSchema(GameBaseSchema):
    """Complete game schema with optional embedded data.

    Attributes:
        categories (List[dict] | None): Game categories - included with ?embed=categories.
        levels (List[dict] | None): Individual levels - included with ?embed=levels.
        platforms (List[dict] | None): Supported platforms - included with ?embed=platforms.
        moderators (List[GameModeratorEmbedSchema] | None): Game moderators - included with
            ?embed=moderators.
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
                "defaulttime": "rta",
                "idefaulttime": "rta",
                "pointsmax": 1000,
                "ipointsmax": 100,
                "required_methods_fg": ["rta", "igt"],
                "required_methods_il": ["rta"],
                "moderators": [
                    {
                        "id": "v8lponvj",
                        "name": "ThePackle",
                        "nickname": None,
                        "url": "https://speedrun.com/user/ThePackle",
                        "country_id": "us",
                        "pfp": None,
                        "gradients": {
                            "gradient_1": "#ff0000",
                            "gradient_2": "#00ff00",
                            "gradient_3": "#0000ff",
                        },
                    },
                ],
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
    moderators: list[GameModeratorEmbedSchema] | None = Field(
        None, description="Included with ?embed=moderators"
    )

    @field_validator("platforms", "categories", "levels", "moderators", mode="before")
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
    defaulttime: TimingMethodType = Field(default="rta")
    idefaulttime: TimingMethodType = Field(default="rta")
    pointsmax: int = Field(
        settings.POINTS_MAX_FG, ge=1, description="WR points for full-game runs"
    )
    ipointsmax: int = Field(
        settings.POINTS_MAX_IL, ge=1, description="WR points for IL runs"
    )
    required_methods_fg: list[TimingMethodType] | None = Field(
        default=None,
        description="Allowed FG timing methods. If null, defaults to all three.",
    )
    required_methods_il: list[TimingMethodType] | None = Field(
        default=None,
        description="Allowed IL timing methods. If null, defaults to all three.",
    )

    @field_validator("rules", mode="after")
    @classmethod
    def _sanitize_rules(
        cls,
        value: str | None,
    ) -> str | None:
        return sanitize_optional_markdown(value)


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
    required_methods_fg: list[TimingMethodType] | None = None
    required_methods_il: list[TimingMethodType] | None = None

    @field_validator("rules", mode="after")
    @classmethod
    def _sanitize_rules(
        cls,
        value: str | None,
    ) -> str | None:
        return sanitize_optional_markdown(value)


GameSchema.model_rebuild()


class ResolveTimingResponse(BaseEmbedSchema):
    """Resolved timing methods for a (game, category, level, variables) selection.

    Attributes:
        resolved_required_methods (list[TimingMethodType]): Timing methods the run must
            provide values for. Resolved by walking VariableValue -> Variable -> Category
            -> Game (`required_methods_il` for ILs, `required_methods_fg` otherwise).
        resolved_primary_method (TimingMethodType): The primary method used for leaderboard
            placement, resolved by the same chain against `defaulttime` / `idefaulttime`.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resolved_required_methods": ["rta", "igt"],
                "resolved_primary_method": "rta",
            },
        },
    )

    resolved_required_methods: list[TimingMethodType] = Field(
        description="Timing methods required for the selection.",
    )
    resolved_primary_method: TimingMethodType = Field(
        description="Primary timing method used for leaderboard placement.",
    )
