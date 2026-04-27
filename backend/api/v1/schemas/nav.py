from __future__ import annotations

from pydantic import BaseModel


class NavItemSchema(BaseModel):
    name: str
    url: str | None
    children: list[NavItemSchema] = []


class SocialLinkSchema(BaseModel):
    platform: str
    url: str


class NavbarResponse(BaseModel):
    nav: list[NavItemSchema]
    social: list[SocialLinkSchema]
