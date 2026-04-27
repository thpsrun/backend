from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class NavItemSchema(BaseModel):
    name: str
    url: str | None
    children: list[NavItemSchema] = []


class SocialLinkSchema(BaseModel):
    platform: str
    url: str


class NavbarResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "nav": [
                    {"name": "Games", "url": "/games", "children": []},
                    {
                        "name": "Guides",
                        "url": None,
                        "children": [
                            {
                                "name": "How to Submit",
                                "url": "/docs/submit",
                                "children": [],
                            },
                        ],
                    },
                ],
                "social": [
                    {"platform": "twitch", "url": "https://twitch.tv/thps_run"},
                    {"platform": "discord", "url": "https://discord.gg/example"},
                ],
            },
        },
    )

    nav: list[NavItemSchema]
    social: list[SocialLinkSchema]
