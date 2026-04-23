from typing import Annotated

from django.db.models import Count, Q, QuerySet, Sum
from django.http import HttpRequest
from ninja import Query, Router, Status
from ninja.responses import codes_4xx
from srl.models import CountryCodes, Players, Runs

from api.permissions import authed, public_read
from api.v1.routers.utils.embeds import parse_embeds
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.players import (
    AwardSchema,
    CountrySchema,
    ModeratedGameEmbedSchema,
    PlayerCreateSchema,
    PlayerCustomizationsEmbed,
    PlayerInfoEmbed,
    PlayerModerationEmbed,
    PlayerResponse,
    PlayerRunsEmbed,
    PlayerSearchResultSchema,
    PlayerSocialsEmbed,
    PlayerStatsEmbed,
    PlayerUpdateSchema,
    extract_gradients,
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

    embeds: dict = {"player": {}, "stats": {}, "runs": {}}

    if "country" in embed_fields:
        if player.countrycode:
            embeds["player"]["country"] = CountrySchema(
                id=player.countrycode.id,
                name=player.countrycode.name,
                flag=(player.countrycode.flag.url if player.countrycode.flag else None),
            )

    if "awards" in embed_fields:
        awards = player.awards.all().order_by("name")
        embeds["stats"]["awards"] = [
            AwardSchema(
                name=award.name,
                description=award.description,
                image=award.image.url if award.image else None,
            )
            for award in awards
        ]

    if "runs" in embed_fields:
        runs = _fetch_player_runs(player, include_obsolete=False, limit=25)
        embeds["runs"]["recent"] = [_serialize_run(run) for run in runs]

    if "profile" in embed_fields:
        runs = _fetch_player_runs(player, include_obsolete=False)
        embeds["runs"]["fg"] = [
            _serialize_run(run) for run in runs if run.runtype == "main"
        ]
        embeds["runs"]["il"] = [
            _serialize_run(run) for run in runs if run.runtype == "il"
        ]

    if "profile-obsolete" in embed_fields:
        runs = _fetch_player_runs(player, include_obsolete=True)
        embeds["runs"]["fg"] = [
            _serialize_run(run) for run in runs if run.runtype == "main"
        ]
        embeds["runs"]["il"] = [
            _serialize_run(run) for run in runs if run.runtype == "il"
        ]

    if "stats" in embed_fields:
        agg = Runs.objects.filter(
            run_players__player=player,
            vid_status="verified",
        ).aggregate(
            total_runs=Count("id"),
            fg_points=Sum("points", filter=Q(runtype="main", obsolete=False)),
            il_points=Sum("points", filter=Q(runtype="il", obsolete=False)),
        )
        embeds["stats"]["total_runs"] = agg["total_runs"]
        embeds["stats"]["fg_points"] = agg["fg_points"] or 0
        embeds["stats"]["il_points"] = agg["il_points"] or 0

    return embeds


@router.get(
    "/search",
    response={200: list[PlayerSearchResultSchema], codes_4xx: ErrorResponse},
    summary="Search Players",
    description="""\
Search for players by name or nickname. Returns lightweight results
suitable for autocomplete/typeahead.

Supported Parameters:
- `q` (str): Search query (min 2 characters). Matches against name and nickname.
- `limit` (int): Max results to return (default 10, max 25).

Examples:
- `/players/search?q=hawk` - Search for players matching "hawk".
- `/players/search?q=spe&limit=5` - Search with a custom limit.
""",
    auth=public_read(),
)
def search_players(
    request: HttpRequest,
    q: Annotated[
        str,
        Query(min_length=2, max_length=30, description="Search query"),
    ],
    limit: Annotated[
        int,
        Query(default=10, ge=1, le=25, description="Max results"),
    ] = 10,
) -> Status:
    players = (
        Players.objects.filter(Q(name__icontains=q) | Q(nickname__icontains=q))
        .select_related("countrycode", "user")
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
                gradients=extract_gradients(p),
            )
            for p in players
        ],
    )


@router.get(
    "/{id}",
    response={200: PlayerResponse, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get Player by ID",
    description="""\
Retrieve a single player by their ID, including optional embedding.

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
""",
    auth=public_read(),
)
def get_player(
    request: HttpRequest,
    id: str,
    embed: Annotated[str | None, Query(description="Comma-separated embeds")] = None,
) -> Status:
    if len(id) > 30:
        return Status(
            400,
            ErrorResponse(
                error="ID must be 30 characters or less",
                details=None,
            ),
        )

    embed_fields = parse_embeds(embed, "players")

    try:
        player = (
            Players.objects.filter(
                Q(id__iexact=id) | Q(name__iexact=id) | Q(nickname__iexact=id)
            )
            .select_related("countrycode", "user")
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

        user = player.user
        gradients = extract_gradients(player)

        player_info = PlayerInfoEmbed(
            name=player.name,
            nickname=player.nickname,
            pronouns=player.pronouns,
            pfp=player.pfp,
            ex_stream=player.ex_stream,
        )

        socials = PlayerSocialsEmbed(
            twitch=player.twitch,
            youtube=player.youtube,
            twitter=player.twitter,
            bluesky=player.bluesky,
            discord=player.discord,
            therun_gg=player.user.therun_gg if player.user else None,
        )

        customizations = PlayerCustomizationsEmbed(
            gradient_1=gradients["gradient_1"] if gradients else None,
            gradient_2=gradients["gradient_2"] if gradients else None,
            gradient_3=gradients["gradient_3"] if gradients else None,
            tagline=user.short_bio if user else None,
            profile_bg=(user.profile_bg.url if user and user.profile_bg else None),
        )

        stats_embed = PlayerStatsEmbed()
        runs_embed = PlayerRunsEmbed()

        mod_games = list(player.moderated_games.all())  # type: ignore
        moderation = PlayerModerationEmbed(
            moderated_games=(
                [
                    ModeratedGameEmbedSchema(id=g.id, name=g.name, slug=g.slug)
                    for g in mod_games
                ]
                if mod_games
                else None
            ),
        )

        if embed_fields:
            embed_data = apply_player_embeds(player, embed_fields)
            if embed_data.get("player"):
                for field, value in embed_data["player"].items():
                    setattr(player_info, field, value)
            if embed_data.get("stats"):
                for field, value in embed_data["stats"].items():
                    setattr(stats_embed, field, value)
            if embed_data.get("runs"):
                for field, value in embed_data["runs"].items():
                    setattr(runs_embed, field, value)

        return Status(
            200,
            PlayerResponse(
                id=player.id,
                url=player.url,
                joined=player.joined,
                player=player_info,
                socials=socials,
                customizations=customizations,
                stats=stats_embed,
                runs=runs_embed,
                moderation=moderation,
            ),
        )

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
    response={201: PlayerResponse, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Create Player",
    description="""\
Creates a brand new player.

REQUIRES MODERATOR ACCESS OR HIGHER.

Request Body:
- `id` (str | None): The player ID; if one is not given, it will auto-generate.
- `url` (str): Speedrun.com profile URL.
- `player` (object): Core player info (name, nickname, pronouns, country_id, pfp, ex_stream).
- `socials` (object): Social links (twitch, youtube, twitter, bluesky, discord).
""",
    auth=authed("users.admin"),
)
def create_player(
    request: HttpRequest,
    player_data: PlayerCreateSchema,
) -> Status:
    try:
        country = None
        if player_data.player.country_id:
            country = CountryCodes.objects.filter(
                id=player_data.player.country_id,
            ).first()
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

        player_fields = player_data.player.model_dump(exclude={"country_id"})
        social_fields = player_data.socials.model_dump()

        player = Players.objects.create(
            id=player_id,
            url=player_data.url,
            countrycode=country,
            **player_fields,
            **social_fields,
        )

        country_embed = None
        if country:
            country_embed = CountrySchema(
                id=country.id,
                name=country.name,
                flag=country.flag.url if country.flag else None,
            )

        return Status(
            201,
            PlayerResponse(
                id=player.id,
                url=player.url,
                joined=player.joined,
                player=PlayerInfoEmbed(
                    name=player.name,
                    nickname=player.nickname,
                    pronouns=player.pronouns,
                    country=country_embed,
                    pfp=player.pfp,
                    ex_stream=player.ex_stream,
                ),
                socials=PlayerSocialsEmbed(
                    twitch=player.twitch,
                    youtube=player.youtube,
                    twitter=player.twitter,
                    bluesky=player.bluesky,
                    discord=player.discord,
                ),
                customizations=PlayerCustomizationsEmbed(),
                stats=PlayerStatsEmbed(),
                runs=PlayerRunsEmbed(),
                moderation=PlayerModerationEmbed(),
            ),
        )

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
    response={200: PlayerResponse, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Update Player",
    description="""\
Updates the player based on their unique ID.

REQUIRES MODERATOR ACCESS OR HIGHER.

Supported Parameters:
- `id` (str): Unique ID of the player being updated.

Request Body:
- `url` (str | None): Updated Speedrun.com profile URL.
- `player` (object | None): Core player info to update (name, nickname, pronouns,
    country_id, pfp, ex_stream).
- `socials` (object | None): Social links to update (twitch, youtube, twitter, bluesky,
    discord).
""",
    auth=authed("users.admin"),
)
def update_player(
    request: HttpRequest,
    id: str,
    player_data: PlayerUpdateSchema,
) -> Status:
    try:
        player = Players.objects.select_related("user").filter(id__iexact=id).first()
        if not player:
            return Status(
                404,
                ErrorResponse(
                    error="Player does not exist",
                    details=None,
                ),
            )

        if player_data.url is not None:
            player.url = player_data.url

        if player_data.player is not None:
            update_fields = player_data.player.model_dump(exclude_unset=True)

            if "country_id" in update_fields:
                if update_fields["country_id"]:
                    country = CountryCodes.objects.filter(
                        id=update_fields["country_id"],
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
                del update_fields["country_id"]

            for field, value in update_fields.items():
                setattr(player, field, value)

        if player_data.socials is not None:
            social_fields = player_data.socials.model_dump(exclude_unset=True)
            for field, value in social_fields.items():
                setattr(player, field, value)

        player.save()

        user = player.user
        gradients = extract_gradients(player)

        return Status(
            200,
            PlayerResponse(
                id=player.id,
                url=player.url,
                joined=player.joined,
                player=PlayerInfoEmbed(
                    name=player.name,
                    nickname=player.nickname,
                    pronouns=player.pronouns,
                    pfp=player.pfp,
                    ex_stream=player.ex_stream,
                ),
                socials=PlayerSocialsEmbed(
                    twitch=player.twitch,
                    youtube=player.youtube,
                    twitter=player.twitter,
                    bluesky=player.bluesky,
                    discord=player.discord,
                ),
                customizations=PlayerCustomizationsEmbed(
                    gradient_1=gradients["gradient_1"] if gradients else None,
                    gradient_2=gradients["gradient_2"] if gradients else None,
                    gradient_3=gradients["gradient_3"] if gradients else None,
                    tagline=user.short_bio if user else None,
                    profile_bg=(
                        user.profile_bg.url if user and user.profile_bg else None
                    ),
                ),
                stats=PlayerStatsEmbed(),
                runs=PlayerRunsEmbed(),
                moderation=PlayerModerationEmbed(
                    moderated_games=None,
                ),
            ),
        )

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
    description="""\
Deletes the selected player based on its ID.

REQUIRES ADMIN ACCESS.

Supported Parameters:
- `id` (str): Unique ID of the player being deleted.
""",
    auth=authed("users.admin"),
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
