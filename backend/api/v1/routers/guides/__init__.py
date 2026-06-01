from api.v1.routers.guides.guides import router as guides_router
from api.v1.routers.guides.tags import router as tags_router

__all__ = [
    "guides_router",
    "tags_router",
]
