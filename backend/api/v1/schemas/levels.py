from typing import Any

from pydantic import ConfigDict, Field, field_validator

from api.v1.schemas.base import BaseEmbedSchema, SlugMixin
from api.v1.schemas.variables import VariableWithValuesSchema


class LevelBaseSchema(SlugMixin, BaseEmbedSchema):
    """Base schema for `Levels` data without embeds.

    Attributes:
        id (str): Unique ID (usually based on SRC) of the level.
        name (str): Level name (e.g., "Warehouse", "School").
        slug (str): URL-friendly version.
        url (str): Link to level on Speedrun.com.
        rules (str | None): Level-specific rules text.
    """

    id: str = Field(..., max_length=10)
    name: str = Field(..., max_length=75)
    slug: str = Field(..., max_length=75, description="URL-friendly slug")
    url: str
    rules: str | None = Field(default=None, max_length=5000)


class LevelSchema(LevelBaseSchema):
    """Complete level schema with optional embedded data.

    Attributes:
        game (dict | None): Game this level belongs to - included with ?embed=game.
        variables (List[dict] | None): Level-specific variables - included with ?embed=variables.
        values (List[dict] | None): Variables with values - included with ?embed=values.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "xd1m508k",
                "name": "Warehouse",
                "slug": "warehouse",
                "url": "https://speedrun.com/thps4/warehouse",
                "rules": "Timing starts on first input and ends on goal complete.",
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
    def convert_model_to_none(
        cls,
        v: Any,
    ) -> dict | None:
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        return None

    @field_validator("variables", "values", mode="before")
    @classmethod
    def convert_list_to_none(
        cls,
        v: Any,
    ) -> list[dict] | None:
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if hasattr(v, "all"):
            return None
        return v


class LevelCreateSchema(SlugMixin, BaseEmbedSchema):
    """Schema for creating new levels.

    Attributes:
        id (str | None): The level ID; if one is not given, it will auto-generate.
        game_id (str): Game ID this level belongs to.
        name (str): Level name.
        slug (str): URL-friendly version.
        url (str): Speedrun.com URL.
        rules (str | None): Level-specific rules.
    """

    id: str | None = Field(
        default=None, max_length=10, description="Auto-generates if omitted"
    )
    name: str = Field(..., max_length=75)
    slug: str = Field(..., max_length=75, description="URL-friendly slug")
    game_id: str
    url: str
    rules: str | None = None
    order: int = Field(
        default=0, exclude=True, description="Sort order; managed via admin panel"
    )


class LevelUpdateSchema(BaseEmbedSchema):
    """Schema for updating levels.

    Attributes:
        game_id (str | None): Updated game ID.
        name (str | None): Updated level name.
        url (str | None): Updated URL.
        rules (str | None): Updated rules.
    """

    game_id: str | None = None
    name: str | None = None
    url: str | None = None
    rules: str | None = None
    order: int = Field(
        default=0, exclude=True, description="Sort order; managed via admin panel"
    )


class GameLevelResponseSchema(LevelBaseSchema):
    """Response schema for game levels with embedded variables.

    Used by the /website/game/{game_id}/levels endpoint.

    Attributes:
        variables (list[VariableWithValuesSchema]): Variables with their possible values.
    """

    variables: list[VariableWithValuesSchema] = Field(default_factory=list)
