PLAYERS_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "v8lponvj",
                        "name": "ThePackle",
                        "nickname": "ThePackle",
                        "url": "https://speedrun.com/user/ThePackle",
                        "pronouns": "he/him",
                        "twitch": "https://twitch.tv/thepackle",
                        "youtube": "https://youtube.com/thepackle",
                        "twitter": "https://twitter.com/thepackle",
                        "bluesky": "https://bsky.app/profile/@thepackle.bsky.social",
                        "discord": "discordusername",
                        "ex_stream": False,
                        "joined": "2025-08-15",
                        "country": {"id": "us", "name": "United States"},
                        "awards": [
                            {
                                "name": "thps.run Admin",
                                "description": "He's the admin!!",
                                "image": "https://example.com/award.png",
                            }
                        ],
                        "runs": [
                            {
                                "id": "y8dwozoj",
                                "game": "Tony Hawk's Pro Skater 4",
                                "category": "Any%",
                                "level": None,
                                "place": 1,
                                "time": "12:34.567",
                                "date": "2025-08-15T10:30:00Z",
                                "video": "https://youtube.com/watch?v=example",
                            }
                        ],
                        "moderated_games": [
                            {
                                "id": "thps4",
                                "name": "Tony Hawk's Pro Skater 4",
                                "slug": "thps4",
                            }
                        ],
                    }
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        404: {"description": "Player could not be found."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "v8lponvj",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Player ID",
        },
        {
            "name": "embed",
            "in": "query",
            "example": "country,awards,runs",
            "schema": {"type": "string"},
            "description": "Comma-separated embeds: country, awards, runs",
        },
    ],
}

PLAYERS_POST = {
    "responses": {
        201: {
            "description": "Player created successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "v8lponvj",
                        "name": "ThePackle",
                        "nickname": "ThePackle",
                        "url": "https://speedrun.com/user/ThePackle",
                        "pronouns": "he/him",
                        "twitch": "https://twitch.tv/thepackle",
                        "youtube": "https://youtube.com/thepackle",
                        "twitter": "https://twitter.com/thepackle",
                        "bluesky": "https://bsky.app/profile/thepackle",
                        "discord": "discordusername",
                        "ex_stream": False,
                        "joined": "2025-08-15",
                    }
                }
            },
        },
        400: {"description": "Invalid request data or country does not exist."},
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
                    "required": ["name"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "example": "ThePackle",
                            "description": "PLAYER NAME",
                        },
                        "nickname": {
                            "type": "string",
                            "example": "ThePackle",
                            "description": "PLAYER NICKNAME",
                        },
                        "country_id": {
                            "type": "string",
                            "example": "us",
                            "description": "COUNTRY CODE ID",
                        },
                        "pronouns": {
                            "type": "string",
                            "example": "he/him",
                            "description": "PLAYER PRONOUNS",
                        },
                        "twitch": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://twitch.tv/thepackle",
                            "description": "TWITCH URL",
                        },
                        "youtube": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://youtube.com/thepackle",
                            "description": "YOUTUBE URL",
                        },
                        "twitter": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://twitter.com/thepackle",
                            "description": "TWITTER URL",
                        },
                        "bluesky": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://bsky.app/profile/thepackle",
                            "description": "BLUESKY URL",
                        },
                        "discord": {
                            "type": "string",
                            "example": "discord.username",
                            "description": "DISCORD USERNAME",
                        },
                    },
                },
                "example": {
                    "name": "ThePackle",
                    "nickname": "ThePackle",
                    "country_id": "us",
                    "pronouns": "he/him",
                    "twitch": "https://twitch.tv/thepackle",
                },
            }
        },
    },
}

PLAYERS_PUT = {
    "responses": {
        200: {
            "description": "Player updated successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "v8lponvj",
                        "name": "ThePackle",
                        "nickname": "ThePackle",
                        "url": "https://speedrun.com/user/ThePackle",
                        "pronouns": "he/him",
                        "twitch": "https://twitch.tv/thepackle",
                        "youtube": "https://youtube.com/thepackle",
                        "twitter": "https://twitter.com/thepackle",
                        "bluesky": "https://bsky.app/profile/@thepackle.bsky.social",
                        "ex_stream": False,
                        "joined": "2025-08-15",
                    }
                }
            },
        },
        400: {"description": "Invalid request data or country does not exist."},
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Player does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "v8lponvj",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Player ID to update",
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
                            "example": "ThePackle",
                            "description": "UPDATED PLAYER NAME",
                        },
                        "nickname": {
                            "type": "string",
                            "example": "ThePackle",
                            "description": "UPDATED PLAYER NICKNAME",
                        },
                        "country_id": {
                            "type": "string",
                            "example": "us",
                            "description": "UPDATED COUNTRY CODE ID",
                        },
                        "pronouns": {
                            "type": "string",
                            "example": "he/him",
                            "description": "UPDATED PLAYER PRONOUNS",
                        },
                        "twitch": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://twitch.tv/thepackle",
                            "description": "UPDATED TWITCH URL",
                        },
                        "youtube": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://youtube.com/thepackle",
                            "description": "UPDATED YOUTUBE URL",
                        },
                        "twitter": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://twitter.com/thepackle",
                            "description": "UPDATED TWITTER URL",
                        },
                        "bluesky": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://bsky.app/profile/thepackle",
                            "description": "UPDATED BLUESKY URL",
                        },
                        "discord": {
                            "type": "string",
                            "example": "discord.username",
                            "description": "DISCORD USERNAME",
                        },
                    },
                },
                "example": {"nickname": "NewNickname", "pronouns": "they/them"},
            }
        },
    },
}

PLAYERS_DELETE = {
    "responses": {
        200: {
            "description": "Player deleted successfully!",
            "content": {
                "application/json": {
                    "example": {"message": "Player 'ThePackle' deleted successfully"}
                }
            },
        },
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Player does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "v8lponvj",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Player ID to delete",
        },
    ],
}

PLAYERS_ALL = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "v8lponvj",
                            "name": "ThePackle",
                            "nickname": "ThePackle",
                            "url": "https://speedrun.com/user/ThePackle",
                            "pronouns": "he/him",
                            "twitch": "https://twitch.tv/thepackle",
                            "youtube": "https://youtube.com/thepackle",
                            "twitter": "https://twitter.com/thepackle",
                            "bluesky": "https://bsky.app/profile/@thepackle.bsky.social",
                            "discord": "discordusername",
                            "joined": "2023-03-12",
                        },
                        {
                            "id": "x81m29qk",
                            "name": "SpeedRunner123",
                            "nickname": "SpeedRunner123",
                            "url": "https://speedrun.com/user/SpeedRunner123",
                            "pronouns": "they/them",
                            "twitch": "https://twitch.tv/speedrunner123",
                            "youtube": None,
                            "twitter": None,
                            "bluesky": None,
                            "discord": None,
                            "joined": "2023-03-11",
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
            "name": "country",
            "in": "query",
            "example": "us",
            "schema": {"type": "string"},
            "description": "Filter by country code",
        },
        {
            "name": "search",
            "in": "query",
            "example": "ThePackle",
            "schema": {"type": "string"},
            "description": "Search by name",
        },
        {
            "name": "embed",
            "in": "query",
            "example": "country,awards",
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
