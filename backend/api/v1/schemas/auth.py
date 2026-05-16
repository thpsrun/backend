import re
from datetime import date, datetime

from ninja import Schema
from pydantic import (
    ConfigDict,
    EmailStr,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from api.v1.schemas.common import (
    BasePlayerInfoSchema,
    CountrySchema,
    ModeratedGameEmbedSchema,
    PlayerSocialsSchema,
    validate_social_url,
)

CountryCodeResponse = CountrySchema
CountryEmbed = CountrySchema
ModeratedGameSchema = ModeratedGameEmbedSchema
SocialsEmbed = PlayerSocialsSchema


class SRCKeyRequest(Schema):
    src_api_key: str = Field(
        ...,
        min_length=1,
        description="Speedrun.com API key to store for run approvals",
    )


class SRCKeyStatusResponse(Schema):
    has_src_key: bool
    message: str


class PlayerEmbed(BasePlayerInfoSchema):
    username: str
    country: CountrySchema | None = None
    is_superuser: bool = False


class CustomizationsEmbed(Schema):
    tagline: str | None = None
    gradient_1: str | None = None
    gradient_2: str | None = None
    gradient_3: str | None = None
    profile_bg: str | None = None


class ModerationEmbed(Schema):
    has_src_key: bool = False
    moderated_games: list[ModeratedGameSchema] = []


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
        max_length=254,
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
    claim_status: str
    joined: date | None
    player: PlayerEmbed
    socials: SocialsEmbed
    customizations: CustomizationsEmbed
    moderation: ModerationEmbed


class PfpUploadResponse(Schema):
    pfp: str


class ProfileBGUploadResponse(Schema):
    profile_bg: str | None


HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class PlayerUpdateEmbed(Schema):
    name: str | None = Field(None, min_length=1, max_length=30)
    nickname: str | None = Field(None, max_length=30)
    pronouns: str | None = Field(None, max_length=50)
    country: str | None = None
    ex_stream: bool | None = None


class SocialsUpdateEmbed(Schema):
    youtube: str | None = Field(None, max_length=200)
    twitter: str | None = Field(None, max_length=200)
    bluesky: str | None = Field(None, max_length=200)
    therun_gg: str | None = Field(None, max_length=30)

    @field_validator(
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


class CustomizationsUpdateEmbed(Schema):
    tagline: str | None = Field(None, max_length=100)
    gradient_1: str | None = Field(None, max_length=7)
    gradient_2: str | None = Field(None, max_length=7)
    gradient_3: str | None = Field(None, max_length=7)

    @field_validator("gradient_1", "gradient_2", "gradient_3", mode="before")
    @classmethod
    def validate_hex_color(
        cls,
        v: str | None,
    ) -> str | None:
        if v is None:
            return v
        if not HEX_COLOR_PATTERN.match(v):
            raise ValueError("Must be a valid hex color (#RRGGBB)")
        return v


class PlayerUpdateRequest(Schema):
    player: PlayerUpdateEmbed | None = None
    socials: SocialsUpdateEmbed | None = None
    customizations: CustomizationsUpdateEmbed | None = None


class SocialAccountListItem(Schema):
    provider: str
    uid: str
    username: str | None = None
    last_login: datetime | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider": "discord",
                "uid": "123456789",
                "username": "anastasia",
                "last_login": "2026-05-15T10:00:00Z",
            },
        },
    )


class AuthenticatorListItem(Schema):
    type: str
    id: int
    name: str | None = None
    added_at: datetime | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "webauthn",
                "id": 7,
                "name": "YubiKey 5C",
                "added_at": "2026-05-15T10:00:00Z",
            },
        },
    )


class AuthMethodsResponse(Schema):
    has_usable_password: bool
    social_accounts: list[SocialAccountListItem]
    authenticators: list[AuthenticatorListItem]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "has_usable_password": True,
                "social_accounts": [
                    {
                        "provider": "discord",
                        "uid": "123",
                        "username": "anastasia",
                        "last_login": "2026-05-15T10:00:00Z",
                    },
                ],
                "authenticators": [
                    {
                        "type": "webauthn",
                        "id": 7,
                        "name": "YubiKey 5C",
                        "added_at": "2026-05-15T10:00:00Z",
                    },
                ],
            },
        },
    )


class SocialAccountListResponse(Schema):
    social_accounts: list[SocialAccountListItem]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "social_accounts": [
                    {
                        "provider": "discord",
                        "uid": "123",
                        "username": "anastasia",
                        "last_login": "2026-05-15T10:00:00Z",
                    },
                ],
            },
        },
    )


class DeletePasswordRequest(Schema):
    password: str | None = None
    mfa_code: str | None = None
    webauthn_assertion: dict | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "password": "currentPassword123",
            },
        },
    )
