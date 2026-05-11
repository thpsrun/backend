from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router, Status
from ninja.errors import HttpError
from ninja.responses import codes_4xx
from srl.game_display import (
    StaleStateError,
    apply_reorder,
    apply_visibility,
    create_display,
    parse_page_loaded_at,
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
    response={200: GameDisplayResponse, codes_4xx: ErrorResponse},
    summary="Get Game Display",
    description=(
        "Superuser-only: returns the current categories, levels, and variable groups for a game,"
        "each with their order and appear_on_main values. The page_loaded_at field must be echoed "
        "as the X-Page-Loaded-At header on subsequent reorder or visibility writes."
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
    response={204: None, codes_4xx: ErrorResponse},
    summary="Reorder Categories, Levels, or Variable Values",
    description=(
        "Superuser-only: assigns indexed `order` values to the IDs provided within a given scope. "
        "Requiress `X-Page-Loaded-At` header to determine what the most recent GET request is."
    ),
    auth=authed("games.display.admin"),
)
def post_reorder(
    request: HttpRequest,
    game_id: str,
    body: ReorderRequest,
) -> HttpResponse:
    game = get_object_or_404(Games, id=game_id)
    page_loaded_at = parse_page_loaded_at(
        request.headers.get("X-Page-Loaded-At"),
    )

    try:
        new_ts = apply_reorder(
            game=game,
            scope=body.scope.value,
            ordered_ids=body.ordered_ids,
            var_id=body.var_id,
            page_loaded_at=page_loaded_at,
        )
    except StaleStateError as exc:
        raise HttpError(409, str(exc))
    except ValueError as exc:
        raise HttpError(400, str(exc))

    response = HttpResponse(status=204)
    response["X-New-Page-Loaded-At"] = new_ts.isoformat()
    return response


@router.post(
    "/admin/games/{game_id}/display/visibility",
    response={204: None, codes_4xx: ErrorResponse},
    summary="Toggle Main Page Visibility For Category Or Variable Value",
    description=(
        "Superuser-only: sets `appear_on_main` on a single category or variable value. "
    ),
    auth=authed("games.display.admin"),
)
def post_visibility(
    request: HttpRequest,
    game_id: str,
    body: VisibilityRequest,
) -> HttpResponse:
    game = get_object_or_404(Games, id=game_id)
    page_loaded_at = parse_page_loaded_at(
        request.headers.get("X-Page-Loaded-At"),
    )

    try:
        new_ts = apply_visibility(
            game=game,
            target_type=body.target_type.value,
            target_id=body.target_id,
            value=body.value,
            page_loaded_at=page_loaded_at,
        )
    except StaleStateError as exc:
        raise HttpError(409, str(exc))
    except ValueError as exc:
        raise HttpError(400, str(exc))
    except (Categories.DoesNotExist, VariableValues.DoesNotExist):
        raise HttpError(404, "Target not found")

    response = HttpResponse(status=204)
    response["X-New-Page-Loaded-At"] = new_ts.isoformat()
    return response
