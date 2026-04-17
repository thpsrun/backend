PLATFORMS_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {"id": "8gej2n3z", "name": "PC", "slug": "pc"}
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        404: {"description": "Platform could not be found."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "8gej2n3z",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Platform ID",
        },
    ],
}

PLATFORMS_POST = {
    "responses": {
        201: {
            "description": "Platform created successfully!",
            "content": {
                "application/json": {
                    "example": {"id": "8gej2n3z", "name": "PC", "slug": "pc"}
                }
            },
        },
        400: {"description": "Invalid request data."},
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
                            "example": "PC",
                            "description": "PLATFORM NAME",
                        }
                    },
                },
                "example": {"name": "PC"},
            }
        },
    },
}

PLATFORMS_PUT = {
    "responses": {
        200: {
            "description": "Platform updated successfully!",
            "content": {
                "application/json": {
                    "example": {"id": "8gej2n3z", "name": "PC", "slug": "pc"}
                }
            },
        },
        400: {"description": "Invalid request data."},
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Platform does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "8gej2n3z",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Platform ID to update",
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
                            "example": "PC",
                            "description": "UPDATED PLATFORM NAME",
                        }
                    },
                },
                "example": {"name": "PC Updated"},
            }
        },
    },
}

PLATFORMS_DELETE = {
    "responses": {
        200: {
            "description": "Platform deleted successfully!",
            "content": {
                "application/json": {
                    "example": {"message": "Platform 'PC' deleted successfully"}
                }
            },
        },
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions."},
        404: {"description": "Platform does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "id",
            "in": "path",
            "required": True,
            "example": "8gej2n3z",
            "schema": {"type": "string", "maxLength": 15},
            "description": "Platform ID to delete",
        },
    ],
}

PLATFORMS_ALL = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": [
                        {"id": "8gej2n3z", "name": "PC", "slug": "pc"},
                        {"id": "nzelreqy", "name": "PlayStation 2", "slug": "ps2"},
                    ]
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
}
