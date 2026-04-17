LEVELS_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "592pxj8d",
                        "name": "Alcatraz",
                        "slug": "alcatraz",
                        "url": "https://speedrun.com/thps34/individual_levels#Alcatraz",
                        "rules": "",
                        "game": {
                            "id": "n2680o1p",
                            "name": "Tony Hawk's Pro Skater 3+4",
                            "slug": "thps34",
                            "release": "2002-10-23",
                            "boxart": "https://example.com/boxart.jpg",
                            "twitch": "Tony Hawk's Pro Skater 3+4",
                            "defaulttime": "realtime",
                            "idefaulttime": "realtime",
                            "pointsmax": 1000,
                            "ipointsmax": 100,
                        },
                        "variables": [
                            {
                                "id": "5lygdn8q",
                                "name": "Platform",
                                "slug": "platform",
                                "scope": "single-level",
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
                    }
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        404: {"description": "Level could not be found."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "592pxj8d",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Level ID",
        },
    ],
}

LEVELS_POST = {
    "responses": {
        201: {
            "description": "Level created successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "592pxj8d",
                        "name": "Alcatraz",
                        "slug": "alcatraz",
                        "url": "https://speedrun.com/thps34/individual_levels#Alcatraz",
                        "rules": "Rulez.",
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
                            "example": "Alcatraz",
                            "description": "LEVEL NAME",
                        },
                        "game_id": {
                            "type": "string",
                            "example": "n2680o1p",
                            "description": "GAME ID THIS LEVEL BELONGS TO",
                        },
                        "rules": {
                            "type": "string",
                            "example": "Rulez.",
                            "description": "LEVEL RULES",
                        },
                    },
                },
                "example": {
                    "name": "Alcatraz",
                    "game_id": "n2680o1p",
                    "rules": "Rulez.",
                },
            }
        },
    },
}

LEVELS_PUT = {
    "responses": {
        200: {
            "description": "Level updated successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "592pxj8d",
                        "name": "Alcatraz",
                        "slug": "alcatraz",
                        "url": "https://speedrun.com/thps4/individual_levels#Alcatraz",
                        "rules": "Rulez.",
                    }
                }
            },
        },
        400: {"description": "Invalid request data or game does not exist."},
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Level does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "592pxj8d",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Level ID to update",
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
                            "example": "Alcatraz",
                            "description": "UPDATED LEVEL NAME",
                        },
                        "game_id": {
                            "type": "string",
                            "example": "n2680o1p",
                            "description": "UPDATED GAME ID",
                        },
                        "rules": {
                            "type": "string",
                            "example": "Rulez.",
                            "description": "UPDATED LEVEL RULES",
                        },
                    },
                },
                "example": {
                    "name": "Alcatraz Updated",
                    "rules": "Rulez.",
                },
            }
        },
    },
}

LEVELS_DELETE = {
    "responses": {
        200: {
            "description": "Level deleted successfully!",
            "content": {
                "application/json": {
                    "example": {"message": "Level 'Alcatraz' deleted successfully"}
                }
            },
        },
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Level does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "592pxj8d",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Level ID to delete",
        },
    ],
}

LEVELS_ALL = {
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
                            "url": "https://speedrun.com/thps34/individual_levels#Alcatraz",
                            "rules": "Rulez.",
                        },
                        {
                            "id": "29vjx18k",
                            "name": "Kona",
                            "slug": "kona",
                            "url": "https://speedrun.com/thps34/individual_levels#Kona",
                            "rules": "Rulez.",
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
