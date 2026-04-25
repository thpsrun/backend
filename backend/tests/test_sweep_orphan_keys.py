from __future__ import annotations

from io import StringIO

from api.models import APIKey, APIKeyRevokedReason
from django.contrib.auth import get_user_model
from django.core.management import call_command
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


class SweepOrphanKeysTests(TestCase):
    def test_sweep_revokes_unbackable_keys(
        self,
    ) -> None:
        User = get_user_model()
        user = User.objects.create_user(  # type: ignore
            username="swu",
            email="swu@example.com",
            password="supersecret123",
        )
        player = Players.objects.create(
            id="swp",
            name="u",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=user,
        )
        game = _make_game("swgm1")
        game.moderators.add(player)
        key, _ = APIKey.objects.create_key(
            user=user,
            label="x",
            scope_capabilities=["runs.verify"],
        )
        key.scope_games.add(game)

        # Bypass signals by deleting the through-table row directly. QuerySet
        # .delete() on an auto-generated M2M through model does NOT fire
        # m2m_changed, so the key stays live for the sweep to find.
        through = Games.moderators.through
        through.objects.filter(
            games_id=game.pk,
            players_id=player.pk,
        ).delete()

        out = StringIO()
        call_command("sweep_orphan_keys", stdout=out)

        key.refresh_from_db()
        self.assertTrue(key.revoked)
        self.assertEqual(
            key.revoked_reason,
            APIKeyRevokedReason.PERMISSION_REVOKED,
        )
        self.assertIn("revoked 1", out.getvalue().lower())

    def test_sweep_leaves_backable_keys_alone(
        self,
    ) -> None:
        User = get_user_model()
        user = User.objects.create_user(  # type: ignore
            username="swokay",
            email="swokay@example.com",
            password="supersecret123",
        )
        key, _ = APIKey.objects.create_key(user=user, label="x")

        out = StringIO()
        call_command("sweep_orphan_keys", stdout=out)

        key.refresh_from_db()
        self.assertFalse(key.revoked)
        self.assertIn("revoked 0", out.getvalue().lower())

    def test_sweep_dry_run_does_not_mutate(
        self,
    ) -> None:
        User = get_user_model()
        user = User.objects.create_user(  # type: ignore
            username="swdry",
            email="swdry@example.com",
            password="supersecret123",
        )
        player = Players.objects.create(
            id="swdryp",
            name="u",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=user,
        )
        game = _make_game("swgm2")
        game.moderators.add(player)
        key, _ = APIKey.objects.create_key(
            user=user,
            label="x",
            scope_capabilities=["runs.verify"],
        )
        key.scope_games.add(game)

        through = Games.moderators.through
        through.objects.filter(
            games_id=game.pk,
            players_id=player.pk,
        ).delete()

        out = StringIO()
        call_command("sweep_orphan_keys", "--dry-run", stdout=out)

        key.refresh_from_db()
        self.assertFalse(key.revoked)
        self.assertIn("dry-run would revoke", out.getvalue().lower())
