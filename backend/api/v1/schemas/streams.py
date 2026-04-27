from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field, model_validator

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

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
        json_schema_extra={
            "example": {
                "player": {"id": "v8lponvj", "name": "ThePackle"},
                "game": {"id": "n2680o1p", "name": "Tony Hawk's Pro Skater 4"},
                "title": "THPS4 Any% attempts",
                "offline_ct": 0,
                "stream_time": "2026-04-26T22:30:00Z",
            },
        },
    )

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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "player_id": "v8lponvj",
                "game_id": "n2680o1p",
                "title": "THPS4 Any% practice",
                "offline_ct": 0,
                "stream_time": "2026-04-26T22:30:00Z",
            },
        },
    )

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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "game_id": "n2680o1p",
                "title": "THPS4 100% attempts",
                "offline_ct": 5,
                "stream_time": None,
            },
        },
    )

    game_id: str | None = None
    title: str | None = None
    offline_ct: int | None = Field(
        default=None, ge=0, description="Minutes since last seen online"
    )
    stream_time: datetime | None = None
