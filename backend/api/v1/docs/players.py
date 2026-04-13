PLAYERS_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "v8lponvj",
                        "url": "https://speedrun.com/user/ThePackle",
                        "joined": "2025-08-15",
                        "player": {
                            "name": "ThePackle",
                            "nickname": "ThePackle",
                            "pronouns": "he/him",
                            "country": {
                                "id": "us",
                                "name": "United States",
                                "flag": None,
                            },
                            "pfp": "/media/pfp/v8lponvj.jpg",
                            "ex_stream": False,
                        },
                        "socials": {
                            "twitch": "https://twitch.tv/thepackle",
                            "youtube": "https://youtube.com/thepackle",
                            "twitter": "https://twitter.com/thepackle",
                            "bluesky": "https://bsky.app/profile/@thepackle.bsky.social",
                            "discord": "discordusername",
                        },
                        "customizations": {
                            "gradient_1": "#ff0044",
                            "gradient_2": "#00aaff",
                            "gradient_3": None,
                            "bio": "I run Tony Hawk games fast.",
                            "short_bio": "THPS speedrunner",
                            "profile_bg": None,
                        },
                        "stats": {
                            "total_runs": 42,
                            "fg_points": 500,
                            "il_points": 1200,
                            "awards": [
                                {
                                    "name": "thps.run Admin",
                                    "description": "He's the admin!!",
                                    "image": "https://example.com/award.png",
                                }
                            ],
                        },
                        "runs": {
                            "recent": [
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
                                    "subcategory": "Any%",
                                    "level": None,
                                    "place": 1,
                                    "points": 50,
                                    "time": "12m 34s 567ms",
                                    "date": "2025-08-15T10:30:00+00:00",
                                    "url": "https://www.speedrun.com/thps4/run/y8dwozoj",
                                    "video": "https://youtube.com/watch?v=example",
                                    "arch_video": None,
                                    "obsolete": False,
                                    "value_slugs": [],
                                }
                            ],
                            "fg": None,
                            "il": None,
                        },
                        "moderation": {
                            "moderated_games": [
                                {
                                    "id": "thps4",
                                    "name": "Tony Hawk's Pro Skater 4",
                                    "slug": "thps4",
                                }
                            ],
                        },
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
            "example": "country,stats,awards,runs",
            "schema": {"type": "string"},
            "description": (
                "Comma-separated embeds: country, stats, awards,"
                " runs, profile, profile-obsolete"
            ),
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
                        "url": "https://speedrun.com/user/ThePackle",
                        "joined": None,
                        "player": {
                            "name": "ThePackle",
                            "nickname": "ThePackle",
                            "pronouns": "he/him",
                            "country": None,
                            "pfp": None,
                            "ex_stream": False,
                        },
                        "socials": {
                            "twitch": "https://twitch.tv/thepackle",
                            "youtube": None,
                            "twitter": None,
                            "bluesky": None,
                            "discord": None,
                        },
                        "customizations": {
                            "gradient_1": None,
                            "gradient_2": None,
                            "gradient_3": None,
                            "bio": None,
                            "short_bio": None,
                            "profile_bg": None,
                        },
                        "stats": {
                            "total_runs": None,
                            "fg_points": None,
                            "il_points": None,
                            "awards": None,
                        },
                        "runs": {
                            "recent": None,
                            "fg": None,
                            "il": None,
                        },
                        "moderation": {
                            "moderated_games": None,
                        },
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
                    "required": ["url", "player"],
                    "properties": {
                        "id": {
                            "type": "string",
                            "example": "v8lponvj",
                            "description": "Player ID (auto-generates if omitted)",
                        },
                        "url": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://speedrun.com/user/ThePackle",
                            "description": "SPEEDRUN.COM PROFILE URL",
                        },
                        "player": {
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
                                "pfp": {
                                    "type": "string",
                                    "example": "/media/pfp/v8lponvj.jpg",
                                    "description": "PROFILE PICTURE PATH",
                                },
                                "ex_stream": {
                                    "type": "boolean",
                                    "example": False,
                                    "description": "EXCLUDE FROM STREAMING",
                                },
                            },
                        },
                        "socials": {
                            "type": "object",
                            "properties": {
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
                    },
                },
                "example": {
                    "url": "https://speedrun.com/user/ThePackle",
                    "player": {
                        "name": "ThePackle",
                        "nickname": "ThePackle",
                        "country_id": "us",
                        "pronouns": "he/him",
                    },
                    "socials": {
                        "twitch": "https://twitch.tv/thepackle",
                    },
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
                        "url": "https://speedrun.com/user/ThePackle",
                        "joined": "2025-08-15",
                        "player": {
                            "name": "ThePackle",
                            "nickname": "NewNickname",
                            "pronouns": "they/them",
                            "country": None,
                            "pfp": None,
                            "ex_stream": False,
                        },
                        "socials": {
                            "twitch": "https://twitch.tv/thepackle",
                            "youtube": None,
                            "twitter": None,
                            "bluesky": None,
                            "discord": None,
                        },
                        "customizations": {
                            "gradient_1": None,
                            "gradient_2": None,
                            "gradient_3": None,
                            "bio": None,
                            "short_bio": None,
                            "profile_bg": None,
                        },
                        "stats": {
                            "total_runs": None,
                            "fg_points": None,
                            "il_points": None,
                            "awards": None,
                        },
                        "runs": {
                            "recent": None,
                            "fg": None,
                            "il": None,
                        },
                        "moderation": {
                            "moderated_games": None,
                        },
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
                        "url": {
                            "type": "string",
                            "format": "uri",
                            "example": "https://speedrun.com/user/ThePackle",
                            "description": "UPDATED SPEEDRUN.COM URL",
                        },
                        "player": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "example": "ThePackle",
                                    "description": "UPDATED PLAYER NAME",
                                },
                                "nickname": {
                                    "type": "string",
                                    "example": "NewNickname",
                                    "description": "UPDATED PLAYER NICKNAME",
                                },
                                "country_id": {
                                    "type": "string",
                                    "example": "us",
                                    "description": "UPDATED COUNTRY CODE ID",
                                },
                                "pronouns": {
                                    "type": "string",
                                    "example": "they/them",
                                    "description": "UPDATED PLAYER PRONOUNS",
                                },
                                "pfp": {
                                    "type": "string",
                                    "example": "/media/pfp/v8lponvj.jpg",
                                    "description": "UPDATED PROFILE PICTURE",
                                },
                                "ex_stream": {
                                    "type": "boolean",
                                    "example": False,
                                    "description": "UPDATED STREAMING EXCLUSION",
                                },
                            },
                        },
                        "socials": {
                            "type": "object",
                            "properties": {
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
                                    "description": "UPDATED DISCORD USERNAME",
                                },
                            },
                        },
                    },
                },
                "example": {
                    "player": {
                        "nickname": "NewNickname",
                        "pronouns": "they/them",
                    },
                },
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
                            "url": "https://speedrun.com/user/ThePackle",
                            "joined": "2023-03-12",
                            "player": {
                                "name": "ThePackle",
                                "nickname": "ThePackle",
                                "pronouns": "he/him",
                                "country": None,
                                "pfp": None,
                                "ex_stream": False,
                            },
                            "socials": {
                                "twitch": "https://twitch.tv/thepackle",
                                "youtube": "https://youtube.com/thepackle",
                                "twitter": "https://twitter.com/thepackle",
                                "bluesky": "https://bsky.app/profile/@thepackle.bsky.social",
                                "discord": "discordusername",
                            },
                            "customizations": {
                                "gradient_1": None,
                                "gradient_2": None,
                                "gradient_3": None,
                                "bio": None,
                                "short_bio": None,
                                "profile_bg": None,
                            },
                            "stats": {
                                "total_runs": None,
                                "fg_points": None,
                                "il_points": None,
                                "awards": None,
                            },
                            "runs": {
                                "recent": None,
                                "fg": None,
                                "il": None,
                            },
                            "moderation": {
                                "moderated_games": None,
                            },
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
