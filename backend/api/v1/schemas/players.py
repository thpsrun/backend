from datetime import date
from typing import Any

from pydantic import ConfigDict, Field, field_validator

from api.v1.schemas.base import BaseEmbedSchema
from api.v1.schemas.common import (
    BasePlayerInfoSchema,
    BaseSocialsWriteSchema,
    CountrySchema,
    ModeratedGameEmbedSchema,
    PlayerSocialsSchema,
    validate_speedrun_url,
)


class GradientsEmbed(BaseEmbedSchema):
    """Three-color gradient palette for a player's display name.

    Attributes:
        gradient_1 (str | None): Primary hex color (#RRGGBB).
        gradient_2 (str | None): Secondary hex color (#RRGGBB).
        gradient_3 (str | None): Tertiary hex color (#RRGGBB).
    """

    gradient_1: str | None = None
    gradient_2: str | None = None
    gradient_3: str | None = None


def extract_gradients(
    player: Any,
) -> dict[str, str | None] | None:
    """Return a gradient dict for a `Players` ORM instance.

    Returns None when the player has no linked `CustomUser` OR when the
    linked user has all three gradient fields unset. Callers pass the
    returned dict straight into a `GradientsEmbed` or into a dict-shaped
    response payload without further transformation.
    """
    user = getattr(player, "user", None)
    if user is None:
        return None
    g1 = user.gradient_1
    g2 = user.gradient_2
    g3 = user.gradient_3
    if not (g1 or g2 or g3):
        return None
    return {
        "gradient_1": g1,
        "gradient_2": g2,
        "gradient_3": g3,
    }


class PlayerSearchResultSchema(BaseEmbedSchema):
    """Lightweight schema for player search/autocomplete results.

    Attributes:
        id (str): Player ID.
        name (str): Player name on Speedrun.com.
        nickname (str | None): Custom nickname override.
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
                "name": "Anastasia",
                "nickname": None,
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
    country_id: str | None = None
    pfp: str | None = None
    gradients: GradientsEmbed | None = None

    @field_validator("country_id", mode="before")
    @classmethod
    def convert_country_to_id(
        cls,
        v: Any,
    ) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if hasattr(v, "id"):
            return v.id
        return None


class AwardSchema(BaseEmbedSchema):
    """Simple schema for awards.

    Attributes:
        name (str): Award name.
        description (str | None): Award description.
        image (str | None): Award image URL.
    """

    name: str = Field(..., max_length=50)
    description: str | None = Field(default=None, max_length=500)
    image: str | None = None


class PlayerInfoEmbed(BasePlayerInfoSchema):
    """Player identity fields with embedded country object (response context)."""

    country: CountrySchema | None = None


PlayerSocialsEmbed = PlayerSocialsSchema


class PlayerCustomizationsEmbed(BaseEmbedSchema):
    gradient_1: str | None = None
    gradient_2: str | None = None
    gradient_3: str | None = None
    tagline: str | None = Field(default=None, max_length=100)
    profile_bg: str | None = None


class PlayerStatsEmbed(BaseEmbedSchema):
    total_runs: int | None = None
    fg_points: float | None = None
    il_points: float | None = None
    awards: list[AwardSchema] | None = None


class PlayerRunsEmbed(BaseEmbedSchema):
    recent: list[dict] | None = None
    fg: list[dict] | None = None
    il: list[dict] | None = None


class PlayerModerationEmbed(BaseEmbedSchema):
    moderated_games: list[ModeratedGameEmbedSchema] | None = None


class PlayerResponse(BaseEmbedSchema):
    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
        json_schema_extra={
            "example": {
                "id": "v8lponvj",
                "url": "https://speedrun.com/user/Anastasia",
                "joined": "2015-06-22",
                "player": {
                    "name": "Anastasia",
                    "nickname": None,
                    "pronouns": "he/him",
                    "country": {"id": "us", "name": "United States", "flag": None},
                    "pfp": None,
                    "ex_stream": False,
                },
                "socials": {
                    "twitch": "https://twitch.tv/Anastasia",
                    "youtube": "https://youtube.com/Anastasia",
                    "twitter": None,
                    "bluesky": None,
                    "discord": None,
                    "therun_gg": None,
                },
                "customizations": {
                    "gradient_1": "#ff0000",
                    "gradient_2": "#00ff00",
                    "gradient_3": "#0000ff",
                    "tagline": "Skate or die",
                    "profile_bg": None,
                },
                "stats": {
                    "total_runs": 42,
                    "fg_points": 15000.0,
                    "il_points": 3200.0,
                    "awards": [],
                },
                "runs": {"recent": [], "fg": [], "il": []},
                "moderation": {"moderated_games": []},
            },
        },
    )

    id: str = Field(..., max_length=10)
    url: str
    joined: date | None = Field(
        default=None,
        description="Date of first verified speedrun",
    )
    player: PlayerInfoEmbed
    socials: PlayerSocialsEmbed
    customizations: PlayerCustomizationsEmbed
    stats: PlayerStatsEmbed
    runs: PlayerRunsEmbed
    moderation: PlayerModerationEmbed


class PlayerCreateInfoEmbed(BasePlayerInfoSchema):
    """Create payload: identity fields plus a country reference by ID."""

    country_id: str | None = None


PlayerCreateSocialsEmbed = BaseSocialsWriteSchema


class PlayerCreateSchema(BaseEmbedSchema):
    id: str | None = Field(
        default=None,
        max_length=10,
        description="Auto-generates if omitted",
    )
    url: str
    player: PlayerCreateInfoEmbed
    socials: PlayerCreateSocialsEmbed = PlayerCreateSocialsEmbed()

    @field_validator("url", mode="before")
    @classmethod
    def _validate_url(
        cls,
        v: str | None,
    ) -> str | None:
        return validate_speedrun_url(v)


class PlayerUpdateInfoEmbed(BaseEmbedSchema):
    """Update payload: all fields optional; country referenced by ID."""

    name: str | None = Field(default=None, max_length=30)
    nickname: str | None = Field(default=None, max_length=30)
    pronouns: str | None = Field(default=None, max_length=50)
    pfp: str | None = Field(default=None, max_length=100)
    ex_stream: bool | None = None
    country_id: str | None = None


PlayerUpdateSocialsEmbed = BaseSocialsWriteSchema


class PlayerUpdateSchema(BaseEmbedSchema):
    url: str | None = None
    player: PlayerUpdateInfoEmbed | None = None
    socials: PlayerUpdateSocialsEmbed | None = None

    @field_validator("url", mode="before")
    @classmethod
    def _validate_url(
        cls,
        v: str | None,
    ) -> str | None:
        return validate_speedrun_url(v)
