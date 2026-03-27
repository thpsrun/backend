NAVBAR_GET = {
    "responses": {
        200: {
            "description": "Success!",
            "content": {
                "application/json": {
                    "example": {
                        "nav": [
                            {
                                "name": "Neversoft Games",
                                "url": None,
                                "children": [
                                    {
                                        "name": "THPS1",
                                        "url": "/games/thps1",
                                        "children": [],
                                    },
                                    {
                                        "name": "THPS2",
                                        "url": "/games/thps2",
                                        "children": [],
                                    },
                                    {
                                        "name": "THPS3",
                                        "url": "/games/thps3",
                                        "children": [],
                                    },
                                ],
                            },
                            {
                                "name": "Resources",
                                "url": None,
                                "children": [
                                    {
                                        "name": "Guides",
                                        "url": "/guides",
                                        "children": [],
                                    },
                                    {
                                        "name": "Leaderboards",
                                        "url": "/leaderboards",
                                        "children": [],
                                    },
                                ],
                            },
                        ],
                        "social": [
                            {
                                "platform": "Discord",
                                "url": "https://discord.gg/example",
                            },
                            {
                                "platform": "Twitter",
                                "url": "https://twitter.com/example",
                            },
                        ],
                    }
                }
            },
        },
        429: {"description": "Rate limit exceeded, calm your horses."},
        500: {"description": "Server Error. Error is logged."},
    },
}
