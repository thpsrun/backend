HISTORY_FG_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "game": "Tony Hawk's Underground",
                        "category": "Any%",
                        "subcategory": "Any% (Beginner)",
                        "level": None,
                        "entries": [
                            {
                                "run_id": "y8dwozoj",
                                "players": [
                                    {
                                        "name": "ThePackle",
                                        "nickname": None,
                                        "gradients": {
                                            "gradient_1": "#ff0044",
                                            "gradient_2": "#00aaff",
                                            "gradient_3": None,
                                        },
                                    }
                                ],
                                "history_time": "0:18:32.000",
                                "history_time_secs": 1112.0,
                                "delta": None,
                                "video": "https://youtube.com/watch?v=abc123",
                                "arch_video": None,
                                "start_date": "2020-01-15T00:00:00",
                                "end_date": "2020-03-22T00:00:00",
                            },
                            {
                                "run_id": "z5dkw2oj",
                                "players": [
                                    {
                                        "name": "SpeedRunner42",
                                        "nickname": "SR42",
                                        "gradients": None,
                                    }
                                ],
                                "history_time": "0:18:30.500",
                                "history_time_secs": 1110.5,
                                "delta": -1.5,
                                "video": "https://youtube.com/watch?v=def456",
                                "arch_video": None,
                                "start_date": "2020-03-22T00:00:00",
                                "end_date": None,
                            },
                        ],
                    }
                }
            },
        },
        404: {
            "description": (
                "Game, category, or level not found, or variable values "
                "don't match any known combination."
            ),
        },
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "game_slug",
            "in": "path",
            "required": True,
            "example": "thug",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Game slug (e.g. thug, thps4, thps12)",
        },
        {
            "name": "category_slug",
            "in": "path",
            "required": True,
            "example": "any",
            "schema": {"type": "string", "maxLength": 50},
            "description": (
                "Category slug (e.g. any, any-no-warp, "
                "all-goals-and-golds)."
            ),
        },
    ],
}


HISTORY_IL_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "game": "Tony Hawk's Pro Skater",
                        "category": "All Goals & Gold",
                        "subcategory": "Warehouse (Console, IGT)",
                        "level": "Warehouse",
                        "entries": [
                            {
                                "run_id": "abc12345",
                                "players": [
                                    {
                                        "name": "ILKing",
                                        "nickname": None,
                                        "gradients": None,
                                    }
                                ],
                                "history_time": "0:01:42.310",
                                "history_time_secs": 102.31,
                                "delta": None,
                                "video": None,
                                "arch_video": None,
                                "start_date": "2019-06-01T00:00:00",
                                "end_date": "2020-01-10T00:00:00",
                            },
                        ],
                    }
                }
            },
        },
        404: {
            "description": (
                "Game, level, category, or variable values not found."
            ),
        },
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "game_slug",
            "in": "path",
            "required": True,
            "example": "thps1",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Game slug (e.g. thug, thps4, thps12)",
        },
        {
            "name": "level_slug",
            "in": "path",
            "required": True,
            "example": "warehouse",
            "schema": {"type": "string", "maxLength": 75},
            "description": "Level slug (e.g. warehouse, manhattan)",
        },
        {
            "name": "category_slug",
            "in": "path",
            "required": True,
            "example": "agg",
            "schema": {"type": "string", "maxLength": 50},
            "description": "IL category slug (e.g. any, agg).",
        },
    ],
}
