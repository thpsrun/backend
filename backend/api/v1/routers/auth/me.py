import logging
import os

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Status
from ninja.responses import codes_4xx
from srl.models import CountryCodes, Players

from api.permissions import player_session_auth
from api.v1.schemas.auth import (
    CountryEmbed,
    CustomizationsEmbed,
    ModeratedGameSchema,
    ModerationEmbed,
    PlayerEmbed,
    PlayerProfileResponse,
    PlayerUpdateRequest,
    SocialsEmbed,
)
from api.v1.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)

router = Router()

PFP_DIR: str = os.path.join(settings.MEDIA_ROOT, "pfp")
os.makedirs(PFP_DIR, exist_ok=True)


def _invalidate_user_sessions(
    user_id: int,
) -> None:
    """Delete every non-expired session row whose decoded payload matches `user_id`."""
    try:
        target: str = str(user_id)
        now = timezone.now()
        for session in Session.objects.filter(expire_date__gte=now):
            if str(session.get_decoded().get("_auth_user_id")) == target:
                session.delete()
    except Exception:
        logger.exception("Failed to invalidate remote sessions for user %s", user_id)


def _build_profile_response(
    player: Players,
) -> PlayerProfileResponse:
    user = player.user
    moderated = list(player.moderated_games.all())

    country_embed: CountryEmbed | None = None
    if player.countrycode:
        country_embed = CountryEmbed(
            id=player.countrycode.id,
            name=player.countrycode.name,
            flag=player.countrycode.flag.url if player.countrycode.flag else None,
        )

    player_embed = PlayerEmbed(
        username=user.username if user else "",
        name=player.name,
        nickname=player.nickname,
        pronouns=player.pronouns,
        country=country_embed,
        pfp=player.pfp,
        is_superuser=user.is_superuser if user else False,
        ex_stream=player.ex_stream,
    )

    socials_embed = SocialsEmbed(
        twitch=player.twitch,
        youtube=player.youtube,
        twitter=player.twitter,
        bluesky=player.bluesky,
        discord=player.discord,
        therun_gg=user.therun_gg if user else None,
    )

    customizations_embed = CustomizationsEmbed(
        tagline=user.short_bio if user else None,
        gradient_1=user.gradient_1 if user else None,
        gradient_2=user.gradient_2 if user else None,
        gradient_3=user.gradient_3 if user else None,
        profile_bg=(user.profile_bg.url if user and user.profile_bg else None),
    )

    moderation_embed = ModerationEmbed(
        has_src_key=bool(user.encrypted_api_key) if user else False,
        moderated_games=[
            ModeratedGameSchema(id=g.id, name=g.name, slug=g.slug) for g in moderated
        ],
    )

    return PlayerProfileResponse(
        player_id=player.id,
        claim_status=player.claim_status,
        joined=player.joined,
        player=player_embed,
        socials=socials_embed,
        customizations=customizations_embed,
        moderation=moderation_embed,
    )


@router.get(
    "/me",
    response={200: PlayerProfileResponse, codes_4xx: ErrorResponse},
    summary="Get My Profile",
    description="Returns the current authenticated player's profile.",
    auth=player_session_auth,
)
def get_me(
    request: HttpRequest,
) -> Status:
    return Status(200, _build_profile_response(request.auth))  # type: ignore


@router.patch(
    "/me",
    response={200: PlayerProfileResponse, codes_4xx: ErrorResponse},
    summary="Update My Profile",
    description="""\
Updates editable fields on the current authenticated player's profile.
Only non-null fields in the request body will be applied.
""",
    auth=player_session_auth,
)
def update_me(
    request: HttpRequest,
    body: PlayerUpdateRequest,
) -> Status:
    player: Players = request.auth  # type: ignore

    player_update_fields: list[str] = []
    user_update_fields: list[str] = []

    if body.player is not None:
        player_fields = body.player.model_fields_set
        for field in ("name", "nickname", "pronouns", "ex_stream"):
            if field in player_fields:
                setattr(player, field, getattr(body.player, field))
                player_update_fields.append(field)

        if "country" in player_fields:
            if body.player.country is None:
                player.countrycode = None
            else:
                country = CountryCodes.objects.filter(id=body.player.country).first()
                if country is None:
                    return Status(
                        400,
                        ErrorResponse(
                            error="Invalid country code",
                            details={"country": body.player.country},
                        ),
                    )
                player.countrycode = country
            player_update_fields.append("countrycode")

    if body.socials is not None:
        socials_fields = body.socials.model_fields_set
        for field in ("twitch", "youtube", "twitter", "bluesky"):
            if field in socials_fields:
                setattr(player, field, getattr(body.socials, field))
                player_update_fields.append(field)
        if "therun_gg" in socials_fields and player.user:
            player.user.therun_gg = body.socials.therun_gg
            user_update_fields.append("therun_gg")

    if body.customizations is not None and player.user:
        custom_fields = body.customizations.model_fields_set
        for field in (
            "gradient_1",
            "gradient_2",
            "gradient_3",
        ):
            if field in custom_fields:
                setattr(player.user, field, getattr(body.customizations, field))
                user_update_fields.append(field)

        if "tagline" in custom_fields:
            player.user.short_bio = body.customizations.tagline
            user_update_fields.append("short_bio")

        if player.user.gradient_2 is not None and player.user.gradient_1 is None:
            return Status(
                400,
                ErrorResponse(
                    error="gradient_2 requires gradient_1 to be set",
                    details=None,
                ),
            )
        if player.user.gradient_3 is not None and player.user.gradient_2 is None:
            return Status(
                400,
                ErrorResponse(
                    error="gradient_3 requires gradient_2 to be set",
                    details=None,
                ),
            )

    if player_update_fields:
        player.save(update_fields=player_update_fields)
    if user_update_fields and player.user:
        player.user.save(update_fields=user_update_fields)

    return Status(200, _build_profile_response(player))


@router.delete(
    "/me",
    response={204: None, codes_4xx: ErrorResponse},
    summary="Delete My Account",
    description="""\
Deletes the authenticated player's account.
Blanks the Player record (runs are preserved) and deletes the linked Django User.
""",
    auth=player_session_auth,
)
def delete_me(
    request: HttpRequest,
) -> Status:
    player: Players = request.auth  # type: ignore
    user = player.user
    user_id: int | None = user.id if user is not None else None
    old_pfp = player.pfp

    try:
        with transaction.atomic():
            player.name = "Anonymous"
            player.nickname = None
            player.pfp = None
            player.pronouns = None
            player.twitch = None
            player.youtube = None
            player.twitter = None
            player.bluesky = None
            player.discord = None
            player.countrycode = None
            player.claim_status = Players.ClaimStatus.DELETED
            player.sync_paused = True
            player.user = None
            player.save(
                update_fields=[
                    "name",
                    "nickname",
                    "pfp",
                    "pronouns",
                    "twitch",
                    "youtube",
                    "twitter",
                    "bluesky",
                    "discord",
                    "countrycode",
                    "claim_status",
                    "sync_paused",
                    "user",
                ]
            )

            player.moderated_games.clear()

            if user is not None:
                if user.profile_bg:
                    user.profile_bg.delete(save=False)
                user.delete()
    except Exception:
        logger.exception("Failed to delete account for player %s", player.id)
        return Status(
            500,
            ErrorResponse(
                error="Failed to delete account",
                details=None,
            ),
        )

    try:
        request.session.flush()
    except Exception:
        logger.exception(
            "Failed to flush current session for deleted player %s", player.id
        )

    if user_id is not None:
        _invalidate_user_sessions(user_id)

    if old_pfp:
        pfp_basename = os.path.basename(old_pfp)
        pfp_fs_path = os.path.join(PFP_DIR, pfp_basename)
        if not os.path.abspath(pfp_fs_path).startswith(
            os.path.abspath(PFP_DIR),
        ):
            logger.warning("Skipping suspicious pfp path: %s", old_pfp)
        else:
            try:
                os.remove(pfp_fs_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning(
                    "Failed to remove pfp file %s after account deletion",
                    pfp_fs_path,
                )

    logger.info(
        "Account deleted: player_id=%s user_id=%s",
        player.id,
        user_id,
    )

    return Status(204, None)
