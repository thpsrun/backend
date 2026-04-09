from django.http import HttpRequest
from ninja import Router, Status
from ninja.responses import codes_4xx

from api.permissions import public_auth
from api.v1.docs.nav import NAVBAR_GET
from api.v1.routers.utils import cache_response, navbar_cache_key
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.nav import NavbarResponse, NavItemSchema, SocialLinkSchema
from nav.models import NavItem, SocialLink

router = Router()


def _sorted_for_display(items: list, key: str = "name") -> list:
    """Sort items: order>=1 first ascending, then order=0 alphabetically by key."""
    ordered = sorted([i for i in items if i.order > 0], key=lambda x: x.order)
    unordered = sorted([i for i in items if i.order == 0], key=lambda x: getattr(x, key))
    return ordered + unordered


def _build_nav_tree() -> list[NavItemSchema]:
    """Fetch all visible NavItems and build a nested tree."""
    all_items = list(NavItem.objects.filter(is_visible=True))

    children_map: dict[int | None, list[NavItem]] = {}
    for item in all_items:
        children_map.setdefault(item.parent_id, []).append(item)

    def build_children(parent_id: int | None) -> list[NavItemSchema]:
        items = children_map.get(parent_id, [])
        sorted_items = _sorted_for_display(items)
        return [
            NavItemSchema(
                name=item.name,
                url=item.url,
                children=build_children(item.pk),
            )
            for item in sorted_items
        ]

    return build_children(None)


def _build_social_links() -> list[SocialLinkSchema]:
    """Fetch all visible SocialLinks, sorted."""
    items = list(SocialLink.objects.filter(is_visible=True))
    sorted_items = _sorted_for_display(items, key="platform")
    return [
        SocialLinkSchema(
            platform=item.platform,
            url=item.url,
        )
        for item in sorted_items
    ]


def _navbar_cache_key(request: HttpRequest) -> str:
    """Wrapper matching the cache_response key_function signature."""
    return navbar_cache_key()


@router.get(
    "/navbar",
    response={200: NavbarResponse, codes_4xx: ErrorResponse, 500: ErrorResponse},
    summary="Get Navbar Data",
    description=(
        "Get the full navigation tree and social media links for the website. "
        "Returns a pre-built nested structure ready for frontend rendering. "
        "This endpoint is heavily cached and only changes when nav items "
        "are modified in the admin."
    ),
    auth=public_auth,
    openapi_extra=NAVBAR_GET,
)
@cache_response(
    timeout=300,
    key_function=_navbar_cache_key,
)
def get_navbar(
    request: HttpRequest,
) -> Status:
    try:
        return Status(
            200,
            NavbarResponse(
                nav=_build_nav_tree(),
                social=_build_social_links(),
            ),
        )
    except Exception as e:
        return Status(
            500,
            ErrorResponse(
                error="Server error!",
                details={"exception": str(e)},
            ),
        )
