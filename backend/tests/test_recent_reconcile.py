from datetime import datetime
from datetime import timezone as _tz
from typing import Any
from unittest import mock

from django.conf import settings
from django.test import TestCase
from srl.models import Categories, Games, ReconciliationItem, ReconciliationJob, Runs
from srl.models.reconciliation import ReconAction, ReconPhase, ReconScope, ReconStatus
from srl.srcom import reconciliation as recon
from srl.tasks.reconciliation import run_bounded_game_reconciliation


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


def _make_job(
    **overrides: Any,
) -> ReconciliationJob:
    """Create a minimal GAME-scope ReconciliationJob for context/task tests."""
    defaults: dict[str, Any] = {
        "scope": ReconScope.GAME.value,
        "target_id": "jy65g3de",
        "phase": ReconPhase.P1.value,
    }
    defaults.update(overrides)
    return ReconciliationJob.objects.create(**defaults)


class ReconContextHygieneTests(TestCase):
    """Job-scoped contextvars must not leak between jobs on a reused worker process."""

    def test_cancelled_job_does_not_poison_next_context(
        self,
    ) -> None:
        """A cancelled job must not instantly cancel the next job on the same worker."""
        cancelled = _make_job(cancel_requested=True)
        with recon.reconciliation_context(cancelled):
            with self.assertRaises(recon.CancellationRequested):
                recon.check_cancelled()

        fresh = _make_job()
        with recon.reconciliation_context(fresh):
            recon.check_cancelled()

    def test_unflushed_items_do_not_leak_into_next_job(
        self,
    ) -> None:
        """Items buffered by a job that died mid-flight must not bleed into the next job."""
        dying = _make_job()
        with recon.reconciliation_context(dying):
            recon.record_reconciliation_item("run", "run1", ReconAction.CREATED.value)

        clean = _make_job()
        with recon.reconciliation_context(clean):
            recon.flush_counts()

        self.assertEqual(ReconciliationItem.objects.count(), 0)
        clean.refresh_from_db()
        self.assertEqual(clean.counts_created, 0)


class BoundedReconcileTaskStatusTests(TestCase):
    def test_cancellation_marks_job_cancelled(
        self,
    ) -> None:
        """A CancellationRequested escape must record CANCELLED, not FAILED."""
        job = _make_job()

        with mock.patch(
            "srl.srcom.recent_reconcile.reconcile_recent_game_runs",
            side_effect=recon.CancellationRequested(),
        ):
            run_bounded_game_reconciliation.apply(args=[str(job.id)])

        job.refresh_from_db()
        self.assertEqual(job.status, ReconStatus.CANCELLED.value)
        self.assertEqual(job.error_summary, "")

    def test_unexpected_error_marks_job_failed(
        self,
    ) -> None:
        """Genuine errors must still record FAILED with the error summary."""
        job = _make_job()

        with mock.patch(
            "srl.srcom.recent_reconcile.reconcile_recent_game_runs",
            side_effect=RuntimeError("boom"),
        ):
            run_bounded_game_reconciliation.apply(args=[str(job.id)])

        job.refresh_from_db()
        self.assertEqual(job.status, ReconStatus.FAILED.value)
        self.assertEqual(job.error_summary, "boom")
