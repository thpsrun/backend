from __future__ import annotations

from api.models import APIKey, APIKeyRevokedReason
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
        defaulttime="realtime",
        idefaulttime="realtime",
        pointsmax=1000,
        ipointsmax=100,
    )


class ApiSignalTests(TestCase):
    def test_removing_mod_revokes_scoped_key(
        self,
    ) -> None:
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
        self.assertIsNotNone(key.revoked_at)

    def test_superuser_demotion_revokes_admin_scoped_key(
        self,
    ) -> None:
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

    def test_empty_scope_key_not_revoked_on_unrelated_mod_change(
        self,
    ) -> None:
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

    def test_saving_user_without_change_leaves_backable_key_untouched(
        self,
    ) -> None:
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

    def test_deactivating_user_revokes_unscoped_key(
        self,
    ) -> None:
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

    def test_user_save_does_not_revoke_player_scoped_submit_key(
        self,
    ) -> None:
        """Regression: saving a claimed player's CustomUser must not revoke a
        game-scoped runs.submit key owned by a non-mod player. The previous
        backability logic mis-classified this case as unbackable.
        """
        User = get_user_model()
        user = User.objects.create_user(  # type: ignore
            username="submitter",
            email="submitter@example.com",
            password="supersecret123",
        )
        Players.objects.create(
            id="psig2",
            name="p",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=user,
        )
        game = _make_game("sggm3")
        key, _ = APIKey.objects.create_key(
            user=user,
            label="x",
            scope_capabilities=["runs.submit"],
        )
        key.scope_games.add(game)

        user.save()

        key.refresh_from_db()
        self.assertFalse(key.revoked)

    def test_reverse_m2m_remove_revokes_scoped_key(
        self,
    ) -> None:
        """Removing a moderator via the reverse side of the M2M should still
        drive auto-revocation.
        """
        User = get_user_model()
        user = User.objects.create_user(  # type: ignore
            username="revmod",
            email="revmod@example.com",
            password="supersecret123",
        )
        player = Players.objects.create(
            id="psig3",
            name="m",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=user,
        )
        game = _make_game("sggm4")
        game.moderators.add(player)

        key, _ = APIKey.objects.create_key(
            user=user,
            label="x",
            scope_capabilities=["runs.verify"],
        )
        key.scope_games.add(game)

        # Reverse side: Games.moderators has related_name="moderated_games" on Players.
        player.moderated_games.remove(game)  # type: ignore

        key.refresh_from_db()
        self.assertTrue(key.revoked)
        self.assertEqual(
            key.revoked_reason,
            APIKeyRevokedReason.PERMISSION_REVOKED,
        )

    def test_deleting_last_scope_game_revokes_key(
        self,
    ) -> None:
        """When a key's only scope game is deleted, the M2M cascade would silently
        empty scope_games and broaden the key. The pre_delete signal revokes it.
        """
        User = get_user_model()
        user = User.objects.create_user(  # type: ignore
            username="gdel",
            email="gdel@example.com",
            password="supersecret123",
            is_superuser=True,
        )
        game = _make_game("sggm5")
        key, _ = APIKey.objects.create_key(
            user=user,
            label="x",
            scope_capabilities=["games.manage"],
        )
        key.scope_games.add(game)

        game.delete()

        key.refresh_from_db()
        self.assertTrue(key.revoked)
        self.assertEqual(
            key.revoked_reason,
            APIKeyRevokedReason.PERMISSION_REVOKED,
        )

    def test_deleting_one_of_several_scope_games_does_not_revoke(
        self,
    ) -> None:
        """If the deleted game was one of several in the key's scope, the key is
        still game-restricted to the remaining set - leave it alone.
        """
        User = get_user_model()
        user = User.objects.create_user(  # type: ignore
            username="gdel2",
            email="gdel2@example.com",
            password="supersecret123",
            is_superuser=True,
        )
        g1 = _make_game("sggm6")
        g2 = _make_game("sggm7")
        key, _ = APIKey.objects.create_key(
            user=user,
            label="x",
            scope_capabilities=["games.manage"],
        )
        key.scope_games.add(g1, g2)

        g1.delete()

        key.refresh_from_db()
        self.assertFalse(key.revoked)
        self.assertEqual(
            list(key.scope_games.values_list("pk", flat=True)),
            [g2.pk],
        )
