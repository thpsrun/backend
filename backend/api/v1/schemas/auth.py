from datetime import date

from ninja import Schema
from pydantic import EmailStr, Field, field_validator, model_validator


class CountryCodeResponse(Schema):
    id: str
    name: str


class SRCKeyRequest(Schema):
    src_api_key: str = Field(
        ...,
        min_length=1,
        description="Speedrun.com API key to store for run approvals",
    )


class SRCKeyStatusResponse(Schema):
    has_src_key: bool
    message: str


class ModeratedGameSchema(Schema):
    id: str
    name: str
    slug: str


class RegisterRequest(Schema):
    src_api_key: str = Field(
        ...,
        min_length=1,
        description="Speedrun.com API key for identity verification",
    )
    save_key: bool = Field(
        False,
        description="If true, the SRC API key is encrypted and stored for future use",
    )
    username: str = Field(
        ...,
        min_length=3,
        max_length=20,
        pattern=r"^[\w.@+-]+$",
        description="Desired username (letters, digits, and @/./+/-/_ only)",
    )
    email: EmailStr = Field(
        ...,
        max_length=64,
        description="Email address",
    )
    password1: str = Field(
        ...,
        min_length=8,
        max_length=64,
        pattern=r"^[\x20-\x7E]+$",
        description="Password (8-64 printable ASCII characters)",
    )
    password2: str = Field(
        ...,
        min_length=8,
        max_length=64,
        pattern=r"^[\x20-\x7E]+$",
        description="Password confirmation (must match password)",
    )

    @model_validator(mode="after")
    def passwords_match(
        self,
    ) -> "RegisterRequest":
        if self.password1 != self.password2:
            raise ValueError("Passwords do not match")
        return self


class RegisterResponse(Schema):
    player_id: str
    player_name: str
    username: str


class PlayerProfileResponse(Schema):
    player_id: str
    name: str
    nickname: str | None
    pronouns: str | None
    countrycode: str | None
    twitch: str | None
    youtube: str | None
    twitter: str | None
    bluesky: str | None
    discord: str | None
    pfp: str | None
    claim_status: str
    username: str
    is_moderator: bool = False
    is_superuser: bool = False
    ex_stream: bool = False
    has_src_key: bool = False
    joined: date | None = None
    moderated_games: list[ModeratedGameSchema] = []


class PfpUploadResponse(Schema):
    pfp: str


class PlayerUpdateRequest(Schema):
    name: str | None = Field(None, max_length=30)
    nickname: str | None = Field(None, max_length=30)
    pronouns: str | None = Field(None, max_length=50)
    countrycode: str | None = None
    twitch: str | None = Field(None, max_length=200)
    youtube: str | None = Field(None, max_length=200)
    twitter: str | None = Field(None, max_length=200)
    bluesky: str | None = Field(None, max_length=200)
    discord: str | None = Field(None, max_length=32)
    ex_stream: bool | None = None

    @field_validator("twitch", "youtube", "twitter", "bluesky", mode="before")
    @classmethod
    def validate_url(
        cls,
        v: str | None,
    ) -> str | None:
        if v is None:
            return v
        from urllib.parse import urlparse

        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Must be a valid http or https URL")
        return v
