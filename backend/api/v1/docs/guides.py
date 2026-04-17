GUIDES_ALL = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "1234",
                            "title": "THPS4 Guide",
                            "slug": "thps4-guide",
                            "game": "thps4",
                            "tags": ["tricks", "beginner", "TAS"],
                            "short_description": "Learn the basics of THPS4!",
                            "created_at": "2025-08-15T10:30:00Z",
                            "updated_at": "2025-08-15T10:30:00Z",
                        }
                    ]
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        404: {"description": "Guide could not be found."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "embed",
            "in": "embed",
            "example": "game",
            "schema": {"pattern": "^[a-z0-9-]+$"},
        },
    ],
}

GUIDES_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "1234",
                        "title": "THPS4 Guide",
                        "slug": "thps4-guide",
                        "game": "thps4",
                        "tags": ["tricks", "beginner", "TAS"],
                        "short_description": "Learn the basics in THPS4!",
                        "content": "# Basics\n\nBlah blah blah...",
                        "created_at": "2025-08-15T10:30:00Z",
                        "updated_at": "2025-08-15T10:30:00Z",
                    }
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        404: {"description": "Guide could not be found."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "embed",
            "in": "embed",
            "example": "game",
            "schema": {"pattern": "^[a-z0-9-]+$"},
        },
    ],
}

GUIDES_POST = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "1234",
                        "title": "THPS4 Guide",
                        "slug": "thps4-guide",
                        "game": "thps4",
                        "tags": ["tricks", "beginner", "TAS"],
                        "short_description": "Learn the basics in THPS4!",
                        "content": "# Basics\n\nBlah blah blah...",
                        "created_at": "2025-08-15T10:30:00Z",
                        "updated_at": "2025-08-15T10:30:00Z",
                    }
                }
            },
        },
        400: {"description": "Invalid response sent to server."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "requestBody": {
        "content": {
            "application/json": {
                "example": {
                    "title": "THPS4 Guide",
                    "slug": "thps4-guide",
                    "game": "thps4",
                    "tags": ["tricks", "beginner", "TAS"],
                    "short_description": "Learn the basics in THPS4!",
                    "content": "# Basics\n\nBlah blah blah...",
                }
            }
        }
    },
}

GUIDES_PUT = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "id": "1234",
                        "title": "THPS4 Guide",
                        "slug": "thps4-guide",
                        "game": "thps4",
                        "tags": ["tricks", "beginner", "TAS"],
                        "short_description": "Learn the advanced in THPS4!",
                        "content": "# Advanced\n\nBlah blah blah...",
                        "created_at": "2025-08-15T10:30:00Z",
                        "updated_at": "2025-08-15T13:30:00Z",
                    }
                }
            },
        },
        404: {"description": "Guide does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "requestBody": {
        "content": {
            "application/json": {
                "example": {
                    "title": "THPS4 Guide",
                    "slug": "thps4-guide",
                    "game": "thps4",
                    "tags": ["tricks", "beginner", "TAS"],
                    "short_description": "Learn the advanced tricks in THPS4!",
                    "content": "# Advanced\n\nBlah blah blah...",
                }
            }
        }
    },
}

GUIDES_DELETE = {
    "responses": {
        200: {
            "description": "Guide deleted successfully!",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Guide 'THPS4 Red Goals Guide' deleted successfully"
                    }
                }
            },
        },
        401: {"description": "API key required for this operation."},
        403: {"description": "Insufficient permissions (contributor required)."},
        404: {"description": "Tag does not exist."},
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
    "parameters": [
        {
            "name": "slug",
            "in": "path",
            "required": True,
            "example": "thps4-red-goals-guide",
            "schema": {"type": "string", "maxLength": 200},
            "description": "Guide slug to delete",
        },
    ],
}
