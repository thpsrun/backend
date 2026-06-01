from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

# Not everything is defined for these Pydantic models, just pretty much anything
# that is needed for the project.


# PLATFORM SCHEMA #
class SrcPlatformModel(BaseModel):
    """Base model for SRC Platforms."""

    id: str
    name: str | None = None


# GAMES SCHEMA #
class SrcGamesNames(BaseModel):
    """Embedded model to show a game's name and Twitch name."""

    international: str
    twitch: str | None = None


class SrcGamesRuleset(BaseModel):
    """Embedded model to show a game's default timing method."""

    model_config = ConfigDict(populate_by_name=True)
    defaulttime: str = Field(..., alias="default-time")


class SrcGamesBoxArtUri(BaseModel):
    """Embedded model to show a game's boxart."""

    uri: str


class SrcGamesAssets(BaseModel):
    """Embedded model to show a game's assets."""

    model_config = ConfigDict(populate_by_name=True)
    cover_large: SrcGamesBoxArtUri = Field(..., alias="cover-large")


class SrcGamesModel(BaseModel):
    """Base model for SRC Games."""

    model_config = ConfigDict(populate_by_name=True)
    id: str
    abbreviation: str
    names: SrcGamesNames
    release_date: str = Field(..., alias="release-date")
    ruleset: SrcGamesRuleset
    assets: SrcGamesAssets
    categories: List[SrcCategoriesModel] | None = None
    levels: List[SrcLevelsModel] | None = None
    variables: List[SrcVariablesModel] | None = None
    platforms: List[SrcPlatformModel]
    moderators: Dict[str, str] = {}

    @field_validator("categories", mode="before")
    @classmethod
    def unwrap_categories(cls, v):
        if v is None:
            return []
        elif isinstance(v, dict) and "data" in v:
            return v["data"]
        return v

    @field_validator("levels", mode="before")
    @classmethod
    def unwrap_levels(cls, v):
        if v is None:
            return []
        elif isinstance(v, dict) and "data" in v:
            return v["data"]
        return v

    @field_validator("variables", mode="before")
    @classmethod
    def unwrap_variables(cls, v):
        if v is None:
            return []
        elif isinstance(v, dict) and "data" in v:
            return v["data"]
        return v

    @field_validator("platforms", mode="before")
    @classmethod
    def unwrap_platforms(cls, v):
        """This is more complex logic since, for `games`, it could be EITHER a list or a dict."""
        if v is None:
            return []
        elif isinstance(v, dict) and "data" in v:
            return v["data"]
        elif isinstance(v, list) and v and isinstance(v[0], str):
            return [{"id": platform_id} for platform_id in v]
        return v


# CATEGORIES/LEVEL SCHEMA #
class SrcCategoriesLevelsScope(BaseModel):
    """Embedded model to show a category or level's scope type."""

    type: str


class SrcCategoriesLevelsLinks(BaseModel):
    """Embedded model to show the link structure within a category or level data."""

    rel: str
    uri: str


class SrcCategoriesModel(BaseModel):
    """Base model for SRC Categories."""

    model_config = ConfigDict(populate_by_name=True)
    id: str
    name: str
    type: str
    scope: SrcCategoriesLevelsScope | None = None
    weblink: str
    rules: str | None = None
    game: SrcGamesModel | None = None

    @field_validator("game", mode="before")
    @classmethod
    def unwrap_game(cls, v):
        if v is None:
            return None
        elif isinstance(v, dict) and "data" in v:
            return v["data"]
        return v


class SrcLevelsModel(BaseModel):
    """Base model for SRC Levels."""

    id: str
    name: str
    weblink: str
    rules: str | None = None
    links: List[SrcCategoriesLevelsLinks]

    @property
    def game(
        self,
    ) -> str | None:
        for link in self.links:
            if link.rel == "game":
                return link.uri.rstrip("/").split("/")[-1]


# VARIABLE VALUES SCHEMA #
class SrcVariableValuesValue(BaseModel):
    """Embedded model to show a VariableValue's information."""

    label: str
    rules: str | None = None


class SrcVariableValuesModel(BaseModel):
    """Base model for SRC Values within a Variable."""

    values: Dict[str, SrcVariableValuesValue]
    default: str | None = None


# VARIABLES SCHEMA #
class SrcVariableScope(BaseModel):
    """Embedded model for scope type of an SRC Variable."""

    type: str
    level: str | None = None


class SrcVariablesModel(BaseModel):
    """Base model for SRC Variables with embedded Values."""

    model_config = ConfigDict(populate_by_name=True)
    id: str
    name: str
    category: str | None = None
    scope: SrcVariableScope
    mandatory: bool = False
    obsoletes: bool = False
    is_subcategory: bool = Field(default=False, alias="is-subcategory")
    values: SrcVariableValuesModel
    links: List[SrcCategoriesLevelsLinks]

    @property
    def game(
        self,
    ) -> str | None:
        for link in self.links:
            if link.rel == "game":
                return link.uri.rstrip("/").split("/")[-1]


# RUNS SCHEMA #
class SrcRunsSystem(BaseModel):
    """Embedded model for system information for an SRC Run."""

    platform: str | None = None
    emulated: bool
    region: str | None = None


class SrcRunsStatus(BaseModel):
    """Embedded model for status information for an SRC Run."""

    model_config = ConfigDict(populate_by_name=True)
    status: str
    examiner: str | None = None
    verify_date: datetime | None = Field(default=None, alias="verify-date")


class SrcRunsPlayers(BaseModel):
    """Embedded model for player information for an SRC Run."""

    rel: str
    id: str | None = None
    uri: str | None = None
    name: str | None = None


class SrcRunsTimes(BaseModel):
    """Embedded model for timing information for an SRC Run."""

    primary_t: float = 0
    realtime_t: float = 0
    realtime_noloads_t: float = 0
    ingame_t: float = 0


class SrcVideoLink(BaseModel):
    """Embedded model for returning video links for an SRC Run."""

    # For some reason the SRC API has both sometimes.
    uri: str | None = None
    text: str | None = None


class SrcVideos(BaseModel):
    """Embedded model for returning the list of video links for an SRC Run."""

    links: list[SrcVideoLink] = Field(default_factory=list)
    text: str | None = None


class SrcRunsModel(BaseModel):
    """Base Model for SRC Runs with embedded Values and Videos."""

    id: str
    weblink: str
    game: str | SrcGamesModel
    level: str | SrcLevelsModel | None
    category: str | SrcCategoriesModel | None
    videos: SrcVideos | None
    comment: str | None
    status: SrcRunsStatus
    players: List[SrcRunsPlayers]
    date: datetime | None
    submitted: datetime | None
    times: SrcRunsTimes
    system: SrcRunsSystem
    values: dict[str, str]

    @computed_field
    @property
    def video_uri(
        self,
    ) -> str | None:
        if self.videos and self.videos.links:
            return self.videos.links[0].uri
        return None

    @field_validator("category", mode="before")
    @classmethod
    def unwrap_categories(cls, v):
        if v is None or v == [] or v == {}:
            return None
        elif isinstance(v, dict) and "data" in v:
            data = v["data"]
            return data if data not in (None, [], {}) else None
        return v

    @field_validator("level", mode="before")
    @classmethod
    def unwrap_level(cls, v):
        if v is None or v == [] or v == {}:
            return None
        elif isinstance(v, dict) and "data" in v:
            data = v["data"]
            return data if data not in (None, [], {}) else None
        return v


# PLAYERS SCHEMA #
class SrcPlayersNames(BaseModel):
    """Embedded model for SRC Players with naming data."""

    international: str
    japanese: str | None


class SrcPlayersModel(BaseModel):
    """Base Model for SRC Players with embedded Values."""

    id: str
    rel: str | None = None
    names: SrcPlayersNames
    name: str | None = None
    pronouns: str | None = None
    weblink: str
    location: dict | None = None
    twitch: dict | None = None
    youtube: dict | None = None
    assets: dict | None = None

    @property
    def country_code(
        self,
    ) -> str | None:
        if self.location and self.location.get("country"):
            return self.location["country"].get("code")
        return None

    @property
    def country_name(
        self,
    ) -> str | None:
        if self.location and self.location.get("country"):
            names = self.location["country"].get("names")
            if names:
                return names.get("international")
        return None

    @property
    def twitch_url(
        self,
    ) -> str | None:
        if self.twitch:
            return self.twitch.get("uri")
        return None

    @property
    def youtube_url(
        self,
    ) -> str | None:
        if self.youtube:
            return self.youtube.get("uri")
        return None

    @property
    def pfp(
        self,
    ) -> str | None:
        if self.assets and self.assets.get("image"):
            return self.assets["image"].get("uri")
        return None


# LEADERBOARD SCHEMA #
class SrcLeaderboardRun(BaseModel):
    """Embedded model for SRC Leaderboard data to show placement and run data."""

    place: int
    run: SrcRunsModel


class SrcLeaderboardEmbeddedPlayer(BaseModel):
    """Permissive shape for embedded leaderboard player entries to better guard against guest users
    within the SRC context."""

    rel: str | None = None
    id: str | None = None
    name: str | None = None
    names: SrcPlayersNames | None = None
    weblink: str | None = None
    pronouns: str | None = None
    location: dict | None = None
    twitch: dict | None = None
    youtube: dict | None = None
    assets: dict | None = None


class SrcLeaderboardPlayers(BaseModel):
    """Embedded model for SRC Leaderboards to show player metadata to board."""

    data: List[SrcLeaderboardEmbeddedPlayer]


class SrcLeaderboardModel(BaseModel):
    """Base model for SRC Leaderboards data with embedded metadata."""

    weblink: str
    game: str
    category: str | None
    level: str | None
    timing: str
    values: dict | None
    runs: List[SrcLeaderboardRun]
    players: SrcLeaderboardPlayers | None = None
