from pydantic import Field

from api.v1.schemas.base import BaseEmbedSchema, SlugMixin


class PlatformSchema(SlugMixin, BaseEmbedSchema):
    """Base schema for `Platforms` data without embeds.

    Attributes:
        id (str): Unique ID (usually based on SRC) of the platform.
        name (str): Platform name (e.g., "PlayStation 2").
        slug (str): URL-friendly version (e.g., "playstation-2").
    """

    id: str = Field(..., max_length=10)
    name: str = Field(..., max_length=30)
    slug: str = Field(..., max_length=30, description="URL-friendly slug")


class PlatformCreateSchema(SlugMixin, BaseEmbedSchema):
    """Schema for creating new platforms.

    Attributes:
        id (str | None): The platform ID; if one is not given, it will auto-generate.
        name (str): Platform name.
        slug (str): URL-friendly version of the platform name.
    """

    id: str | None = Field(
        default=None, max_length=10, description="Auto-generates if omitted"
    )
    name: str = Field(..., max_length=30)


class PlatformUpdateSchema(BaseEmbedSchema):
    """Schema for updating platforms.

    Attributes:
        name (str | None): Updated platform name.
        slug (str | None): Updated URL-friendly platform slug.
    """

    name: str | None = Field(default=None, max_length=30)
    slug: str | None = Field(default=None, max_length=30)
