import re
from typing import Any

import bleach
import markdown as _markdown_lib
from pydantic import ConfigDict, Field, field_validator

from api.v1.schemas.base import BaseEmbedSchema, SlugMixin, TimestampMixin
from api.v1.schemas.common import CountrySchema
from api.v1.schemas.games import GameSchema
from api.v1.schemas.players import GradientsEmbed

CONTENT_MAX_LENGTH: int = 50_000

_DANGEROUS_URL_ATTR: re.Pattern[str] = re.compile(
    r"""(?:href|src|xlink:href)\s*=\s*["']?\s*(?:javascript|vbscript|data|file|about):""",
    re.IGNORECASE,
)


def _reject_dangerous_links(
    cleaned: str,
) -> None:
    """Render markdown to HTML and raise if any link or image uses a blocked scheme.

    Bleach strips raw HTML tags, but cannot see inside markdown syntax easily."""
    html: str = _markdown_lib.markdown(cleaned, extensions=["fenced_code"])
    if _DANGEROUS_URL_ATTR.search(html):
        raise ValueError(
            "Markdown contains a link or image with an unsupported URL scheme",
        )


def _sanitize_markdown_source(
    value: str,
) -> str:
    """Strip every HTML tag and comment, then reject dangerous markdown links."""
    cleaned: str = bleach.clean(value, tags=[], strip=True, strip_comments=True)
    if not cleaned.strip():
        raise ValueError("content is empty after stripping HTML")
    _reject_dangerous_links(cleaned)
    return cleaned


class TagSchema(SlugMixin, BaseEmbedSchema):
    """Base schema for `Tag` data without embeds.

    Attributes:
        id (int): Unique tag ID.
        name (str): Tag name (e.g., "Tricks", "Glitches").
        slug (str): URL-friendly version of name.
        description (str): Description of what this tag represents.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "Tricks",
                "slug": "tricks",
                "description": "Advanced tricks and techniques.",
            },
        },
    )

    id: int
    name: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=100, description="URL-friendly slug")
    description: str


class GuideAuthorSchema(BaseEmbedSchema):
    """Author identity for a guide, mirroing other parts of the codebase.

    Attributes:
        name (str): Author display name (Players.name, or User.username when unclaimed).
        nickname (str | None): Optional nickname override.
        country (CountrySchema | None): Country of the linked player.
        gradients (GradientsEmbed | None): Name gradient colors.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "TheAnastasia",
                "nickname": "Anastasia",
                "country": {"id": "us", "name": "United States"},
                "gradients": {
                    "gradient_1": "#5BCEFA",
                    "gradient_2": "#F5A9B8",
                    "gradient_3": "#FFFFFF",
                },
            },
        },
    )

    name: str = Field(..., max_length=150)
    nickname: str | None = Field(default=None, max_length=30)
    country: CountrySchema | None = None
    gradients: GradientsEmbed | None = None


class GuideListSchema(TimestampMixin, BaseEmbedSchema):
    """Simplified guide schema for list views.

    Attributes:
        title (str): Guide title.
        slug (str): URL-friendly slug.
        short_description (str): Brief description.
        author (GuideAuthorSchema | None): Author identity, populated from the guide owner.
        created_at (datetime | None): When guide was created.
        updated_at (datetime | None): When guide was last updated.
        game (GameSchema | None): Associated game.
        tags (list[TagSchema] | None): Associated tags.
    """

    title: str = Field(..., max_length=200)
    slug: str = Field(
        ..., min_length=1, max_length=200, description="URL-friendly slug"
    )
    short_description: str = Field(..., max_length=500)
    author: GuideAuthorSchema | None = None
    game: GameSchema | None = Field(
        default=None, description="Included with ?embed=game"
    )
    tags: list[TagSchema] | None = Field(
        default=None, description="Included with ?embed=tags"
    )

    @field_validator("tags", mode="before")
    @classmethod
    def _drop_m2m_manager(
        cls,
        value: Any,
    ) -> Any:
        # `guide.tags` is a Django ManyRelatedManager when read via
        # from_attributes; routers populate this field explicitly, so treat
        # the unresolved manager as no value.
        if (
            value is not None
            and hasattr(value, "all")
            and not isinstance(value, (list, tuple))
        ):
            return None
        return value


class GuideSchema(GuideListSchema):
    """Full guide schema including content body.

    Attributes:
        content (str): Full guide content (Markdown supported).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Getting Started with THPS4 Speedruns",
                "slug": "getting-started",
                "short_description": "A beginner's guide to speedrunning THPS4.",
                "content": "# Intro\n\nWelcome to THPS4 speedruns...",
                "author": {
                    "name": "TheAnastasia",
                    "nickname": "Anastasia",
                    "country": {"id": "us", "name": "United States"},
                    "gradients": {
                        "gradient_1": "#5BCEFA",
                        "gradient_2": "#F5A9B8",
                        "gradient_3": "#FFFFFF",
                    },
                },
                "created_at": "2025-01-15T12:00:00Z",
                "updated_at": "2025-01-20T09:30:00Z",
                "game": None,
                "tags": None,
            },
        },
    )

    content: str = Field(..., description="Supports Markdown")


class GuideCreateSchema(BaseEmbedSchema):
    """Schema for creating new guides.

    Attributes:
        title (str): Guide title.
        game_id (str): Associated game ID.
        tag_ids (list[int] | None): List of tag IDs to associate with guide.
        short_description (str): Brief description.
        content (str): Full guide content.
    """

    title: str = Field(..., min_length=1, max_length=200)
    game_id: str
    tag_ids: list[int] | None = Field(default=[])
    short_description: str = Field(..., min_length=1, max_length=500)
    content: str = Field(
        ...,
        min_length=1,
        max_length=CONTENT_MAX_LENGTH,
        description="Supports Markdown",
    )

    @field_validator("content", mode="after")
    @classmethod
    def _strip_content_html(
        cls,
        value: str,
    ) -> str:
        return _sanitize_markdown_source(value)


class GuideUpdateSchema(BaseEmbedSchema):
    """Schema for updating existing guides.

    Attributes:
        title (str | None): Updated guide title.
        slug (str | None): Updated URL-friendly slug.
        game_id (str | None): Updated associated game ID.
        tag_ids (list[int] | None): Updated list of tag IDs.
        short_description (str | None): Updated brief description.
        content (str | None): Updated full content.
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(
        default=None, min_length=1, max_length=200, description="URL-friendly slug"
    )
    game_id: str | None = None
    tag_ids: list[int] | None = None
    short_description: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(
        default=None,
        min_length=1,
        max_length=CONTENT_MAX_LENGTH,
    )

    @field_validator("content", mode="after")
    @classmethod
    def _strip_content_html(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        return _sanitize_markdown_source(value)


class TagCreateSchema(BaseEmbedSchema):
    """Schema for creating new tags.

    Attributes:
        name (str): Tag name.
        description (str): Tag description.
    """

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)


class TagUpdateSchema(BaseEmbedSchema):
    """Schema for updating existing tags.

    Attributes:
        name (str | None): Updated tag name.
        slug (str | None): Updated URL-friendly slug.
        description (str | None): Updated tag description.
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(
        default=None, min_length=1, max_length=100, description="URL-friendly slug"
    )
    description: str | None = Field(default=None, min_length=1, max_length=500)


TagListSchema = TagSchema
