from datetime import datetime

from ninja import Schema


class WRHistoryPlayerSchema(Schema):
    """Schema to define player information within the WR History.

    Attributes:
        name (str): The name of the player.
        nickname (str): Optional name of the player that is displayed insteado of the name.
    """

    name: str
    nickname: str | None = None


class WRHistoryEntrySchema(Schema):
    """Schema for a single entry in the THPS4 oldest-runs embed.

    Attributes:
        run_id (str): The ID of the run being returned.
        players(list[WRHistoryPlayerSchema]): List of the players + their names returned.
        history_time (str): Stringified version of the time.
        history_time_secs (float): Float version of the time in seconds.
        delta (float | None): Delta, in seconds, between the last run and current.
        video (str | None): Approved video of the run.
        arch_video (str | None): Archived video of the run.
        start_date (datetime): Start time of the run being the world record.
        end_date (datetime | None): End time of the run being the world record.
    """

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
    """Schema for an entire game's history.

    Attributes:
        game (str): Game name with the history in question.
        category (str): Category name.
        subcategory (str): Computed subcategory of the run.
        level (str | None): Name of the level in IL speedruns.
        entries (list[WRHistoryEntrySchema]): List of all of the approved world records for query.
    """

    game: str
    category: str
    subcategory: str
    level: str | None = None
    entries: list[WRHistoryEntrySchema]
