from pydantic import Field

from api.v1.schemas.base import BaseEmbedSchema


class CountrySchema(BaseEmbedSchema):
    """Country code reference shape.

    Attributes:
        id (str): Country code ID.
        name (str): Country name.
        flag (str | None): Flag image URL override.
    """

    id: str
    name: str
    flag: str | None = None


class ModeratedGameEmbedSchema(BaseEmbedSchema):
    """Game summary used in moderation lists.

    Attributes:
        id (str): Game ID.
        name (str): Game name.
        slug (str): Game slug/abbreviation.
    """

    id: str = Field(..., max_length=10)
    name: str
    slug: str


class BaseSocialsSchema(BaseEmbedSchema):
    """Core set of social URLs common to every player-facing schema."""

    twitch: str | None = None
    youtube: str | None = None
    twitter: str | None = None
    bluesky: str | None = None
    discord: str | None = None


class PlayerSocialsSchema(BaseSocialsSchema):
    """Socials for a player profile response, including therun_gg."""

    therun_gg: str | None = None


class BasePlayerInfoSchema(BaseEmbedSchema):
    """Shared player identity fields. `country` varies by context and is declared
    on subclasses (full `CountrySchema` in responses, `country_id: str` in
    create/update payloads)."""

    name: str = Field(..., max_length=30)
    nickname: str | None = Field(default=None, max_length=30)
    pronouns: str | None = Field(default=None, max_length=50)
    pfp: str | None = Field(
        default=None, max_length=100, description="Profile picture URL"
    )
    ex_stream: bool = Field(default=False, description="Exclude from streaming bots")
