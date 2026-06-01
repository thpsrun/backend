from __future__ import annotations

from api.backability import is_key_backable
from api.models import APIKey
from django.contrib.auth import get_user_model
from django.test import TestCase
from srl.models.games import Games
from srl.models.players import Players


def _make_game(
    game_id: str,
) -> Games:
    return Games.objects.create(
        id=game_id,
        name=game_id,
        slug=game_id,
        twitch=game_id,
        release="2000-01-01",
        boxart=f"https://example.com/{game_id}.png",
        defaulttime="rta",
        idefaulttime="rta",
        pointsmax=1000,
        ipointsmax=100,
    )


class BackabilityTests(TestCase):
    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="bkuser",
            email="bkuser@example.com",
            password="supersecret123",
        )

    def test_empty_scope_always_backable(
        self,
    ) -> None:
        key, _ = APIKey.objects.create_key(user=self.user, label="x")
        self.assertTrue(is_key_backable(key))

    def test_inactive_user_empty_scope_not_backable(
        self,
    ) -> None:
        key, _ = APIKey.objects.create_key(user=self.user, label="x")
        self.user.is_active = False
        self.user.save()
        key.refresh_from_db()
        self.assertFalse(is_key_backable(key))

    def test_mod_scoped_key_backable_when_still_mod(
        self,
    ) -> None:
        game = _make_game("bkgm1")
        player = Players.objects.create(
            id="bkp1",
            name="m",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=self.user,
        )
        game.moderators.add(player)
        key, _ = APIKey.objects.create_key(
            user=self.user,
            label="x",
            scope_capabilities=["runs.verify"],
        )
        key.scope_games.add(game)
        self.assertTrue(is_key_backable(key))

    def test_mod_scoped_key_not_backable_after_demotion(
        self,
    ) -> None:
        game = _make_game("bkgm2")
        player = Players.objects.create(
            id="bkp2",
            name="m",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=self.user,
        )
        game.moderators.add(player)
        key, _ = APIKey.objects.create_key(
            user=self.user,
            label="x",
            scope_capabilities=["runs.verify"],
        )
        key.scope_games.add(game)

        # Bypass signals: direct through-table delete so the signal handlers
        # don't pre-revoke before we assert.
        through = Games.moderators.through
        through.objects.filter(
            games_id=game.pk,
            players_id=player.pk,
        ).delete()

        self.assertFalse(is_key_backable(key))

    def test_non_scoped_capability_requires_global_perm(
        self,
    ) -> None:
        key, _ = APIKey.objects.create_key(
            user=self.user,
            label="x",
            scope_capabilities=["users.admin"],
        )
        self.assertFalse(is_key_backable(key))

        self.user.is_superuser = True
        self.user.save()
        key.refresh_from_db()
        self.assertTrue(is_key_backable(key))

    def test_player_scoped_key_backable_for_claimed_non_mod(
        self,
    ) -> None:
        """Regression: a claimed player with a game-scoped runs.submit key should
        stay backable even though they are not a moderator of the scope game.
        Previously backability treated every game-scoped cap as mod-requiring and
        incorrectly revoked these keys on the next user.save().
        """
        game = _make_game("bkgm3")
        Players.objects.create(
            id="bkp3",
            name="m",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=self.user,
        )
        key, _ = APIKey.objects.create_key(
            user=self.user,
            label="submit-only",
            scope_capabilities=["runs.submit"],
        )
        key.scope_games.add(game)
        self.assertTrue(is_key_backable(key))

    def test_player_scoped_key_unbackable_if_player_unclaimed(
        self,
    ) -> None:
        game = _make_game("bkgm4")
        player = Players.objects.create(
            id="bkp4",
            name="m",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=self.user,
        )
        key, _ = APIKey.objects.create_key(
            user=self.user,
            label="submit-only",
            scope_capabilities=["runs.submit"],
        )
        key.scope_games.add(game)
        self.assertTrue(is_key_backable(key))

        player.claim_status = Players.ClaimStatus.UNCLAIMED
        player.save()
        self.assertFalse(is_key_backable(key))

    def test_su_only_cap_revoked_when_superuser_lost(
        self,
    ) -> None:
        """Regression: runs.delete is superuser-only, but the old check used
        games.manage as a proxy — a demoted-from-SU but still-mod user kept
        their runs.delete key marked backable when it shouldn't have been.
        """
        game = _make_game("bkgm5")
        player = Players.objects.create(
            id="bkp5",
            name="m",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=self.user,
        )
        game.moderators.add(player)
        self.user.is_superuser = True
        self.user.save()

        key, _ = APIKey.objects.create_key(
            user=self.user,
            label="delete-only",
            scope_capabilities=["runs.delete"],
        )
        key.scope_games.add(game)
        self.assertTrue(is_key_backable(key))

        self.user.is_superuser = False
        self.user.save()
        key.refresh_from_db()
        # Still a mod of the game, but runs.delete needs SU. Must be unbackable.
        self.assertFalse(is_key_backable(key))
