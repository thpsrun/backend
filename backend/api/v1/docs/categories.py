CATEGORIES_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "rklge08d",
                        "name": "Any%",
                        "slug": "any",
                        "type": "per-game",
                        "url": "https://speedrun.com/thps4/full_game#Any",
                        "rules": "Rulez.",
                        "appear_on_main": True,
                        "hidden": False,
                        "game": {
                            "id": "n2680o1p",
                            "name": "Tony Hawk's Pro Skater 4",
                            "slug": "thps4",
                            "release": "2002-10-23",
                            "boxart": "https://example.com/boxart.jpg",
                            "twitch": "Tony Hawk's Pro Skater 4",
                            "defaulttime": "realtime",
                            "idefaulttime": "realtime",
                            "pointsmax": 1000,
                            "ipointsmax": 100,
                        },
                        "variables": [
                            {
                                "id": "fdsw34df",
                                "name": "Platform",
                                "slug": "platform",
                                "scope": "full-game",
                                "hidden": False,
                                "values": [
                                    {
                                        "value": "pcdfsf",
                                        "name": "PC",
                                        "slug": "pc",
                                        "hidden": False,
                                        "rules": "",
                                    }
                                ],
                            }
                        ],
                    }
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        404: {"description": "Category could not be found."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "rklge08d",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Category ID",
        },
    ],
}

CATEGORIES_POST = {
    "responses": {
        201: {
            "description": "Category created successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "rklge08d",
                        "name": "Any%",
                        "slug": "any",
                        "type": "per-game",
                        "url": "https://speedrun.com/thps4/full_game#Any",
                        "rules": "Rulez.",
                        "appear_on_main": True,
                        "hidden": False,
                    }
                }
            },
        },
        400: {"description": "Invalid request data or game does not exist."},
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["name", "game_id"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "example": "Any%",
                            "description": "Category name (e.g. Any%, 100%)",
                        },
                        "game_id": {
                            "type": "string",
                            "example": "n2680o1p",
                            "description": "Game ID this category belongs to",
                        },
                        "type": {
                            "type": "string",
                            "enum": ["per-game", "per-level"],
                            "example": "per-game",
                            "description": "per-game or per-level",
                        },
                        "rules": {
                            "type": "string",
                            "example": "Rulez.",
                            "description": "Category-specific rules text",
                        },
                        "appear_on_main": {
                            "type": "boolean",
                            "example": True,
                            "description": "Show on the main leaderboard page",
                        },
                        "hidden": {
                            "type": "boolean",
                            "example": False,
                            "description": "Hide from public listings",
                        },
                    },
                },
                "example": {
                    "name": "Any%",
                    "game_id": "n2680o1p",
                    "type": "per-game",
                    "rules": "Rulez.",
                    "appear_on_main": True,
                    "hidden": False,
                },
            }
        },
    },
}

CATEGORIES_PUT = {
    "responses": {
        200: {
            "description": "Category updated successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "rklge08d",
                        "name": "Any%",
                        "slug": "any",
                        "type": "per-game",
                        "url": "https://speedrun.com/thps4/full_game#Any",
                        "rules": "Complete the game as fast as possible.",
                        "appear_on_main": True,
                        "hidden": False,
                    }
                }
            },
        },
        400: {"description": "Invalid request data or game does not exist."},
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Category does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "rklge08d",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Category ID to update",
        },
    ],
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "example": "Any%",
                            "description": "Updated category name",
                        },
                        "game_id": {
                            "type": "string",
                            "example": "n2680o1p",
                            "description": "Updated game ID",
                        },
                        "type": {
                            "type": "string",
                            "enum": ["per-game", "per-level"],
                            "example": "per-game",
                            "description": "Updated category type",
                        },
                        "rules": {
                            "type": "string",
                            "example": "Complete the game as fast as possible.",
                            "description": "Updated rules text",
                        },
                        "appear_on_main": {
                            "type": "boolean",
                            "example": True,
                            "description": "Show on the main leaderboard page",
                        },
                        "hidden": {
                            "type": "boolean",
                            "example": False,
                            "description": "Hide from public listings",
                        },
                    },
                },
                "example": {
                    "name": "Any%",
                    "rules": "Complete the game as fast as possible with new rules.",
                    "appear_on_main": True,
                },
            }
        },
    },
}

CATEGORIES_DELETE = {
    "responses": {
        200: {
            "description": "Category deleted successfully!",
            "content": {
                "application/json": {
                    "example": {"message": "Category 'Any%' deleted successfully"}
                }
            },
        },
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Category does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "rklge08d",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Category ID to delete",
        },
    ],
}

CATEGORIES_ALL = {
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
                        },
                        {
                            "id": "xd1m508k",
                            "name": "100%",
                            "slug": "100",
                            "type": "per-game",
                            "url": "https://speedrun.com/thps4/full_game#100",
                            "rules": "Rulez.",
                            "appear_on_main": True,
                            "hidden": False,
                        },
                    ]
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
}
