from django.conf import settings

from srl.leaderboard.recompute import run_leaderboard_recompute
from srl.leaderboard.resolution import resolve_leaderboard
from srl.models import Runs
from srl.srcom.leaderboards import sync_single_run
from srl.srcom.reconciliation import flush_counts, reconciliation_context
from srl.utils import src_api


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
        for rid in run_ids:
            reconcile_one_run(rid)
        flush_counts()
        seen: set[tuple] = set()
        runs = Runs.objects.filter(id__in=run_ids).select_related(
            "game",
            "category",
            "level",
        )
        for run in runs:
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
            run_leaderboard_recompute(variant)

    if job_id is None:
        _do()
    else:
        from srl.models import ReconciliationJob

        job = ReconciliationJob.objects.get(id=job_id)
        with reconciliation_context(job):
            _do()
