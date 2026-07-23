import logging
from typing import Callable

from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings

from srl.leaderboard.recompute import recompute_variant_locked
from srl.leaderboard.resolution import resolve_leaderboard
from srl.models import Games, ReconciliationJob, Runs
from srl.models.reconciliation import ReconAction
from srl.srcom.leaderboards import (
    _ensure_category_for_obsolete_run,
    _ensure_level_for_obsolete_run,
    _reconcile_run_from_payload,
    _sync_game_structure,
    sync_single_run,
)
from srl.srcom.reconciliation import (
    CancellationRequested,
    check_cancelled,
    flush_counts,
    reconciliation_context,
    record_reconciliation_item,
)
from srl.srcom.schema.src import SrcRunsModel
from srl.utils import src_api, src_api_paginate, src_api_probe

logger = logging.getLogger(__name__)

_JOB_CONTROL_EXCEPTIONS = (CancellationRequested, SoftTimeLimitExceeded)


def _recent_verified_run_ids(
    game_id: str,
    limit: int,
) -> list[str]:
    """Return the last `limit` verified run ids for a game, newest verify-date first.

    Arguments:
        game_id (str): The SRC game id to query.
        limit (int): Maximum number of run ids to return.

    Returns:
        List of run id strings from SRC, most-recently-verified first.
    """
    url = (
        f"https://www.speedrun.com/api/v1/runs?game={game_id}"
        f"&status=verified&orderby=verify-date&direction=desc&max={int(limit)}"
    )
    data = src_api(url)
    runs = data if isinstance(data, list) else []
    return [r["id"] for r in runs if isinstance(r, dict) and r.get("id")]


def _run_under_job_context(
    job_id: str | None,
    fn: Callable[[], None],
) -> None:
    """Run `fn` under the job's reconciliation context, or bare when `job_id` is None.

    Arguments:
        job_id (str | None): `ReconciliationJob` UUID string, or None for a context-free run.
        fn (Callable[[], None]): The zero-argument reconcile body to execute.
    """
    if job_id is None:
        fn()
        return
    job = ReconciliationJob.objects.get(id=job_id)
    with reconciliation_context(job):
        fn()


def _recompute_affected_variants(
    run_ids: list[str],
) -> None:
    """Recompute each unique leaderboard variant touched by `run_ids`, exactly once.

    Arguments:
        run_ids (list[str]): Run ids whose leaderboard variants should be rebuilt.
    """
    seen: set[tuple] = set()
    runs = Runs.objects.filter(id__in=run_ids).select_related(
        "game", "category", "level"
    )
    for run in runs:
        check_cancelled()
        variant = resolve_leaderboard(run)
        key = (
            variant["game_id"],
            variant["category_id"],
            variant["level_id"],
            variant["runtype"],
            tuple(sorted((variant.get("variable_value_map") or {}).items())),
        )
        if key in seen:
            continue
        seen.add(key)
        recompute_variant_locked(variant)


def _fetch_game_runs_from_src(
    game_id: str,
) -> dict[str, dict]:
    """Bulk-fetch every SRC run of a game, keyed by run id.

    Arguments:
        game_id (str): Canonical SRC game id to crawl.

    Returns:
        payloads (dict[str, dict]): Bare SRC run payloads keyed by run id.
    """
    payloads: dict[str, dict] = {}
    for raw_run in src_api_paginate(
        f"https://speedrun.com/api/v1/runs?game={game_id}",
    ):
        check_cancelled()
        run_id = raw_run.get("id") if isinstance(raw_run, dict) else None
        if run_id:
            payloads[run_id] = raw_run
    return payloads


def reconcile_one_run(
    run_id: str,
) -> None:
    """Reconcile a single run against SRC (reuses the discovery/recon single-run path).

    Arguments:
        run_id (str): The SRC run id to sync.
    """
    sync_single_run(run_id)


def reconcile_recent_game_runs(
    game_id: str,
    job_id: str | None,
    limit: int | None = None,
) -> None:
    """Reconcile the last N verified runs for a game, then recompute their unique variants.

    Arguments:
        game_id (str): The SRC game id whose recent runs will be reconciled.
        job_id (str | None): `ReconciliationJob` UUID string. When provided, syncs run under
            reconciliation context (enabling item recording and points=0 behaviour). When
            ``None``, the reconciliation is run without a job context.
        limit (int | None): Maximum number of recent runs to process.
    """
    limit = limit or settings.RECON_RECENT_RUN_LIMIT
    run_ids = _recent_verified_run_ids(game_id, limit)

    def _do() -> None:
        """Sync each recent run, persist buffered items, then recompute variants."""
        for rid in run_ids:
            reconcile_one_run(rid)
        flush_counts()
        _recompute_affected_variants(run_ids)

    _run_under_job_context(job_id, _do)


def reconcile_game_sweep(
    game_id: str,
    job_id: str | None,
    runtype: str,
) -> None:
    """Reconcile every local run of `runtype` for a game, then recompute affected variants.

    Keys off the local DB (so obsolete runs are reached), fetches the game's runs from SRC
    in bulk, upserts metadata preserving the obsolete flag, records runs missing on SRC,
    and recomputes each unique affected leaderboard variant.

    Arguments:
        game_id (str): SRC game id to sweep.
        job_id (str | None): ReconciliationJob UUID; when set, runs under reconciliation context.
        runtype (str): "main" for full-game boards or "il" for individual-level boards.
    """

    def _do() -> None:
        """Upsert every local run of the runtype from SRC, then recompute variants."""
        game_info = Games.objects.filter(id=game_id).first()
        if game_info is None:
            return
        try:
            _sync_game_structure(game_id)
        except _JOB_CONTROL_EXCEPTIONS:
            raise
        except Exception:
            # A stale category/level tree is repairable per run (the _ensure_* guards below fetch
            # anything missing), so log and keep sweeping rather than aborting the whole job.
            logger.warning(
                "sweep structure sync failed for game %s",
                game_id,
                exc_info=True,
            )

        run_ids = list(
            Runs.objects.filter(game=game_id, runtype=runtype).values_list(
                "id", flat=True
            ),
        )
        src_payloads = _fetch_game_runs_from_src(game_id)

        for run_id in run_ids:
            check_cancelled()
            raw_run = src_payloads.get(run_id)
            if raw_run is None:
                # Absent from the bulk crawl: tell "deleted on SRC" apart from a transient
                # failure with a single-run probe. The probe retries 420/503 internally, so a
                # non-200 here is already past the retry budget.
                status_code, envelope = src_api_probe(
                    f"https://speedrun.com/api/v1/runs/{run_id}",
                )
                if status_code == 404:
                    record_reconciliation_item(
                        "run",
                        run_id,
                        ReconAction.MISSING_ON_SRC.value,
                        error="run not found on SRC (deleted?)",
                    )
                    continue
                if status_code != 200 or not isinstance(envelope, dict):
                    record_reconciliation_item(
                        "run",
                        run_id,
                        ReconAction.FAILED.value,
                        error=f"SRC fetch failed with status {status_code}",
                    )
                    continue
                raw_run = envelope.get("data")

            if not isinstance(raw_run, dict):
                record_reconciliation_item(
                    "run",
                    run_id,
                    ReconAction.FAILED.value,
                    error="SRC response missing run data",
                )
                continue

            try:
                src_run = SrcRunsModel.model_validate(raw_run)
            except _JOB_CONTROL_EXCEPTIONS:
                raise
            except Exception:
                record_reconciliation_item(
                    "run",
                    run_id,
                    ReconAction.FAILED.value,
                    error="run payload failed validation",
                )
                continue

            if not _ensure_category_for_obsolete_run(src_run):
                record_reconciliation_item(
                    "run",
                    run_id,
                    ReconAction.FAILED.value,
                    error="category unavailable",
                )
                continue
            if not _ensure_level_for_obsolete_run(src_run):
                record_reconciliation_item(
                    "run",
                    run_id,
                    ReconAction.FAILED.value,
                    error="level unavailable",
                )
                continue

            try:
                _reconcile_run_from_payload(src_run, game_info)
            except _JOB_CONTROL_EXCEPTIONS:
                raise
            except Exception as exc:
                record_reconciliation_item(
                    "run",
                    run_id,
                    ReconAction.FAILED.value,
                    error=f"run upsert failed: {exc}"[:500],
                )
                continue

        flush_counts()
        _recompute_affected_variants(run_ids)

    _run_under_job_context(job_id, _do)
