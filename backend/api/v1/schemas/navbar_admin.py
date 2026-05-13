from __future__ import annotations

from ninja import Schema


class NavbarAdminItem(Schema):
    id: int
    name: str
    url: str | None
    parent_id: int | None
    order: int
    is_visible: bool
    children: list[NavbarAdminItem] = []

    class Config:
        json_schema_extra = {
            "example": {
                "id": 7,
                "name": "Games",
                "url": "/games",
                "parent_id": None,
                "order": 1,
                "is_visible": True,
                "children": [],
            },
        }


class NavbarAdminSocial(Schema):
    id: int
    platform: str
    url: str
    order: int
    is_visible: bool

    class Config:
        json_schema_extra = {
            "example": {
                "id": 3,
                "platform": "Discord",
                "url": "https://discord.gg/thps",
                "order": 1,
                "is_visible": True,
            },
        }


class NavbarStateResponse(Schema):
    items: list[NavbarAdminItem]
    social: list[NavbarAdminSocial]

    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "id": 7,
                        "name": "Games",
                        "url": "/games",
                        "parent_id": None,
                        "order": 1,
                        "is_visible": True,
                        "children": [
                            {
                                "id": 14,
                                "name": "THPS 4",
                                "url": "/games/thps4",
                                "parent_id": 7,
                                "order": 1,
                                "is_visible": True,
                                "children": [],
                            },
                        ],
                    },
                ],
                "social": [
                    {
                        "id": 3,
                        "platform": "Discord",
                        "url": "https://discord.gg/thps",
                        "order": 1,
                        "is_visible": True,
                    },
                ],
            },
        }


class NavItemCreate(Schema):
    name: str
    url: str | None = None
    parent_id: int | None = None
    order: int = 0
    is_visible: bool = True

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Games",
                "url": "/games",
                "parent_id": None,
                "order": 1,
                "is_visible": True,
            },
        }


class NavItemUpdate(Schema):
    name: str | None = None
    url: str | None = None
    parent_id: int | None = None
    order: int | None = None
    is_visible: bool | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Games & Tracks",
                "is_visible": False,
            },
        }


class SocialLinkCreate(Schema):
    platform: str
    url: str
    order: int = 0
    is_visible: bool = True

    class Config:
        json_schema_extra = {
            "example": {
                "platform": "Discord",
                "url": "https://discord.gg/thps",
                "order": 1,
                "is_visible": True,
            },
        }


class SocialLinkUpdate(Schema):
    platform: str | None = None
    url: str | None = None
    order: int | None = None
    is_visible: bool | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://discord.gg/thpsrun",
            },
        }


class NavItemReorderRequest(Schema):
    parent_id: int | None = None
    ordered_ids: list[int]

    class Config:
        json_schema_extra = {
            "example": {
                "parent_id": None,
                "ordered_ids": [7, 12, 3],
            },
        }


class SocialReorderRequest(Schema):
    ordered_ids: list[int]

    class Config:
        json_schema_extra = {
            "example": {
                "ordered_ids": [3, 1, 2],
            },
        }
