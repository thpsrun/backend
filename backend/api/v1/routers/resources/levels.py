from textwrap import dedent
from typing import Annotated

from django.http import HttpRequest
from ninja import Query, Router, Status
from ninja.responses import codes_4xx
from pydantic import Field
from srl.models import Games, Levels, Variables, VariableValues

from api.permissions import admin_auth, moderator_auth, public_auth
from api.v1.docs.levels import (
    LEVELS_ALL,
    LEVELS_DELETE,
    LEVELS_GET,
    LEVELS_POST,
    LEVELS_PUT,
)
from api.v1.schemas.base import ErrorResponse, validate_embeds
from api.v1.schemas.levels import LevelCreateSchema, LevelSchema, LevelUpdateSchema
from api.v1.utils import get_or_generate_id

router = Router()


def _filter_level_variables(
    variables: list[Variables],
    level: Levels,
) -> list[Variables]:
    """Filter variables relevant to a specific level (single-level + all-levels)."""
    filtered = []
    for var in variables:
        if var.scope == "single-level" and var.level_id == level.id:
            filtered.append(var)
        elif var.scope == "all-levels":
            filtered.append(var)
    return filtered


def apply_level_embeds(
    level: Levels,
    embed_fields: list[str],
    all_variables: list[Variables] | None = None,
    values_by_var: dict[str, list[VariableValues]] | None = None,
) -> dict:
    """Apply embeds to a level instance.

    When all_variables and values_by_var are provided (batch mode),
    filters in Python to avoid per-level DB queries.
    """
    embeds = {}

    if "game" in embed_fields:
        if level.game:
            embeds["game"] = {
                "id": level.game.id,
                "name": level.game.name,
                "slug": level.game.slug,
                "release": level.game.release.isoformat(),
                "boxart": level.game.boxart,
                "twitch": level.game.twitch,
                "defaulttime": level.game.defaulttime,
                "idefaulttime": level.game.idefaulttime,
                "pointsmax": level.game.pointsmax,
                "ipointsmax": level.game.ipointsmax,
            }

    if "variables" in embed_fields or "values" in embed_fields:
        if all_variables is not None:
            level_vars = _filter_level_variables(all_variables, level)
        else:
            single_level = list(
                Variables.objects.filter(
                    game=level.game, level=level, scope="single-level",
                ).order_by("name")
            )
            all_levels = list(
                Variables.objects.filter(
                    game=level.game, scope="all-levels",
                ).order_by("name")
            )
            level_vars = single_level + all_levels

        variables_data = []
        for var in level_vars:
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
                        "archive": val.archive,
                        "rules": val.rules,
                    }
                    for val in values
                ]

            variables_data.append(var_data)

        embed_key = "values" if "values" in embed_fields else "variables"
        embeds[embed_key] = variables_data

    return embeds


@router.get(
    "/all",
    response={200: list[LevelSchema], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get All Levels",
    description=dedent(
        """Retrieves all levels within a `Games` object, including optional embedding.

    **Supported Parameters:**
    - `game_id` (str | None): Filter by specific game ID or its slug.
    - `limit` (int | None): Results per page (default 50, max 100).
    - `offset` (int | None): Results to skip (default 0).
    - `embed` (list | None): Comma-separated list of resources to embed.

    **Supported Embeds:**
    - `game`: Includes the metadata of the game the level belongs to.
    - `variables`: Include metadata of the variables belonging to this level.
    - `values`: Include all metadata for each variable and its values.

    **Examples:**
    - `/levels/all` - Get all levels.
    - `/levels/all?game_id=thps4` - Get all levels for THPS4.
    - `/levels/all?game_id=thps4&embed=game` - Get THPS4 levels with game info.
    - `/levels/all?limit=10&offset=20` - Get levels 21-30 from the overall list.
    """
    ),
    auth=public_auth,
    openapi_extra=LEVELS_ALL,
)
def get_all_levels(
    request: HttpRequest,
    game_id: Annotated[
        str | None, Query, Field(description="Filter by game ID")
    ] = None,
    embed: Annotated[
        str | None, Query, Field(description="Comma-separated embeds")
    ] = None,
    limit: Annotated[
        int,
        Query,
        Field(
            ge=1,
            le=100,
            description="Maximum number of returned objects (default 50, less than 100)",
        ),
    ] = 50,
    offset: Annotated[int, Query, Field(ge=0, description="Offset from 0")] = 0,
) -> Status:
    # Checks to see what embeds are being used versus what is allowed
    # via this endpoint. It will return an error to the client if they
    # have an embed type not supported.
    embed_fields = []
    if embed:
        embed_fields = [field.strip() for field in embed.split(",") if field.strip()]
        invalid_embeds = validate_embeds("levels", embed_fields)
        if invalid_embeds:
            return Status(400, ErrorResponse(
                error=f"Invalid embed(s): {', '.join(invalid_embeds)}",
                details=None,
            ))

    try:
        queryset = Levels.objects.select_related("game").order_by("name")

        if game_id:
            queryset = queryset.filter(game__id=game_id)

        levels = list(queryset[offset : offset + limit])

        all_variables = None
        values_by_var = None
        if levels and ("variables" in embed_fields or "values" in embed_fields):
            game_obj = levels[0].game
            all_variables = list(
                Variables.objects.filter(
                    game=game_obj,
                    scope__in=["single-level", "all-levels"],
                ).order_by("name")
            )
            if "values" in embed_fields:
                var_ids = [v.id for v in all_variables]
                all_values = VariableValues.objects.filter(
                    var_id__in=var_ids,
                ).order_by("name")
                values_by_var: dict[str, list[VariableValues]] = {}
                for val in all_values:
                    values_by_var.setdefault(val.var_id, []).append(val)

        level_schemas = []
        for level in levels:
            level_data = LevelSchema.model_validate(level)

            if embed_fields:
                embed_data = apply_level_embeds(
                    level, embed_fields, all_variables, values_by_var,
                )
                for field, data in embed_data.items():
                    setattr(level_data, field, data)

            level_schemas.append(level_data)

        return Status(200, level_schemas)
    except Exception as e:
        return Status(500, ErrorResponse(
            error="Level Retrieval Failure",
            details={"exception": str(e)},
        ))


@router.get(
    "/{id}",
    response={200: LevelSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get Level by ID",
    description=dedent(
        """Retrieve a single level based upon its ID, including optional embedding.

    **Supported Parameters:**
    - `id` (str): Unique ID of the level being queried.
    - `embed` (list | None): Comma-separated list of resources to embed.

    **Supported Embeds:**
    - `game`: Includes the metadata of the game the level belongs to
    - `variables`: Include metadata of the variables belonging to this level
    - `values`: Include all metadata for each variable and its values

    **Examples:**
    - `/levels/592pxj8d` - Get level by ID
    - `/levels/592pxj8d?embed=game` - Get level with game info
    - `/levels/592pxj8d?embed=variables,values` - Get level with variables and values
    """
    ),
    auth=public_auth,
    openapi_extra=LEVELS_GET,
)
def get_level(
    request: HttpRequest,
    id: str,
    embed: Annotated[
        str | None, Query, Field(description="Comma-separated embeds")
    ] = None,
) -> Status:
    if len(id) > 15:
        return Status(400, ErrorResponse(
            error="ID must be 15 characters or less",
            details=None,
        ))

    # Checks to see what embeds are being used versus what is allowed
    # via this endpoint. It will return an error to the client if they
    # have an embed type not supported.
    embed_fields = []
    if embed:
        embed_fields = [field.strip() for field in embed.split(",") if field.strip()]
        invalid_embeds = validate_embeds("levels", embed_fields)
        if invalid_embeds:
            return Status(400, ErrorResponse(
                error=f"Invalid embed(s): {', '.join(invalid_embeds)}",
                details={"valid_embeds": ["game", "variables", "values"]},
            ))

    try:
        level = Levels.objects.filter(id__iexact=id).first()
        if not level:
            return Status(404, ErrorResponse(
                error="Level ID does not exist",
                details=None,
            ))

        level_data = LevelSchema.model_validate(level)

        if embed_fields:
            embed_data = apply_level_embeds(level, embed_fields)
            for field, data in embed_data.items():
                setattr(level_data, field, data)

        return Status(200, level_data)

    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to retrieve level",
            details={"exception": str(e)},
        ))


@router.post(
    "/",
    response={200: LevelSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Create Level",
    description=dedent(
        """Creates a brand new level.

    **REQUIRES MODERATOR ACCESS OR HIGHER.**

    **Request Body:**
    - `id` (str): Unique ID (usually based on SRC) of the level.
    - `name` (str): Level name (e.g., "Warehouse", "School").
    - `slug` (str): URL-friendly version.
    - `type` (str): Whether this is per-game or per-level category.
    - `url` (str): Link to level on Speedrun.com.
    - `rules` (str | None): Level-specific rules text.
    - `appear_on_main` (bool): Whether to show on main page.
    - `archive` (bool): Whether category is hidden from listings.
    - `game` (str): Game this category belongs to.
    - `variables` (List[dict]): Associated variables to the category.
    - `values` (List[dict]): Associated values to the category.
    """
    ),
    auth=moderator_auth,
    openapi_extra=LEVELS_POST,
)
def create_level(
    request: HttpRequest,
    level_data: LevelCreateSchema,
) -> Status:
    try:
        game = Games.objects.filter(id=level_data.game_id).first()
        if not game:
            return Status(404, ErrorResponse(
                error="Game does not exist",
                details=None,
            ))

        try:
            level_id = get_or_generate_id(
                level_data.id,
                lambda id: Levels.objects.filter(id=id).exists(),
            )
        except ValueError as e:
            return Status(400, ErrorResponse(
                error="ID Already Exists",
                details={"exception": str(e)},
            ))

        create_data = level_data.model_dump(exclude={"game_id"})
        create_data["id"] = level_id
        level = Levels.objects.create(game=game, **create_data)

        return Status(200, LevelSchema.model_validate(level))

    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to create level",
            details={"exception": str(e)},
        ))


@router.put(
    "/{id}",
    response={200: LevelSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Update Level",
    description=dedent(
        """Updates the level based on its unique ID.

    **REQUIRES MODERATOR ACCESS OR HIGHER.**

    **Supported Parameters:**
    - `id` (str): Unique ID of the level being edited.

    **Request Body:**
    - `name` (str | None): Level name (e.g., "Warehouse", "School").
    - `slug` (str | None): URL-friendly version.
    - `type` (str | None): Whether this is per-game or per-level category.
    - `url` (str | None): Link to level on Speedrun.com.
    - `rules` (str | None): Level-specific rules text.
    - `archive` (bool): Whether category is hidden from listings.
    - `game` (str | None): Game this category belongs to.
    - `variables` (list[dict]): Associated variables to the category.
    - `values` (list[dict]): Associated values to the category.
    """
    ),
    auth=moderator_auth,
    openapi_extra=LEVELS_PUT,
)
def update_level(
    request: HttpRequest,
    id: str,
    level_data: LevelUpdateSchema,
) -> Status:
    try:
        level = Levels.objects.filter(id__iexact=id).first()
        if not level:
            return Status(404, ErrorResponse(
                error="Level does not exist",
                details=None,
            ))

        update_data = level_data.model_dump(exclude_unset=True)
        if "game_id" in update_data:
            game = Games.objects.filter(id=update_data["game_id"]).first()
            if not game:
                return Status(404, ErrorResponse(
                    error="Game does not exist",
                    details=None,
                ))
            level.game = game
            del update_data["game_id"]

        for field, value in update_data.items():
            setattr(level, field, value)

        level.save()
        return Status(200, LevelSchema.model_validate(level))

    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to update level",
            details={"exception": str(e)},
        ))


@router.delete(
    "/{id}",
    response={200: dict[str, str], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Delete Level",
    description=dedent(
        """Deletes the selected level by its ID.

    **REQUIRES ADMIN ACCESS.**

    **Supported Parameters:**
    - `id` (str): Unique ID of the level being deleted.
    """
    ),
    auth=admin_auth,
    openapi_extra=LEVELS_DELETE,
)
def delete_level(
    request: HttpRequest,
    id: str,
) -> Status:
    try:
        level = Levels.objects.filter(id__iexact=id).first()
        if not level:
            return Status(404, ErrorResponse(
                error="Level does not exist",
                details=None,
            ))

        name = level.name
        level.delete()
        return Status(200, {"message": f"Level '{name}' deleted successfully"})
    except Exception as e:
        return Status(500, ErrorResponse(
            error="Failed to delete level",
            details={"exception": str(e)},
        ))
