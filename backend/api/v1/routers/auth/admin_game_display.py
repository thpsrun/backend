from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router, Status
from ninja.errors import HttpError
from srl.game_display import (
    apply_reorder,
    apply_visibility,
    create_display,
)
from srl.models import Categories, Games, VariableValues

from api.permissions import authed
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.game_display import (
    GameDisplayResponse,
    ReorderRequest,
    VisibilityRequest,
)

router = Router()


@router.get(
    "/admin/games/{game_id}/display",
    response={
        200: GameDisplayResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Get Game Display",
    description=(
        "Superuser Only: returns the current categories, levels, and variable groups for a game, "
        "each with their order and appear_on_main values."
    ),
    auth=authed("games.display.admin"),
)
def get_game_display(
    request: HttpRequest,
    game_id: str,
) -> Status:
    game = get_object_or_404(Games, id=game_id)
    bundle = create_display(game)
    return Status(200, bundle)


@router.post(
    "/admin/games/{game_id}/display/reorder",
    response={
        204: None,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Reorder Categories, Levels, or Variable Values",
    description=(
        "Superuser Only: assigns indexed `order` values to the IDs provided within a given scope."
    ),
    auth=authed("games.display.admin"),
)
def post_reorder(
    request: HttpRequest,
    game_id: str,
    body: ReorderRequest,
) -> HttpResponse:
    game = get_object_or_404(Games, id=game_id)

    try:
        apply_reorder(
            game=game,
            scope=body.scope.value,
            ordered_ids=body.ordered_ids,
            var_id=body.var_id,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))

    return HttpResponse(status=204)


@router.post(
    "/admin/games/{game_id}/display/visibility",
    response={
        204: None,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Toggle Main Page Visibility For Category Or Variable Value",
    description=(
        "Superuser Only: sets `appear_on_main` on a single category or variable value. "
    ),
    auth=authed("games.display.admin"),
)
def post_visibility(
    request: HttpRequest,
    game_id: str,
    body: VisibilityRequest,
) -> HttpResponse:
    game = get_object_or_404(Games, id=game_id)

    try:
        apply_visibility(
            game=game,
            target_type=body.target_type.value,
            target_id=body.target_id,
            value=body.value,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))
    except (Categories.DoesNotExist, VariableValues.DoesNotExist):
        raise HttpError(404, "Target not found")

    return HttpResponse(status=204)
