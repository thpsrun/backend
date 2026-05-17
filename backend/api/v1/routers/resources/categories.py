from typing import Annotated

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest
from ninja import Query, Router, Status
from srl.models import Categories, Games, Variables, VariableValues

from api.permissions import authed, public_read
from api.v1.routers.utils.embeds import parse_embeds, serialize_game_embed
from api.v1.routers.utils.resolvers import game_from_body, game_from_category_path
from api.v1.schemas.base import CategoryTypeType, ErrorResponse
from api.v1.schemas.categories import (
    CategoryCreateSchema,
    CategorySchema,
    CategoryUpdateSchema,
)
from api.v1.utils import get_or_generate_id

router = Router()


def _filter_scope(
    variables: list[Variables],
    category: Categories,
) -> list[Variables]:
    """Filter variables by scope rules for a given category type."""
    filtered = []
    for var in variables:
        if var.cat:
            if var.scope == "single-level":
                continue
            if category.type == "per-game" and var.scope == "all-levels":
                continue
            if category.type == "per-level" and var.scope == "full-game":
                continue
            if var.cat.id is not None and var.cat.id != category.id:
                continue
            filtered.append(var)
    return filtered


def apply_category_embeds(
    category: Categories,
    embed_fields: list[str],
    all_variables: list[Variables] | None = None,
    values_by_var: dict[str, list[VariableValues]] | None = None,
) -> dict:
    """Apply embeds to a category instance.

    When all_variables and values_by_var are provided (batch mode),
    filters in Python to avoid per-category DB queries.
    """
    embeds = {}

    if "game" in embed_fields:
        if category.game:
            embeds["game"] = serialize_game_embed(category.game)

    if "variables" in embed_fields or "values" in embed_fields:
        if all_variables is not None:
            variables = _filter_scope(all_variables, category)
        else:
            scope_exclude = Q(scope="single-level") | Q(
                scope="all-levels" if category.type == "per-game" else "full-game"
            )
            variables = list(
                Variables.objects.filter(
                    game=category.game,
                )
                .filter(
                    Q(cat=category) | Q(cat__isnull=True),
                )
                .exclude(
                    scope_exclude,
                )
                .order_by("name")
            )

        variables_data = []
        for var in variables:
            var_data = {
                "id": var.id,
                "name": var.name,
                "slug": var.slug,
                "scope": var.scope,
                "archive": var.archive,
            }

            if "values" in embed_fields:
                if values_by_var is not None:
                    values = values_by_var.get(var.id, [])
                else:
                    values = list(
                        VariableValues.objects.filter(var=var).order_by("name")
                    )
                var_data["values"] = [
                    {
                        "value": val.value,
                        "name": val.name,
                        "slug": val.slug,
                        "appear_on_main": val.appear_on_main,
                        "archive": val.archive,
                        "rules": val.rules,
                        "defaulttime": val.defaulttime,
                        "allowed_methods": val.allowed_methods,
                    }
                    for val in values
                ]

            variables_data.append(var_data)

        embed_key = "values" if "values" in embed_fields else "variables"
        embeds[embed_key] = variables_data

    return embeds


@router.get(
    "/all",
    response={
        200: list[CategorySchema],
        400: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get All Categories",
    description="""\
Retrieves all categories within a `Games` object, including optional embedding and
querying.

Supported Parameters:
- `game` (str | None): Filter by specific game ID or its slug.
- `type` (str | None): Filter by category type (`per-game` or `per-level`).
- `limit` (int | None): Results per page (default 50, max 100).
- `offset` (int | None): Results to skip (default 0).
- `embed` (list | None): Comma-separated list of resources to embed.

Supported Embeds:
- `variables`: Include metadata of the variables belonging to this category.
- `values`: Include all metadata for each variable and its values.

Examples:
- `/categories/all` - Get all categories
- `/categories/all?game=thps4` - Get all categories for THPS4.
- `/categories/all?type=per-game&limit=20` - Get first 20 full-game categories.
- `/categories/all?game=thps4&embed=variables` - Get THPS4 categories with variables.
""",
    auth=public_read(),
)
def get_all_categories(
    request: HttpRequest,
    game: Annotated[str | None, Query(description="Filter by game ID or slug")] = None,
    type: Annotated[
        CategoryTypeType | None, Query(description="Filter by type")
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
    if not game:
        return Status(
            400,
            ErrorResponse(
                error="Please provide the game's unique ID or slug.",
                details=None,
            ),
        )

    embed_fields = parse_embeds(embed, "categories")

    try:
        queryset = (
            Categories.objects.filter(
                Q(game__id__iexact=game) | Q(game__slug__iexact=game)
            )
            .select_related("game")
            .order_by("name")
        )

        if type:
            queryset = queryset.filter(type=type)

        categories = list(queryset[offset : offset + limit])

        all_variables = None
        values_by_var = None
        if categories and ("variables" in embed_fields or "values" in embed_fields):
            game_obj = categories[0].game
            all_variables = list(
                Variables.objects.filter(game=game_obj).order_by("name")
            )
            if "values" in embed_fields:
                var_ids = [v.id for v in all_variables]
                all_values = VariableValues.objects.filter(
                    var_id__in=var_ids,
                ).order_by("name")
                values_by_var: dict[str, list[VariableValues]] = {}
                for val in all_values:
                    values_by_var.setdefault(val.var_id, []).append(val)

        category_schemas = []
        for category in categories:
            category_data = CategorySchema.model_validate(category)

            if embed_fields:
                embed_data = apply_category_embeds(
                    category,
                    embed_fields,
                    all_variables,
                    values_by_var,
                )
                for field, data in embed_data.items():
                    setattr(category_data, field, data)

            category_schemas.append(category_data)

        return Status(200, category_schemas)
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Category Retrieval Failed",
                details={"exception": str(e)},
            ),
        )


@router.get(
    "/{id}",
    response={
        200: CategorySchema,
        400: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Get Category by ID",
    description="""\
Retrieves a single category based upon its ID, including optional embedding.

Supported Parameters:
- `id` (str): Unique ID of the category being queried.
- `embed` (list | None): Comma-separated list of resources to embed.

Supported Embeds:
- `game`: Includes the metadata of the game the category belongs to.
- `variables`: Include metadata of the variables belonging to this category.
- `values`: Include all metadata for each variable and its values.

Examples:
- `/categories/rklge08d` - Get category by ID.
- `/categories/rklge08d?embed=game` - Get category with game info.
- `/categories/rklge08d?embed=variables,values` - Get category with variables and values.
""",
    auth=public_read(),
)
def get_category(
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

    embed_fields = parse_embeds(embed, "categories")

    try:
        category = (
            Categories.objects.select_related("game")
            .filter(
                id__iexact=id,
            )
            .first()
        )
        if not category:
            return Status(
                404,
                ErrorResponse(
                    error="Category ID Doesn't Exist",
                    details=None,
                ),
            )

        category_data = CategorySchema.model_validate(category)

        if embed_fields:
            embed_data = apply_category_embeds(category, embed_fields)
            for field, data in embed_data.items():
                setattr(category_data, field, data)

        return Status(200, category_data)
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Category Retrieval Failure",
                details={"exception": str(e)},
            ),
        )


@router.post(
    "/",
    response={
        201: CategorySchema,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        422: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Create Category",
    description="""\
Creates a brand new category.

Request Body:
- `id` (str): Unique ID (usually based on SRC) of the category.
- `name` (str): Category name (e.g., "Any%", "100%").
- `slug` (str): URL-friendly version.
- `type` (str): Whether this is per-game or per-level category.
- `url` (str): Link to category on Speedrun.com.
- `rules` (str | None): Category-specific rules text.
- `appear_on_main` (bool): Whether to show on main page.
- `archive` (bool): Whether category is hidden from listings.
- `game` (str): Game this category belongs to.
- `variables` (list[dict]): Associated variables to the category.
- `values` (list[dict]): Associated values to the category.
""",
    auth=authed("games.manage", target_resolver=game_from_body),
)
def create_category(
    request: HttpRequest,
    category_data: CategoryCreateSchema,
) -> Status:
    try:
        game = Games.objects.filter(id=category_data.game_id).first()
        if not game:
            return Status(
                404,
                ErrorResponse(
                    error="Game Doesn't Exist",
                    details=None,
                ),
            )

        try:
            category_id = get_or_generate_id(
                category_data.id,
                lambda id: Categories.objects.filter(id=id).exists(),
            )
        except ValueError:
            return Status(
                400,
                ErrorResponse(
                    error="ID Already Exists",
                    details=None,
                ),
            )

        create_data = category_data.model_dump(exclude={"game_id"}, exclude_unset=True)
        create_data["id"] = category_id
        category = Categories(game=game, **create_data)
        try:
            category.full_clean()
        except ValidationError as e:
            return Status(
                422,
                ErrorResponse(
                    error="Validation failed",
                    details={"errors": e.message_dict},
                ),
            )
        category.save()

        return Status(201, CategorySchema.model_validate(category))
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to create category",
                details={"exception": str(e)},
            ),
        )


@router.put(
    "/{id}",
    response={
        200: CategorySchema,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        422: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Update Category",
    description="""\
Updates the category based on its unique ID.

Supported Parameters:
- `id` (str): Unique ID of the category being edited.

Request Body:
- `name` (str | None): Category name (e.g., "Any%", "100%").
- `slug` (str | None): URL-friendly version.
- `type` (str | None): Whether this is per-game or per-level category.
- `url` (str | None): Link to category on Speedrun.com.
- `rules` (str | None): Category-specific rules text.
- `appear_on_main` (bool | None): Whether to show on main page.
- `archive` (bool | None): Whether category is hidden from listings.
- `game` (str | None): Game this category belongs to.
- `variables` (list[dict] | None): Associated variables to the category.
- `values` (list[dict] | None): Associated values to the category.
""",
    auth=authed("games.manage", target_resolver=game_from_category_path),
)
def update_category(
    request: HttpRequest,
    id: str,
    category_data: CategoryUpdateSchema,
) -> Status:
    try:
        category = (
            Categories.objects.select_related("game")
            .filter(
                id__iexact=id,
            )
            .first()
        )
        if not category:
            return Status(
                404,
                ErrorResponse(
                    error="Category does not exist",
                    details=None,
                ),
            )

        update_data = category_data.model_dump(exclude_unset=True)
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
            category.game = game
            del update_data["game_id"]

        for field, value in update_data.items():
            setattr(category, field, value)

        try:
            category.full_clean()
        except ValidationError as e:
            return Status(
                422,
                ErrorResponse(
                    error="Validation failed",
                    details={"errors": e.message_dict},
                ),
            )
        category.save()
        return Status(200, CategorySchema.model_validate(category))
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to update category",
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
    summary="Delete Category",
    description="""\
Deletes the selected category based on its ID.

Supported Parameters:
- `id` (str): Unique ID of the category being deleted.
""",
    auth=authed("users.admin"),
)
def delete_category(
    request: HttpRequest,
    id: str,
) -> Status:
    try:
        category = (
            Categories.objects.select_related("game")
            .filter(
                id__iexact=id,
            )
            .first()
        )
        if not category:
            return Status(
                404,
                ErrorResponse(
                    error="Category does not exist",
                    details=None,
                ),
            )

        name = category.name
        category.delete()
        return Status(200, {"message": f"Category '{name}' deleted successfully"})
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to delete category",
                details={"exception": str(e)},
            ),
        )
