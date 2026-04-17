GAMES_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
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
                        "rules": "Timing starts on ...",
                    }
                }
            },
        },
        404: {"description": "Game does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "thps4",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Game ID or slug to retrieve",
        },
    ],
}

GAMES_POST = {
    "responses": {
        201: {
            "description": "Game created successfully!",
            "content": {
                "application/json": {
                    "example": {
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
                        "rules": "Timing starts on ...",
                    }
                }
            },
        },
        400: {"description": "Invalid request data or game with slug already exists."},
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
                    "required": ["name", "slug"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "example": "Tony Hawk's Pro Skater 4",
                            "description": "GAME NAME",
                        },
                        "slug": {
                            "type": "string",
                            "example": "thps4",
                            "description": "GAME URL SLUG",
                        },
                        "release": {
                            "type": "string",
                            "format": "date",
                            "example": "2002-10-23",
                            "description": "GAME RELEASE DATE",
                        },
                        "boxart": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://example.com/boxart.jpg",
                            "description": "GAME BOXART URL",
                        },
                        "twitch": {
                            "type": "string",
                            "example": "Tony Hawk's Pro Skater 4",
                            "description": "TWITCH GAME NAME",
                        },
                        "defaulttime": {
                            "type": "string",
                            "enum": ["realtime", "realtime_noloads", "ingame"],
                            "example": "realtime",
                            "description": "DEFAULT TIMING METHOD",
                        },
                        "idefaulttime": {
                            "type": "string",
                            "enum": ["realtime", "realtime_noloads", "ingame"],
                            "example": "realtime",
                            "description": "DEFAULT IL TIMING METHOD",
                        },
                        "rules": {
                            "type": "string",
                            "maxLength": 5000,
                            "example": "Timing starts on ...",
                            "description": "GAME-LEVEL RULES",
                        },
                    },
                },
                "example": {
                    "name": "Tony Hawk's Pro Skater 4",
                    "slug": "thps4",
                    "release": "2002-10-23",
                    "boxart": "https://example.com/boxart.jpg",
                    "twitch": "Tony Hawk's Pro Skater 4",
                    "defaulttime": "realtime",
                    "idefaulttime": "realtime",
                    "rules": "Timing starts on ...",
                },
            }
        },
    },
}

GAMES_PUT = {
    "responses": {
        200: {
            "description": "Game updated successfully!",
            "content": {
                "application/json": {
                    "example": {
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
                        "rules": "Timing starts on ...",
                    }
                }
            },
        },
        400: {"description": "Invalid request data."},
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Game does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "thps4",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Game ID or slug to update",
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
                            "example": "Tony Hawk's Pro Skater 4",
                            "description": "UPDATED GAME NAME",
                        },
                        "slug": {
                            "type": "string",
                            "example": "thps4",
                            "description": "UPDATED GAME SLUG",
                        },
                        "release": {
                            "type": "string",
                            "format": "date",
                            "example": "2002-10-23",
                            "description": "UPDATED RELEASE DATE",
                        },
                        "boxart": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://example.com/boxart.jpg",
                            "description": "UPDATED BOXART URL",
                        },
                        "twitch": {
                            "type": "string",
                            "example": "Tony Hawk's Pro Skater 4",
                            "description": "UPDATED TWITCH NAME",
                        },
                        "defaulttime": {
                            "type": "string",
                            "enum": ["realtime", "realtime_noloads", "ingame"],
                            "example": "realtime",
                            "description": "UPDATED DEFAULT TIMING",
                        },
                        "idefaulttime": {
                            "type": "string",
                            "enum": ["realtime", "realtime_noloads", "ingame"],
                            "example": "realtime",
                            "description": "UPDATED IL DEFAULT TIMING",
                        },
                        "rules": {
                            "type": "string",
                            "maxLength": 5000,
                            "example": "Timing starts on ...",
                            "description": "UPDATED GAME-LEVEL RULES",
                        },
                    },
                },
                "example": {
                    "name": "Tony Hawk's Pro Skater 4 Updated",
                    "boxart": "https://example.com/new-boxart.jpg",
                },
            }
        },
    },
}

GAMES_DELETE = {
    "responses": {
        200: {
            "description": "Game deleted successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Game 'Tony Hawk's Pro Skater 4' deleted successfully"
                    }
                }
            },
        },
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions (admin required)."},
        404: {"description": "Game does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "thps4",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Game ID or slug to delete",
        },
    ],
}

GAMES_ALL = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": [
                        {
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
                            "rules": "Timing starts on ...",
                        },
                        {
                            "id": "k6qw5o9p",
                            "name": "Tony Hawk's Pro Skater 3",
                            "slug": "thps3",
                            "release": "2001-10-28",
                            "boxart": "https://example.com/thps3-boxart.jpg",
                            "twitch": "Tony Hawk's Pro Skater 3",
                            "defaulttime": "realtime",
                            "idefaulttime": "realtime",
                            "pointsmax": 1000,
                            "ipointsmax": 100,
                            "rules": None,
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
