import logging

from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Status
from ninja.errors import HttpError
from ninja.responses import codes_4xx

from api.models import APIKey, APIKeyRevokedReason
from api.permissions import authed
from api.v1.routers.auth.api_keys import _build_key_response
from api.v1.schemas.api_keys import APIKeyResponse
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()


@router.get(
    "/admin/api-keys",
    response={200: list[APIKeyResponse], codes_4xx: ErrorResponse},
    summary="List API Keys For Any User",
    description="Superuser Only: Returns every API key owned by the requested user.",
    auth=authed("api_keys.admin"),
)
def admin_list_keys(
    request: HttpRequest,
    user: str,
) -> Status:
    User = get_user_model()
    if not User.objects.filter(pk=user).exists():
        raise HttpError(404, f"User {user!r} not found")
    keys = APIKey.objects.filter(user_id=user).order_by("-created")
    return Status(200, [_build_key_response(k) for k in keys])


@router.delete(
    "/admin/api-keys/{key_id}",
    response={204: None, codes_4xx: ErrorResponse},
    summary="Revoke Any API Key",
    description="Superuser Only: revokes any API key by ID, regardless of owner.",
    auth=authed("api_keys.admin"),
)
def admin_revoke_key(
    request: HttpRequest,
    key_id: str,
) -> Status:
    key = get_object_or_404(APIKey, pk=key_id)
    if key.revoke(APIKeyRevokedReason.ADMIN):
        logger.info(
            "API key admin-revoked: id=%s user=%s by=%s",
            key.pk,
            key.user.id,
            request.user.pk,
        )
    return Status(204, None)
