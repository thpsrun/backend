STREAMS_LIVE = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "player": {"id": "player1", "name": "SpeedRunner123"},
                            "game": {"id": "thps4", "name": "Tony Hawk's Pro Skater 4"},
                            "title": "WRWRWRWRWRWRWR",
                            "url": "https://twitch.tv/speedrunner123",
                            "started_at": "2025-08-15T08:30:00Z",
                        },
                        {
                            "player": {"id": "player2", "name": "THPS Man"},
                            "game": {"id": "thps2", "name": "Tony Hawk's Pro Skater 2"},
                            "title": "Practice",
                            "url": "https://twitch.tv/thpsman",
                            "started_at": "2025-08-15T09:45:00Z",
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

STREAMS_GAME = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "player": {"id": "player1", "name": "SpeedRunner123"},
                            "game": {"id": "thps4", "name": "Tony Hawk's Pro Skater 4"},
                            "title": "WRWRWRWRWRWRWRWRWR",
                            "url": "https://twitch.tv/speedrunner123",
                            "started_at": "2025-08-15T08:30:00Z",
                        }
                    ]
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        404: {"description": "Game not found."},
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

STREAMS_PLAYER = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "player": {
                            "id": "v8lponvj",
                            "name": "ThePackle",
                            "twitch": "https://twitch.tv/thepackle",
                            "youtube": "https://youtube.com/thepackle",
                        },
                        "is_live": True,
                        "current_stream": {
                            "player": {"id": "v8lponvj", "name": "ThePackle"},
                            "game": {"id": "thps4", "name": "Tony Hawk's Pro Skater 4"},
                            "title": "Any% WR",
                            "url": "https://twitch.tv/thepackle",
                            "started_at": "2025-08-15T08:30:00Z",
                        },
                        "ex_stream": False,
                    }
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        404: {"description": "Player not found."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "player_id",
            "in": "path",
            "required": True,
            "example": "v8lponvj",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Player ID",
        },
    ],
}

STREAMS_POST = {
    "responses": {
        201: {
            "description": "Stream created successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "player": {"id": "v8lponvj", "name": "ThePackle"},
                        "game": {"id": "n2680o1p", "name": "Tony Hawk's Pro Skater 4"},
                        "title": "Going for Any% WR",
                        "offline_ct": 0,
                        "stream_time": "2025-08-15T08:30:00Z",
                    }
                }
            },
        },
        400: {"description": "Invalid request data or player/game does not exist."},
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
                    "required": ["player_id", "title"],
                    "properties": {
                        "player_id": {
                            "type": "string",
                            "example": "v8lponvj",
                            "description": "Player ID of the streamer",
                        },
                        "game_id": {
                            "type": "string",
                            "example": "n2680o1p",
                            "description": "Game being played (optional)",
                        },
                        "title": {
                            "type": "string",
                            "example": "Going for Any% WR",
                            "description": "Stream title from Twitch",
                        },
                        "offline_ct": {
                            "type": "integer",
                            "example": 0,
                            "description": "Failed API checks before marking offline",
                        },
                        "stream_time": {
                            "type": "string",
                            "format": "date-time",
                            "example": "2025-08-15T08:30:00Z",
                            "description": "When the stream started (optional)",
                        },
                    },
                },
                "example": {
                    "player_id": "v8lponvj",
                    "game_id": "n2680o1p",
                    "title": "Going for Any% WR",
                    "offline_ct": 0,
                    "stream_time": "2025-08-15T08:30:00Z",
                },
            }
        },
    },
}

STREAMS_PUT = {
    "responses": {
        200: {
            "description": "Stream updated successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "player": {"id": "v8lponvj", "name": "ThePackle"},
                        "game": {"id": "n2680o1p", "name": "Tony Hawk's Pro Skater 4"},
                        "title": "100% Speedrun Practice",
                        "offline_ct": 1,
                        "stream_time": "2025-08-15T08:30:00Z",
                    }
                }
            },
        },
        400: {"description": "Invalid request data or game does not exist."},
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Stream does not exist for this player."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "player_id",
            "in": "path",
            "required": True,
            "example": "v8lponvj",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Player ID to update stream for",
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
                            "description": "Updated game ID",
                        },
                        "title": {
                            "type": "string",
                            "example": "100% Speedrun Practice",
                            "description": "Updated stream title",
                        },
                        "offline_ct": {
                            "type": "integer",
                            "example": 1,
                            "description": "Updated offline counter",
                        },
                        "stream_time": {
                            "type": "string",
                            "format": "date-time",
                            "example": "2025-08-15T08:30:00Z",
                            "description": "Updated stream start time",
                        },
                    },
                },
                "example": {
                    "title": "100% Speedrun Practice",
                    "offline_ct": 1,
                },
            }
        },
    },
}

STREAMS_DELETE = {
    "responses": {
        200: {
            "description": "Stream deleted successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Stream for player 'ThePackle' deleted successfully"
                    }
                }
            },
        },
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Stream does not exist for this player."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "player_id",
            "in": "path",
            "required": True,
            "example": "v8lponvj",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Player ID to delete stream for",
        },
    ],
}
