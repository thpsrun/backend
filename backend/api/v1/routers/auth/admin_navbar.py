from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from nav.models import NavItem, SocialLink
from nav.services import (
    create_nav_item,
    create_social_link,
    delete_nav_item,
    delete_social_link,
    get_navbar_state,
    reorder_nav_items,
    reorder_social_links,
    update_nav_item,
    update_social_link,
)
from ninja import Router, Status
from ninja.errors import HttpError

from api.permissions import authed
from api.v1.schemas.base import ErrorResponse
from api.v1.schemas.navbar_admin import (
    NavbarAdminItem,
    NavbarAdminSocial,
    NavbarStateResponse,
    NavItemCreate,
    NavItemReorderRequest,
    NavItemUpdate,
    SocialLinkCreate,
    SocialLinkUpdate,
    SocialReorderRequest,
)

router = Router()


def _nav_item_payload(
    item: NavItem,
) -> dict:
    return {
        "id": item.pk,
        "name": item.name,
        "url": item.url,
        "parent_id": item.parent_id,  # type: ignore
        "order": item.order,
        "is_visible": item.is_visible,
        "children": [],
    }


def _social_payload(
    link: SocialLink,
) -> dict:
    return {
        "id": link.pk,
        "platform": link.platform,
        "url": link.url,
        "order": link.order,
        "is_visible": link.is_visible,
    }


@router.get(
    "/admin/navbar",
    response={
        200: NavbarStateResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Get Navbar Admin State",
    description=(
        "Superuser Only: returns the full nav tree (including hidden items) and social links, "
        "with their order and visibility."
    ),
    auth=authed("navbar.admin"),
)
def get_navbar_admin(
    request: HttpRequest,
) -> Status:
    return Status(200, get_navbar_state())


@router.post(
    "/admin/navbar/items",
    response={
        201: NavbarAdminItem,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Create Nav Item",
    description="Superuser Only: create a new navigation item, optionally under a parent.",
    auth=authed("navbar.admin"),
)
def post_nav_item(
    request: HttpRequest,
    body: NavItemCreate,
) -> Status:
    try:
        item = create_nav_item(body.model_dump())
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return Status(201, _nav_item_payload(item))


@router.post(
    "/admin/navbar/items/reorder",
    response={
        204: None,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Reorder Nav Items Under a Parent",
    description=(
        "Superuser Only: assigns indexed `order` values to the items provided, in the order "
        "given. The `parent_id` selects the sibling group; pass null for root items. "
        "`ordered_ids` MUST contain every sibling ID under that parent exactly once. "
        "Partial submissions are rejected with 400. The frontend must always send the full "
        "sibling set, even if only one item was moved or changed."
    ),
    auth=authed("navbar.admin"),
)
def post_nav_reorder(
    request: HttpRequest,
    body: NavItemReorderRequest,
) -> HttpResponse:
    try:
        reorder_nav_items(
            parent_id=body.parent_id,
            ordered_ids=body.ordered_ids,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return HttpResponse(status=204)


@router.patch(
    "/admin/navbar/items/{int:item_id}",
    response={
        200: NavbarAdminItem,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Update Nav Item",
    description=(
        "Superuser Only: partially update a navigation item. Only fields present in the request "
        "body are touched. Use this to rename, toggle visibility, change the URL, change parent, "
        "or change the order index of a single item."
    ),
    auth=authed("navbar.admin"),
)
def patch_nav_item(
    request: HttpRequest,
    item_id: int,
    body: NavItemUpdate,
) -> Status:
    item = get_object_or_404(NavItem, pk=item_id)
    try:
        item = update_nav_item(item, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return Status(200, _nav_item_payload(item))


@router.delete(
    "/admin/navbar/items/{int:item_id}",
    response={
        204: None,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Delete Nav Item",
    description=(
        "Superuser Only: delete a navigation item. Rejects with 409 if the item has children; "
        "remove or reparent them first."
    ),
    auth=authed("navbar.admin"),
)
def delete_nav_item_endpoint(
    request: HttpRequest,
    item_id: int,
) -> HttpResponse:
    item = get_object_or_404(NavItem, pk=item_id)
    try:
        delete_nav_item(item)
    except ValueError as exc:
        raise HttpError(409, str(exc))
    return HttpResponse(status=204)


@router.post(
    "/admin/navbar/social",
    response={
        201: NavbarAdminSocial,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Create Social Link",
    description="Superuser Only: create a new social media link.",
    auth=authed("navbar.admin"),
)
def post_social(
    request: HttpRequest,
    body: SocialLinkCreate,
) -> Status:
    try:
        link = create_social_link(body.model_dump())
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return Status(201, _social_payload(link))


@router.post(
    "/admin/navbar/social/reorder",
    response={
        204: None,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    summary="Reorder Social Links",
    description=(
        "Superuser Only: assigns indexed `order` values across all social links. `ordered_ids` "
        "MUST contain every SocialLink ID exactly once. Partial submissions are rejected with "
        "400. The frontend must always send the full set, even if only one link moved."
    ),
    auth=authed("navbar.admin"),
)
def post_social_reorder(
    request: HttpRequest,
    body: SocialReorderRequest,
) -> HttpResponse:
    try:
        reorder_social_links(
            ordered_ids=body.ordered_ids,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return HttpResponse(status=204)


@router.patch(
    "/admin/navbar/social/{int:link_id}",
    response={
        200: NavbarAdminSocial,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Update Social Link",
    description=(
        "Superuser Only: partially update a social link. Only fields present in the request "
        "body are touched."
    ),
    auth=authed("navbar.admin"),
)
def patch_social(
    request: HttpRequest,
    link_id: int,
    body: SocialLinkUpdate,
) -> Status:
    link = get_object_or_404(SocialLink, pk=link_id)
    try:
        link = update_social_link(link, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return Status(200, _social_payload(link))


@router.delete(
    "/admin/navbar/social/{int:link_id}",
    response={
        204: None,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
    summary="Delete Social Link",
    description="Superuser Only: delete a social media link.",
    auth=authed("navbar.admin"),
)
def delete_social(
    request: HttpRequest,
    link_id: int,
) -> HttpResponse:
    link = get_object_or_404(SocialLink, pk=link_id)
    delete_social_link(link)
    return HttpResponse(status=204)
