from __future__ import annotations

from api.backability import is_key_backable
from api.models import APIKey
from django.contrib.auth import get_user_model
from django.test import TestCase
from srl.models.games import Games
from srl.models.players import Players


def _make_game(game_id: str) -> Games:
    return Games.objects.create(
        id=game_id,
        name=game_id,
        slug=game_id,
        twitch=game_id,
        release="2000-01-01",
        boxart=f"https://example.com/{game_id}.png",
        defaulttime="realtime",
        idefaulttime="realtime",
        pointsmax=1000,
        ipointsmax=100,
    )


class BackabilityTests(TestCase):
    def setUp(self) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="bkuser",
            email="bkuser@example.com",
            password="supersecret123",
        )

    def test_empty_scope_always_backable(self) -> None:
        key, _ = APIKey.objects.create_key(user=self.user, label="x")
        self.assertTrue(is_key_backable(key))

    def test_inactive_user_empty_scope_not_backable(self) -> None:
        key, _ = APIKey.objects.create_key(user=self.user, label="x")
        self.user.is_active = False
        self.user.save()
        key.refresh_from_db()
        self.assertFalse(is_key_backable(key))

    def test_mod_scoped_key_backable_when_still_mod(self) -> None:
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

    def test_mod_scoped_key_not_backable_after_demotion(self) -> None:
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

    def test_non_scoped_capability_requires_global_perm(self) -> None:
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
