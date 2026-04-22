from collections.abc import Callable
from typing import Any

from django.http import HttpRequest
from ninja.errors import HttpError
from ninja.security import APIKeyHeader, SessionAuth
from rules.permissions import add_perm
from srl.models import Players
from srl.rules import (
    is_authenticated,
    is_game_moderator,
    is_guide_game_moderator,
    is_run_game_moderator,
    is_run_participant,
    is_superuser,
    owns_guide,
)

from api.csrf import enforce_csrf
from api.models import APIKey, RoleAPIKey


class RoleBasedAPIKeyAuth(APIKeyHeader):
    """Django Ninja authentication class with role-based permissions."""

    param_name = "X-API-Key"

    def __init__(
        self,
        required_role: str = "read_only",
    ) -> None:
        """
        Initialize with required role.

        Arguments:
            required_role: Minimum role required ('read_only', 'contributor', 'moderator', 'admin')
        """
        self.required_role: str = required_role
        super().__init__()

    def authenticate(
        self,
        request: HttpRequest,
        key: str,
    ) -> dict[str, Any] | None:
        """Validate API key and check role permissions.

        Arguments:
            request: HTTP request object
            key: API key from X-API-Key header

        Returns:
            Dict with API key info if authorized, None if unauthorized
        """
        try:
            api_key_obj: RoleAPIKey | None = RoleAPIKey.objects.get_from_key(key)  # type: ignore
            if not api_key_obj:
                return None

            if not api_key_obj.has_role(self.required_role):
                return None

            return {
                "api_key": key,
                "api_key_obj": api_key_obj,
                "role": api_key_obj.role,
                "name": api_key_obj.name,
                "created_by": api_key_obj.created_by,
            }

        except RoleAPIKey.DoesNotExist:
            pass

        return None


class PublicOrRoleAuth:
    """Hybrid authentication: allows public GET requests, requires API key for other methods."""

    def __init__(
        self,
        required_role: str = "read_only",
    ) -> None:
        """
        Initialize with required role for non-GET requests.

        Arguments:
            required_role: Minimum role required for non-GET requests
        """
        self.required_role: str = required_role
        self.role_auth: RoleBasedAPIKeyAuth = RoleBasedAPIKeyAuth(required_role)

    def __call__(
        self,
        request: HttpRequest,
    ) -> dict[str, Any] | None:
        """Authenticate based on HTTP method.

        Arguments:
            request: HTTP request object

        Returns:
            Auth info dict or None if unauthorized
        """
        if request.method == "GET":
            return {"role": "public", "authenticated": False, "public_access": True}

        api_key_header: str | None = request.headers.get("X-API-Key")
        if not api_key_header:
            return None

        return self.role_auth.authenticate(request, api_key_header)


class PlayerSessionAuth(SessionAuth):
    def authenticate(
        self,
        request: HttpRequest,
        token: str,
    ) -> Players | None:
        """
        Validate the session and return the associated Players instance.

        Arguments:
            request: HTTP request with session data.
            token: Unused for session auth (Django Ninja passes a dummy value).

        Returns:
            Players instance if authenticated and claimed, else None.
        """
        enforce_csrf(request)
        user = super().authenticate(request, token)
        if user is None:
            return None
        try:
            player: Players = user.player  # type: ignore
        except Players.DoesNotExist:
            return None
        if player.claim_status != Players.ClaimStatus.CLAIMED:
            return None
        return player


class SuperuserSessionAuth(PlayerSessionAuth):
    def authenticate(
        self,
        request: HttpRequest,
        token: str,
    ) -> Players | None:
        player = super().authenticate(request, token)
        if player is None:
            return None
        if not hasattr(player, "user") or player.user is None:
            return None
        if not player.user.is_superuser:
            return None
        return player


public_auth: PublicOrRoleAuth = PublicOrRoleAuth("read_only")
read_only_auth: RoleBasedAPIKeyAuth = RoleBasedAPIKeyAuth("read_only")
contributor_auth: RoleBasedAPIKeyAuth = RoleBasedAPIKeyAuth("contributor")
moderator_auth: RoleBasedAPIKeyAuth = RoleBasedAPIKeyAuth("moderator")
admin_auth: RoleBasedAPIKeyAuth = RoleBasedAPIKeyAuth("admin")

api_key_required: RoleBasedAPIKeyAuth = read_only_auth

player_session_auth: PlayerSessionAuth = PlayerSessionAuth()
superuser_session_auth: SuperuserSessionAuth = SuperuserSessionAuth()

# Map of capabilities/features of the site and whether the capability is scoped to a specific game.
CAPABILITY_SCOPED: dict[str, bool] = {
    "runs.submit": True,
    "runs.edit_own": True,
    "runs.edit_any": True,
    "runs.verify": True,
    "runs.delete": True,
    "guides.create": True,
    "guides.edit_own": True,
    "guides.edit_any": True,
    "guides.delete_own": True,
    "guides.delete_any": True,
    "games.manage": True,
    "api_keys.create_own": False,
    "api_keys.list_own": False,
    "api_keys.revoke_own": False,
    "api_keys.admin": False,
    "users.admin": False,
    "users.view_private": False,
}


def _register_capabilities() -> None:
    # Runs capabilities
    add_perm("runs.submit", is_authenticated)
    add_perm("runs.edit_own", is_authenticated & is_run_participant)  # type: ignore
    add_perm("runs.edit_any", is_superuser | is_run_game_moderator)  # type: ignore
    add_perm("runs.verify", is_superuser | is_run_game_moderator)  # type: ignore
    add_perm("runs.delete", is_superuser)

    # Guides capabilities
    add_perm("guides.create", is_authenticated)
    add_perm("guides.edit_own", is_authenticated & owns_guide)  # type: ignore
    add_perm("guides.edit_any", is_superuser | is_guide_game_moderator)  # type: ignore
    add_perm("guides.delete_own", is_authenticated & owns_guide)  # type: ignore
    add_perm("guides.delete_any", is_superuser | is_guide_game_moderator)  # type: ignore

    # Games capabilities
    add_perm("games.manage", is_superuser | is_game_moderator)  # type: ignore

    # API keys capabilities
    add_perm("api_keys.create_own", is_authenticated)
    add_perm("api_keys.list_own", is_authenticated)
    add_perm("api_keys.revoke_own", is_authenticated)

    # Admin capabilities
    add_perm("api_keys.admin", is_superuser)
    add_perm("users.admin", is_superuser)
    add_perm("users.view_private", is_superuser)


_register_capabilities()


def _resolve_caller(request: HttpRequest) -> tuple[Any, "APIKey | None"]:
    api_key_header: str | None = request.headers.get("X-API-Key")
    if api_key_header:
        try:
            key: APIKey = APIKey.objects.get_from_key(api_key_header)  # type: ignore
        except APIKey.DoesNotExist:
            raise HttpError(401, "Invalid API key")
        if not APIKey.objects.get_usable_keys().filter(pk=key.pk).exists():
            raise HttpError(401, "API key not usable")
        return key.user, key

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        raise HttpError(401, "Authentication required")

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        enforce_csrf(request)
    return user, None


def _extract_target_game_id(target: Any) -> Any:
    if target is None:
        return None
    if hasattr(target, "moderators") and not hasattr(target, "game"):
        return target.pk
    if hasattr(target, "game_id"):
        return target.game_id
    if hasattr(target, "game") and target.game is not None:
        return target.game.pk
    return None


def _key_scope_admits(
    key: "APIKey",
    capability: str,
    target: Any | None,
) -> bool:
    caps: list[str] = list(key.scope_capabilities or [])
    if caps and capability not in caps:
        return False

    if not CAPABILITY_SCOPED.get(capability, False):
        return True

    scope_games: list[Any] = list(
        key.scope_games.values_list("pk", flat=True),
    )
    if not scope_games:
        return True

    if target is None:
        return False
    target_game_id = _extract_target_game_id(target)
    return target_game_id in scope_games


def authed(
    capability: str,
    target_resolver: Callable[[HttpRequest], Any] | None = None,
) -> Callable[[HttpRequest], Any]:
    def dependency(request: HttpRequest) -> Any:
        user, key = _resolve_caller(request)
        target = target_resolver(request) if target_resolver else None

        if not user.has_perm(capability, target):
            raise HttpError(403, f"Permission denied: {capability}")

        if key is not None and not _key_scope_admits(key, capability, target):
            raise HttpError(403, "API key scope does not cover this action")

        request.user = user
        request.api_key = key  # type: ignore
        return user

    return dependency


def public_read() -> Callable[[HttpRequest], Any]:
    def dependency(request: HttpRequest) -> Any:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user
        return None

    return dependency
