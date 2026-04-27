from datetime import datetime

from ninja import Schema
from pydantic import ConfigDict


class WRHistoryPlayerSchema(Schema):
    name: str
    nickname: str | None = None


class WRHistoryEntrySchema(Schema):
    run_id: str
    players: list[WRHistoryPlayerSchema]
    history_time: str
    history_time_secs: float
    delta: float | None = None
    video: str | None = None
    arch_video: str | None = None
    start_date: datetime
    end_date: datetime | None = None


class WRHistoryResponseSchema(Schema):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "game": "Tony Hawk's Pro Skater 4",
                "category": "Any%",
                "subcategory": "Beginner",
                "level": None,
                "entries": [
                    {
                        "run_id": "y8dwozoj",
                        "players": [{"name": "ThePackle", "nickname": None}],
                        "history_time": "1m 23s",
                        "history_time_secs": 83.5,
                        "delta": -2.1,
                        "video": "https://www.youtube.com/watch?v=abcdefg",
                        "arch_video": None,
                        "start_date": "2018-05-12T00:00:00Z",
                        "end_date": "2019-04-03T00:00:00Z",
                    },
                ],
            },
        },
    )

    game: str
    category: str
    subcategory: str
    level: str | None = None
    entries: list[WRHistoryEntrySchema]
