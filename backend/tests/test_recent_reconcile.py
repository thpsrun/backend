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
        """Both runs sync, but their shared variant recomputes exactly once (locked)."""
        from srl.srcom import recent_reconcile

        with mock.patch.object(
            recent_reconcile, "_recent_verified_run_ids", return_value=["a", "b"]
        ), mock.patch.object(
            recent_reconcile, "reconcile_one_run"
        ) as one, mock.patch.object(
            recent_reconcile, "recompute_variant_locked"
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


class StartReconciliationTargetResolutionTests(TestCase):
    def setUp(
        self,
    ) -> None:
        """Reset the lock cache and create the game the target strings resolve to."""
        # The reconcile lock lives in the cache; dispatch is mocked here so the lock is
        # never released. Clear it between tests so each starts from a clean lock state.
        from django.core.cache import cache

        cache.clear()
        self.game = Games.objects.create(
            id="ok6qq06g",
            name="Tony Hawk's Underground 2",
            slug="thug2",
            twitch="THUG2",
            release="2004-01-01",
            boxart="https://x.invalid/c",
            defaulttime="rta",
            idefaulttime="rta",
            pointsmax=1000,
            ipointsmax=100,
        )

    def _start(
        self,
        target_id: str,
    ) -> Any:
        """Call the view directly with an unauthenticated request, dispatch stubbed out."""
        import api.v1.routers.auth.reconcile as r
        from api.v1.schemas.reconciliation import (
            ReconcileRequest,
            ReconcileScope,
            SourceOfTruth,
        )

        payload = ReconcileRequest(
            scope=ReconcileScope.GAME,
            source_of_truth=SourceOfTruth.SRC,
            target_id=target_id,
        )
        request = mock.Mock()
        request.user.is_authenticated = False
        with mock.patch.object(r, "_dispatch_recon_job"):
            return r.start_reconciliation(request, payload)

    def test_slug_target_is_stored_as_canonical_game_id(
        self,
    ) -> None:
        """Passing the slug must persist the SRC game id on the job, not the slug."""
        status, body = self._start("thug2")

        self.assertEqual(status, 202)
        job = ReconciliationJob.objects.get(id=body["id"])
        self.assertEqual(job.target_id, "ok6qq06g")

    def test_id_target_is_accepted_unchanged(
        self,
    ) -> None:
        """Passing the SRC id directly must keep working."""
        status, body = self._start("ok6qq06g")

        self.assertEqual(status, 202)
        job = ReconciliationJob.objects.get(id=body["id"])
        self.assertEqual(job.target_id, "ok6qq06g")

    def test_unknown_target_is_rejected_without_creating_a_job(
        self,
    ) -> None:
        """A target matching no local game must error out before a job is queued."""
        from ninja.errors import HttpError

        with self.assertRaises(HttpError) as ctx:
            self._start("not-a-real-game")

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ReconciliationJob.objects.count(), 0)

    def test_slug_target_resolution_is_case_insensitive(
        self,
    ) -> None:
        """'THUG2' must resolve like 'thug2' (shared resolve_game_or_none semantics)."""
        status, body = self._start("THUG2")

        self.assertEqual(status, 202)
        job = ReconciliationJob.objects.get(id=body["id"])
        self.assertEqual(job.target_id, "ok6qq06g")


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

    def test_unknown_mode_marks_job_failed(
        self,
    ) -> None:
        """An unrecognized mode must fail the job, not silently run a RECENT pass."""
        job = _make_job(mode="bogus")

        run_bounded_game_reconciliation.apply(args=[str(job.id)])

        job.refresh_from_db()
        self.assertEqual(job.status, ReconStatus.FAILED.value)
        self.assertIn("Unknown reconcile mode", job.error_summary)

    def test_soft_time_limit_marks_job_failed_with_clear_summary(
        self,
    ) -> None:
        """A soft time limit escape must finalize the job (FAILED) and release the lock."""
        from celery.exceptions import SoftTimeLimitExceeded

        job = _make_job()

        with mock.patch(
            "srl.srcom.recent_reconcile.reconcile_recent_game_runs",
            side_effect=SoftTimeLimitExceeded(),
        ):
            run_bounded_game_reconciliation.apply(args=[str(job.id)])

        job.refresh_from_db()
        self.assertEqual(job.status, ReconStatus.FAILED.value)
        self.assertIn("soft time limit", job.error_summary)


class GameSweepTests(TestCase):
    """reconcile_game_sweep fetch strategy, item recording, and error propagation."""

    def setUp(
        self,
    ) -> None:
        """Create a game with two local main runs for the sweep to process."""
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

    def _patched_sweep(
        self,
    ) -> Any:
        """Patch every collaborator of reconcile_game_sweep on its module."""
        from srl.srcom import recent_reconcile

        return mock.patch.multiple(
            recent_reconcile,
            _sync_game_structure=mock.DEFAULT,
            _fetch_game_runs_from_src=mock.DEFAULT,
            src_api_probe=mock.DEFAULT,
            SrcRunsModel=mock.DEFAULT,
            _ensure_category_for_obsolete_run=mock.DEFAULT,
            _ensure_level_for_obsolete_run=mock.DEFAULT,
            _reconcile_run_from_payload=mock.DEFAULT,
            recompute_variant_locked=mock.DEFAULT,
        )

    def test_bulk_payloads_skip_the_per_run_probe(
        self,
    ) -> None:
        """Runs present in the bulk crawl must be upserted without any per-run GET."""
        from srl.srcom import recent_reconcile

        with self._patched_sweep() as mocks:
            mocks["_fetch_game_runs_from_src"].return_value = {
                "a": {"id": "a"},
                "b": {"id": "b"},
            }
            mocks["_ensure_category_for_obsolete_run"].return_value = True
            mocks["_ensure_level_for_obsolete_run"].return_value = True

            recent_reconcile.reconcile_game_sweep(
                self.game.id, job_id=None, runtype="main"
            )

            mocks["src_api_probe"].assert_not_called()
            self.assertEqual(mocks["_reconcile_run_from_payload"].call_count, 2)
            self.assertEqual(mocks["recompute_variant_locked"].call_count, 1)

    def test_run_absent_from_bulk_is_probed_and_recorded_missing(
        self,
    ) -> None:
        """A 404 on the fallback probe must record MISSING_ON_SRC, not FAILED."""
        from srl.srcom import recent_reconcile

        job = _make_job(mode="full_game")

        with self._patched_sweep() as mocks:
            mocks["_fetch_game_runs_from_src"].return_value = {}
            mocks["src_api_probe"].return_value = (404, None)

            recent_reconcile.reconcile_game_sweep(
                self.game.id, job_id=str(job.id), runtype="main"
            )

            self.assertEqual(mocks["src_api_probe"].call_count, 2)

        items = ReconciliationItem.objects.filter(job=job)
        self.assertEqual(items.count(), 2)
        self.assertEqual(
            set(items.values_list("action", flat=True)),
            {ReconAction.MISSING_ON_SRC.value},
        )
        job.refresh_from_db()
        self.assertEqual(job.counts_skipped, 2)

    def test_soft_time_limit_escapes_the_sweep_loop(
        self,
    ) -> None:
        """Celery's soft-limit signal must abort the sweep, not be logged as a run failure."""
        from celery.exceptions import SoftTimeLimitExceeded
        from srl.srcom import recent_reconcile

        with self._patched_sweep() as mocks:
            mocks["_fetch_game_runs_from_src"].return_value = {
                "a": {"id": "a"},
                "b": {"id": "b"},
            }
            mocks["_ensure_category_for_obsolete_run"].return_value = True
            mocks["_ensure_level_for_obsolete_run"].return_value = True
            mocks["_reconcile_run_from_payload"].side_effect = SoftTimeLimitExceeded()

            with self.assertRaises(SoftTimeLimitExceeded):
                recent_reconcile.reconcile_game_sweep(
                    self.game.id, job_id=None, runtype="main"
                )

            # The first run's failure must abort the loop; run "b" is never attempted.
            self.assertEqual(mocks["_reconcile_run_from_payload"].call_count, 1)
