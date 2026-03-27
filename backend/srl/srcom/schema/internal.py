from pydantic import BaseModel, Field

from srl.srcom.schema.src import SrcLeaderboardRun, SrcPlayersModel


class RunSyncContext(BaseModel):
    """Base model to provide internal run context to leaderboard and run creation functions."""

    game_id: str
    category_id: str
    category_name: str
    category_type: str
    level_id: str | None = None
    level_name: str | None = None
    wr_time_secs: float
    max_points: int
    default_time_type: str
    variable_value_map: dict[str, str]
    download_pfp: bool = False
    lrt_fix: bool = False
    players_data: list[SrcPlayersModel]
    runs_data: SrcLeaderboardRun


class RunSyncTimesContext(BaseModel):
    """Additional context that converts differnet time definitions."""

    time_secs: float = Field(..., alias="realtime_t")
    timenl_secs: float = Field(..., alias="realtime_noloads_t")
    timeigt_secs: float = Field(..., alias="ingame_t")
