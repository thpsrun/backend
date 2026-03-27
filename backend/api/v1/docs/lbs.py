LBS_FG_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "runs": [
                            {
                                "id": "y8dwozoj",
                                "place": 1,
                                "points": 1000,
                                "date": "2025-08-15",
                                "video": "https://youtube.com/watch?v=example",
                                "arch_video": None,
                                "level": None,
                                "times": {"p_time": "12:34.567"},
                                "players": [
                                    {
                                        "name": "ThePackle",
                                        "country": {
                                            "id": "us",
                                            "name": "United States",
                                        },
                                    }
                                ],
                            }
                        ],
                        "stats": {
                            "main_count": 142,
                            "il_count": 1830,
                            "player_count": 65,
                        },
                        "recent": [
                            {
                                "runtype": "main",
                                "category": "Any%",
                                "level": None,
                                "subcategory": "Any% (Beginner)",
                                "p_time": "12:34.567",
                                "p_time_secs": 754.567,
                                "place": 3,
                                "player_name": "ThePackle",
                                "player_country": "United States",
                                "v_date": "2025-08-16T10:30:00",
                            }
                        ],
                    }
                }
            },
        },
        400: {
            "description": (
                "Invalid embed types, slug too long, or per-level category used "
                "(use IL endpoints instead)."
            ),
        },
        404: {"description": "Game or category not found."},
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
                "Full-game category slug (e.g. any, any-no-warp, "
                "all-goals-and-golds). Must be a per-game category."
            ),
        },
        {
            "name": "values",
            "in": "query",
            "example": "beginner",
            "schema": {"type": "string"},
            "description": (
                "Comma-separated variable value slugs to filter by subcategory. "
                "Order does not matter. Omit to return all subcategories."
            ),
        },
        {
            "name": "embed",
            "in": "query",
            "example": "stats,recent",
            "schema": {"type": "string"},
            "description": "Comma-separated embeds: stats, recent",
        },
    ],
}


LBS_IL_SUMMARY_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "levels": [
                            {
                                "name": "Foundry",
                                "slug": "foundry",
                                "categories": [
                                    {
                                        "name": "Any%",
                                        "slug": "any",
                                        "runs": [
                                            {
                                                "id": "abc12345",
                                                "place": 1,
                                                "points": 100,
                                                "date": "2025-01-15",
                                                "video": "https://youtube.com/watch?v=example",
                                                "level": "foundry",
                                                "times": {"p_time": "0:42.310"},
                                                "players": [
                                                    {
                                                        "name": "ThePackle",
                                                        "country": {
                                                            "id": "us",
                                                            "name": "United States",
                                                        },
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                        "stats": {
                            "main_count": 142,
                            "il_count": 1830,
                            "player_count": 65,
                        },
                        "recent": [
                            {
                                "runtype": "il",
                                "category": "Any%",
                                "level": "Foundry",
                                "subcategory": "Foundry",
                                "p_time": "0:42.310",
                                "p_time_secs": 42.31,
                                "place": 1,
                                "player_name": "ThePackle",
                                "player_country": "United States",
                                "v_date": "2025-01-16T10:30:00",
                            }
                        ],
                    }
                }
            },
        },
        400: {"description": "Invalid embed types or too many value slugs."},
        404: {"description": "Game not found."},
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
            "name": "values",
            "in": "query",
            "example": "normal",
            "schema": {"type": "string"},
            "description": (
                "Comma-separated variable value slugs to filter by subcategory. "
                "Order does not matter. Omit to return all subcategories."
            ),
        },
        {
            "name": "embed",
            "in": "query",
            "example": "stats,recent",
            "schema": {"type": "string"},
            "description": "Comma-separated embeds: stats, recent",
        },
    ],
}


LBS_IL_DETAIL_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "runs": [
                            {
                                "id": "abc12345",
                                "place": 1,
                                "points": 100,
                                "date": "2025-01-15",
                                "video": "https://youtube.com/watch?v=example",
                                "level": "foundry",
                                "times": {"p_time": "0:42.310"},
                                "players": [
                                    {
                                        "name": "ThePackle",
                                        "country": {
                                            "id": "us",
                                            "name": "United States",
                                        },
                                    }
                                ],
                            }
                        ],
                        "stats": {
                            "main_count": 142,
                            "il_count": 1830,
                            "player_count": 65,
                        },
                        "recent": [
                            {
                                "runtype": "il",
                                "category": "Any%",
                                "level": "Foundry",
                                "subcategory": "Foundry",
                                "p_time": "0:42.310",
                                "p_time_secs": 42.31,
                                "place": 1,
                                "player_name": "ThePackle",
                                "player_country": "United States",
                                "v_date": "2025-01-16T10:30:00",
                            }
                        ],
                    }
                }
            },
        },
        400: {
            "description": (
                "Invalid embed types, slug too long, or per-game category used "
                "(use FG endpoint instead)."
            ),
        },
        404: {
            "description": (
                "Game, level, or category not found, or level/category does not "
                "belong to this game."
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
            "name": "level_slug",
            "in": "path",
            "required": True,
            "example": "foundry",
            "schema": {"type": "string", "maxLength": 75},
            "description": "Level slug (e.g. foundry, manhattan, training)",
        },
        {
            "name": "category_slug",
            "in": "path",
            "required": True,
            "example": "any",
            "schema": {"type": "string", "maxLength": 50},
            "description": (
                "IL category slug (e.g. any, 100). Must be a per-level category."
            ),
        },
        {
            "name": "values",
            "in": "query",
            "example": "beginner",
            "schema": {"type": "string"},
            "description": (
                "Comma-separated variable value slugs to filter by subcategory. "
                "Order does not matter. Omit to return all subcategories."
            ),
        },
        {
            "name": "embed",
            "in": "query",
            "example": "stats,recent",
            "schema": {"type": "string"},
            "description": "Comma-separated embeds: stats, recent",
        },
    ],
}
