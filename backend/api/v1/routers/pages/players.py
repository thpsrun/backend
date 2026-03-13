from textwrap import dedent
from typing import Annotated, Any

from django.db.models import Q
from django.http import HttpRequest
from ninja import Query, Router
from ninja.responses import codes_4xx
from pydantic import Field
from srl.models import Players

from api.permissions import public_auth
from api.v1.routers.utils.query_utils import query_player_runs
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.players import AwardSchema, CountrySchema, PlayerBaseSchema

router = Router()


@router.get(
    "/player/{user}",
    response={200: dict[str, Any], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get Player Profile",
    description=dedent(
        """
    Gets profile information and run history for a specific player.

    The player can be looked up by their Speedrun.com ID, username, or nickname
    (case-insensitive).

    By default, only current (non-obsolete) runs are returned. Use
    `?embed=obsoletes` to include ALL runs, including those that have been
    superseded by faster times.

    **Supported Embeds:**
    - `obsoletes`: Includes all runs for the player, including obsolete ones.
        When omitted, only current approved runs are returned.

    **Supported Parameters:**
    - `user` (str): The player's SRC ID, name, or nickname.

    **Examples:**
    - `/player/bobby` - Gets Bobby's profile and current runs.
    - `/player/bobby?embed=obsoletes` - Gets Bobby's profile and ALL runs,
        including obsolete ones.

    """
    ),
    auth=public_auth,
)
def get_player_data(
    request: HttpRequest,
    user: str,
    embed: Annotated[
        str | None,
        Query,
        Field(description="Comma-separated embed types: obsoletes"),
    ] = None,
) -> tuple[int, dict[str, Any] | ErrorResponse]:
    player = (
        Players.objects.filter(
            Q(id__iexact=user) | Q(name__iexact=user) | Q(nickname__iexact=user)
        )
        .select_related("countrycode")
        .prefetch_related("awards")
        .first()
    )

    if not player:
        return 404, ErrorResponse(
            error=f"Player '{user}' not found.",
            details={"user": user},
        )

    embed_fields = [e.strip() for e in embed.split(",")] if embed else []
    valid_embed_types = ["obsoletes"]

    if embed_fields:
        invalid_embeds = [f for f in embed_fields if f not in valid_embed_types]
        if invalid_embeds:
            return 400, ErrorResponse(
                error=f"Invalid embed type(s): {', '.join(invalid_embeds)}",
                details={"valid_embed_types": valid_embed_types},
            )

    include_obsoletes = "obsoletes" in embed_fields

    try:
        runs = query_player_runs(player.id, include_obsoletes=include_obsoletes)

        country = (
            CountrySchema(
                id=player.countrycode.id,
                name=player.countrycode.name,
            ).model_dump()
            if player.countrycode
            else None
        )

        awards = [
            AwardSchema(
                name=a.name,
                description=a.description,
                image=a.image,
            ).model_dump()
            for a in player.awards.all()
        ]

        response_dict: dict[str, Any] = {
            "player": PlayerBaseSchema.model_validate(player).model_dump(),
            "country": country,
            "awards": awards,
            "runs": runs,
        }

        return 200, response_dict

    except Exception as e:
        return 500, ErrorResponse(
            error="Server error!",
            details={"exception": str(e)},
        )
