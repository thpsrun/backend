from urllib.parse import urlparse

from pydantic import Field, ValidationInfo, field_validator

from api.v1.schemas.base import BaseEmbedSchema

ALLOWED_SOCIAL_HOSTS: dict[str, frozenset[str]] = {
    "twitch": frozenset(
        {
            "twitch.tv",
            "www.twitch.tv",
        }
    ),
    "youtube": frozenset(
        {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "youtu.be",
        }
    ),
    "twitter": frozenset(
        {
            "twitter.com",
            "www.twitter.com",
            "x.com",
            "www.x.com",
        }
    ),
    "bluesky": frozenset(
        {
            "bsky.app",
            "www.bsky.app",
            "bsky.social",
        }
    ),
}

ALLOWED_SPEEDRUN_HOSTS: frozenset[str] = frozenset(
    {
        "speedrun.com",
        "www.speedrun.com",
    }
)


def validate_social_url(
    field_name: str,
    value: str | None,
) -> str | None:
    if value is None:
        return value
    try:
        parsed = urlparse(value)
    except ValueError as e:
        raise ValueError(f"{field_name} is not a valid URL") from e
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"{field_name} must be a valid http(s) URL")
    host: str = (parsed.hostname or "").lower()
    allowed: frozenset[str] | None = ALLOWED_SOCIAL_HOSTS.get(field_name)
    if allowed is not None and host not in allowed:
        raise ValueError(
            f"{field_name} URL host must be one of: {', '.join(sorted(allowed))}",
        )
    return value


def sanitize_social_url(
    field_name: str,
    value: str | None,
) -> str | None:
    """Sanitizes social URLs (e.g. BlueSky or Twitter) to prevent malformed or bad data."""
    if value is None or value == "":
        return None
    try:
        return validate_social_url(field_name, value)
    except (ValueError, TypeError):
        return None


def validate_speedrun_url(
    value: str | None,
) -> str | None:
    if value is None:
        return value
    try:
        parsed = urlparse(value)
    except ValueError as e:
        raise ValueError("url is not a valid URL") from e
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("url must be a valid http(s) URL")
    host: str = (parsed.hostname or "").lower()
    if host not in ALLOWED_SPEEDRUN_HOSTS:
        raise ValueError("url must be a speedrun.com URL")
    return value


def sanitize_speedrun_url(
    value: str | None,
) -> str | None:
    if value is None or value == "":
        return None
    try:
        return validate_speedrun_url(value)
    except (ValueError, TypeError):
        return None


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


class BaseSocialsWriteSchema(BaseSocialsSchema):
    """Inbound socials payload. Enforces scheme + per-field domain allowlist."""

    @field_validator(
        "twitch",
        "youtube",
        "twitter",
        "bluesky",
        mode="before",
    )
    @classmethod
    def _validate_url(
        cls,
        v: str | None,
        info: ValidationInfo,
    ) -> str | None:
        return validate_social_url(info.field_name or "", v)


class PlayerSocialsSchema(BaseSocialsSchema):
    """Socials for a player profile response, including therun_gg."""

    therun_gg: str | None = None


class BasePlayerInfoSchema(BaseEmbedSchema):
    """Shared player identity fields across the codebase."""

    name: str = Field(..., max_length=30)
    nickname: str | None = Field(default=None, max_length=30)
    pronouns: str | None = Field(default=None, max_length=50)
    pfp: str | None = Field(
        default=None, max_length=100, description="Profile picture URL"
    )
    ex_stream: bool = Field(default=False, description="Exclude from streaming bots")
