from datetime import datetime

from ninja import Schema


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
    game: str
    category: str
    subcategory: str
    level: str | None = None
    entries: list[WRHistoryEntrySchema]
