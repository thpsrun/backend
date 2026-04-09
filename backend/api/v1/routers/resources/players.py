from textwrap import dedent
from typing import Annotated

from django.db.models import Count, Q, QuerySet, Sum
from django.http import HttpRequest
from ninja import Query, Router, Status
from ninja.responses import codes_4xx
from pydantic import Field
from srl.models import CountryCodes, Players, Runs

from api.permissions import admin_auth, moderator_auth, public_auth
from api.v1.docs.players import PLAYERS_DELETE, PLAYERS_GET, PLAYERS_POST, PLAYERS_PUT
from api.v1.schemas.base import ErrorResponse, validate_embeds
from api.v1.schemas.players import (
    ModeratedGameEmbedSchema,
    PlayerCreateSchema,
    PlayerSchema,
    PlayerSearchResultSchema,
    PlayerUpdateSchema,
)
from api.v1.schemas.runs import compute_run_subcategory
from api.v1.utils import get_or_generate_id

router = Router()


def apply_player_embeds(
    player: Players,
    embed_fields: list[str],
) -> dict:
    def _serialize_run(
        run: Runs,
    ) -> dict:
        return {
            "id": run.id,
            "game": (
                {
                    "name": run.game.name,
                    "slug": run.game.slug,
                }
                if run.game
                else None
            ),
            "category": (
                {
                    "name": run.category.name,
                    "slug": run.category.slug,
                }
                if run.category
                else None
            ),
            "subcategory": compute_run_subcategory(run),
            "level": (
                {
                    "name": run.level.name,
                    "slug": run.level.slug,
                }
                if run.level
                else None
            ),
            "place": run.place,
            "points": run.points,
            "time": run.time if run.p_time == "0" else run.p_time,
            "date": run.v_date.isoformat() if run.v_date else None,
            "url": run.url,
            "video": run.video,
            "arch_video": run.arch_video,
            "obsolete": run.obsolete,
            "value_slugs": [rvv.value.slug for rvv in run.runvariablevalues_set.all()],
        }

    def _fetch_player_runs(
        player: Players,
        *,
        include_obsolete: bool,
        limit: int | None = None,
    ) -> QuerySet[Runs]:
        qs = (
            Runs.objects.filter(run_players__player=player, vid_status="verified")
            .select_related("game", "category", "level")
            .prefetch_related("runvariablevalues_set__value")
            .order_by("-v_date")
        )
        if not include_obsolete:
            qs = qs.filter(obsolete=False)
        return qs[:limit] if limit else qs

    embeds = {}

    if "country" in embed_fields:
        if player.countrycode:
            embeds["country"] = {
                "id": player.countrycode.id,
                "name": player.countrycode.name,
            }

    if "awards" in embed_fields:
        awards = player.awards.all().order_by("name")
        embeds["awards"] = [
            {
                "name": award.name,
                "description": award.description,
                "image": award.image.url if award.image else None,
            }
            for award in awards
        ]

    if "runs" in embed_fields:
        runs = _fetch_player_runs(player, include_obsolete=False, limit=25)
        embeds["runs"] = [_serialize_run(run) for run in runs]

    if "profile" in embed_fields:
        runs = _fetch_player_runs(player, include_obsolete=False)
        embeds["fg"] = [_serialize_run(run) for run in runs if run.runtype == "main"]
        embeds["il"] = [_serialize_run(run) for run in runs if run.runtype == "il"]

    if "profile-obsolete" in embed_fields:
        runs = _fetch_player_runs(player, include_obsolete=True)
        embeds["fg"] = [_serialize_run(run) for run in runs if run.runtype == "main"]
        embeds["il"] = [_serialize_run(run) for run in runs if run.runtype == "il"]

    if "stats" in embed_fields:
        agg = Runs.objects.filter(
            run_players__player=player,
            vid_status="verified",
        ).aggregate(
            total_runs=Count("id"),
            fg_points=Sum("points", filter=Q(runtype="main", obsolete=False)),
            il_points=Sum("points", filter=Q(runtype="il", obsolete=False)),
        )
        embeds["stats"] = {
            "total_runs": agg["total_runs"],
            "fg_points": agg["fg_points"] or 0,
            "il_points": agg["il_points"] or 0,
        }

    return embeds


@router.get(
    "/search",
    response={200: list[PlayerSearchResultSchema], codes_4xx: ErrorResponse},
    summary="Search Players",
    description=dedent(
        """Search for players by name or nickname. Returns lightweight results
    suitable for autocomplete/typeahead.

    Supported Parameters:
    - `q` (str): Search query (min 2 characters). Matches against name and nickname.
    - `limit` (int): Max results to return (default 10, max 25).

    Examples:
    - `/players/search?q=hawk` - Search for players matching "hawk".
    - `/players/search?q=spe&limit=5` - Search with a custom limit.
    """
    ),
    auth=public_auth,
)
def search_players(
    request: HttpRequest,
    q: Annotated[
        str,
        Query,
        Field(min_length=2, max_length=30, description="Search query"),
    ],
    limit: Annotated[
        int,
        Query,
        Field(default=10, ge=1, le=25, description="Max results"),
    ] = 10,
) -> Status:
    players = (
        Players.objects.filter(Q(name__icontains=q) | Q(nickname__icontains=q))
        .select_related("countrycode")
        .order_by("name")[:limit]
    )
    return Status(
        200,
        [
            PlayerSearchResultSchema(
                id=p.id,
                name=p.name,
                nickname=p.nickname,
                country_id=p.countrycode.id if p.countrycode else None,
            )
            for p in players
        ],
    )


@router.get(
    "/{id}",
    response={200: PlayerSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get Player by ID",
    description=dedent(
        """Retrieve a single player by their ID, including optional embedding.

    Exclusively for this endpoint, you can also GET a player by their username or their nickname.

    Supported Parameters:
    - `id` (str): Unique ID of the player being queried.
    - `embed` (list | None): Comma-separated list of resources to embed.

    Supported Embeds:
    - `country`: Includes the metadata of the country associated with the player, if any.
    - `stats`: Includes total verified runs, full-game points, and IL points.
    - `awards`: Include the metadata of the awards the player has collected, if any.
    - `runs`: Last 25 verified non-obsolete runs as a flat list.
    - `profile`: All verified non-obsolete runs split into `fg` and `il` keys.
    - `profile-obsolete`: All verified runs (including obsolete) split into `fg` and `il` keys.

    Examples:
    - `/players/v8lponvj` - Get player by ID.
    - `/players/v8lponvj?embed=country` - Get player with country info.
    - `/players/v8lponvj?embed=country,stats,awards,profile` - Get player with stats and profile.
    """
    ),
    auth=public_auth,
    openapi_extra=PLAYERS_GET,
)
def get_player(
    request: HttpRequest,
    id: str,
    embed: Annotated[
        str | None, Query, Field(description="Comma-separated embeds")
    ] = None,
) -> Status:
    if len(id) > 30:
        return Status(
            400,
            ErrorResponse(
                error="ID must be 30 characters or less",
                details=None,
            ),
        )

    embed_fields = []
    if embed:
        embed_fields = [field.strip() for field in embed.split(",") if field.strip()]
        invalid_embeds = validate_embeds("players", embed_fields)
        if invalid_embeds:
            return Status(
                400,
                ErrorResponse(
                    error=f"Invalid embed(s): {', '.join(invalid_embeds)}",
                    details={
                        "valid_embeds": [
                            "country",
                            "stats",
                            "awards",
                            "runs",
                            "profile",
                            "profile-obsolete",
                        ]
                    },
                ),
            )

    try:
        player = (
            Players.objects.filter(
                Q(id__iexact=id) | Q(name__iexact=id) | Q(nickname__iexact=id)
            )
            .select_related("countrycode")
            .prefetch_related("moderated_games")
            .first()
        )
        if not player:
            return Status(
                404,
                ErrorResponse(
                    error="Player ID does not exist",
                    details=None,
                ),
            )

        player_data = PlayerSchema.model_validate(player)

        mod_games = list(player.moderated_games.all())  # type: ignore
        player_data.moderated_games = (
            [
                ModeratedGameEmbedSchema(id=g.id, name=g.name, slug=g.slug)
                for g in mod_games
            ]
            if mod_games
            else None
        )

        if embed_fields:
            embed_data = apply_player_embeds(player, embed_fields)
            for field, data in embed_data.items():
                setattr(player_data, field, data)

        return Status(200, player_data)

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve player",
                details={"exception": str(e)},
            ),
        )


@router.post(
    "/",
    response={201: PlayerSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Create Player",
    description=dedent(
        """Creates a brand new player.

    REQUIRES MODERATOR ACCESS OR HIGHER.

    Request Body:
    - `id` (str | None): The player ID; if one is not given, it will auto-generate.
    - `name` (str): Player's name on Speedrun.com.
    - `nickname` (str | None): Custom nickname override (displayed instead of name).
    - `url` (str): Speedrun.com profile URL.
    - `pfp` (str | None): Profile picture URL.
    - `pronouns` (str | None): Player's pronouns.
    - `twitch` (str | None): Twitch channel URL.
    - `youtube` (str | None): YouTube channel URL.
    - `twitter` (str | None): Twitter profile URL.
    - `bluesky` (str | None): Bluesky profile URL.
    - `ex_stream` (bool): Whether the player is marked to be excluded from streams.
    """
    ),
    auth=moderator_auth,
    openapi_extra=PLAYERS_POST,
)
def create_player(
    request: HttpRequest,
    player_data: PlayerCreateSchema,
) -> Status:
    try:
        country = None
        if player_data.country_id:
            country = CountryCodes.objects.filter(id=player_data.country_id).first()
            if not country:
                return Status(
                    400,
                    ErrorResponse(
                        error="Country code does not exist",
                        details=None,
                    ),
                )

        try:
            player_id = get_or_generate_id(
                player_data.id,
                lambda id: Players.objects.filter(id=id).exists(),
            )
        except ValueError as e:
            return Status(
                400,
                ErrorResponse(
                    error="ID Already Exists",
                    details={"exception": str(e)},
                ),
            )

        create_data = player_data.model_dump(exclude={"country_id"})
        create_data["id"] = player_id
        player = Players.objects.create(countrycode=country, **create_data)

        return Status(201, PlayerSchema.model_validate(player))

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to create player",
                details={"exception": str(e)},
            ),
        )


@router.put(
    "/{id}",
    response={200: PlayerSchema, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Update Player",
    description=dedent(
        """Updates the player based on their unique ID.

    REQUIRES MODERATOR ACCESS OR HIGHER.

    Supported Parameters:
    - `id` (str): Unique ID of the player being updated.

    Request Body:
    - name (str | None): Player's name on Speedrun.com.
    - nickname (str | None): Custom nickname override (displayed instead of name).
    - url (str | None): Speedrun.com profile URL.
    - pfp (str | None): Profile picture URL.
    - pronouns (str | None): Player's pronouns.
    - twitch (str | None): Twitch channel URL.
    - youtube (str | None): YouTube channel URL.
    - twitter (str | None): Twitter profile URL.
    - bluesky (str | None): Bluesky profile URL.
    - ex_stream (bool | None): Whether the player is marked to be excluded from streams.
    """
    ),
    auth=moderator_auth,
    openapi_extra=PLAYERS_PUT,
)
def update_player(
    request: HttpRequest,
    id: str,
    player_data: PlayerUpdateSchema,
) -> Status:
    try:
        player = Players.objects.filter(id__iexact=id).first()
        if not player:
            return Status(
                404,
                ErrorResponse(
                    error="Player does not exist",
                    details=None,
                ),
            )

        update_data = player_data.model_dump(exclude_unset=True)

        if "country_id" in update_data:
            if update_data["country_id"]:
                country = CountryCodes.objects.filter(
                    id=update_data["country_id"]
                ).first()
                if not country:
                    return Status(
                        400,
                        ErrorResponse(
                            error="Country code does not exist",
                            details=None,
                        ),
                    )
                player.countrycode = country
            else:
                player.countrycode = None
            del update_data["country_id"]

        for field, value in update_data.items():
            setattr(player, field, value)

        player.save()
        return Status(200, PlayerSchema.model_validate(player))

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to update player",
                details={"exception": str(e)},
            ),
        )


@router.delete(
    "/{id}",
    response={200: dict[str, str], codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Delete Player",
    description=dedent(
        """Deletes the selected player based on its ID.

    REQUIRES ADMIN ACCESS.

    Supported Parameters:
    - `id` (str): Unique ID of the player being deleted.
    """
    ),
    auth=admin_auth,
    openapi_extra=PLAYERS_DELETE,
)
def delete_player(
    request: HttpRequest,
    id: str,
) -> Status:
    try:
        player = Players.objects.filter(id__iexact=id).first()
        if not player:
            return Status(
                404,
                ErrorResponse(
                    error="Player does not exist",
                    details=None,
                ),
            )

        name = player.nickname if player.nickname else player.name
        player.delete()
        return Status(200, {"message": f"Player '{name}' deleted successfully"})

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to delete player",
                details={"exception": str(e)},
            ),
        )
