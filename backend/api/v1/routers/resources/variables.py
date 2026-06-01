from typing import Annotated

from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.utils.text import slugify
from ninja import Query, Router, Status
from srl.models import Categories, Games, Levels, Variables, VariableValues

from api.permissions import authed, public_read
from api.v1.routers.utils.embeds import (
    parse_embeds,
    serialize_category_embed,
    serialize_game_embed,
    serialize_level_embed,
)
from api.v1.routers.utils.resolvers import (
    game_from_body,
    game_from_variable_body,
    game_from_variable_path,
    game_from_variable_value_path,
)
from api.v1.schemas.base import ErrorResponse, VariableScopeType
from api.v1.schemas.variables import (
    VariableCreateSchema,
    VariableSchema,
    VariableUpdateSchema,
    VariableValueCreateSchema,
    VariableValueSchema,
    VariableValueUpdateSchema,
    VariableWithValuesSchema,
)
from api.v1.utils import get_or_generate_id

router = Router(tags=["Variables"])


def apply_variable_embeds(
    variable: Variables,
    embed_fields: list[str],
) -> dict:
    """Apply requested embeds to a variable instance."""
    embeds = {}

    if "game" in embed_fields:
        if variable.game:
            embeds["game"] = serialize_game_embed(variable.game)

    if "category" in embed_fields:
        if variable.cat:
            embeds["category"] = serialize_category_embed(variable.cat)

    if "level" in embed_fields:
        if variable.level:
            embeds["level"] = serialize_level_embed(variable.level)

    return embeds


def apply_value_embeds(
    value: VariableValues,
    embed_fields: list[str],
) -> dict:
    """Apply requested embeds to a variable value instance."""
    embeds = {}

    if "variable" in embed_fields:
        if value.var:
            embeds["variable"] = {
                "id": value.var.id,
                "name": value.var.name,
                "slug": value.var.slug,
                "scope": value.var.scope,
                "defaulttime": value.var.defaulttime,
                "archive": value.var.archive,
            }

    return embeds


@router.get(
    "/all",
    response={
        200: list[VariableSchema],
        400: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get All Variables",
    description="""\
Retrieve all variables within the `Variables` object, including optional embedding and
filtering

Supported Embeds:
- `game`: Include metadata of the game the variable belongs to
- `category`: Include metadata of the category the variable belongs to
- `level`: Include metadata of the level the variable belongs to

Supported Parameters:
- `game_id`: Filter by specific game ID or slug
- `category_id`: Filter by specific category ID
- `level_id`: Filter by specific level ID
- `scope`: Filter by scope (`global`, `full-game`, `all-levels`, `single-level`)
- `embed`: Comma-separated list of resources to embed
- `limit`: Results per page (default 50, max 100)
- `offset`: Results to skip (default 0)

Examples:
- `/variables/all` - Get all variables
- `/variables/all?game_id=thps4` - Get all variables for THPS4
- `/variables/all?scope=full-game` - Get all full-game variables
- `/variables/all?game_id=thps4&embed=game,category` - Get THPS4 variables with embeds
""",
    auth=public_read(),
)
def get_all_variables(
    request: HttpRequest,
    game_id: Annotated[str | None, Query(description="Filter by game ID")] = None,
    category_id: Annotated[
        str | None, Query(description="Filter by category ID")
    ] = None,
    level_id: Annotated[str | None, Query(description="Filter by level ID")] = None,
    scope: Annotated[
        VariableScopeType | None, Query(description="Filter by scope")
    ] = None,
    embed: Annotated[str | None, Query(description="Comma-separated embeds")] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of returned objects (default 50, less than 100)",
        ),
    ] = 50,
    offset: Annotated[int, Query(ge=0, description="Offset from 0")] = 0,
) -> Status:
    embed_fields = parse_embeds(embed, "variables")

    try:
        queryset = (
            Variables.objects.select_related(
                "game",
                "cat",
                "level",
            )
            .all()
            .order_by("name")
        )

        # If parameters are fulfilled by the client, this will further
        # drill down what the client is looking for.
        if game_id:
            queryset = queryset.filter(game__id=game_id)
        if category_id:
            queryset = queryset.filter(cat__id=category_id)
        if level_id:
            queryset = queryset.filter(level__id=level_id)
        if scope:
            queryset = queryset.filter(scope=scope)

        variables = queryset[offset : offset + limit]

        # For each of the variables, it will go through and add additional context
        # if the embed option is provided. If not, it will provide basic information
        # (e.g. the ID of the value), with additional information provided if declared.
        variable_schemas = []
        for variable in variables:
            variable_data = VariableSchema.model_validate(variable)

            if embed_fields:
                embed_data = apply_variable_embeds(variable, embed_fields)
                for field, data in embed_data.items():
                    setattr(variable_data, field, data)

            variable_schemas.append(variable_data)

        return Status(200, variable_schemas)

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve variables",
                details={"exception": str(e)},
            ),
        )


@router.get(
    "/values/all",
    response={
        200: list[VariableValueSchema],
        400: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get All Variable Values",
    description="""\
Retrieve all values for a specific variable.

Supported Embeds:
- `variable`: Include metadata of the variable this value belongs to

Supported Parameters:
- `variable_id` (required): Filter by specific variable ID
- `embed`: Comma-separated list of resources to embed
- `limit`: Results per page (default 50, max 100)
- `offset`: Results to skip (default 0)

Examples:
- `/variables/values/all?variable_id=5lygdn8q` - Get all values for a variable
- `/variables/values/all?variable_id=5lygdn8q&embed=variable` - With embeds
""",
    auth=public_read(),
)
def get_all_values(
    request: HttpRequest,
    variable_id: Annotated[
        str | None, Query(description="Filter by variable ID (required)")
    ] = None,
    embed: Annotated[str | None, Query(description="Comma-separated embeds")] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of returned objects (default 50, less than 100)",
        ),
    ] = 50,
    offset: Annotated[int, Query(ge=0, description="Offset from 0")] = 0,
) -> Status:
    if not variable_id:
        return Status(
            400,
            ErrorResponse(
                error="Please provide the variable's unique ID.",
                details=None,
            ),
        )

    embed_fields = []
    if embed:
        embed_fields = [field.strip() for field in embed.split(",") if field.strip()]
        valid_embeds = {"variable"}
        invalid_embeds = [field for field in embed_fields if field not in valid_embeds]
        if invalid_embeds:
            return Status(
                400,
                ErrorResponse(
                    error=f"Invalid embed(s): {', '.join(invalid_embeds)}",
                    details={"valid_embeds": ["variable"]},
                ),
            )

    try:
        variable = Variables.objects.filter(id__iexact=variable_id).first()
        if not variable:
            return Status(
                404,
                ErrorResponse(
                    error="Variable does not exist",
                    details=None,
                ),
            )

        queryset = VariableValues.objects.filter(var=variable).order_by("name")
        values = queryset.select_related("var")[offset : offset + limit]

        value_schemas = []
        for value in values:
            value_data = VariableValueSchema.model_validate(value)

            if embed_fields:
                embed_data = apply_value_embeds(value, embed_fields)
                for field, data in embed_data.items():
                    setattr(value_data, field, data)

            value_schemas.append(value_data)

        return Status(200, value_schemas)

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve variable values",
                details={"exception": str(e)},
            ),
        )


@router.post(
    "/values/",
    response={
        201: VariableValueSchema,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        422: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Create Variable Value",
    description="""\
Creates a brand new variable value.

Request Body:
- `variable_id` (str): Variable ID this value belongs to.
- `name` (str): Value name.
- `value` (str | None): Value ID; if not provided, one will be auto-generated.
- `slug` (str | None): URL-friendly slug; auto-generated from name if not provided.
- `archive` (bool): Whether value is archived/hidden.
- `rules` (str | None): Rules specific to this value choice.
""",
    auth=authed("games.manage", target_resolver=game_from_variable_body),
)
def create_value(
    request: HttpRequest,
    value_data: VariableValueCreateSchema,
) -> Status:
    try:
        variable = Variables.objects.filter(id__iexact=value_data.variable_id).first()
        if not variable:
            return Status(
                400,
                ErrorResponse(
                    error="Variable does not exist",
                    details=None,
                ),
            )

        try:
            value_id = get_or_generate_id(
                value_data.value,
                lambda id: VariableValues.objects.filter(value=id).exists(),
            )
        except ValueError as e:
            return Status(
                400,
                ErrorResponse(
                    error="Value ID Already Exists",
                    details={"exception": str(e)},
                ),
            )

        value_slug = value_data.slug if value_data.slug else slugify(value_data.name)

        new_value = VariableValues(
            value=value_id,
            var=variable,
            name=value_data.name,
            slug=value_slug,
            archive=value_data.archive,
            rules=value_data.rules,
            defaulttime=value_data.defaulttime,
            required_methods=value_data.required_methods,
        )
        try:
            new_value.full_clean()
        except ValidationError as e:
            return Status(
                422,
                ErrorResponse(
                    error="Validation failed",
                    details={"errors": e.message_dict},
                ),
            )
        new_value.save()

        return Status(201, VariableValueSchema.model_validate(new_value))

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to create variable value",
                details={"exception": str(e)},
            ),
        )


@router.get(
    "/values/{value_id}",
    response={
        200: VariableValueSchema,
        400: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get Variable Value by ID",
    description="""\
Retrieve a single variable value by its ID.

Supported Embeds:
- `variable`: Include metadata of the variable this value belongs to

Examples:
- `/variables/values/pc` - Get value by ID
- `/variables/values/pc?embed=variable` - Get value with variable data
""",
    auth=public_read(),
)
def get_value(
    request: HttpRequest,
    value_id: str,
    embed: Annotated[str | None, Query(description="Comma-separated embeds")] = None,
) -> Status:
    if len(value_id) > 10:
        return Status(
            400,
            ErrorResponse(
                error="Value ID must be 10 characters or less",
                details=None,
            ),
        )

    embed_fields = []
    if embed:
        embed_fields = [field.strip() for field in embed.split(",") if field.strip()]
        valid_embeds = {"variable"}
        invalid_embeds = [field for field in embed_fields if field not in valid_embeds]
        if invalid_embeds:
            return Status(
                400,
                ErrorResponse(
                    error=f"Invalid embed(s): {', '.join(invalid_embeds)}",
                    details={"valid_embeds": ["variable"]},
                ),
            )

    try:
        value = (
            VariableValues.objects.select_related("var")
            .filter(value__iexact=value_id)
            .first()
        )
        if not value:
            return Status(
                404,
                ErrorResponse(
                    error="Variable value does not exist",
                    details=None,
                ),
            )

        value_data = VariableValueSchema.model_validate(value)

        if embed_fields:
            embed_data = apply_value_embeds(value, embed_fields)
            for field, data in embed_data.items():
                setattr(value_data, field, data)

        return Status(200, value_data)

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve variable value",
                details={"exception": str(e)},
            ),
        )


@router.put(
    "/values/{value_id}",
    response={
        200: VariableValueSchema,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        422: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Update Variable Value",
    description="""\
Updates the variable value based on its unique ID.

Supported Parameters:
- `value_id` (str): Unique ID of the value being updated.

Request Body:
- `variable_id` (str | None): Updated variable ID.
- `name` (str | None): Updated value name.
- `slug` (str | None): Updated URL-friendly slug.
- `archive` (bool | None): Updated archive status.
- `rules` (str | None): Updated rules.
""",
    auth=authed("games.manage", target_resolver=game_from_variable_value_path),
)
def update_value(
    request: HttpRequest,
    value_id: str,
    value_data: VariableValueUpdateSchema,
) -> Status:
    try:
        value = VariableValues.objects.filter(value__iexact=value_id).first()
        if not value:
            return Status(
                404,
                ErrorResponse(
                    error="Variable value does not exist",
                    details=None,
                ),
            )

        update_data = value_data.model_dump(exclude_unset=True)

        if "variable_id" in update_data:
            variable = Variables.objects.filter(
                id__iexact=update_data["variable_id"]
            ).first()
            if not variable:
                return Status(
                    400,
                    ErrorResponse(
                        error="Variable does not exist",
                        details=None,
                    ),
                )
            value.var = variable
            del update_data["variable_id"]

        for field, val in update_data.items():
            setattr(value, field, val)

        try:
            value.full_clean()
        except ValidationError as e:
            return Status(
                422,
                ErrorResponse(
                    error="Validation failed",
                    details={"errors": e.message_dict},
                ),
            )
        value.save()

        return Status(200, VariableValueSchema.model_validate(value))

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to update variable value",
                details={"exception": str(e)},
            ),
        )


@router.delete(
    "/values/{value_id}",
    response={
        200: dict[str, str],
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Delete Variable Value",
    description="""\
Deletes the selected variable value by its ID.

Supported Parameters:
- `value_id` (str): Unique ID of the value being deleted.
""",
    auth=authed("users.admin"),
)
def delete_value(
    request: HttpRequest,
    value_id: str,
) -> Status:
    try:
        value = VariableValues.objects.filter(value__iexact=value_id).first()
        if not value:
            return Status(
                404,
                ErrorResponse(
                    error="Variable value does not exist",
                    details=None,
                ),
            )

        name = value.name
        value.delete()
        return Status(200, {"message": f"Variable value '{name}' deleted successfully"})

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to delete variable value",
                details={"exception": str(e)},
            ),
        )


@router.get(
    "/{id}",
    response={
        200: VariableWithValuesSchema,
        400: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get Variable by ID",
    description="""\
Retrieve a single variable by its ID, including optional embedding.

Supported Embeds:
- `game`: Include metadata related to the game
- `category`: Include metadata related to the category
- `level`: Include metadata related to the level

Examples:
- `/variables/5lygdn8q` - Get variable by ID
- `/variables/5lygdn8q?embed=game` - Get variable with game data
- `/variables/5lygdn8q?embed=game,category,level` - Get variable with all embeds
""",
    auth=public_read(),
)
def get_variable(
    request: HttpRequest,
    id: str,
    embed: Annotated[str | None, Query(description="Comma-separated embeds")] = None,
) -> Status:
    if len(id) > 15:
        return Status(
            400,
            ErrorResponse(
                error="ID must be 15 characters or less",
                details=None,
            ),
        )

    # Checks to see what embeds are being used versus what is allowed
    # via this endpoint. It will return an error to the client if they
    # have an embed type not supported.
    embed_fields = []
    if embed:
        embed_fields = [field.strip() for field in embed.split(",") if field.strip()]
        valid_embeds = {"game", "category", "level"}
        invalid_embeds = [field for field in embed_fields if field not in valid_embeds]
        if invalid_embeds:
            return Status(
                400,
                ErrorResponse(
                    error=f"Invalid embed(s): {', '.join(invalid_embeds)}",
                    details={"valid_embeds": ["game", "category", "level"]},
                ),
            )

    try:
        variable = (
            Variables.objects.select_related(
                "game",
                "cat",
                "level",
            )
            .filter(id__iexact=id)
            .first()
        )
        if not variable:
            return Status(
                404,
                ErrorResponse(
                    error="Variable ID does not exist",
                    details=None,
                ),
            )

        values = VariableValues.objects.filter(var=variable).order_by("name")

        variable_data = {
            "id": variable.id,
            "name": variable.name,
            "slug": variable.slug,
            "scope": variable.scope,
            "defaulttime": variable.defaulttime,
            "archive": variable.archive,
            "values": [
                {
                    "value": val.value,
                    "name": val.name,
                    "slug": val.slug,
                    "defaulttime": val.defaulttime,
                    "archive": val.archive,
                    "rules": val.rules,
                }
                for val in values
            ],
        }

        if embed_fields:
            embed_data = apply_variable_embeds(variable, embed_fields)
            variable_data.update(embed_data)

        return Status(200, VariableWithValuesSchema(**variable_data))

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve variable",
                details={"exception": str(e)},
            ),
        )


@router.post(
    "/",
    response={
        201: VariableSchema,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        422: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Create Variable",
    description="""\
Creates a brand new variable with validation for scope and relationship constraints.

Request Body:
- `game_id` (str): Game ID this variable belongs to.
- `name` (str): Variable name.
- `scope` (str): Where variable applies (`global`, `full-game`, `all-levels`, `single-level`).
- `archive` (bool): Whether variable is archived/hidden from listings.
- `category_id` (str | None): Specific category ID.
- `level_id` (str | None): Specific level ID (required if scope is `single-level`).
""",
    auth=authed("games.manage", target_resolver=game_from_body),
)
def create_variable(
    request: HttpRequest,
    variable_data: VariableCreateSchema,
) -> Status:
    try:
        game = Games.objects.filter(id=variable_data.game_id).first()
        if not game:
            return Status(
                400,
                ErrorResponse(
                    error="Game does not exist",
                    details=None,
                ),
            )

        category = None
        if variable_data.category_id:
            category = Categories.objects.filter(id=variable_data.category_id).first()
            if not category:
                return Status(
                    400,
                    ErrorResponse(
                        error="Category does not exist",
                        details=None,
                    ),
                )

        level = None
        if variable_data.level_id:
            if variable_data.scope != "single-level":
                return Status(
                    400,
                    ErrorResponse(
                        error="If level_id is provided, scope must be 'single-level'",
                        details=None,
                    ),
                )
            level = Levels.objects.filter(id=variable_data.level_id).first()
            if not level:
                return Status(
                    400,
                    ErrorResponse(
                        error="Level does not exist",
                        details=None,
                    ),
                )
        elif variable_data.scope == "single-level":
            return Status(
                400,
                ErrorResponse(
                    error="If scope is 'single-level', level_id must be provided",
                    details=None,
                ),
            )

        try:
            variable_id = get_or_generate_id(
                variable_data.id,
                lambda id: Variables.objects.filter(id=id).exists(),
            )
        except ValueError as e:
            return Status(
                400,
                ErrorResponse(
                    error="ID Already Exists",
                    details={"exception": str(e)},
                ),
            )

        create_data = variable_data.model_dump(
            exclude={"game_id", "category_id", "level_id"},
            exclude_unset=True,
        )
        create_data["id"] = variable_id
        variable = Variables(game=game, cat=category, level=level, **create_data)
        try:
            variable.full_clean()
        except ValidationError as e:
            return Status(
                422,
                ErrorResponse(
                    error="Validation failed",
                    details={"errors": e.message_dict},
                ),
            )
        variable.save()

        return Status(201, VariableSchema.model_validate(variable))

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to create variable",
                details={"exception": str(e)},
            ),
        )


@router.put(
    "/{id}",
    response={
        200: VariableSchema,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        422: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Update Variable",
    description="""\
Updates the variable based on its unique ID.

Supported Parameters:
- `id` (str): Unique ID of the variable being updated.

Request Body:
- `game_id` (str | None): Updated game ID.
- `name` (str | None): Updated variable name.
- `scope` (str | None): Updated scope (`global`, `full-game`, `all-levels`, `single-level`).
- `archive` (bool | None): Updated archive status.
- `category_id` (str | None): Updated category ID.
- `level_id` (str | None): Updated level ID.
""",
    auth=authed("games.manage", target_resolver=game_from_variable_path),
)
def update_variable(
    request: HttpRequest,
    id: str,
    variable_data: VariableUpdateSchema,
) -> Status:
    try:
        variable = (
            Variables.objects.select_related(
                "game",
                "cat",
                "level",
            )
            .filter(id__iexact=id)
            .first()
        )
        if not variable:
            return Status(
                404,
                ErrorResponse(
                    error="Variable does not exist",
                    details=None,
                ),
            )

        update_data = variable_data.model_dump(exclude_unset=True)

        if "game_id" in update_data:
            game = Games.objects.filter(id=update_data["game_id"]).first()
            if not game:
                return Status(
                    400,
                    ErrorResponse(
                        error="Game does not exist",
                        details=None,
                    ),
                )
            variable.game = game
            del update_data["game_id"]

        if "category_id" in update_data:
            if update_data["category_id"]:
                category = Categories.objects.filter(
                    id=update_data["category_id"]
                ).first()
                if not category:
                    return Status(
                        400,
                        ErrorResponse(
                            error="Category does not exist",
                            details=None,
                        ),
                    )
                variable.cat = category
            else:
                variable.cat = None  # type: ignore
            del update_data["category_id"]

        if "level_id" in update_data:
            if update_data["level_id"]:
                level = Levels.objects.filter(id=update_data["level_id"]).first()
                if not level:
                    return Status(
                        400,
                        ErrorResponse(
                            error="Level does not exist",
                            details=None,
                        ),
                    )
                variable.level = level
            else:
                variable.level = None
            del update_data["level_id"]

        for field, value in update_data.items():
            setattr(variable, field, value)

        try:
            variable.full_clean()
        except ValidationError as e:
            return Status(
                422,
                ErrorResponse(
                    error="Validation failed",
                    details={"errors": e.message_dict},
                ),
            )

        variable.save()

        return Status(200, VariableSchema.model_validate(variable))

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to update variable",
                details={"exception": str(e)},
            ),
        )


@router.delete(
    "/{id}",
    response={
        200: dict[str, str],
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Delete Variable",
    description="""\
Deletes the selected variable by its ID. Also deletes associated values.

Supported Parameters:
- `id` (str): Unique ID of the variable being deleted.
""",
    auth=authed("users.admin"),
)
def delete_variable(
    request: HttpRequest,
    id: str,
) -> Status:
    try:
        variable = (
            Variables.objects.select_related(
                "game",
                "cat",
                "level",
            )
            .filter(id__iexact=id)
            .first()
        )
        if not variable:
            return Status(
                404,
                ErrorResponse(
                    error="Variable does not exist",
                    details=None,
                ),
            )

        name = variable.name
        variable.delete()
        return Status(
            200, {"message": f"Variable '{name}' and its values deleted successfully"}
        )

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to delete variable",
                details={"exception": str(e)},
            ),
        )
