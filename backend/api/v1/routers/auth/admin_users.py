import io
import logging
import os
from typing import Any

from allauth.account.forms import ResetPasswordForm
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import File, Router, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile
from srl.models import Awards, Games, Players

from api.models import APIKey, APIKeyRevokedReason
from api.permissions import authed
from api.v1.routers.auth.pfp import PFP_DIR, PFP_MAX_PIXELS
from api.v1.routers.auth.profile_bg import PROFILE_BG_MAX_PIXELS
from api.v1.routers.utils.images import ImageValidationError, validate_image
from api.v1.schemas.admin_users import (
    AdminPfpResponse,
    AdminProfileBGResponse,
    AwardEntry,
    BanRequest,
    ModeratedGame,
    SessionsRevokedResponse,
)
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()


def _resolve_player(
    ident: str,
) -> Players:
    by_id = list(Players.objects.filter(id=ident))
    if len(by_id) == 1:
        return by_id[0]

    by_name = list(
        Players.objects.filter(
            Q(name__iexact=ident)
            | Q(nickname__iexact=ident)
            | Q(user__username__iexact=ident),
        ).distinct(),
    )
    if len(by_name) == 0:
        raise HttpError(404, f"No player matches identifier {ident!r}")
    if len(by_name) > 1:
        raise HttpError(
            409,
            f"Ambiguous identifier {ident!r}; use Player ID",
        )
    return by_name[0]


def _resolve_user(
    ident: str,
) -> Any:
    player = _resolve_player(ident)
    if player.user and player.user.id is None:
        raise HttpError(
            404,
            f"Player {player.id} has no claimed user account",
        )
    return player.user


def _revoke_user_sessions(
    user: Any,
) -> int:
    target_id = str(user.pk)
    keys_to_kill: list[str] = []
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        data = session.get_decoded()
        if data.get("_auth_user_id") == target_id:
            keys_to_kill.append(session.session_key)
    deleted, _ = Session.objects.filter(session_key__in=keys_to_kill).delete()
    return deleted


def _refuse_self_target(
    request: HttpRequest,
    target_user: Any,
) -> None:
    actor_user = getattr(request, "user", None)
    if actor_user is not None and actor_user.pk == target_user.pk:
        raise HttpError(
            400,
            "Cannot perform admin action on your own account",
        )


@router.get(
    "/admin/users/{ident}/moderates",
    response={
        200: list[ModeratedGame],
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="List Games Moderated By a Player",
    description=(
        "Superuser Only: returns the games on which the resolved player is a moderator. Identifier "
        "may be a Player ID, name, nickname, or the linked Django username. ID lookup always wins; "
        "if a name shadows another player's ID, use the explicit Player ID."
    ),
    auth=authed("users.admin"),
)
def list_moderates(
    request: HttpRequest,
    ident: str,
) -> Status:
    player = _resolve_player(ident)
    games = player.moderated_games.all().order_by("name")  # type: ignore
    payload = [ModeratedGame(game_id=g.id, game_name=g.name) for g in games]
    return Status(200, payload)


@router.post(
    "/admin/users/{ident}/moderates/{game_id}",
    response={
        204: None,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Add Player As Moderator Of a Game",
    description=(
        "Superuser Only: adds the resolved player to the game's moderator list."
    ),
    auth=authed("users.admin"),
)
def add_moderator(
    request: HttpRequest,
    ident: str,
    game_id: str,
) -> Status:
    player = _resolve_player(ident)
    game = get_object_or_404(Games, id=game_id)
    game.moderators.add(player)
    logger.info(
        "admin add moderator: actor=%s player=%s game=%s",
        request.user.pk,
        player.id,
        game.id,
    )
    return Status(204, None)


@router.delete(
    "/admin/users/{ident}/moderates/{game_id}",
    response={
        204: None,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Remove Player As Moderator Of A Game",
    description=(
        "Superuser Only: removes the resolved player from the game's moderator list."
    ),
    auth=authed("users.admin"),
)
def remove_moderator(
    request: HttpRequest,
    ident: str,
    game_id: str,
) -> Status:
    player = _resolve_player(ident)
    game = get_object_or_404(Games, id=game_id)
    game.moderators.remove(player)
    logger.info(
        "admin remove moderator: actor=%s player=%s game=%s",
        request.user.pk,
        player.id,
        game.id,
    )
    return Status(204, None)


@router.get(
    "/admin/users/{ident}/awards",
    response={
        200: list[AwardEntry],
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="List Awards Held By a Player",
    description="Superuser Only: returns the awards on the resolved player's profile.",
    auth=authed("users.admin"),
)
def list_awards(
    request: HttpRequest,
    ident: str,
) -> Status:
    player = _resolve_player(ident)
    awards = player.awards.all().order_by("name")
    payload = [AwardEntry(award_id=a.pk, award_name=a.name) for a in awards]
    return Status(200, payload)


@router.post(
    "/admin/users/{ident}/awards/{award_id}",
    response={
        204: None,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Grant Award To a Player",
    description="Superuser Only: adds the award to the resolved player.",
    auth=authed("users.admin"),
)
def add_award(
    request: HttpRequest,
    ident: str,
    award_id: int,
) -> Status:
    player = _resolve_player(ident)
    award = get_object_or_404(Awards, pk=award_id)
    player.awards.add(award)
    logger.info(
        "admin add award: actor=%s player=%s award=%s",
        request.user.pk,
        player.id,
        award.pk,
    )
    return Status(204, None)


@router.delete(
    "/admin/users/{ident}/awards/{award_id}",
    response={
        204: None,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Revoke Award From a Player",
    description="Superuser Only: removes the award from the resolved player.",
    auth=authed("users.admin"),
)
def remove_award(
    request: HttpRequest,
    ident: str,
    award_id: int,
) -> Status:
    player = _resolve_player(ident)
    award = get_object_or_404(Awards, pk=award_id)
    player.awards.remove(award)
    logger.info(
        "admin remove award: actor=%s player=%s award=%s",
        request.user.pk,
        player.id,
        award.pk,
    )
    return Status(204, None)


@router.post(
    "/admin/users/{ident}/pfp",
    response={
        200: AdminPfpResponse,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
        500: ErrorResponse,
    },
    summary="Upload Profile Picture For a Player",
    description=(
        "Superuser Only: writes a new profile picture for the resolved "
        "player. Same validation rules as the /me/pfp endpoint: JPEG, PNG, "
        "WEBP, or GIF, up to 5 MB and 4 MP. Saves to static/pfp/`playerid`.jpg."
    ),
    auth=authed("users.admin"),
)
def admin_upload_pfp(
    request: HttpRequest,
    ident: str,
    file: UploadedFile = File(...),  # type: ignore
) -> Status:
    player = _resolve_player(ident)

    if not file.size or file.size > 5 * 1024 * 1024:
        return Status(
            400,
            ErrorResponse(
                error="Image exceeds maximum size of 5 MB",
                details=None,
            ),
        )

    raw: bytes = b"".join(file.chunks())

    try:
        rgb = validate_image(raw, file.content_type, max_pixels=PFP_MAX_PIXELS)
    except ImageValidationError as e:
        return Status(
            400,
            ErrorResponse(
                error=e.message,
                details=None,
            ),
        )

    safe_id = "".join(c for c in player.id if c.isalnum() or c in "-_")
    file_path = os.path.join(PFP_DIR, f"{safe_id}.jpg")
    temp_path = f"{file_path}.tmp"

    try:
        rgb.save(temp_path, "JPEG", quality=85)
        os.replace(temp_path, file_path)
    except OSError:
        logger.exception("Admin failed to write pfp for player %s", player.id)
        return Status(
            500,
            ErrorResponse(
                error="Failed to save profile picture",
                details=None,
            ),
        )

    pfp_url = f"{settings.MEDIA_URL}pfp/{player.id}.jpg"
    player.pfp = pfp_url
    player.save(update_fields=["pfp"])

    logger.info(
        "admin upload pfp: actor=%s player=%s",
        request.user.pk,
        player.id,
    )
    return Status(200, AdminPfpResponse(pfp=pfp_url))


@router.delete(
    "/admin/users/{ident}/pfp",
    response={
        204: None,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Delete Profile Picture For a Player",
    description=(
        "Superuser Only: removes the player's profile picture file from disk (if present) and "
        "clears the URL on the player row."
    ),
    auth=authed("users.admin"),
)
def admin_delete_pfp(
    request: HttpRequest,
    ident: str,
) -> Status:
    player = _resolve_player(ident)
    safe_id = "".join(c for c in player.id if c.isalnum() or c in "-_")
    file_path = os.path.join(PFP_DIR, f"{safe_id}.jpg")
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass
    player.pfp = None
    player.save(update_fields=["pfp"])
    logger.info(
        "admin delete pfp: actor=%s player=%s",
        request.user.pk,
        player.id,
    )
    return Status(204, None)


@router.post(
    "/admin/users/{ident}/profile-bg",
    response={
        200: AdminProfileBGResponse,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Upload Profile Background For a Player",
    description=(
        "Superuser Only: writes a new profile background image for the resolved "
        "player. Same validation rules as the /me/profile-bg endpoint: JPEG, "
        "PNG, WEBP, or GIF, up to 10 MB and 12 MP. Saves to MEDIA_ROOT/profile_bg/."
    ),
    auth=authed("users.admin"),
)
def admin_upload_profile_bg(
    request: HttpRequest,
    ident: str,
    file: UploadedFile = File(...),  # type: ignore
) -> Status:
    player = _resolve_player(ident)

    if not player.user:
        return Status(
            404,
            ErrorResponse(
                error=f"Player {player.id} has no claimed user account",
                details=None,
            ),
        )

    if not file.size or file.size > 10 * 1024 * 1024:
        return Status(
            400,
            ErrorResponse(
                error="Image exceeds maximum size of 10 MB",
                details=None,
            ),
        )

    raw: bytes = b"".join(file.chunks())

    try:
        rgb = validate_image(raw, file.content_type, max_pixels=PROFILE_BG_MAX_PIXELS)
    except ImageValidationError as e:
        return Status(
            400,
            ErrorResponse(
                error=e.message,
                details=None,
            ),
        )

    buffer = io.BytesIO()
    rgb.save(buffer, "JPEG", quality=85)
    buffer.seek(0)

    safe_id = "".join(c for c in player.id if c.isalnum() or c in "-_")
    filename = f"{safe_id}.jpg"

    if player.user.profile_bg:
        player.user.profile_bg.delete(save=False)

    player.user.profile_bg.save(
        filename,
        ContentFile(buffer.getvalue()),
        save=True,
    )

    logger.info(
        "admin upload profile_bg: actor=%s player=%s",
        request.user.pk,
        player.id,
    )
    return Status(
        200,
        AdminProfileBGResponse(profile_bg=player.user.profile_bg.url),
    )


@router.delete(
    "/admin/users/{ident}/profile-bg",
    response={
        204: None,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Delete Profile Background For a Player",
    description=("Superuser Only: removes the player's profile background image."),
    auth=authed("users.admin"),
)
def admin_delete_profile_bg(
    request: HttpRequest,
    ident: str,
) -> Status:
    player = _resolve_player(ident)

    if not player.user:
        return Status(
            404,
            ErrorResponse(
                error=f"Player {player.id} has no claimed user account",
                details=None,
            ),
        )

    if player.user.profile_bg:
        player.user.profile_bg.delete(save=True)

    logger.info(
        "admin delete profile_bg: actor=%s player=%s",
        request.user.pk,
        player.id,
    )
    return Status(204, None)


@router.delete(
    "/admin/users/{ident}/sessions",
    response={
        200: SessionsRevokedResponse,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Revoke All Active Sessions For a User",
    description=(
        "Superuser Only: deletes the specified user account (cannot be done to own account)"
    ),
    auth=authed("users.admin"),
)
def admin_revoke_sessions(
    request: HttpRequest,
    ident: str,
) -> Status:
    user = _resolve_user(ident)
    _refuse_self_target(request, user)
    revoked = _revoke_user_sessions(user)
    logger.info(
        "admin revoke sessions: actor=%s target=%s revoked=%d",
        request.user.pk,
        user.pk,
        revoked,
    )
    return Status(200, SessionsRevokedResponse(revoked=revoked))


@router.post(
    "/admin/users/{ident}/password-reset",
    response={
        204: None,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Force Password Reset For a User",
    description=(
        "Superuser Only: sets the user's password to unusable, deletes all of their unexpired "
        "sessions, then sends a password reset email to the address on file."
    ),
    auth=authed("users.admin"),
)
def admin_password_reset(
    request: HttpRequest,
    ident: str,
) -> Status:
    user = _resolve_user(ident)
    _refuse_self_target(request, user)

    with transaction.atomic():
        user.set_unusable_password()
        user.save(update_fields=["password"])
        sessions_revoked = _revoke_user_sessions(user)

    if not user.email:
        logger.warning(
            "admin password reset (no email on record): actor=%s target=%s",
            request.user.pk,
            user.pk,
        )
        return Status(
            400,
            ErrorResponse(
                error="User has no email address on record",
                details=None,
            ),
        )

    form = ResetPasswordForm({"email": user.email})
    if form.is_valid():
        form.save(request=request)

    logger.info(
        "admin password reset: actor=%s target=%s sessions_revoked=%d",
        request.user.pk,
        user.pk,
        sessions_revoked,
    )
    return Status(204, None)


@router.post(
    "/admin/users/{ident}/ban",
    response={
        204: None,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Ban a User",
    description=(
        "Superuser Only: revokes all specified player's API keys, flips is_active to False, "
        "deletes all of their sessions, and sets Players.sync_paused to True."
    ),
    auth=authed("users.admin"),
)
def admin_ban_user(
    request: HttpRequest,
    ident: str,
    body: BanRequest,
) -> Status:
    user = _resolve_user(ident)
    _refuse_self_target(request, user)
    reason = body.reason or ""

    with transaction.atomic():
        for key in APIKey.objects.filter(user=user, revoked_at__isnull=True):
            key.revoke(APIKeyRevokedReason.BANNED)

        user.is_active = False
        user.save(update_fields=["is_active"])

        try:
            player = user.player
        except Players.DoesNotExist:
            player = None
        if player is not None:
            player.sync_paused = True
            player.save(update_fields=["sync_paused"])

    sessions_revoked = _revoke_user_sessions(user)
    logger.info(
        "admin ban: actor=%s target=%s reason=%r sessions_revoked=%d",
        request.user.pk,
        user.pk,
        reason,
        sessions_revoked,
    )
    return Status(204, None)


@router.delete(
    "/admin/users/{ident}/ban",
    response={
        204: None,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
    summary="Un-Ban a User",
    description=(
        "Superuser Only: flips is_active back to True and clears Players.sync_paused."
    ),
    auth=authed("users.admin"),
)
def admin_unban_user(
    request: HttpRequest,
    ident: str,
) -> Status:
    user = _resolve_user(ident)
    _refuse_self_target(request, user)

    with transaction.atomic():
        user.is_active = True
        user.save(update_fields=["is_active"])
        try:
            player = user.player
        except Players.DoesNotExist:
            player = None
        if player is not None:
            player.sync_paused = False
            player.save(update_fields=["sync_paused"])

    logger.info(
        "admin unban: actor=%s target=%s",
        request.user.pk,
        user.pk,
    )
    return Status(204, None)
