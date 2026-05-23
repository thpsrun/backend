from accounts.models import CustomUser
from api.models import APIKey
from api.v1.routers.auth.moderation import (
    ModerationError,
    _apply_moderation,
)
from api.v1.routers.resources.runs import router as runs_router
from api.v1.schemas.runs import ModeratorActionIn
from auditlog.context import clear_actor
from django.db import transaction
from django.test import TestCase
from ninja.testing import TestClient
from srl.models import Games, Players, Runs
from srl.models.base import LeaderboardChoices
from srl.models.src_sync import SRCSyncTask

User = CustomUser


class ApplyModerationTests(TestCase):
    run: Runs  # pyright: ignore[reportIncompatibleVariableOverride]

    def setUp(
        self,
    ) -> None:
        self.game = Games.objects.create(
            id="testgame",
            name="Test Game",
            slug="test-game",
            twitch="Test Game",
            release="2000-01-01",
            boxart="https://example.invalid/cover",
            defaulttime="rta",
            idefaulttime="rta",
            pointsmax=1000,
            ipointsmax=100,
        )
        self.user = User.objects.create_user(
            username="modplayer",
            email="mod@example.invalid",
            password="testpass",
        )
        self.user.encrypted_api_key = "fake-key"
        self.user.save(update_fields=["encrypted_api_key"])
        self.player = Players.objects.create(
            id="modplayer",
            name="modplayer",
            user=self.user,
        )
        self.game.moderators.add(self.player)
        self.run = Runs.objects.create(  # type: ignore[assignment]
            id="run01",
            game=self.game,
            runtype="main",
            place=1,
            vid_status="new",
            time="5m 00s",
            time_secs=300.0,
        )

    def tearDown(
        self,
    ) -> None:
        clear_actor()
        super().tearDown()

    def test_verify_creates_sync_task_and_sets_status(
        self,
    ) -> None:
        action = ModeratorActionIn(action="verify")
        with transaction.atomic():
            sync_task = _apply_moderation(
                run=self.run,
                action_in=action,
                actor_player=self.player,
            )
            self.run.save()

        assert sync_task is not None
        self.assertEqual(sync_task.action, SRCSyncTask.ActionType.VERIFY)
        self.assertEqual(sync_task.payload, {"status": {"status": "verified"}})
        self.run.refresh_from_db()
        self.assertEqual(self.run.vid_status, "verified")
        self.assertEqual(self.run.approver, self.player)

    def test_verify_requires_src_key(
        self,
    ) -> None:
        self.user.encrypted_api_key = None
        self.user.save(update_fields=["encrypted_api_key"])
        action = ModeratorActionIn(action="verify")
        with self.assertRaises(ModerationError) as ctx:
            with transaction.atomic():
                _apply_moderation(
                    run=self.run,
                    action_in=action,
                    actor_player=self.player,
                )
        self.assertEqual(ctx.exception.code, 403)

    def test_verify_fails_if_run_already_verified(
        self,
    ) -> None:
        self.run.vid_status = "verified"
        self.run.save(update_fields=["vid_status"])
        action = ModeratorActionIn(action="verify")
        with self.assertRaises(ModerationError) as ctx:
            with transaction.atomic():
                _apply_moderation(
                    run=self.run,
                    action_in=action,
                    actor_player=self.player,
                )
        self.assertEqual(ctx.exception.code, 400)

    def test_reject_requires_reason(
        self,
    ) -> None:
        action = ModeratorActionIn(action="reject", reason=None)
        with self.assertRaises(ModerationError) as ctx:
            with transaction.atomic():
                _apply_moderation(
                    run=self.run,
                    action_in=action,
                    actor_player=self.player,
                )
        self.assertEqual(ctx.exception.code, 400)

    def test_reject_payload_includes_reason(
        self,
    ) -> None:
        action = ModeratorActionIn(action="reject", reason="cheat suspected")
        with transaction.atomic():
            sync_task = _apply_moderation(
                run=self.run,
                action_in=action,
                actor_player=self.player,
            )
            self.run.save()
        assert sync_task is not None
        self.assertEqual(
            sync_task.payload,
            {"status": {"status": "rejected", "reason": "cheat suspected"}},
        )
        self.assertEqual(sync_task.action, SRCSyncTask.ActionType.REJECT)

    def test_review_sets_notes_and_returns_none(
        self,
    ) -> None:
        action = ModeratorActionIn(action="review", notes="please reupload")
        with transaction.atomic():
            sync_task = _apply_moderation(
                run=self.run,
                action_in=action,
                actor_player=self.player,
            )
            self.run.save()
        self.assertIsNone(sync_task)
        self.run.refresh_from_db()
        self.assertEqual(self.run.vid_status, "review")
        self.assertEqual(self.run.review_notes, "please reupload")

    def test_review_requires_notes(
        self,
    ) -> None:
        action = ModeratorActionIn(action="review", notes=None)
        with self.assertRaises(ModerationError) as ctx:
            with transaction.atomic():
                _apply_moderation(
                    run=self.run,
                    action_in=action,
                    actor_player=self.player,
                )
        self.assertEqual(ctx.exception.code, 400)

    def test_review_blank_notes_rejected(
        self,
    ) -> None:
        action = ModeratorActionIn(action="review", notes="   ")
        with self.assertRaises(ModerationError) as ctx:
            with transaction.atomic():
                _apply_moderation(
                    run=self.run,
                    action_in=action,
                    actor_player=self.player,
                )
        self.assertEqual(ctx.exception.code, 400)

    def test_review_allowed_when_already_in_review(
        self,
    ) -> None:
        self.run.vid_status = "review"
        self.run.review_notes = "old notes"
        self.run.save(update_fields=["vid_status", "review_notes"])
        action = ModeratorActionIn(action="review", notes="updated notes")
        with transaction.atomic():
            _apply_moderation(
                run=self.run,
                action_in=action,
                actor_player=self.player,
            )
            self.run.save()
        self.run.refresh_from_db()
        self.assertEqual(self.run.review_notes, "updated notes")

    def test_review_blocked_when_run_verified(
        self,
    ) -> None:
        self.run.vid_status = "verified"
        self.run.save(update_fields=["vid_status"])
        action = ModeratorActionIn(action="review", notes="too late")
        with self.assertRaises(ModerationError) as ctx:
            with transaction.atomic():
                _apply_moderation(
                    run=self.run,
                    action_in=action,
                    actor_player=self.player,
                )
        self.assertEqual(ctx.exception.code, 409)


class UpdateRunModeratorActionTests(TestCase):
    """PUT /runs/:run_id with moderator_action - atomic data + verdict.

    Builds its own auth/player/game setup rather than reusing AuthTestBase,
    because AuthTestBase creates a superuser with no linked Player and the
    moderation helper requires both a Player and a stored SRC key on its
    User.
    """

    run: Runs  # pyright: ignore[reportIncompatibleVariableOverride]

    def setUp(
        self,
    ) -> None:
        self.client = TestClient(runs_router)  # type: ignore

        self.mod_user = User.objects.create_user(
            username="modactor",
            email="modactor@example.invalid",
            password="testpass",
            is_superuser=True,
            is_staff=True,
        )
        self.mod_user.encrypted_api_key = "fake-key"
        self.mod_user.save(update_fields=["encrypted_api_key"])

        self.mod_player = Players.objects.create(
            id="modactor",
            name="modactor",
            user=self.mod_user,
        )

        self.key_obj, self.api_key = APIKey.objects.create_key(
            user=self.mod_user,
            label="Mod Test Key",
            description="Test key for moderator-action integration tests",
        )

        self.mod_game = Games.objects.create(
            id="modgame",
            name="Mod Game",
            slug="mod-game",
            twitch="Mod Game",
            release="2000-01-01",
            boxart="https://example.invalid/cover",
            defaulttime="rta",
            idefaulttime="rta",
            pointsmax=1000,
            ipointsmax=100,
            required_methods_fg=[LeaderboardChoices.REALTIME],
            required_methods_il=[LeaderboardChoices.REALTIME],
        )
        self.mod_game.moderators.add(self.mod_player)

        self.run = Runs.objects.create(  # type: ignore[assignment]
            id="modrun",
            game=self.mod_game,
            runtype="main",
            place=1,
            vid_status="new",
            time="5m 00s",
            time_secs=300.0,
            url="https://speedrun.com/mod-game/run/modrun",
        )

    def tearDown(
        self,
    ) -> None:
        clear_actor()
        super().tearDown()

    def test_data_edit_and_verify_atomic(
        self,
    ) -> None:
        response = self.client.put(
            "/modrun",
            json={
                "time": "4m 30s",
                "time_secs": 270.0,
                "moderator_action": {"action": "verify"},
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.vid_status, "verified")
        self.assertEqual(self.run.time_secs, 270.0)
        self.assertEqual(self.run.approver, self.mod_player)
        self.assertEqual(
            SRCSyncTask.objects.filter(
                run=self.run,
                action=SRCSyncTask.ActionType.VERIFY,
            ).count(),
            1,
        )

    def test_data_edit_without_action_unchanged_behavior(
        self,
    ) -> None:
        response = self.client.put(
            "/modrun",
            json={
                "time": "4m 30s",
                "time_secs": 270.0,
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.vid_status, "new")
        self.assertEqual(self.run.time_secs, 270.0)
        self.assertEqual(
            SRCSyncTask.objects.filter(
                run=self.run,
                action__in=[
                    SRCSyncTask.ActionType.VERIFY,
                    SRCSyncTask.ActionType.REJECT,
                ],
            ).count(),
            0,
        )

    def test_invalid_state_rolls_back_data_edit(
        self,
    ) -> None:
        self.run.vid_status = "verified"
        self.run.save(update_fields=["vid_status"])
        original_time_secs = self.run.time_secs

        response = self.client.put(
            "/modrun",
            json={
                "time": "4m 30s",
                "time_secs": 270.0,
                "moderator_action": {"action": "verify"},
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)

        self.run.refresh_from_db()
        self.assertEqual(self.run.time_secs, original_time_secs)
        self.assertEqual(self.run.vid_status, "verified")

    def test_review_action_sets_notes_no_sync_task(
        self,
    ) -> None:
        response = self.client.put(
            "/modrun",
            json={
                "moderator_action": {
                    "action": "review",
                    "notes": "please reupload",
                },
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.vid_status, "review")
        self.assertEqual(self.run.review_notes, "please reupload")
        self.assertEqual(SRCSyncTask.objects.filter(run=self.run).count(), 0)

    def test_reject_with_reason_creates_sync_task(
        self,
    ) -> None:
        response = self.client.put(
            "/modrun",
            json={
                "moderator_action": {
                    "action": "reject",
                    "reason": "cheat suspected",
                },
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.vid_status, "rejected")
        sync_task = SRCSyncTask.objects.get(
            run=self.run,
            action=SRCSyncTask.ActionType.REJECT,
        )
        self.assertEqual(
            sync_task.payload,
            {
                "status": {
                    "status": "rejected",
                    "reason": "cheat suspected",
                }
            },
        )
