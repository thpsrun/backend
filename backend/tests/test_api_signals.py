from __future__ import annotations

from api.models import APIKey, APIKeyRevokedReason
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


class ApiSignalTests(TestCase):
    def test_removing_mod_revokes_scoped_key(self) -> None:
        User = get_user_model()
        user = User.objects.create_user(  # type: ignore
            username="modsig",
            email="modsig@example.com",
            password="supersecret123",
        )
        player = Players.objects.create(
            id="psig1",
            name="m",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=user,
        )
        game = _make_game("sggm1")
        game.moderators.add(player)

        key, _ = APIKey.objects.create_key(
            user=user,
            label="x",
            scope_capabilities=["runs.verify"],
        )
        key.scope_games.add(game)

        game.moderators.remove(player)

        key.refresh_from_db()
        self.assertTrue(key.revoked)
        self.assertEqual(
            key.revoked_reason,
            APIKeyRevokedReason.PERMISSION_REVOKED,
        )

    def test_superuser_demotion_revokes_admin_scoped_key(self) -> None:
        User = get_user_model()
        user = User.objects.create_user(  # type: ignore
            username="admsig",
            email="admsig@example.com",
            password="supersecret123",
            is_superuser=True,
        )
        key, _ = APIKey.objects.create_key(
            user=user,
            label="x",
            scope_capabilities=["users.admin"],
        )

        user.is_superuser = False
        user.save()

        key.refresh_from_db()
        self.assertTrue(key.revoked)
        self.assertEqual(
            key.revoked_reason,
            APIKeyRevokedReason.PERMISSION_REVOKED,
        )

    def test_empty_scope_key_not_revoked_on_unrelated_mod_change(self) -> None:
        User = get_user_model()
        alice = User.objects.create_user(  # type: ignore
            username="alicesig",
            email="alicesig@example.com",
            password="supersecret123",
        )
        key, _ = APIKey.objects.create_key(user=alice, label="x")

        bob = User.objects.create_user(  # type: ignore
            username="bobsig",
            email="bobsig@example.com",
            password="supersecret123",
        )
        bob_player = Players.objects.create(
            id="pbsig",
            name="b",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=bob,
        )
        game = _make_game("sggm2")
        game.moderators.add(bob_player)
        game.moderators.remove(bob_player)

        key.refresh_from_db()
        self.assertFalse(key.revoked)

    def test_saving_user_without_change_leaves_backable_key_untouched(self) -> None:
        User = get_user_model()
        user = User.objects.create_user(  # type: ignore
            username="resave",
            email="resave@example.com",
            password="supersecret123",
        )
        key, _ = APIKey.objects.create_key(user=user, label="x")

        user.save()

        key.refresh_from_db()
        self.assertFalse(key.revoked)

    def test_deactivating_user_revokes_unscoped_key(self) -> None:
        User = get_user_model()
        user = User.objects.create_user(  # type: ignore
            username="deact",
            email="deact@example.com",
            password="supersecret123",
        )
        key, _ = APIKey.objects.create_key(user=user, label="x")

        user.is_active = False
        user.save()

        key.refresh_from_db()
        self.assertTrue(key.revoked)
        self.assertEqual(
            key.revoked_reason,
            APIKeyRevokedReason.PERMISSION_REVOKED,
        )
