from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_EXAMPLE_NOTIFICATION: dict[str, Any] = {
    "id": 123,
    "type": "run_approved",
    "target_type": "run",
    "target_id": "abc123",
    "title": "Run approved",
    "body": "Your THPS3 Any% run was approved.",
    "payload": {
        "run_id": "abc123",
        "game_id": "thps3",
        "game_name": "THPS3",
        "category_name": "Any%",
    },
    "is_read": False,
    "read_at": None,
    "created_at": "2026-05-18T20:14:00Z",
}


class NotificationOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"example": _EXAMPLE_NOTIFICATION},
    )

    id: int
    type: str
    target_type: str
    target_id: str
    title: str
    body: str
    payload: dict[str, Any]
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class NotificationListOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "count": 1,
                "limit": 25,
                "offset": 0,
                "items": [_EXAMPLE_NOTIFICATION],
            },
        },
    )

    count: int
    limit: int
    offset: int
    items: list[NotificationOut]


class UnreadCountOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"count": 4}},
    )

    count: int


class ReadByTargetIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"target_type": "run", "target_id": "abc123"},
        },
    )

    target_type: str = Field(..., min_length=1, max_length=50)
    target_id: str = Field(..., min_length=1, max_length=100)


class ReadCountOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"updated": 3}},
    )

    updated: int


class PreferenceOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "kind": "run_approved",
                "label": "Run Approved",
                "description": "One of your submitted runs was approved.",
                "enabled": True,
            },
        },
    )

    kind: str
    label: str
    description: str
    enabled: bool


class PreferencesOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "preferences": [
                    {
                        "kind": "run_approved",
                        "label": "Run Approved",
                        "description": "One of your submitted runs was approved.",
                        "enabled": True,
                    },
                    {
                        "kind": "run_denied",
                        "label": "Run Denied",
                        "description": "One of your submitted runs was denied.",
                        "enabled": True,
                    },
                    {
                        "kind": "user_data_export",
                        "label": "Data Export",
                        "description": "Notifications about your account data export.",
                        "enabled": True,
                    },
                ],
            },
        },
    )

    preferences: list[PreferenceOut]


class PreferencesUpdateIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "preferences": {
                    "run_denied": False,
                    "api_key_expiring": False,
                    "user_data_export": False,
                },
            },
        },
    )

    preferences: dict[str, bool]


class NotificationKindOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "kind": "run_approved",
                "label": "Run Approved",
                "description": "One of your submitted runs was approved.",
                "default_enabled": True,
            },
        },
    )

    kind: str
    label: str
    description: str
    default_enabled: bool


class NotificationKindsOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "kinds": [
                    {
                        "kind": "run_approved",
                        "label": "Run Approved",
                        "description": "One of your submitted runs was approved.",
                        "default_enabled": True,
                    },
                    {
                        "kind": "user_data_export",
                        "label": "Data Export",
                        "description": "Notifications about your account data export.",
                        "default_enabled": True,
                    },
                ],
            },
        },
    )

    kinds: list[NotificationKindOut]
