from __future__ import annotations

from enum import Enum

from ninja import Schema


class ReorderScope(str, Enum):
    CATEGORY = "category"
    LEVEL = "level"
    VARIABLE_VALUE = "variable_value"


class VisibilityTargetType(str, Enum):
    CATEGORY = "category"
    VARIABLE_VALUE = "variable_value"


class DisplayItem(Schema):
    id: str
    name: str
    order: int
    appear_on_main: bool | None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "wkpoq402",
                "name": "Any%",
                "order": 1,
                "appear_on_main": True,
            },
        }


class VariableGroup(Schema):
    variable_id: str
    variable_name: str
    values: list[DisplayItem]

    class Config:
        json_schema_extra = {
            "example": {
                "variable_id": "5lyo15el",
                "variable_name": "Difficulty",
                "values": [
                    {
                        "id": "21d4zd0q",
                        "name": "Normal",
                        "order": 1,
                        "appear_on_main": True,
                    },
                ],
            },
        }


class GameDisplayResponse(Schema):
    game_id: str
    game_name: str
    categories: list[DisplayItem]
    levels: list[DisplayItem]
    variable_groups: list[VariableGroup]

    class Config:
        json_schema_extra = {
            "example": {
                "game_id": "yd4ovrk1",
                "game_name": "Tony Hawk's Pro Skater 4",
                "categories": [
                    {
                        "id": "wkpoq402",
                        "name": "Any%",
                        "order": 1,
                        "appear_on_main": True,
                    },
                ],
                "levels": [
                    {
                        "id": "rdnpd2dl",
                        "name": "College",
                        "order": 0,
                        "appear_on_main": None,
                    },
                ],
                "variable_groups": [
                    {
                        "variable_id": "5lyo15el",
                        "variable_name": "Difficulty",
                        "values": [
                            {
                                "id": "21d4zd0q",
                                "name": "Normal",
                                "order": 1,
                                "appear_on_main": True,
                            },
                        ],
                    },
                ],
            },
        }


class ReorderRequest(Schema):
    scope: ReorderScope
    ordered_ids: list[str]
    var_id: str | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "scope": "category",
                "ordered_ids": ["wkpoq402", "9d8mqkop"],
                "var_id": None,
            },
        }


class VisibilityRequest(Schema):
    target_type: VisibilityTargetType
    target_id: str
    value: bool

    class Config:
        json_schema_extra = {
            "example": {
                "target_type": "category",
                "target_id": "wkpoq402",
                "value": True,
            },
        }
