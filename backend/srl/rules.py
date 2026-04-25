from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from rules.predicates import predicate

from srl.models.players import Players
from srl.models.run_players import RunPlayers

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from guides.models import Guides

    from srl.models.games import Games
    from srl.models.runs import Runs


UserLike: TypeAlias = "AbstractBaseUser | AnonymousUser | None"


@predicate
def is_authenticated(
    user: UserLike,
) -> bool:
    return bool(user and getattr(user, "is_authenticated", False))


@predicate
def is_superuser(
    user: UserLike,
) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_superuser", False),
    )


@predicate
def has_claimed_player(
    user: UserLike,
) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    player = getattr(user, "player", None)
    if player is None:
        return False
    return getattr(player, "claim_status", None) == Players.ClaimStatus.CLAIMED


@predicate
def is_game_moderator(
    user: UserLike,
    game: "Games | None",
) -> bool:
    if not user or not getattr(user, "is_authenticated", False) or game is None:
        return False
    player = getattr(user, "player", None)
    if player is None:
        return False
    return game.moderators.filter(pk=player.pk).exists()


@predicate
def is_run_game_moderator(
    user: UserLike,
    run: "Runs | None",
) -> bool:
    if run is None:
        return False
    return is_game_moderator(user, run.game)


@predicate
def is_run_participant(
    user: UserLike,
    run: "Runs | None",
) -> bool:
    if not user or not getattr(user, "is_authenticated", False) or run is None:
        return False
    player = getattr(user, "player", None)
    if player is None:
        return False
    return RunPlayers.objects.filter(run=run, player=player).exists()


@predicate
def owns_guide(
    user: UserLike,
    guide: "Guides | None",
) -> bool:
    if not user or not getattr(user, "is_authenticated", False) or guide is None:
        return False
    return getattr(guide, "owner_id", None) == user.pk


@predicate
def is_guide_game_moderator(
    user: UserLike,
    guide: "Guides | None",
) -> bool:
    if guide is None:
        return False
    return is_game_moderator(user, guide.game)
