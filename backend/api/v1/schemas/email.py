from __future__ import annotations

from datetime import datetime
from typing import Literal

from ninja import Schema
from pydantic import ConfigDict, EmailStr, Field


class EmailStateResponse(Schema):
    email: str
    verified: bool
    pending_email: str | None
    pending_expires_at: datetime | None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "current@example.com",
                "verified": True,
                "pending_email": "new@example.com",
                "pending_expires_at": "2026-05-25T17:11:00Z",
            },
        },
    )


class EmailChangeRequest(Schema):
    new_email: EmailStr = Field(
        ...,
        max_length=254,
        description="New email address to switch to",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"new_email": "new@example.com"},
        },
    )


class EmailChangeResponse(Schema):
    status: Literal["verification_sent"]
    new_email: str
    expires_at: datetime | None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "verification_sent",
                "new_email": "new@example.com",
                "expires_at": "2026-05-25T17:11:00Z",
            },
        },
    )


class EmailVerifyRequest(Schema):
    code: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description=(
            "Verification key received via email link (HMAC-signed token, "
            "typically 50-70 characters)."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "MQ:1wRgt9:fnmCgpZZMvUbESmRq8R5k9xfUWDH3lOBM932gLeoOyQ"
            },
        },
    )
