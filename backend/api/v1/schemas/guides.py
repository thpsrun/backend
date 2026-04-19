from datetime import datetime

from pydantic import ConfigDict, Field

from api.v1.schemas.base import BaseEmbedSchema, SlugMixin, TimestampMixin
from api.v1.schemas.games import GameSchema


class TagSchema(SlugMixin, BaseEmbedSchema):
    """Base schema for `Tag` data without embeds.

    Attributes:
        name (str): Tag name (e.g., "Tricks", "Glitches").
        slug (str): URL-friendly version of name.
        description (str): Description of what this tag represents.
    """

    description: str


class GuideSchema(SlugMixin, TimestampMixin, BaseEmbedSchema):
    """Base schema for `Guide` data without embeds.

    Attributes:
        title (str): Guide title.
        slug (str): URL-friendly version of title.
        short_description (str): Brief description of guide content.
        content (str): Full guide content (Markdown supported).
        created_at (datetime | None): When guide was created.
        updated_at (datetime | None): When guide was last updated.
        game (GameSchema | None): Associated game - included with ?embed=game.
        tags (list[TagSchema] | None): Associated tags - included with ?embed=tags.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Getting Started with THPS4 Speedruns",
                "slug": "getting-started",
                "title": "Getting Started with THPS4 Speedruns",
                "short_description": "A beginner's guide to speedrunning THPS4.",
                "content": "# Intro\n\nWelcome to THPS4 speedruns...",
                "created_at": "2025-01-15T12:00:00Z",
                "updated_at": "2025-01-20T09:30:00Z",
                "game": None,
                "tags": None,
            },
        },
    )

    title: str
    short_description: str
    content: str = Field(..., description="Supports Markdown")

    game: GameSchema | None = Field(
        default=None, description="Included with ?embed=game"
    )
    tags: list[TagSchema] | None = Field(
        default=None, description="Included with ?embed=tags"
    )


class GuideCreateSchema(BaseEmbedSchema):
    """Schema for creating new guides.

    Attributes:
        title (str): Guide title.
        game_id (str): Associated game ID.
        tag_ids (list[TagSchema] | None): List of tag IDs to associate with guide.
        short_description (str): Brief description.
        content (str): Full guide content.
    """

    title: str = Field(..., min_length=1, max_length=200)
    game_id: str
    tag_ids: list[int] | None = Field(default=[])
    short_description: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1, description="Supports Markdown")


class GuideUpdateSchema(BaseEmbedSchema):
    """Schema for updating existing guides.

    Attributes:
        title (str | None): Updated guide title.
        slug (str | None): Updated URL-friendly slug.
        game_id (str | None): Updated associated game ID.
        tag_ids (list[str] | None): Updated list of tag IDs.
        short_description (str | None): Updated brief description.
        content (str | None): Updated full content.
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(
        default=None, min_length=1, max_length=15, description="URL-friendly slug"
    )
    game_id: str | None = None
    tag_ids: list[str] | None = None
    short_description: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, min_length=1)


class TagCreateSchema(BaseEmbedSchema):
    """Schema for creating new tags.

    Attributes:
        name (str): Tag name.
        description (str): Tag description.
    """

    name: str = Field(..., min_length=1, max_length=25)
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
        default=None, min_length=1, max_length=15, description="URL-friendly slug"
    )
    description: str | None = Field(default=None, min_length=1, max_length=500)


class GuideListSchema(BaseEmbedSchema):
    """Simplified guide schema for list views.

    Attributes:
        title (str): Guide title.
        slug (str): URL-friendly slug.
        short_description (str): Brief description.
        created_at (datetime | None): When guide was created.
        updated_at (datetime | None): When guide was last updated.
        game (GameSchema | None): Associated game.
        tags (list[TagSchema] | None): Associated tags.
    """

    title: str
    slug: str = Field(..., min_length=1, max_length=15, description="URL-friendly slug")
    short_description: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    game: GameSchema | None = None
    tags: list[TagSchema] | None = None


class TagListSchema(SlugMixin, BaseEmbedSchema):
    """Simplified tag schema for list views.

    Attributes:
        name (str): Tag name.
        slug (str): URL-friendly slug.
        description (str): Tag description.
    """

    description: str
