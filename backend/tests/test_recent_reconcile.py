from datetime import datetime
from datetime import timezone as _tz
from unittest import mock

from django.conf import settings
from django.test import TestCase
from srl.models import Categories, Games, Runs


class ReconSettingTests(TestCase):
    def test_recent_run_limit_default(self) -> None:
        self.assertEqual(getattr(settings, "RECON_RECENT_RUN_LIMIT", None), 20)


class BoundedReconcileTests(TestCase):
    def setUp(
        self,
    ) -> None:
        self.game = Games.objects.create(
            id="jy65g3de",
            name="THPS1",
            slug="thps1",
            twitch="THPS1",
            release="2000-01-01",
            boxart="https://x.invalid/c",
            defaulttime="rta",
            idefaulttime="rta",
            pointsmax=1000,
            ipointsmax=100,
        )
        self.cat = Categories.objects.create(
            id="wkpjr8kr",
            game=self.game,
            name="Any%",
            type="per-game",
            defaulttime="rta",
        )
        for rid, secs in (("a", 300.0), ("b", 310.0)):
            Runs.objects.create(
                id=rid,
                game=self.game,
                category=self.cat,
                runtype="main",
                place=0,
                vid_status="verified",
                obsolete=False,
                points=0,
                time_secs=secs,
                date=datetime(2024, 1, 1, tzinfo=_tz.utc),
            )

    def test_reconciles_recent_runs_and_recomputes_unique_variants(
        self,
    ) -> None:
        from srl.srcom import recent_reconcile

        with mock.patch.object(
            recent_reconcile, "_recent_verified_run_ids", return_value=["a", "b"]
        ), mock.patch.object(
            recent_reconcile, "reconcile_one_run"
        ) as one, mock.patch.object(
            recent_reconcile, "run_leaderboard_recompute"
        ) as recompute:
            recent_reconcile.reconcile_recent_game_runs(
                self.game.id, job_id=None, limit=20
            )

        self.assertEqual(one.call_count, 2)
        self.assertEqual(recompute.call_count, 1)


class ReconcileRoutingTests(TestCase):
    def test_game_scope_routes_to_bounded(
        self,
    ) -> None:
        """GAME scope must dispatch the bounded reconcile task."""
        import api.v1.routers.auth.reconcile as r

        with mock.patch.object(r.run_bounded_game_reconciliation, "delay") as bounded:
            r._dispatch_recon_job("jid")
        bounded.assert_called_once_with("jid")
