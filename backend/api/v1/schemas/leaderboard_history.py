from ninja import Schema
from pydantic import ConfigDict

from api.v1.schemas.leaderboard import LeaderboardPlayerEmbed


class HistoricalEntrySchema(Schema):
    rank: int
    total_points: int
    fg_points: int
    il_points: int
    player: LeaderboardPlayerEmbed


class HistoricalMetaSchema(Schema):
    mode: str
    year: int
    month: int
    scope: str
    scope_game_id: str | None
    period_start: str
    period_end_exclusive: str
    earliest_possible: str | None


class HistoricalLeaderboardResponseSchema(Schema):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rankings": [
                    {
                        "rank": 1,
                        "total_points": 4250,
                        "fg_points": 3100,
                        "il_points": 1150,
                        "player": {
                            "id": "p_abc",
                            "name": "PlayerOne",
                            "nickname": None,
                            "url": "https://thps.run/players/playerone",
                            "pfp": None,
                            "country": {
                                "id": "us",
                                "name": "United States",
                                "flag": None,
                            },
                            "gradients": {
                                "gradient_1": "#ff0000",
                                "gradient_2": "#00ff00",
                                "gradient_3": "#0000ff",
                            },
                        },
                    },
                ],
                "meta": {
                    "mode": "monthly",
                    "year": 2020,
                    "month": 10,
                    "scope": "all",
                    "scope_game_id": None,
                    "period_start": "2020-10-01T00:00:00Z",
                    "period_end_exclusive": "2020-11-01T00:00:00Z",
                    "earliest_possible": "2014-08",
                },
            },
        },
    )

    rankings: list[HistoricalEntrySchema]
    meta: HistoricalMetaSchema


class TimeTravelerErrorSchema(Schema):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Are you a time traveler?",
                "current": "2026-04",
            },
        },
    )

    detail: str
    current: str


class EarliestPossibleErrorSchema(Schema):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "That game didn't even come out yet???",
                "earliest_possible": "2014-08",
            },
        },
    )

    detail: str
    earliest_possible: str


class GameNotFoundErrorSchema(Schema):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"detail": "Game 'thps12' not found"},
        },
    )

    detail: str
