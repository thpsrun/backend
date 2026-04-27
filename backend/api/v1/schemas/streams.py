from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from api.v1.schemas.base import BaseEmbedSchema


class StreamSchema(BaseEmbedSchema):
    """Base schema for `Streams` data without embeds.

    Attributes:
        player (dict): Player information from the Players model.
        game (dict | None): Game being played.
        title (str): Stream title.
        offline_ct (int): Minutes since last seen online.
        stream_time (datetime | None): When the stream started.
    """

    player: dict
    game: dict | None = None
    title: str = Field(..., max_length=100)
    offline_ct: int = Field(..., ge=0, description="Minutes since last seen online")
    stream_time: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def transform_nowstreaming_model(
        cls,
        data: Any,
    ) -> Any:
        if hasattr(data, "streamer"):
            streamer = data.streamer
            game = data.game
            return {
                "player": {
                    "id": streamer.id,
                    "name": streamer.nickname if streamer.nickname else streamer.name,
                },
                "game": ({"id": game.id, "name": game.name} if game else None),
                "title": data.title,
                "offline_ct": data.offline_ct,
                "stream_time": data.stream_time,
            }
        return data


class StreamCreateSchema(BaseEmbedSchema):
    """Schema for creating streams.

    Attributes:
        player_id (str): Player ID who is streaming.
        game_id (str | None): Game ID being played.
        title (str): Stream title.
        offline_ct (int): Offline counter (minutes since last seen).
        stream_time (datetime | None): Stream start time.
    """

    player_id: str
    game_id: str | None = None
    title: str
    offline_ct: int = Field(
        default=0, ge=0, description="Minutes since last seen online"
    )
    stream_time: datetime | None = None


class StreamUpdateSchema(BaseEmbedSchema):
    """Schema for updating streams.

    Attributes:
        game_id (str | None): Updated game ID being played.
        title (str | None): Updated stream title.
        offline_ct (int | None): Updated offline counter (minutes since last seen).
        stream_time (datetime | None): Updated stream start time.
    """

    game_id: str | None = None
    title: str | None = None
    offline_ct: int | None = Field(
        default=None, ge=0, description="Minutes since last seen online"
    )
    stream_time: datetime | None = None
