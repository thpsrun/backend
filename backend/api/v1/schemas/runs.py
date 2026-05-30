from datetime import datetime
from typing import Any, Literal

from ninja import Schema
from pydantic import ConfigDict, Field, field_validator, model_validator

from api.v1.schemas.base import BaseEmbedSchema, RunTypeType, TimingMethodType


def compute_run_subcategory(
    data: Any,
) -> str | None:
    """Compute subcategory display string from a run's prefetched RunVariableValues.

    Requires the queryset to have:
        .select_related("category", "level", "platform")
        .prefetch_related("runvariablevalues_set__value")
    """
    level = getattr(data, "level", None)
    category = getattr(data, "category", None)
    if level:
        base = getattr(level, "name", "") or ""
    elif category:
        base = getattr(category, "name", "") or ""
    else:
        base = ""

    try:
        rvvs = list(data.runvariablevalues_set.all())
        rvvs_sorted = sorted(rvvs, key=lambda x: x.variable_id)
        values = [rvv.value.name for rvv in rvvs_sorted]
    except Exception:
        values = []

    if values:
        return f"{base} ({', '.join(values)})"
    return base or None


_TIME_FIELDS = (
    "time",
    "time_secs",
    "timenl",
    "timenl_secs",
    "timeigt",
    "timeigt_secs",
    "p_time",
    "p_time_secs",
)


class RunTimesSchema(BaseEmbedSchema):
    """Nested timing data for a run.

    Attributes:
        time (str | None): RTA formatted time string (e.g., "1:23.456").
        time_secs (float | None): RTA time in seconds.
        timenl (str | None): Load-removed formatted time string.
        timenl_secs (float | None): Load-removed time in seconds.
        timeigt (str | None): In-game formatted time string.
        timeigt_secs (float | None): In-game time in seconds.
        p_time (str | None): Primary timing method formatted string.
        p_time_secs (float | None): Primary timing method in seconds.
    """

    time: str | None = Field(
        default=None,
        max_length=25,
        description="RTA formatted (e.g. 1:23.456)",
    )
    time_secs: float | None = Field(
        default=None,
        ge=0,
        description="RTA in seconds",
    )
    timenl: str | None = Field(
        default=None,
        max_length=25,
        description="Load-removed formatted",
    )
    timenl_secs: float | None = Field(
        default=None,
        ge=0,
        description="Load-removed in seconds",
    )
    timeigt: str | None = Field(
        default=None,
        max_length=25,
        description="In-game formatted",
    )
    timeigt_secs: float | None = Field(
        default=None,
        ge=0,
        description="In-game in seconds",
    )
    p_time: str | None = Field(
        default=None,
        max_length=25,
        description="Primary timing method formatted",
    )
    p_time_secs: float | None = Field(
        default=None,
        ge=0,
        description="Primary timing method in seconds",
    )


class RunBaseSchema(BaseEmbedSchema):
    """Base schema for `Runs` data without embeds.

    Attributes:
        id (str): Unique ID (usually based on SRC) of the run.
        runtype (str): Whether this is a full-game or individual level run.
        place (int): Leaderboard position.
        subcategory (str | None): Human-readable subcategory description.
        times (RunTimesSchema): Nested timing data (RTA, LRT, IGT, primary).
        platform (str | None): SRC platform ID; null if no platform recorded.
        emulated (bool): Whether the run was played on an emulator.
        description (str | None): Run notes/description.
        video (str | None): YouTube/Twitch URL.
        arch_video (str | None): Archived video URL.
        date (datetime | None): Submission date.
        v_date (datetime | None): Verification date.
        url (str): Speedrun.com URL.
        resolved_primary_method (TimingMethodType): Effective primary timing method per the
            VariableValue > Variable > Category > Game inheritance chain.
        resolved_required_methods (list[TimingMethodType]): Effective allowed timing methods for
            this run after inheritance.
    """

    id: str = Field(..., max_length=10)
    runtype: RunTypeType = Field(
        ...,
        description="main=full-game, il=individual level",
    )
    place: int = Field(..., ge=0)
    points: int = Field(default=0, ge=0)
    obsolete: bool = Field(
        default=False,
        description="When true, the run is obsolete & points do not count toward a player's total.",
    )
    subcategory: str | None = Field(
        default=None,
        max_length=100,
        description="Human-readable subcategory combo",
    )
    times: RunTimesSchema = Field(description="Nested timing data")
    platform: str | None = Field(
        default=None,
        max_length=10,
        description="SRC platform ID; null if none recorded",
    )
    emulated: bool = Field(
        default=False,
        description="Run was played on an emulator",
    )
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="Run notes/description",
    )
    video: str | None = None
    arch_video: str | None = Field(
        default=None, description="Archived/mirrored video URL"
    )
    date: datetime | None = None
    v_date: datetime | None = Field(default=None, description="Verification date")
    url: str
    resolved_primary_method: TimingMethodType = Field(
        default="rta",
        description=(
            "Effective primary timing method per the "
            "VariableValue > Variable > Category > Game chain."
        ),
    )
    resolved_required_methods: list[TimingMethodType] = Field(
        default_factory=list,
        description="Effective allowed timing methods for this run after inheritance.",
    )

    @field_validator("platform", mode="before")
    @classmethod
    def convert_platform_to_id(
        cls,
        v: Any,
    ) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if hasattr(v, "id"):
            return v.id
        return None

    @model_validator(mode="before")
    @classmethod
    def nest_timing_fields(
        cls,
        data: Any,
    ) -> Any:
        """Restructures timing fields and computes subcategory from variable values."""
        if isinstance(data, dict):
            if "times" not in data:
                data["times"] = {f: data.pop(f, None) for f in _TIME_FIELDS}
            return data
        if hasattr(data, "time"):
            data.times = RunTimesSchema(
                **{f: getattr(data, f, None) for f in _TIME_FIELDS},
            )
        if hasattr(data, "runvariablevalues_set"):
            data.subcategory = compute_run_subcategory(data)
        if hasattr(data, "_primary_timing_method"):
            try:
                data.resolved_primary_method = data._primary_timing_method()
            except Exception:
                data.resolved_primary_method = "rta"
        if hasattr(data, "_resolved_required_methods"):
            try:
                data.resolved_required_methods = data._resolved_required_methods()
            except Exception:
                data.resolved_required_methods = []
        return data


class RunSchema(RunBaseSchema):
    """Complete run schema with optional embedded data.

    Attributes:
        game (str | dict | None): Game ID (default) or full game info with ?embed=game.
        category (str | dict | None): Category ID (default) or full category info with
            ?embed=category.
        level (str | dict | None): Level ID (default) or full level info with ?embed=level.
        players (List[dict]): All players who participated in this run (always included).
        variables (dict[str, str] | list[dict]): Variable ID:Value ID mapping (default) or
            full variable info with ?embed=variables.
        bonus (int): Field that holds the monthly streak bonus, if the run is the world record.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "y8dwozoj",
                "runtype": "main",
                "place": 1,
                "points": 1000,
                "obsolete": False,
                "subcategory": "Any% (PC)",
                "times": {
                    "time": "12:34.567",
                    "time_secs": 754.567,
                    "timenl": None,
                    "timenl_secs": None,
                    "timeigt": None,
                    "timeigt_secs": None,
                    "p_time": "12:34.567",
                    "p_time_secs": 754.567,
                },
                "platform": "8gej2n93",
                "emulated": False,
                "description": "Used the new strat at the dam.",
                "video": "https://youtube.com/watch?v=example",
                "arch_video": "https://archive.thps.run/videos/y8dwozoj.mp4",
                "date": "2025-08-15T00:00:00Z",
                "v_date": "2025-08-15T10:30:00Z",
                "url": "https://speedrun.com/thps4/run/y8dwozoj",
                "resolved_primary_method": "rta",
                "resolved_required_methods": ["rta"],
                "game": "n2680o1p",
                "category": "rklge08d",
                "level": None,
                "players": [{"id": "v8lponvj", "name": "ThePackle", "order": 1}],
                "variables": {"5lygdn8q": "pc"},
            },
        },
    )

    game: str | dict | None = Field(None, description="ID or embedded with ?embed=game")
    category: str | dict | None = Field(
        None, description="ID or embedded with ?embed=category"
    )
    level: str | dict | None = Field(
        None, description="ID or embedded with ?embed=level"
    )
    players: list[dict] = Field(default_factory=list)
    variables: dict[str, str] | list[dict] = Field(
        default_factory=dict,
        description="ID mapping or embedded with ?embed=variables",
    )
    bonus: int = Field(default=0, le=4, description="Streak month bonus", exclude=True)

    @field_validator("game", "category", "level", mode="before")
    @classmethod
    def convert_model_to_id(
        cls,
        v: Any,
    ) -> str | dict | None:
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            return v
        if hasattr(v, "id"):
            return v.id
        return None

    @field_validator("variables", mode="before")
    @classmethod
    def convert_variables_to_mapping(
        cls,
        v: Any,
    ) -> dict[str, str] | list[dict]:
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        if isinstance(v, list):
            return v
        if hasattr(v, "all"):
            return {}
        return {}

    @field_validator("players", mode="before")
    @classmethod
    def convert_players_manager_to_list(
        cls,
        v: Any,
    ) -> list[dict]:
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if hasattr(v, "all"):
            return []
        return []


class RunModSchema(RunSchema):
    """Run schema for authed moderator responses, exposing import validation flags.

    Identical to `RunSchema` plus mod-only `import_issues` / `has_import_issues`. Never
    used by public endpoints.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "y8dwozoj",
                "runtype": "main",
                "place": 1,
                "points": 1000,
                "obsolete": False,
                "subcategory": "Any% (PC)",
                "times": {
                    "time": "12:34.567",
                    "time_secs": 754.567,
                    "timenl": None,
                    "timenl_secs": None,
                    "timeigt": None,
                    "timeigt_secs": None,
                    "p_time": "12:34.567",
                    "p_time_secs": 754.567,
                },
                "platform": "8gej2n93",
                "emulated": False,
                "description": "Used the new strat at the dam.",
                "video": "https://youtube.com/watch?v=example",
                "arch_video": "https://archive.thps.run/videos/y8dwozoj.mp4",
                "date": "2025-08-15T00:00:00Z",
                "v_date": "2025-08-15T10:30:00Z",
                "url": "https://speedrun.com/thps4/run/y8dwozoj",
                "resolved_primary_method": "rta",
                "resolved_required_methods": ["rta", "igt"],
                "game": "n2680o1p",
                "category": "rklge08d",
                "level": None,
                "players": [{"id": "v8lponvj", "name": "ThePackle", "order": 1}],
                "variables": {"5lygdn8q": "pc"},
                "import_issues": [
                    {"type": "missing_timing_methods", "methods": ["rta"]},
                ],
                "has_import_issues": True,
            },
        },
    )

    import_issues: list[dict] = Field(
        default_factory=list,
        description="Import-time validation issues detected for this run (mod-only).",
    )
    has_import_issues: bool = Field(
        default=False,
        description="True when the run has one or more unresolved import issues.",
    )


class PlayerRunEmbedSchema(RunBaseSchema):
    """Schema for embedding run data in player profile responses.

    Extends RunBaseSchema with serialized game, category, level, and player
    data shaped for the frontend player profile view.

    Attributes:
        game (dict): Game info (name, slug).
        category (dict | None): Category info (name, slug) if present.
        level (dict | None): Level info (name, slug) if present.
        players (list[dict]): Populated separately via player_data_export.
    """

    game: dict = Field(default_factory=dict)
    category: dict | None = None
    level: dict | None = None
    players: list[dict] = Field(default_factory=list)

    @field_validator("game", mode="before")
    @classmethod
    def serialize_game(
        cls,
        v: Any,
    ) -> dict:
        if hasattr(v, "name"):
            return {"name": v.name, "slug": v.slug}
        if isinstance(v, dict):
            return v
        return {}

    @field_validator("category", mode="before")
    @classmethod
    def serialize_category(
        cls,
        v: Any,
    ) -> dict | None:
        if v is None:
            return None
        if hasattr(v, "name"):
            return {"name": v.name, "slug": v.slug}
        if isinstance(v, dict):
            return v
        return None

    @field_validator("level", mode="before")
    @classmethod
    def serialize_level(
        cls,
        v: Any,
    ) -> dict | None:
        if v is None:
            return None
        if hasattr(v, "name"):
            return {"name": v.name, "slug": v.slug}
        if isinstance(v, dict):
            return v
        return None


class RunCreateSchema(BaseEmbedSchema):
    """Schema for creating runs.

    Attributes:
        id (str | None): The run ID; if one is not given, it will auto-generate.
        game_id (str): Game ID.
        category_id (str | None): Category ID.
        level_id (str | None): Level ID (for ILs).
        player_ids (list[str] | None): List of player IDs in order of participation.
        runtype (str): Run type (main or il).
        place (int): Leaderboard position.
        time (str | None): Formatted time string.
        time_secs (float | None): Time in seconds.
        video (str | None): Video URL.
        date (datetime | None): Submission date.
        v_date (datetime | None): Verification date.
        url (str): Speedrun.com URL.
        variable_values (dict[str, str] | None): Variable value selections.
    """

    id: str | None = Field(
        default=None, max_length=10, description="Auto-generates if omitted"
    )
    game_id: str
    category_id: str | None = None
    level_id: str | None = Field(default=None, description="For IL runs")
    player_ids: list[str] | None = Field(None, description="In order of participation")
    runtype: RunTypeType = Field(...)
    place: int = Field(..., ge=1)
    time: str | None = Field(default=None, max_length=25)
    time_secs: float | None = Field(default=None, ge=0)
    timenl: str | None = Field(default=None, max_length=25)
    timenl_secs: float | None = Field(default=None, ge=0)
    timeigt: str | None = Field(default=None, max_length=25)
    timeigt_secs: float | None = Field(default=None, ge=0)
    video: str | None = None
    arch_video: str | None = Field(
        default=None, description="Archived/mirrored video URL"
    )
    obsolete: bool = Field(default=False, description="Mark the run as obsolete")
    platform_id: str | None = None
    approver_id: str | None = None
    description: str | None = Field(default=None, max_length=5000)
    emulated: bool = Field(default=False, description="Emulated run")
    date: datetime | None = None
    v_date: datetime | None = Field(default=None, description="Verification date")
    url: str
    variable_values: dict[str, str] | None = Field(None)


class ModeratorActionIn(Schema):
    """Optional moderator verdict applied atomically with a run-data edit."""

    action: Literal["verify", "reject", "review"]
    reason: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Required when action='reject'. Sent verbatim to speedrun.com "
            "as the rejection reason; not persisted on the Run row."
        ),
    )
    notes: str | None = Field(
        default=None,
        max_length=2000,
        description=(
            "Required when action='review'. Stored as Runs.review_notes "
            "and surfaced to the runner."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "action": "verify",
            },
        },
    }


class RunUpdateSchema(BaseEmbedSchema):
    """Schema for updating runs.

    Attributes:
        game_id (str | None): Updated game ID.
        category_id (str | None): Updated category ID.
        level_id (str | None): Updated level ID.
        player_ids (list[str] | None): Updated list of player IDs.
        runtype (str | None): Updated run type.
        place (int | None): Updated leaderboard position.
        time (str | None): Updated formatted time string.
        time_secs (float | None): Updated time in seconds.
        video (str | None): Updated video URL.
        date (datetime | None): Updated submission date.
        v_date (datetime | None): Updated verification date.
        url (str | None): Updated Speedrun.com URL.
        variable_values (dict[str, str] | None): Updated variable selections.
    """

    game_id: str | None = None
    category_id: str | None = None
    level_id: str | None = None
    player_ids: list[str] | None = Field(None, description="In order of participation")
    runtype: RunTypeType | None = None
    place: int | None = Field(default=None, ge=1)
    time: str | None = Field(default=None, max_length=25)
    time_secs: float | None = Field(default=None, ge=0)
    timenl: str | None = Field(default=None, max_length=25)
    timenl_secs: float | None = Field(default=None, ge=0)
    timeigt: str | None = Field(default=None, max_length=25)
    timeigt_secs: float | None = Field(default=None, ge=0)
    video: str | None = None
    arch_video: str | None = Field(
        default=None, description="Archived/mirrored video URL"
    )
    obsolete: bool | None = Field(default=None, description="Mark the run as obsolete")
    platform_id: str | None = None
    approver_id: str | None = None
    description: str | None = Field(default=None, max_length=5000)
    emulated: bool | None = None
    date: datetime | None = None
    v_date: datetime | None = Field(default=None, description="Verification date")
    url: str | None = None
    variable_values: dict[str, str] | None = None
    moderator_action: ModeratorActionIn | None = Field(
        default=None,
        description=(
            "Optional moderator verdict applied atomically with this run "
            "update. Requires moderator privileges on the run's game and "
            "(for verify/reject) a stored SRC API key. Omit for runner-style "
            "edits."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "place": 1,
                    "time": "5m 00s",
                    "time_secs": 300.0,
                },
                {
                    "place": 1,
                    "time": "5m 00s",
                    "time_secs": 300.0,
                    "moderator_action": {"action": "verify"},
                },
                {
                    "moderator_action": {
                        "action": "review",
                        "notes": (
                            "Video shows a cut at 00:42 - please " "reupload uncut."
                        ),
                    },
                },
            ],
        },
    }
