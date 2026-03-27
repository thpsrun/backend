MAIN_PAGE_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "latest_wrs": [
                            {
                                "id": "y8dwozoj",
                                "game_slug": "thps4",
                                "category": {
                                    "name": "Any%",
                                    "slug": "any",
                                },
                                "players": [
                                    {
                                        "name": "ThePackle",
                                        "nickname": None,
                                        "country": {
                                            "id": "us",
                                            "name": "United States",
                                        },
                                    }
                                ],
                                "time": "12:34.567",
                                "date": "2025-08-15T10:30:00",
                                "video": "https://youtube.com/watch?v=example",
                                "value_slugs": ["normal", "pc"],
                            }
                        ],
                        "latest_pbs": [
                            {
                                "id": "z9fxpakl",
                                "game_slug": "thps3",
                                "category": {
                                    "name": "100%",
                                    "slug": "100",
                                },
                                "players": [
                                    {
                                        "name": "SpeedRunner123",
                                        "nickname": None,
                                        "country": {
                                            "id": "ca",
                                            "name": "Canada",
                                        },
                                    }
                                ],
                                "time": "25:43.123",
                                "date": "2025-01-14T15:20:00",
                                "video": "https://youtube.com/watch?v=example2",
                                "value_slugs": ["normal", "ps2"],
                            }
                        ],
                        "records": [
                            {
                                "id": "y8dwozoj",
                                "game": {
                                    "name": "Tony Hawk's Pro Skater 4",
                                    "slug": "thps4",
                                },
                                "category": {
                                    "name": "Any%",
                                    "slug": "any",
                                },
                                "players": [
                                    {
                                        "name": "ThePackle",
                                        "nickname": None,
                                        "country": {
                                            "id": "us",
                                            "name": "United States",
                                        },
                                    }
                                ],
                                "time": "12:34.567",
                                "date": "2025-08-15",
                                "video": "https://youtube.com/watch?v=example",
                                "value_slugs": ["normal", "pc"],
                            }
                        ],
                    }
                }
            },
        },
        400: {
            "description": "Invalid embed types requested or missing embed parameter."
        },
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "embed",
            "in": "query",
            "required": True,
            "example": "latest-wrs,latest-pbs,records",
            "schema": {"type": "string"},
            "description": "Comma-separated embed types: latest-wrs, latest-pbs, records",
        },
    ],
}

GAME_CATEGORIES_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "rklge08d",
                            "name": "Any%",
                            "slug": "any",
                            "type": "per-game",
                            "url": "https://speedrun.com/thps4/full_game#Any",
                            "rules": "Rulez.",
                            "appear_on_main": True,
                            "hidden": False,
                            "variables": [
                                {
                                    "id": "5lygdn8q",
                                    "name": "Platform",
                                    "slug": "platform",
                                    "scope": "full-game",
                                    "hidden": False,
                                    "values": [
                                        {
                                            "value": "pc",
                                            "name": "PC",
                                            "slug": "pc",
                                            "hidden": False,
                                            "rules": "",
                                        },
                                        {
                                            "value": "ps2",
                                            "name": "PlayStation 2",
                                            "slug": "ps2",
                                            "hidden": False,
                                            "rules": "",
                                        },
                                    ],
                                }
                            ],
                        },
                        {
                            "id": "xd1m508k",
                            "name": "100%",
                            "slug": "100",
                            "type": "per-game",
                            "url": "https://speedrun.com/thps4/full_game#100",
                            "rules": "",
                            "appear_on_main": True,
                            "hidden": False,
                            "variables": [
                                {
                                    "id": "5lygdn8q",
                                    "name": "Platform",
                                    "slug": "platform",
                                    "scope": "full-game",
                                    "hidden": False,
                                    "values": [
                                        {
                                            "value": "pc",
                                            "name": "PC",
                                            "slug": "pc",
                                            "hidden": False,
                                            "rules": "",
                                        }
                                    ],
                                }
                            ],
                        },
                    ]
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        404: {"description": "Game could not be found."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "game_id",
            "in": "path",
            "required": True,
            "example": "thps4",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Game ID or slug",
        },
    ],
}

GAME_LEVELS_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "592pxj8d",
                            "name": "Alcatraz",
                            "slug": "alcatraz",
                            "url": "https://speedrun.com/thps4/individual_levels#Alcatraz",
                            "rules": "Rulez.",
                            "variables": [
                                {
                                    "id": "9k2xfl7m",
                                    "name": "Difficulty",
                                    "slug": "difficulty",
                                    "scope": "single-level",
                                    "hidden": False,
                                    "values": [
                                        {
                                            "value": "normal",
                                            "name": "Normal",
                                            "slug": "normal",
                                            "hidden": False,
                                            "rules": "",
                                        },
                                        {
                                            "value": "sick",
                                            "name": "Sick",
                                            "slug": "sick",
                                            "hidden": False,
                                            "rules": "",
                                        },
                                    ],
                                }
                            ],
                        },
                        {
                            "id": "29vjx18k",
                            "name": "Kona",
                            "slug": "kona",
                            "url": "https://speedrun.com/thps4/individual_levels#Kona",
                            "rules": "Rulez.",
                            "variables": [
                                {
                                    "id": "9k2xfl7m",
                                    "name": "Difficulty",
                                    "slug": "difficulty",
                                    "scope": "single-level",
                                    "hidden": False,
                                    "values": [
                                        {
                                            "value": "normal",
                                            "name": "Normal",
                                            "slug": "normal",
                                            "hidden": False,
                                            "rules": "",
                                        }
                                    ],
                                }
                            ],
                        },
                    ]
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        404: {"description": "Game could not be found."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "game_id",
            "in": "path",
            "required": True,
            "example": "thps4",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Game ID or slug",
        },
    ],
}
