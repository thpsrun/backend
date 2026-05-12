import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Status
from ninja.errors import HttpError
from ninja.responses import codes_4xx
from srl.models import Games

from api.models import APIKey, APIKeyRevokedReason
from api.permissions import (
    CAPABILITY_SCOPED,
    MOD_SCOPES,
    PLAYER_SCOPES,
    SU_ONLY_SCOPES,
    authed,
)
from api.v1.schemas.api_keys import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyPatchRequest,
    APIKeyResponse,
    CapabilitiesResponse,
    GameEmbed,
)
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()


def _build_key_response(
    key: APIKey,
) -> APIKeyResponse:
    return APIKeyResponse(
        id=str(key.pk),
        label=key.label,
        description=key.description,
        prefix=key.prefix,
        scope_capabilities=list(key.scope_capabilities or []),
        scope_games=[str(g) for g in key.scope_games.values_list("pk", flat=True)],
        created=key.created,
        expiry_date=key.expiry_date,
        last_used=key.last_used,
        last_used_ip=key.last_used_ip,
        revoked=key.revoked,
        revoked_reason=key.revoked_reason,
        revoked_at=key.revoked_at,
    )


def _create_apikey_response(
    key: APIKey,
    raw: str,
) -> APIKeyCreateResponse:
    base = _build_key_response(key)
    return APIKeyCreateResponse(**base.model_dump(), key=raw)


def _check_user_capes(
    user,
    capability: str,
) -> bool:
    if user.is_superuser:
        return True
    for g in Games.objects.all().iterator():
        if user.has_perm(capability, g):
            return True
    return False


def _user_moderates_any_game(
    user,
) -> bool:
    player = getattr(user, "player", None)
    if player is None:
        return False
    return Games.objects.filter(moderators=player).exists()


def _user_game_check(
    user,
) -> QuerySet[Games]:
    """Games the user has game-specific moderator powers on (or all, for SU).

    Used for the /me/capabilities advisory endpoint so the frontend knows
    which games to offer as scope options when creating a new key.
    """
    if user.is_superuser:
        return Games.objects.all()
    player = getattr(user, "player", None)
    if player is None:
        return Games.objects.none()
    return Games.objects.filter(moderators=player)


def _enforce_presenting_key(
    request: HttpRequest,
    capabilities: list[str],
    games: list[str],
) -> None:
    """Checks scope and subset of scope of the presented API key."""
    presenting: APIKey | None = getattr(request, "api_key", None)
    if presenting is None:
        return

    presenter_caps: set[str] = set(presenting.scope_capabilities or [])
    if presenter_caps:
        if not capabilities:
            raise HttpError(
                403,
                "Presenting API key is capability-scoped; new key must "
                "specify scope_capabilities within the presenting key's scope",
            )
        invalid = sorted(set(capabilities) - presenter_caps)
        if invalid:
            raise HttpError(
                403,
                f"Presenting API key scope does not include: {invalid}",
            )

    presenter_games: set[str] = {
        str(g) for g in presenting.scope_games.values_list("pk", flat=True)
    }
    if presenter_games:
        if not games:
            raise HttpError(
                403,
                "Presenting API key is game-scoped; new key must also specify "
                "scope_games within the presenting key's scope",
            )
        invalid_games = sorted({str(g) for g in games} - presenter_games)
        if invalid_games:
            raise HttpError(
                403,
                f"Presenting API key does not include games: {invalid_games}",
            )


def _resolve_scope_games(
    games: list[str],
) -> dict[str, Games]:
    """Fetch the requested scope games in one query and raise 400 if any are unknown."""
    if not games:
        return {}
    games_map: dict[str, Games] = {
        str(pk): g for pk, g in Games.objects.in_bulk(games).items()
    }
    missing = sorted({str(g) for g in games} - games_map.keys())
    if missing:
        raise HttpError(400, f"Unknown games: {missing}")
    return games_map


def _enforce_user_can_scope(
    user,
    capabilities: list[str],
    games_map: dict[str, Games],
) -> None:
    for cap in capabilities:
        if cap not in CAPABILITY_SCOPED:
            raise HttpError(400, f"Unknown capability: {cap!r}")

        if CAPABILITY_SCOPED[cap]:
            if games_map:
                for game_id, g in games_map.items():
                    if not user.has_perm(cap, g):
                        raise HttpError(
                            400,
                            f"Cannot scope key: you do not have {cap!r} on "
                            f"game {game_id!r}",
                        )
            else:
                if not _check_user_capes(user, cap):
                    raise HttpError(
                        400,
                        f"Cannot scope key: you do not have {cap!r} on any game",
                    )
        else:
            if not user.has_perm(cap):
                raise HttpError(
                    400,
                    f"Cannot scope key: you do not have {cap!r}",
                )


@router.get(
    "/me/api-keys",
    response={200: list[APIKeyResponse], codes_4xx: ErrorResponse},
    summary="List My API Keys",
    description="Returns every API key the authenticated user owns, newest first.",
    auth=authed("api_keys.list_own"),
)
def list_my_keys(
    request: HttpRequest,
) -> Status:
    keys = APIKey.objects.filter(user=request.user).order_by("-created")
    return Status(200, [_build_key_response(k) for k in keys])


@router.post(
    "/me/api-keys",
    response={201: APIKeyCreateResponse, codes_4xx: ErrorResponse},
    summary="Create An API Key",
    description="""\
Creates a new API key for the authenticated user. The raw key string is
returned exactly once in the `key` field and cannot be recovered later.

Scopes:
- Empty `scope_capabilities` means the key carries the owner's full natural
  scope at request time.
- Empty `scope_games` means the key is not restricted by game.
- When authenticating with an existing API key, the new key's scope must be
  a subset of the presenting key's scope.
""",
    auth=authed("api_keys.create_own"),
)
def create_my_key(
    request: HttpRequest,
    body: APIKeyCreateRequest,
) -> Status:
    max_per_user: int = getattr(settings, "API_KEY_MAX_PER_USER", 10)
    active_count: int = (
        APIKey.objects.get_usable_keys().filter(user=request.user).count()
    )
    if active_count >= max_per_user:
        raise HttpError(
            400,
            f"Max active API keys per user reached ({max_per_user})",
        )

    _enforce_presenting_key(
        request,
        body.scope_capabilities,
        body.scope_games,
    )
    games_map = _resolve_scope_games(body.scope_games)
    _enforce_user_can_scope(
        request.user,
        body.scope_capabilities,
        games_map,
    )

    key_obj, raw = APIKey.objects.create_key(
        user=request.user,
        label=body.label,
        description=body.description,
        scope_capabilities=body.scope_capabilities,
        expiry_date=timezone.now() + timedelta(days=body.expiry_days),
    )
    if games_map:
        key_obj.scope_games.add(*games_map.values())

    logger.info(
        "API key created: id=%s user=%s label=%r caps=%s games=%s",
        key_obj.pk,
        request.user.pk,
        body.label,
        body.scope_capabilities,
        body.scope_games,
    )

    return Status(201, _create_apikey_response(key_obj, raw))


@router.get(
    "/me/api-keys/{key_id}",
    response={200: APIKeyResponse, codes_4xx: ErrorResponse},
    summary="Get An API Key",
    description="Returns a single API key owned by the authenticated user.",
    auth=authed("api_keys.list_own"),
)
def get_my_key(
    request: HttpRequest,
    key_id: str,
) -> Status:
    key = get_object_or_404(APIKey, pk=key_id, user=request.user)
    return Status(200, _build_key_response(key))


@router.patch(
    "/me/api-keys/{key_id}",
    response={200: APIKeyResponse, codes_4xx: ErrorResponse},
    summary="Update An API Key",
    description="Updates the label or description on an API key. Scope and "
    "expiry are immutable after creation.",
    auth=authed("api_keys.list_own"),
)
def patch_my_key(
    request: HttpRequest,
    key_id: str,
    body: APIKeyPatchRequest,
) -> Status:
    key = get_object_or_404(APIKey, pk=key_id, user=request.user)
    updated_fields: list[str] = []
    if body.label is not None:
        key.label = body.label
        updated_fields.append("label")
    if body.description is not None:
        key.description = body.description
        updated_fields.append("description")
    if updated_fields:
        key.save(update_fields=updated_fields)
    return Status(200, _build_key_response(key))


@router.delete(
    "/me/api-keys/{key_id}",
    response={204: None, codes_4xx: ErrorResponse},
    summary="Revoke An API Key",
    description="Revokes one of the authenticated user's API keys. Revocation "
    "is permanent; the row is kept for audit history.",
    auth=authed("api_keys.revoke_own"),
)
def revoke_my_key(
    request: HttpRequest,
    key_id: str,
) -> Status:
    key = get_object_or_404(APIKey, pk=key_id, user=request.user)
    key.revoke(APIKeyRevokedReason.USER)
    return Status(204, None)


@router.get(
    "/me/capabilities",
    response={200: CapabilitiesResponse, codes_4xx: ErrorResponse},
    summary="Get My Capabilities",
    description="Returns the capabilities the authenticated user can exercise "
    "and the games on which they have any game-scoped power. Useful for the "
    "frontend to drive the API key creation UI.",
    auth=authed("api_keys.list_own"),
)
def my_capabilities(
    request: HttpRequest,
) -> Status:
    user = request.user
    has_claimed_player: bool = user.has_perm("profile.edit_own")
    mods_any_game: bool = user.is_superuser or _user_moderates_any_game(user)

    capabilities: list[str] = []
    for cap, scoped in CAPABILITY_SCOPED.items():
        if not scoped:
            if user.has_perm(cap):
                capabilities.append(cap)
            continue
        if cap in PLAYER_SCOPES:
            if has_claimed_player:
                capabilities.append(cap)
            continue
        if cap in MOD_SCOPES:
            if mods_any_game:
                capabilities.append(cap)
            continue
        if cap in SU_ONLY_SCOPES:
            if user.is_superuser:
                capabilities.append(cap)
            continue

    games: list[GameEmbed] = [
        GameEmbed(id=str(g.pk), name=g.name, slug=g.slug)
        for g in _user_game_check(user)
    ]

    return Status(200, CapabilitiesResponse(capabilities=capabilities, games=games))
