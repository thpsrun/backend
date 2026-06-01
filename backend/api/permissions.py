from collections.abc import Callable
from typing import Any

from auditlog.context import set_actor
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest
from ninja.errors import HttpError
from rules.permissions import add_perm
from srl.rules import (
    has_claimed_player,
    is_authenticated,
    is_game_moderator,
    is_guide_game_moderator,
    is_run_game_moderator,
    is_run_participant,
    is_superuser,
    owns_guide,
)

from api.csrf import enforce_csrf
from api.models import APIKey

# Capabilities exposed as API-key scopes. Each maps to True if game-scoped, False if
# user-scoped. The /me/capabilities advisory endpoint, the API key scope-creation path,
# and the backability check that drives signal-based revocation all read from this dict.
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
    "games.audit.view": True,
    "api_keys.create_own": False,
    "api_keys.list_own": False,
    "api_keys.revoke_own": False,
}

# Capabilities that are registered for has_perm() checks but only reachable via session
# authentication. Keep these out of CAPABILITY_SCOPED so they don't show up in the API key
# scope-picker or /me/capabilities - they're frontend-only.
SESSION_ONLY_CAPABILITIES: frozenset[str] = frozenset(
    {
        "profile.edit_own",
        "submissions.list_own",
        "notifications.read_own",
        "notifications.manage_own",
    },
)

# Admin-only capabilities. Registered for has_perm() and usable on authed(...) routes
# (a superuser's unscoped API key still admits them), but intentionally not exposed as
# a scope pick: there's no "just users.admin" sub-key story we want to surface, and these
# don't belong in the /me/capabilities advisory aimed at end users.
ADMIN_ONLY_CAPABILITIES: frozenset[str] = frozenset(
    {
        "api_keys.admin",
        "users.admin",
        "sync_logs.admin",
        "reconcile.admin",
        "games.display.admin",
        "navbar.admin",
    },
)

# Categorization of the game-scoped capabilities by the natural power a user needs to exercise
# them. Source of truth for both the /me/capabilities advisory endpoint and the backability
# check used by the revocation signals and nightly sweep.
PLAYER_SCOPES: frozenset[str] = frozenset(
    {
        "runs.submit",
        "runs.edit_own",
        "guides.create",
        "guides.edit_own",
        "guides.delete_own",
    },
)
MOD_SCOPES: frozenset[str] = frozenset(
    {
        "runs.edit_any",
        "runs.verify",
        "guides.edit_any",
        "guides.delete_any",
        "games.manage",
        "games.audit.view",
    },
)
SU_ONLY_SCOPES: frozenset[str] = frozenset({"runs.delete"})

# Fail fast at import time if a new scoped capability is added to CAPABILITY_SCOPED without
# being categorized above. Keeps /me/capabilities and the backability check from silently
# diverging from the registry.
_SCOPED_CAPS: frozenset[str] = frozenset(
    cap for cap, scoped in CAPABILITY_SCOPED.items() if scoped
)
_CATEGORIZED_SCOPED_CAPS: frozenset[str] = PLAYER_SCOPES | MOD_SCOPES | SU_ONLY_SCOPES
assert _CATEGORIZED_SCOPED_CAPS == _SCOPED_CAPS, (
    "Scoped capability categorization drift. "
    f"Uncategorized: {sorted(_SCOPED_CAPS - _CATEGORIZED_SCOPED_CAPS)}. "
    f"Unknown: {sorted(_CATEGORIZED_SCOPED_CAPS - _SCOPED_CAPS)}."
)

# Disjoint tiers: a cap belongs to exactly one of the three registries.
_TIER_SETS: dict[str, frozenset[str]] = {
    "CAPABILITY_SCOPED": frozenset(CAPABILITY_SCOPED.keys()),
    "SESSION_ONLY_CAPABILITIES": SESSION_ONLY_CAPABILITIES,
    "ADMIN_ONLY_CAPABILITIES": ADMIN_ONLY_CAPABILITIES,
}
for _a, _b in (
    ("CAPABILITY_SCOPED", "SESSION_ONLY_CAPABILITIES"),
    ("CAPABILITY_SCOPED", "ADMIN_ONLY_CAPABILITIES"),
    ("SESSION_ONLY_CAPABILITIES", "ADMIN_ONLY_CAPABILITIES"),
):
    _overlap = _TIER_SETS[_a] & _TIER_SETS[_b]
    assert not _overlap, f"Capability appears in both {_a} and {_b}: {sorted(_overlap)}"


def _register_capabilities() -> None:
    # Ignore the type: ignores, please. pylance likes to raise errors since it doesn't completely
    # understand these in this context lol.
    registered: set[str] = set()

    def reg(name: str, rule) -> None:
        registered.add(name)
        add_perm(name, rule)

    # Runs capabilities
    reg("runs.submit", is_authenticated & has_claimed_player)  # type: ignore
    reg("runs.edit_own", is_authenticated & is_run_participant)  # type: ignore
    reg("runs.edit_any", is_superuser | is_run_game_moderator)  # type: ignore
    reg("runs.verify", is_superuser | is_run_game_moderator)  # type: ignore
    reg("runs.delete", is_superuser)

    # Guides capabilities
    reg("guides.create", is_authenticated & has_claimed_player)  # type: ignore
    reg("guides.edit_own", is_authenticated & owns_guide)  # type: ignore
    reg("guides.edit_any", is_superuser | is_guide_game_moderator)  # type: ignore
    reg("guides.delete_own", is_authenticated & owns_guide)  # type: ignore
    reg("guides.delete_any", is_superuser | is_guide_game_moderator)  # type: ignore

    # Games capabilities
    reg("games.manage", is_superuser | is_game_moderator)  # type: ignore
    reg("games.audit.view", is_superuser | is_game_moderator)  # type: ignore

    # API keys capabilities
    reg("api_keys.create_own", is_authenticated)
    reg("api_keys.list_own", is_authenticated)
    reg("api_keys.revoke_own", is_authenticated)
    reg("api_keys.admin", is_superuser)

    # Notifications capabilities (session-only)
    reg("notifications.read_own", is_authenticated)
    reg("notifications.manage_own", is_authenticated)

    # Profile / submissions (session-only)
    reg("profile.edit_own", is_authenticated & has_claimed_player)  # type: ignore
    reg("submissions.list_own", is_authenticated & has_claimed_player)  # type: ignore

    # Admin capabilities
    reg("users.admin", is_superuser)
    reg("sync_logs.admin", is_superuser)
    reg("reconcile.admin", is_superuser)
    reg("games.display.admin", is_superuser)
    reg("navbar.admin", is_superuser)

    declared: set[str] = (
        set(CAPABILITY_SCOPED)
        | set(SESSION_ONLY_CAPABILITIES)
        | set(ADMIN_ONLY_CAPABILITIES)
    )
    unregistered = declared - registered
    undeclared = registered - declared
    assert not unregistered and not undeclared, (
        "Capability registry drift between add_perm calls and "
        "CAPABILITY_SCOPED/SESSION_ONLY_CAPABILITIES/ADMIN_ONLY_CAPABILITIES. "
        f"Declared but not registered: {sorted(unregistered)}. "
        f"Registered but not declared: {sorted(undeclared)}."
    )


_register_capabilities()


def _resolve_caller(
    request: HttpRequest,
) -> tuple[Any, "APIKey | None"]:
    api_key_header: str | None = request.headers.get("X-API-Key")
    if api_key_header:
        try:
            key: APIKey = APIKey.objects.get_from_key(api_key_header)
        except APIKey.DoesNotExist:
            raise HttpError(401, "Invalid or unusable API key")
        return key.user, key

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        raise HttpError(401, "Authentication Required!")
    if not user.is_active:
        raise HttpError(403, "Account Disabled")

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        enforce_csrf(request)
    return user, None


def _extract_target_game_id(
    target: Any,
) -> Any:
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
    """Verifies differences between scopes and games, ensuring that the user has no powers than
    they had requested."""
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
    capability: str | list[str],
    target_resolver: Callable[[HttpRequest], Any] | None = None,
) -> Callable[[HttpRequest], Any]:
    capabilities: tuple[str, ...] = (
        (capability,) if isinstance(capability, str) else tuple(capability)
    )
    if not capabilities:
        raise ValueError("authed() requires at least one capability!")

    def dependency(
        request: HttpRequest,
    ) -> Any:
        user, key = _resolve_caller(request)
        target = target_resolver(request) if target_resolver else None

        user_perm_failed: bool = True
        for cap in capabilities:
            if not user.has_perm(cap, target):
                continue
            user_perm_failed = False
            if key is not None and not _key_scope_admits(key, cap, target):
                continue
            request.user = user
            request.api_key = key  # type: ignore

            actor_label = (
                (getattr(key, "label", "") if key else "")
                or getattr(user, "username", "")
                or ""
            )
            set_actor(user=user, api_key=key, label=actor_label[:128])
            return user

        if user_perm_failed:
            label = (
                capabilities[0]
                if len(capabilities) == 1
                else f"any of {list(capabilities)}"
            )
            raise HttpError(403, f"Permission denied: {label}")
        raise HttpError(403, "API key scope does not cover this action")

    return dependency


def session_only(
    capability: str | list[str] | None = None,
    target_resolver: Callable[[HttpRequest], Any] | None = None,
) -> Callable[[HttpRequest], Any]:
    if capability is None:
        capabilities: tuple[str, ...] = ()
    elif isinstance(capability, str):
        capabilities = (capability,)
    else:
        capabilities = tuple(capability)

    def dependency(
        request: HttpRequest,
    ) -> Any:
        if request.headers.get("X-API-Key"):
            raise HttpError(403, "This endpoint requires session authentication.")

        user, _ = _resolve_caller(request)
        request.user = user
        request.api_key = None  # type: ignore

        actor_label = getattr(user, "username", "") or ""
        set_actor(user=user, api_key=None, label=actor_label[:128])

        if not capabilities:
            return user

        target = target_resolver(request) if target_resolver else None
        for cap in capabilities:
            if user.has_perm(cap, target):
                return user

        label = (
            capabilities[0]
            if len(capabilities) == 1
            else f"any of {list(capabilities)}"
        )
        raise HttpError(403, f"Permission denied: {label}")

    return dependency


def public_read() -> Callable[[HttpRequest], Any]:
    def dependency(
        request: HttpRequest,
    ) -> Any:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user

        # Instead of 401'ing anonymous API requests, this will return an AnonymousUser class.
        return AnonymousUser()

    return dependency
