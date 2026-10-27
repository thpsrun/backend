from pydantic import BaseModel, ConfigDict, Field

from srl.srcom.schema.src import SrcLeaderboardRun, SrcRunsTimes


class RunSyncContext(BaseModel):
    """Base model to provide internal run context to leaderboard and run creation functions."""

    model_config = ConfigDict(extra="ignore")

    game_id: str
    category_id: str
    category_name: str
    category_type: str
    level_id: str | None = None
    level_name: str | None = None
    max_points: int
    default_time_type: str
    variable_value_map: dict[str, str]
    lrt_fix: bool = False
    runs_data: SrcLeaderboardRun
    wr_times: SrcRunsTimes | None = None


class RunSyncTimesContext(BaseModel):
    """Additional context that converts differnet time definitions."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    time_secs: float = Field(..., alias="realtime_t")
    timenl_secs: float = Field(..., alias="realtime_noloads_t")
    timeigt_secs: float = Field(..., alias="ingame_t")
