from collections import defaultdict
from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from srl.leaderboard.resolution import resolve_leaderboard
from srl.models import Games, ReconciliationJob, Runs, RunVariableValues, Series
from srl.models.reconciliation import ReconAction, ReconScope, ReconStatus
from srl.srcom.recon_accumulators import get_affected_players, get_affected_variants
from srl.srcom.reconciliation import (
    CancellationRequested,
    check_cancelled,
    check_reconciliation,
    dispatch_chain_with_recon,
    dispatch_with_recon,
    reconciliation_context,
    record_failure,
    record_reconciliation_item,
    release_lock,
)
from srl.srcom.utils import create_leaderboard_link, variables_hash
from srl.utils import src_api_paginate

from ._common import init_recon_job, logger, recon_job_finalize
from .recalc import recalculate_leaderboard_task, recalculate_streaks_task

SERIES_RECON_ALL_TARGET = "*"
STUCK_THRESHOLD_MINUTES = 70


def _convert_to_lb_data(
    descriptor: dict,
) -> dict | None:
    var_values = descriptor.get("variable_values") or {}
    var_combo = list(var_values.items()) if var_values else None
    return create_leaderboard_link(
        game_id=descriptor["game_id"],
        category_id=descriptor["category_id"],
        il_id=descriptor.get("level_id"),
        var_combo=var_combo,
    )


def _resolve_game(
    raw: str,
) -> str:
    """Resolve raw `game_id` or slug to the canonical game id in one query."""
    if not raw:
        return raw
    match = Games.objects.filter(Q(id=raw) | Q(slug=raw)).only("id").first()
    if match is not None:
        return match.id
    return raw


def _build_filter_for_phase2(
    job: ReconciliationJob,
) -> dict:
    """Build the scope_filter passed to each sync_obsolete_runs child.

    For LEADERBOARD scope: full (game, category, level, variables) match.
    For GAME scope: just the game id."""
    if job.scope == ReconScope.GAME.value:
        return {"kind": "game", "game_id": _resolve_game(job.target_id)}
    descriptor = job.target_descriptor or {}
    return {
        "kind": "leaderboard",
        "game_id": _resolve_game(descriptor.get("game_id", "")),
        "category_id": descriptor.get("category_id", ""),
        "level_id": descriptor.get("level_id"),
        "variables": descriptor.get("variable_values", {}),
    }


def _scan_game_player_ids(
    game_id: str,
) -> set[str]:
    """Return every distinct user player_id with a verified run on the game."""
    if not game_id:
        return set()

    players: set[str] = set()
    for run in src_api_paginate(
        f"https://www.speedrun.com/api/v1/runs?game={game_id}&status=verified",
    ):
        for p in run.get("players") or []:
            if p.get("rel") == "user" and p.get("id"):
                players.add(p["id"])
    return players


@shared_task(bind=True, name="srl.run_reconciliation_job")
def run_reconciliation_job(
    self,
    job_id: str,
) -> None:
    from srl.srcom.leaderboards import (
        sync_game_runs,
        sync_leaderboards,
        sync_single_run,
    )

    job = ReconciliationJob.objects.get(id=job_id)
    init_recon_job(job, self.request.id)

    with recon_job_finalize(job_id):
        with reconciliation_context(job):
            try:
                if job.scope == ReconScope.RUN.value:
                    sync_single_run(job.target_id)
                elif job.scope == ReconScope.LEADERBOARD.value:
                    lb_data = _convert_to_lb_data(job.target_descriptor)
                    if lb_data is None:
                        raise ValueError(
                            f"failed to fetch leaderboard for descriptor: "
                            f"{job.target_descriptor}",
                        )
                    sync_leaderboards(lb_data)
                elif job.scope == ReconScope.GAME.value:
                    sync_game_runs(job.target_id)
                else:
                    raise ValueError(f"Unknown scope: {job.scope}")
            except CancellationRequested:
                pass
            except Exception as e:
                record_failure(job_id, str(e)[:1000])


@shared_task(bind=True, name="srl.run_series_reconciliation")
def run_series_reconciliation(
    self,
    job_id: str,
) -> None:
    """Drive a SERIES-scoped reconciliation job.

    When ``job.target_id`` is the sentinel ``SERIES_RECON_ALL_TARGET`` (``"*"``) the task sweeps
    every Series row in the local DB. Otherwise it scopes to the single series identified by
    ``target_id`` so callers can refresh one franchise without scanning unrelated series.
    """

    job = ReconciliationJob.objects.get(id=job_id)
    init_recon_job(job, self.request.id)

    with recon_job_finalize(job_id):
        with reconciliation_context(job):
            try:
                _run_series_body(job, job_id)
            except CancellationRequested:
                pass
            except Exception as e:
                record_failure(job_id, str(e)[:1000])


def _run_series_body(
    job: ReconciliationJob,
    job_id: str,
) -> None:
    from srl.srcom.series import import_new_game, iter_series_games, sync_series

    existing_ids = set(Games.objects.values_list("id", flat=True))

    target = (job.target_id or "").strip()
    if target and target != SERIES_RECON_ALL_TARGET:
        series_qs = Series.objects.filter(id=target).only("id")
    else:
        series_qs = Series.objects.all().only("id")

    for series in series_qs:
        check_cancelled()

        try:
            sync_series(series.id)
        except Exception as series_exc:
            record_reconciliation_item(
                "series",
                series.id,
                ReconAction.FAILED.value,
                error=str(series_exc)[:500],
            )
            record_failure(
                job_id,
                f"series {series.id}: {str(series_exc)[:200]}",
            )
            continue

        try:
            games_iter = iter_series_games(series.id)
        except Exception as iter_exc:
            record_failure(
                job_id,
                f"series {series.id} games list: {str(iter_exc)[:200]}",
            )
            continue

        for src_game in games_iter:
            check_cancelled()
            src_game_id = src_game.get("id") or ""
            src_game_name = (src_game.get("names") or {}).get(
                "international",
                src_game_id,
            )
            if not src_game_id:
                continue

            if src_game_id in existing_ids:
                record_reconciliation_item(
                    "series_game",
                    src_game_id,
                    ReconAction.SKIPPED_NO_CHANGE.value,
                    changes={
                        "series_id": series.id,
                        "name": src_game_name,
                        "reason": "already_in_db",
                    },
                )
                continue

            try:
                summary = import_new_game(src_game_id)
            except Exception as game_exc:
                record_reconciliation_item(
                    "series_game",
                    src_game_id,
                    ReconAction.FAILED.value,
                    changes={
                        "series_id": series.id,
                        "name": src_game_name,
                    },
                    error=str(game_exc)[:500],
                )
                record_failure(
                    job_id,
                    f"{src_game_id}: {str(game_exc)[:200]}",
                )
                continue

            existing_ids.add(src_game_id)
            record_reconciliation_item(
                "series_game",
                src_game_id,
                ReconAction.CREATED.value,
                changes={"series_id": series.id, **summary},
            )


@shared_task(name="srl.dispatch_phase_2")
def dispatch_phase_2(
    recon_job_id: str,
) -> None:
    """Dispatch obsolete-run sweeps for every affected player after phase 1."""
    from srl.srcom.leaderboards import sync_obsolete_runs

    try:
        with check_reconciliation(recon_job_id):
            job = ReconciliationJob.objects.get(id=recon_job_id)

            # Single-run reconciliations have no leaderboard to enumerate players from.
            if job.scope == ReconScope.RUN.value:
                return

            players = get_affected_players(recon_job_id)
            scope_filter = _build_filter_for_phase2(job)

            # In GAME scope, pull the player roster from SRC too so we catch submitters whose
            # only run was already obsolete locally and would otherwise be missed.
            if job.scope == ReconScope.GAME.value:
                extra = _scan_game_player_ids(scope_filter["game_id"])
                players = players | extra

            for player_id in players:
                dispatch_with_recon(
                    sync_obsolete_runs,
                    player_id,
                    scope_filter=scope_filter,
                )
    except CancellationRequested:
        return
    except Exception as exc:
        logger.exception(
            "dispatch_phase_2_failed",
            extra={"job_id": recon_job_id},
        )
        record_failure(recon_job_id, f"phase2: {str(exc)[:500]}")


@shared_task(name="srl.dispatch_phase_3")
def dispatch_phase_3(
    recon_job_id: str,
) -> None:
    """Phase 3: recompute points and streaks for every affected leaderboard variant."""
    try:
        with check_reconciliation(recon_job_id):
            variants = list(get_affected_variants(recon_job_id))
            if not variants:
                return

            # Group variants by (game, category, level) so we can bulk-load all candidate runs
            # and their RVVs once per group, then pick the first candidate whose variable hash
            # matches each variant.
            groups: dict[tuple, list] = defaultdict(list)
            for variant in variants:
                groups[(variant.game, variant.category, variant.level)].append(variant)

            for (game_id, category_id, level_id), group_variants in groups.items():
                candidate_ids = list(
                    Runs.objects.filter(
                        game_id=game_id,
                        category_id=category_id,
                        level_id=level_id,
                    ).values_list("id", flat=True),
                )
                if not candidate_ids:
                    continue

                rvvs_by_run: dict[str, dict[str, str]] = defaultdict(dict)
                for run_id, var_id, val_id in RunVariableValues.objects.filter(
                    run_id__in=candidate_ids,
                ).values_list("run_id", "variable_id", "value_id"):
                    rvvs_by_run[run_id][var_id] = val_id

                run_id_by_hash: dict[str, str] = {}
                for run_id in candidate_ids:
                    vh = variables_hash(rvvs_by_run.get(run_id, {}))
                    run_id_by_hash.setdefault(vh, run_id)

                wanted_run_ids = {
                    rid
                    for rid in (
                        run_id_by_hash.get(v.variables_hash) for v in group_variants
                    )
                    if rid is not None
                }
                if not wanted_run_ids:
                    continue

                runs_by_id = Runs.objects.select_related(
                    "game",
                    "category",
                    "level",
                ).in_bulk(wanted_run_ids)

                for variant in group_variants:
                    run_id = run_id_by_hash.get(variant.variables_hash)
                    if run_id is None:
                        continue
                    run = runs_by_id.get(run_id)
                    if run is None:
                        continue

                    leaderboard_dict = resolve_leaderboard(run)
                    dispatch_chain_with_recon(
                        recalculate_leaderboard_task.si(leaderboard_dict),
                        recalculate_streaks_task.si(leaderboard_dict),
                    )
    except CancellationRequested:
        return
    except Exception as exc:
        logger.exception(
            "dispatch_phase_3_failed",
            extra={"job_id": recon_job_id},
        )
        record_failure(recon_job_id, f"phase3: {str(exc)[:500]}")


@shared_task(name="srl.sweep_stuck_reconciliation_jobs")
def sweep_stuck_reconciliation_jobs() -> int:
    cutoff = timezone.now() - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
    stuck = ReconciliationJob.objects.filter(
        status=ReconStatus.RUNNING.value,
        started_at__lt=cutoff,
    )
    count = 0
    for job in stuck:
        job.status = ReconStatus.FAILED.value
        job.error_summary = "worker crashed or task lost (sweeper)"
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_summary", "finished_at"])
        release_lock(job)
        count += 1

    return count
