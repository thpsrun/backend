from typing import Any

from django.http import HttpRequest
from ninja.security import APIKeyHeader, SessionAuth
from srl.models import Players

from api.csrf import enforce_csrf
from api.models import RoleAPIKey


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
            api_key_obj: RoleAPIKey | None = RoleAPIKey.objects.get_from_key(key)
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
