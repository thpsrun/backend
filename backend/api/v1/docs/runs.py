RUNS_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "fsdfsdfsdfs",
                        "time": "12:34.567",
                        "place": 1,
                        "runtype": "main",
                        "subcategory": "Normal, PC",
                        "video": "https://youtube.com/watch?v=example",
                        "arch_video": "https://archive.thps.run/videos/sdfffsdf.mp4",
                        "url": "https://speedrun.com/thps4/run/fsdfsdfsdfs",
                        "date": "2025-08-15",
                        "v_date": "2025-08-15T10:30:00Z",
                        "vid_status": "verified",
                        "obsolete": False,
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
                        "category": {
                            "id": "rklge08d",
                            "name": "Any%",
                            "slug": "any",
                            "type": "per-game",
                            "url": "https://speedrun.com/thps4/full_game#Any",
                            "rules": "Rulez.",
                            "appear_on_main": True,
                            "hidden": False,
                        },
                        "players": [
                            {
                                "id": "v8lponvj",
                                "name": "ThePackle",
                                "url": "https://speedrun.com/user/ThePackle",
                                "country": "United States",
                                "pronouns": "he/him",
                                "twitch": "https://twitch.tv/thepackle",
                                "youtube": "https://youtube.com/thepackle",
                                "twitter": "https://twitter.com/thepackle",
                                "bluesky": "https://bsky.app/profile/@thepackle.bsky.social",
                                "order": 1,
                            }
                        ],
                        "variables": [
                            {
                                "variable": {
                                    "id": "5lygdn8q",
                                    "name": "NG+?",
                                    "slug": "ng-plus",
                                    "scope": "full-game",
                                },
                                "value": {"value": "pc", "name": "PC", "slug": "pc"},
                            }
                        ],
                    }
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        404: {"description": "Run could not be found."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "y8dwozoj",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Run ID",
        },
        {
            "name": "embed",
            "in": "query",
            "example": "game,category,players,variables",
            "schema": {"type": "string"},
            "description": "Comma-separated embeds: game, category, level, players, variables",
        },
    ],
}

RUNS_POST = {
    "responses": {
        201: {
            "description": "Run created successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "21q4tfg34f34",
                        "time": "12:34.567",
                        "place": 1,
                        "runtype": "main",
                        "subcategory": "Any% (Normal)",
                        "video": "https://youtube.com/watch?v=example",
                        "url": "https://speedrun.com/thps4/run/21q4tfg34f34",
                        "date": "2025-08-15",
                        "v_date": "2025-08-15T10:30:00Z",
                        "vid_status": "new",
                        "obsolete": False,
                    }
                }
            },
        },
        400: {
            "description": "Invalid request data, resource does not exist, or validation failed."
        },
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
                    "required": ["game_id", "time"],
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "example": "n2680o1p",
                            "description": "GAME ID FOR THIS RUN",
                        },
                        "category_id": {
                            "type": "string",
                            "example": "rklge08d",
                            "description": "CATEGORY ID FOR THIS RUN",
                        },
                        "level_id": {
                            "type": "string",
                            "example": "592pxj8d",
                            "description": "LEVEL ID FOR IL RUNS",
                        },
                        "player_id": {
                            "type": "string",
                            "example": "v8lponvj",
                            "description": "PRIMARY PLAYER ID",
                        },
                        "player2_id": {
                            "type": "string",
                            "example": "x81m29qk",
                            "description": "SECOND PLAYER ID FOR CO-OP RUNS",
                        },
                        "time": {
                            "type": "string",
                            "example": "12:34.567",
                            "description": "RUN TIME",
                        },
                        "runtype": {
                            "type": "string",
                            "enum": ["main", "il"],
                            "example": "main",
                            "description": "RUN TYPE",
                        },
                        "subcategory": {
                            "type": "string",
                            "example": "Normal, PC",
                            "description": "RUN SUBCATEGORY TEXT",
                        },
                        "video": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://youtube.com/watch?v=example",
                            "description": "VIDEO URL",
                        },
                        "date": {
                            "type": "string",
                            "format": "date",
                            "example": "2025-08-15",
                            "description": "RUN DATE",
                        },
                        "variable_values": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                            "example": {"5lygdn8q": "pc"},
                            "description": "VARIABLE ID TO VALUE ID MAPPING",
                        },
                    },
                },
                "example": {
                    "game_id": "n2680o1p",
                    "category_id": "rklge08d",
                    "player_id": "v8lponvj",
                    "time": "12:34.567",
                    "runtype": "main",
                    "subcategory": "Normal, PC",
                    "video": "https://youtube.com/watch?v=example",
                    "date": "2025-08-15",
                    "variable_values": {"5lygdn8q": "pc"},
                },
            }
        },
    },
}

RUNS_PUT = {
    "responses": {
        200: {
            "description": "Run updated successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "21q4tfg34f34",
                        "time": "12:34.567",
                        "place": 1,
                        "runtype": "main",
                        "subcategory": "Any% (Normal)",
                        "video": "https://youtube.com/watch?v=example",
                        "url": "https://speedrun.com/thps4/run/21q4tfg34f34",
                        "date": "2025-08-15",
                        "v_date": "2025-08-15T10:30:00Z",
                        "vid_status": "new",
                        "obsolete": False,
                    }
                }
            },
        },
        400: {
            "description": "Invalid request data, game/category/level/player does not exist."
        },
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Run does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "y8dwozoj",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Run ID to update",
        },
    ],
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "example": "n2680o1p",
                            "description": "UPDATED GAME ID",
                        },
                        "category_id": {
                            "type": "string",
                            "example": "rklge08d",
                            "description": "UPDATED CATEGORY ID",
                        },
                        "level_id": {
                            "type": "string",
                            "example": "592pxj8d",
                            "description": "UPDATED LEVEL ID",
                        },
                        "player_id": {
                            "type": "string",
                            "example": "v8lponvj",
                            "description": "UPDATED PRIMARY PLAYER ID",
                        },
                        "player2_id": {
                            "type": "string",
                            "example": "x81m29qk",
                            "description": "UPDATED SECOND PLAYER ID",
                        },
                        "time": {
                            "type": "string",
                            "example": "12:34.567",
                            "description": "UPDATED RUN TIME",
                        },
                        "runtype": {
                            "type": "string",
                            "enum": ["main", "il"],
                            "example": "main",
                            "description": "UPDATED RUN TYPE",
                        },
                        "subcategory": {
                            "type": "string",
                            "example": "Normal, PC",
                            "description": "UPDATED SUBCATEGORY",
                        },
                        "video": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://youtube.com/watch?v=example",
                            "description": "UPDATED VIDEO URL",
                        },
                        "date": {
                            "type": "string",
                            "format": "date",
                            "example": "2025-08-15",
                            "description": "UPDATED RUN DATE",
                        },
                        "vid_status": {
                            "type": "string",
                            "enum": ["new", "verified", "rejected"],
                            "example": "verified",
                            "description": "UPDATED VERIFICATION STATUS",
                        },
                        "variable_values": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                            "example": {"5lygdn8q": "pc"},
                            "description": "UPDATED VARIABLE VALUES",
                        },
                    },
                },
                "example": {
                    "time": "12:30.000",
                    "video": "https://youtube.com/watch?v=newvideo",
                    "vid_status": "verified",
                },
            }
        },
    },
}

RUNS_DELETE = {
    "responses": {
        200: {
            "description": "Run deleted successfully!",
            "content": {
                "application/json": {"example": {"message": "Run deleted successfully"}}
            },
        },
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Run does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "y8dwozoj",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Run ID to delete",
        },
    ],
}

RUNS_ALL = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "y8dwozoj",
                            "time": "12:34.567",
                            "place": 1,
                            "runtype": "main",
                            "subcategory": "Any% (No Major Glitches)",
                            "video": "https://youtube.com/watch?v=example",
                            "url": "https://speedrun.com/thps4/run/y8dwozoj",
                            "date": "2025-08-15",
                            "v_date": "2025-08-15T10:30:00Z",
                            "vid_status": "verified",
                            "obsolete": False,
                        },
                        {
                            "id": "z9fxpakl",
                            "time": "13:45.123",
                            "place": 2,
                            "runtype": "main",
                            "subcategory": "Any% (No Major Glitches)",
                            "video": "https://youtube.com/watch?v=example2",
                            "url": "https://speedrun.com/thps4/run/z9fxpakl",
                            "date": "2025-01-14",
                            "v_date": "2025-01-14T15:20:00Z",
                            "vid_status": "verified",
                            "obsolete": False,
                        },
                    ]
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "game_id",
            "in": "query",
            "example": "thps4",
            "schema": {"type": "string"},
            "description": "Filter by game",
        },
        {
            "name": "category_id",
            "in": "query",
            "example": "rklge08d",
            "schema": {"type": "string"},
            "description": "Filter by category",
        },
        {
            "name": "level_id",
            "in": "query",
            "example": "592pxj8d",
            "schema": {"type": "string"},
            "description": "Filter by level",
        },
        {
            "name": "player_id",
            "in": "query",
            "example": "v8lponvj",
            "schema": {"type": "string"},
            "description": "Filter by player",
        },
        {
            "name": "runtype",
            "in": "query",
            "example": "main",
            "schema": {"type": "string", "pattern": "^(main|il)$"},
            "description": "Filter by run type",
        },
        {
            "name": "place",
            "in": "query",
            "example": 1,
            "schema": {"type": "integer", "minimum": 1},
            "description": "Filter by place",
        },
        {
            "name": "status",
            "in": "query",
            "example": "verified",
            "schema": {"type": "string", "pattern": "^(verified|new|rejected)$"},
            "description": "Filter by status",
        },
        {
            "name": "search",
            "in": "query",
            "example": "normal",
            "schema": {"type": "string"},
            "description": "Search subcategory text",
        },
        {
            "name": "embed",
            "in": "query",
            "example": "game,category,players",
            "schema": {"type": "string"},
            "description": "Comma-separated embeds",
        },
        {
            "name": "limit",
            "in": "query",
            "example": 50,
            "schema": {"type": "integer", "minimum": 1, "maximum": 100},
            "description": "Results per page (default 50, max 100)",
        },
        {
            "name": "offset",
            "in": "query",
            "example": 0,
            "schema": {"type": "integer", "minimum": 0},
            "description": "Results to skip (default 0)",
        },
    ],
}
