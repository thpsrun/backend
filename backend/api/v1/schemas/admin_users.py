from ninja import Schema
from pydantic import Field


class BanRequest(Schema):
    reason: str | None = Field(
        default=None,
        max_length=255,
        description="Optional reason recorded in the audit log.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "reason": "Repeated harassment reports.",
            },
        }


class SessionsRevokedResponse(Schema):
    revoked: int = Field(
        ...,
        description="Number of session rows deleted for the target user.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "revoked": 3,
            },
        }


class ModeratedGame(Schema):
    game_id: str
    game_name: str

    class Config:
        json_schema_extra = {
            "example": {
                "game_id": "thps1",
                "game_name": "Tony Hawk's Pro Skater",
            },
        }


class AwardEntry(Schema):
    award_id: int
    award_name: str

    class Config:
        json_schema_extra = {
            "example": {
                "award_id": 7,
                "award_name": "Sub-1 Club",
            },
        }


class AdminPfpResponse(Schema):
    pfp: str = Field(
        ...,
        description="Public URL of the saved profile picture.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "pfp": "/media/pfp/abc12345.jpg",
            },
        }


class AdminProfileBGResponse(Schema):
    profile_bg: str = Field(
        ...,
        description="Public URL of the saved profile background image.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "profile_bg": "/media/profile_bg/abc12345.jpg",
            },
        }
