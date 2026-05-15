from datetime import datetime
from typing import Annotated

from django.http import HttpRequest
from ninja import Query, Router, Status
from srl.models import Games, NowStreaming, Players

from api.permissions import authed, public_read
from api.v1.routers.utils.resolvers import game_from_body, game_from_stream_path
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.streams import StreamCreateSchema, StreamSchema, StreamUpdateSchema

router = Router()


@router.get(
    "/live",
    response={
        200: list[StreamSchema],
        500: ErrorResponse,
    },
    summary="Get Live Streamers",
    description="""\
Get list of currently live streamers playing speedrun games.

Supported Parameters:
- `game_id`: Filter by specific game being streamed.
- `limit`: Maximum results to return (default 20, max 50).

Examples:
- `/streams/live` - All live streamers.
- `/streams/live?game_id=thps4` - Streamers playing THPS4.
""",
    auth=public_read(),
)
def get_live_streams(
    request: HttpRequest,
    game_id: Annotated[str | None, Query(description="Filter by game")] = None,
    limit: Annotated[int, Query(ge=1, le=50, description="Max results")] = 20,
) -> Status:
    try:
        queryset = NowStreaming.objects.select_related("streamer", "game").order_by(
            "-stream_time",
        )

        if game_id:
            queryset = queryset.filter(game_id=game_id)

        streams = list(queryset[:limit])
        stream_schemas = [StreamSchema.model_validate(s) for s in streams]

        return Status(200, stream_schemas)

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve live streams",
                details={"exception": str(e)},
            ),
        )


@router.get(
    "/{player_id}",
    response={200: StreamSchema, 404: ErrorResponse, 500: ErrorResponse},
    summary="Get Stream by Player",
    description="""\
Retrieve the live stream record for a single player.

Supported Parameters:
- `player_id` (str): Unique ID of the player whose stream is being requested.
""",
    auth=public_read(),
)
def get_stream(
    request: HttpRequest,
    player_id: str,
) -> Status:
    try:
        stream = (
            NowStreaming.objects.select_related("streamer", "game")
            .filter(streamer_id=player_id)
            .first()
        )
        if not stream:
            return Status(
                404,
                ErrorResponse(
                    error="Stream does not exist for this player",
                    details=None,
                ),
            )

        return Status(200, StreamSchema.model_validate(stream))

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to retrieve stream",
                details={"exception": str(e)},
            ),
        )


@router.post(
    "/",
    response={
        201: StreamSchema,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Create Stream",
    description="""\
Creates a new stream record for a player.

Request Body:
- `player_id` (str): Player ID who is streaming.
- `game_id` (str | None): Game ID being played.
- `title` (str): Stream title.
- `offline_ct` (int): Offline counter (minutes since last seen).
- `stream_time` (datetime | None): Stream start time (ISO format).
""",
    auth=authed("games.manage", target_resolver=game_from_body),
)
def create_stream(
    request: HttpRequest,
    stream_data: StreamCreateSchema,
) -> Status:
    """Create a new stream for a player."""
    try:
        player = Players.objects.filter(id=stream_data.player_id).first()
        if not player:
            return Status(
                400,
                ErrorResponse(
                    error="Player does not exist",
                    details=None,
                ),
            )

        existing_stream = NowStreaming.objects.filter(streamer=player).first()
        if existing_stream:
            return Status(
                400,
                ErrorResponse(
                    error="Player already has an active stream. Use PUT to update it.",
                    details=None,
                ),
            )

        game = None
        if stream_data.game_id:
            game = Games.objects.filter(id=stream_data.game_id).first()
            if not game:
                return Status(
                    400,
                    ErrorResponse(
                        error="Game does not exist",
                        details=None,
                    ),
                )

        stream = NowStreaming.objects.create(
            streamer=player,
            game=game,
            title=stream_data.title,
            offline_ct=stream_data.offline_ct,
            stream_time=stream_data.stream_time or datetime.now(),
        )

        return Status(201, StreamSchema.model_validate(stream))

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to create stream",
                details={"exception": str(e)},
            ),
        )


@router.put(
    "/{player_id}",
    response={
        200: StreamSchema,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Update Stream",
    description="""\
Updates the stream for a specific player.

Supported Parameters:
- `player_id` (str): Unique ID of the player whose stream is being updated.

Request Body:
- `game_id` (str | None): Updated game ID being played.
- `title` (str | None): Updated stream title.
- `offline_ct` (int | None): Updated offline counter (minutes since last seen).
- `stream_time` (datetime | None): Updated stream start time (ISO format).
""",
    auth=authed("games.manage", target_resolver=game_from_stream_path),
)
def update_stream(
    request: HttpRequest,
    player_id: str,
    stream_data: StreamUpdateSchema,
) -> Status:
    try:
        player = Players.objects.filter(id=player_id).first()
        if not player:
            return Status(
                404,
                ErrorResponse(
                    error="Player does not exist",
                    details=None,
                ),
            )

        stream = NowStreaming.objects.filter(streamer=player).first()
        if not stream:
            return Status(
                404,
                ErrorResponse(
                    error="Stream does not exist for this player",
                    details=None,
                ),
            )

        update_data = stream_data.model_dump(exclude_unset=True)

        if "game_id" in update_data:
            if update_data["game_id"]:
                game = Games.objects.filter(id=update_data["game_id"]).first()
                if not game:
                    return Status(
                        400,
                        ErrorResponse(
                            error="Game does not exist",
                            details=None,
                        ),
                    )
                stream.game = game
            else:
                stream.game = None
            del update_data["game_id"]

        for field, value in update_data.items():
            setattr(stream, field, value)

        stream.save()

        return Status(200, StreamSchema.model_validate(stream))

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to update stream",
                details={"exception": str(e)},
            ),
        )


@router.delete(
    "/{player_id}",
    response={
        200: dict[str, str],
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Delete Stream",
    description="""\
Deletes the stream for a specific player.

Supported Parameters:
- `player_id` (str): Unique ID of the player whose stream is being deleted.
""",
    auth=authed("users.admin"),
)
def delete_stream(
    request: HttpRequest,
    player_id: str,
) -> Status:
    try:
        player = Players.objects.filter(id=player_id).first()
        if not player:
            return Status(
                404,
                ErrorResponse(
                    error="Player does not exist",
                    details=None,
                ),
            )

        stream = NowStreaming.objects.filter(streamer=player).first()
        if not stream:
            return Status(
                404,
                ErrorResponse(
                    error="Stream does not exist for this player",
                    details=None,
                ),
            )

        player_name = player.nickname if player.nickname else player.name
        stream.delete()

        return Status(
            200, {"message": f"Stream for player '{player_name}' deleted successfully"}
        )

    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Failed to delete stream",
                details={"exception": str(e)},
            ),
        )
