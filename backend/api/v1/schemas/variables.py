from typing import Any

from pydantic import ConfigDict, Field, field_validator

from api.v1.schemas.base import (
    BaseEmbedSchema,
    SlugMixin,
    TimingMethodType,
    VariableScopeType,
)


class VariableValueSchema(BaseEmbedSchema):
    """Schema for `VariableValues` data with optional embeds.

    Attributes:
        value (str): Unique ID (usually based on SRC) of the variable value.
        name (str): Human-readable name (e.g., "Hard Mode").
        slug (str): URL-friendly version.
        defaulttime (str | None): Most-specific timing override. When set, takes
            precedence over the parent variable, the category, and the game.
        allowed_methods (list[TimingMethodType] | None): When set, narrows allowed methods for
            runs with this value. Must be a non-empty subset of the parent variable's effective
            allowed methods. Null inherits.
        archive (bool): Whether this value is archived/hidden.
        rules (str | None): Specific rules for this value choice.
        variable (dict | None): Variable this value belongs to - included with ?embed=variable.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "value": "pc",
                "name": "PC",
                "slug": "pc",
                "defaulttime": None,
                "allowed_methods": None,
                "archive": False,
                "rules": None,
            },
        },
    )

    value: str = Field(..., max_length=10)
    name: str = Field(..., max_length=50)
    slug: str = Field(..., max_length=50, description="URL-friendly slug")
    appear_on_main: bool = Field(
        default=False, exclude=True, description="Show on main leaderboard page"
    )
    order: int = Field(
        default=0, exclude=True, description="Sort order; managed via admin panel"
    )
    defaulttime: TimingMethodType | None = Field(
        default=None,
        description="Most-specific timing override; takes precedence over variable/category/game",
    )
    allowed_methods: list[TimingMethodType] | None = Field(
        default=None,
        description=(
            "When set, narrows allowed methods for runs with this value. "
            "Must be a non-empty subset of the parent variable's effective allowed methods. "
            "Null inherits."
        ),
    )
    archive: bool = Field(default=False, description="Hidden from listings")
    rules: str | None = Field(default=None, max_length=5000)
    variable: dict | None = Field(None, description="Included with ?embed=variable")

    @field_validator("variable", mode="before")
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


class VariableBaseSchema(SlugMixin, BaseEmbedSchema):
    """Base variable schema without embeds.

    Attributes:
        id (str): Unique ID (usually based on SRC) of the variable.
        name (str): Variable name (e.g., "Difficulty").
        slug (str): URL-friendly version.
        scope (str): Where this variable applies (global, full-game, etc.).
        defaulttime (str | None): Variable-level timing override. When set, takes
            precedence over the category and game timing methods. When null, the
            variable inherits its category's (or game's) timing.
        allowed_methods (list[TimingMethodType] | None): When set, narrows allowed methods for
            runs that include this variable. Must be a non-empty subset of the parent
            (category/game). Null inherits.
        archive (bool): Whether variable is archived/hidden.
    """

    id: str = Field(..., max_length=10)
    name: str = Field(..., max_length=50)
    slug: str = Field(..., max_length=50, description="URL-friendly slug")
    scope: VariableScopeType = Field(
        ...,
        description="Where this variable applies",
    )
    defaulttime: TimingMethodType | None = Field(
        default=None,
        description="Variable-level timing override; takes precedence over category and game",
    )
    allowed_methods: list[TimingMethodType] | None = Field(
        default=None,
        description=(
            "When set, narrows allowed methods for runs that include this variable. "
            "Must be a non-empty subset of the parent (category/game). Null inherits."
        ),
    )
    archive: bool = Field(default=False, description="Hidden from listings")


class VariableSchema(VariableBaseSchema):
    """Variable schema without embedded values.

    Attributes:
        game (dict | None): Game this variable belongs to - included with ?embed=game.
        category (dict | None): Specific category - included with ?embed=category.
        level (dict | None): Specific level (if scope=single-level) - included with
            ?embed=level.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "5lygdn8q",
                "name": "Platform",
                "slug": "platform",
                "scope": "full-game",
                "defaulttime": None,
                "allowed_methods": None,
                "archive": False,
            },
        },
    )

    game: dict | None = Field(None, description="Included with ?embed=game")
    category: dict | None = Field(None, description="Included with ?embed=category")
    level: dict | None = Field(None, description="Included with ?embed=level")

    @field_validator("game", "category", "level", mode="before")
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


class VariableWithValuesSchema(VariableSchema):
    """Variable schema with embedded possible values.

    Attributes:
        values (List[VariableValueSchema]): Possible values/choices for this variable.
    """

    values: list[VariableValueSchema]


class VariableCreateSchema(BaseEmbedSchema):
    """Schema for creating variables.

    Attributes:
        id (str | None): The variable ID; if one is not given, it will auto-generate.
        game_id (str): Game ID this variable belongs to.
        name (str): Variable name.
        slug (str): URL-friendly version.
        scope (str): Where this variable applies.
        defaulttime (str | None): Variable-level timing override. When set, takes
            precedence over the category and game timing methods.
        archive (bool): Whether variable is archived/hidden.
        category_id (str | None): Specific category ID.
        level_id (str | None): Specific level ID (if scope=single-level).
    """

    id: str | None = Field(
        default=None, max_length=10, description="Auto-generates if omitted"
    )
    game_id: str
    name: str = Field(..., max_length=50)
    slug: str = Field(..., max_length=50, description="URL-friendly slug")
    scope: VariableScopeType = Field(...)
    defaulttime: TimingMethodType | None = Field(
        default=None,
        description="Variable-level timing override; takes precedence over category and game",
    )
    archive: bool = Field(default=False, description="Hidden from listings")
    category_id: str | None = Field(
        None, description="If not applying to all categories"
    )
    level_id: str | None = Field(None, description="If scope=single-level")
    allowed_methods: list[TimingMethodType] | None = Field(
        default=None,
        description="Allowed timing methods; null inherits.",
    )


class VariableUpdateSchema(BaseEmbedSchema):
    """Schema for updating variables.

    Attributes:
        game_id (str | None): Updated game ID.
        name (str | None): Updated variable name.
        scope (str | None): Updated scope.
        defaulttime (str | None): Updated variable-level timing override.
        archive (bool | None): Updated archive status.
        category_id (str | None): Updated category ID.
        level_id (str | None): Updated level ID.
    """

    game_id: str | None = None
    name: str | None = Field(default=None, max_length=50)
    scope: VariableScopeType | None = None
    defaulttime: TimingMethodType | None = None
    archive: bool | None = None
    category_id: str | None = None
    level_id: str | None = None
    allowed_methods: list[TimingMethodType] | None = None


class VariableValueCreateSchema(BaseEmbedSchema):
    """Schema for creating variable values.

    Attributes:
        value (str | None): The value ID; if one is not given, it will auto-generate.
        variable_id (str): Variable ID this value belongs to.
        name (str): Value name.
        slug (str | None): URL-friendly version; auto-generated from name if not provided.
        defaulttime (str | None): Most-specific timing override.
        archive (bool): Whether value is archived/hidden.
        rules (str | None): Rules specific to this value choice.
    """

    value: str | None = Field(
        default=None, max_length=10, description="Auto-generates if omitted"
    )
    variable_id: str
    name: str = Field(..., max_length=50)
    slug: str | None = Field(
        default=None,
        max_length=50,
        description="URL-friendly; auto-generates from name",
    )
    appear_on_main: bool = Field(
        default=False, exclude=True, description="Show on main leaderboard page"
    )
    order: int = Field(
        default=0, exclude=True, description="Sort order; managed via admin panel"
    )
    defaulttime: TimingMethodType | None = Field(
        default=None,
        description="Most-specific timing override; takes precedence over variable/category/game",
    )
    archive: bool = Field(default=False, description="Hidden from listings")
    rules: str | None = Field(default=None, max_length=5000)
    allowed_methods: list[TimingMethodType] | None = Field(
        default=None,
        description="Allowed timing methods; null inherits.",
    )


class VariableValueUpdateSchema(BaseEmbedSchema):
    """Schema for updating variable values.

    Attributes:
        variable_id (str | None): Updated variable ID.
        name (str | None): Updated value name.
        slug (str | None): Updated URL-friendly slug.
        defaulttime (str | None): Updated value-level timing override.
        archive (bool | None): Updated archive status.
        rules (str | None): Updated rules.
    """

    variable_id: str | None = None
    name: str | None = Field(default=None, max_length=50)
    slug: str | None = Field(default=None, max_length=50)
    appear_on_main: bool = Field(
        default=False, exclude=True, description="Show on main leaderboard page"
    )
    order: int = Field(
        default=0, exclude=True, description="Sort order; managed via admin panel"
    )
    defaulttime: TimingMethodType | None = None
    archive: bool | None = None
    rules: str | None = Field(default=None, max_length=5000)
    allowed_methods: list[TimingMethodType] | None = None
