from typing import Any

from pydantic import ConfigDict, Field, field_validator

from api.v1.schemas.base import BaseEmbedSchema, SlugMixin
from api.v1.schemas.variables import VariableWithValuesSchema


class CategoryBaseSchema(SlugMixin, BaseEmbedSchema):
    """Base schema for `Category` data without embeds.

    Attributes:
        id (str): Unique ID (usually based on SRC) of the category.
        name (str): Category name (e.g., "Any%", "100%").
        slug (str): URL-friendly version.
        type (str): Whether this is per-game or per-level category.
        url (str): Link to category on Speedrun.com.
        rules (str | None): Category-specific rules text.
        appear_on_main (bool): Whether to show on main page.
        archive (bool): Whether category is hidden from listings.
    """

    id: str = Field(..., max_length=10)
    name: str = Field(..., max_length=50)
    slug: str = Field(..., max_length=50, description="URL-friendly slug")
    type: str = Field(..., pattern="^(per-level|per-game)$")
    url: str
    rules: str | None = Field(default=None, max_length=5000)
    appear_on_main: bool = Field(
        default=False, exclude=True, description="Show on main leaderboard page"
    )
    players: int = Field(default=1, ge=1, description="Number of players accepted")
    archive: bool = Field(default=False, description="Hidden from listings")


class CategorySchema(CategoryBaseSchema):
    """Complete category schema with optional embedded data.

    Extends the base schema to include optional embedded game data when requested
    via ?embed=game parameter.

    Attributes:
        game (dict | None): Game this category belongs to - included with ?embed=game.
        variables (List[dict] | None): Category variables - included with ?embed=variables.
        values (List[dict] | None): Variables with values - included with ?embed=values.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "rklge08d",
                "name": "Any%",
                "slug": "any",
                "type": "per-game",
                "url": "https://speedrun.com/thps4/full_game#Any",
                "rules": "Rulez.",
                "players": 1,
                "archive": False,
            },
        },
    )

    game: dict | None = Field(None, description="Included with ?embed=game")
    variables: list[dict] | None = Field(
        None, description="Included with ?embed=variables"
    )
    values: list[dict] | None = Field(None, description="Included with ?embed=values")

    @field_validator("game", mode="before")
    @classmethod
    def convert_model_to_none(cls, v: Any) -> dict | None:
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        return None

    @field_validator("variables", "values", mode="before")
    @classmethod
    def convert_list_to_none(cls, v: Any) -> list[dict] | None:
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if hasattr(v, "all"):
            return None
        return v


class CategoryCreateSchema(SlugMixin, BaseEmbedSchema):
    """Schema for creating new categories.

    Attributes:
        id (str | None): The category ID; if one is not given, it will auto-generate.
        game_id (str): ID of the game this category belongs to.
        name (str): The category name.
        slug (str): URL-friendly version.
        type (str): The category type (per-level or per-game).
        url (str): Speedrun.com URL.
        rules (str | None): Category-specific rules.
        appear_on_main (bool): Whether to show on main page.
        archive (bool): Whether category is hidden.
    """

    id: str | None = Field(
        default=None, max_length=10, description="Auto-generates if omitted"
    )
    name: str = Field(..., max_length=50)
    slug: str = Field(..., max_length=50, description="URL-friendly slug")
    game_id: str
    type: str = Field(..., pattern="^(per-level|per-game)$")
    url: str
    rules: str | None = None
    appear_on_main: bool = Field(
        default=False, exclude=True, description="Show on main leaderboard page"
    )
    players: int = Field(default=1, ge=1, description="Number of players accepted")
    order: int = Field(
        default=0, exclude=True, description="Sort order; managed via admin panel"
    )
    archive: bool = Field(default=False, description="Hidden from listings")


class CategoryUpdateSchema(BaseEmbedSchema):
    """Schema for updating categories.

    All fields optional for partial updates.

    Attributes:
        game_id (str | None): Unique ID (usually based on SRC) of the category.
        name (str | None): Updated category name.
        type (str | None): Updated category type.
        url (str | None): Updated URL.
        rules (str | None): Updated rules.
        appear_on_main (bool | None): Updated main page visibility.
        hidden (bool | None): Updated hidden status.
    """

    game_id: str | None = None
    name: str | None = None
    type: str | None = Field(None, pattern="^(per-level|per-game)$")
    url: str | None = None
    rules: str | None = None
    appear_on_main: bool | None = Field(
        None, description="Show on main leaderboard page"
    )
    players: int | None = Field(None, ge=1, description="Number of players accepted")
    order: int | None = Field(
        default=None, description="Sort order; managed via admin panel"
    )
    archive: bool | None = Field(default=None, description="Hidden from listings")


class GameCategoryResponseSchema(CategoryBaseSchema):
    """Response schema for game categories with embedded variables.

    Used by the /website/game/{game_id}/categories endpoint.

    Attributes:
        variables (list[VariableWithValuesSchema]): Variables with their possible values.
    """

    variables: list[VariableWithValuesSchema] = Field(default_factory=list)
