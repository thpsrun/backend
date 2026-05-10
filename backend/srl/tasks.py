from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests as http_requests
import sentry_sdk
from celery import shared_task
from django.conf import settings as cfg
from django.core.management import call_command
from django.db import transaction
from django.db.models import Min

from srl.encryption import decrypt_src_key
from srl.leaderboard.recalculation import (
    build_leaderboard_metadata,
    clear_leaderboard_history,
    get_leaderboard_time_column,
    get_runs_for_leaderboard,
    process_leaderboard,
)
from srl.leaderboard.resolution import resolve_leaderboard
from srl.leaderboard.streaks import apply_streak_to_run
from srl.models import Games, ReconciliationJob, Runs, RunVariableValues, SRCSyncTask
from srl.models.reconciliation import ReconPhase, ReconScope, ReconStatus
from srl.srcom.leaderboards import (
    sync_game_runs,
    sync_leaderboards,
    sync_obsolete_runs,
    sync_single_run,
)
from srl.srcom.recon_accumulators import get_affected_players, get_affected_variants
from srl.srcom.reconciliation import (
    CancellationRequested,
    check_reconciliation,
    decrement_pending,
    dispatch_chain_with_recon,
    dispatch_with_recon,
    finalize_after_drain,
    flush_counts,
    reconciliation_context,
    record_failure,
    release_lock,
)
from srl.srcom.utils import create_leaderboard_link, variables_hash
from srl.srcom.v2 import is_v2_enabled
from srl.srcom.v2.client import (
    SrcV2AuthError,
    SrcV2Client,
    SrcV2ContractError,
    SrcV2Error,
    SrcV2NetworkError,
    SrcV2PermissionError,
    SrcV2RateLimited,
    SrcV2ServerError,
    SrcV2ValidationError,
)
from srl.srcom.v2.errors import ErrorCategory
from srl.srcom.v2.session import (
    refresh_bot_session as _refresh_bot_session,
)
from srl.srcom.v2.session import (
    trip_circuit_breaker as _trip_circuit_breaker,
)
from srl.utils import src_api_paginate

V2_RETRY_BACKOFF = [30, 60, 120, 300, 600]
STUCK_THRESHOLD_MINUTES = 70

SRC_API_BASE = "https://www.speedrun.com/api/v1"
SRC_TIMEOUT = 15
RETRY_BACKOFF = [30, 60, 120, 300, 600]


@shared_task
def recalculate_leaderboard_task(
    leaderboard_dict: dict,
    recon_job_id: str | None = None,
) -> None:
    """Recalculate points and history for a single leaderboard variant.

    Clears existing RunHistory for the variant, then rebuilds from scratch. Dispatched by
    recalculate_run() when a run is verified, and by Phase 3 of a reconciliation job (one dispatch
    per affected variant).
    """
    with check_reconciliation(recon_job_id):
        (
            game_time_columns,
            game_is_ce,
            value_timings,
            variable_timings,
            category_timings,
        ) = build_leaderboard_metadata([leaderboard_dict])

        with transaction.atomic():
            clear_leaderboard_history(leaderboard_dict)
            process_leaderboard(
                leaderboard_dict,
                dry_run=False,
                game_is_ce=game_is_ce,
                game_time_columns=game_time_columns,
                value_timings=value_timings,
                variable_timings=variable_timings,
                category_timings=category_timings,
            )


@shared_task
def recalculate_streaks_task(
    leaderboard_dict: dict,
    recon_job_id: str | None = None,
) -> None:
    """Recalculate streak bonus for the current WR on a leaderboard variant.

    Finds the fastest verified run on the leaderboard and applies streak logic. Dispatched by
    recalculate_run() (chained after recalculate_leaderboard_task) and by Phase 3 of a
    reconciliation job (chained per affected variant).
    """
    with check_reconciliation(recon_job_id):
        time_col = get_leaderboard_time_column(leaderboard_dict)

        runs_qs = (
            get_runs_for_leaderboard(leaderboard_dict)
            .exclude(**{f"{time_col}__lte": 0})
            .exclude(**{f"{time_col}__isnull": True})
        )

        result = runs_qs.aggregate(min_time=Min(time_col))
        wr_time = result["min_time"]
        if wr_time is None:
            return

        wr_run = (
            runs_qs.filter(**{time_col: wr_time})
            .select_related("game")
            .prefetch_related("players")
            .first()
        )
        if not wr_run:
            return

        result = apply_streak_to_run(wr_run)
        if result is not None:
            new_bonus, new_points = result
            wr_run.bonus = new_bonus
            wr_run.points = new_points
            wr_run.save(update_fields=["bonus", "points"])


@shared_task
def build_streaks_task() -> None:
    """Run the full build_streaks management command.

    Used by the daily Celery Beat schedule (midnight UTC) to award monthly
    anniversary bonuses to current WR holders.
    """
    call_command("build_streaks")


@shared_task
def sync_src_action(
    sync_task_id: int,
) -> None:
    """Execute an SRC API sync operation with retry logic.

    Retrieves the SRCSyncTask, decrypts the moderator's API key, and calls the appropriate SRC
    endpoint. On retryable failures (420, 503, connection errors), re-queues itself with exponential
    backoff. After 5 failed attempts, marks the task as failed and reports to Sentry.
    """
    try:
        sync_task = SRCSyncTask.objects.select_related(
            "run",
            "moderator__user",
        ).get(id=sync_task_id)
    except SRCSyncTask.DoesNotExist:
        return

    if sync_task.status == SRCSyncTask.Status.SYNCED:
        return

    user = sync_task.moderator.user if sync_task.moderator else None
    if not user or not user.encrypted_api_key:
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.last_error = "No SRC API key stored for moderator"
        sync_task.save(
            update_fields=["status", "last_error", "updated_at"],
        )
        sentry_sdk.capture_message(
            f"SRC sync failed: no valid API key for " f"sync task {sync_task_id}",
            level="error",
        )
        return

    try:
        api_key = decrypt_src_key(user.encrypted_api_key)
    except Exception as e:
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.last_error = f"Cannot decrypt SRC API key: {e}"
        sync_task.save(
            update_fields=["status", "last_error", "updated_at"],
        )
        sentry_sdk.capture_message(
            f"SRC sync failed: no valid API key for " f"sync task {sync_task_id}",
            level="error",
        )
        return

    run_id = sync_task.run.id
    if sync_task.action in (
        SRCSyncTask.ActionType.VERIFY,
        SRCSyncTask.ActionType.REJECT,
    ):
        url = f"{SRC_API_BASE}/runs/{run_id}/status"
    elif sync_task.action == SRCSyncTask.ActionType.CHANGE_PLAYERS:
        url = f"{SRC_API_BASE}/runs/{run_id}/players"
    else:
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.last_error = f"Unknown action: {sync_task.action}"
        sync_task.save(
            update_fields=["status", "last_error", "updated_at"],
        )
        return

    sync_task.attempts += 1
    try:
        response = http_requests.put(
            url,
            json=sync_task.payload,
            headers={"X-API-Key": api_key},
            timeout=SRC_TIMEOUT,
        )
    except http_requests.RequestException as e:
        _handle_retryable_failure(
            sync_task,
            f"Connection error: {e}",
        )
        return

    # Permanent failures (don't retry)
    if response.status_code in (400, 401, 403, 404):
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.last_error = (
            f"SRC returned {response.status_code}: " f"{response.text[:500]}"
        )
        sync_task.save(
            update_fields=[
                "status",
                "attempts",
                "last_error",
                "updated_at",
            ],
        )
        sentry_sdk.capture_message(
            f"SRC sync permanently failed for task "
            f"{sync_task_id}: HTTP {response.status_code}",
            level="error",
        )
        return

    # Retryable failures (420 rate limit, 503 unavailable)
    if response.status_code in (420, 503):
        _handle_retryable_failure(
            sync_task,
            f"SRC returned {response.status_code}: " f"{response.text[:200]}",
        )
        return

    if response.status_code not in (200, 204):
        _handle_retryable_failure(
            sync_task,
            f"Unexpected status {response.status_code}: " f"{response.text[:200]}",
        )
        return

    sync_task.status = SRCSyncTask.Status.SYNCED
    sync_task.last_error = ""
    sync_task.save(
        update_fields=[
            "status",
            "attempts",
            "last_error",
            "updated_at",
        ],
    )


def _handle_retryable_failure(
    sync_task: "SRCSyncTask",
    error_msg: str,
) -> None:
    """Handles attempts to retry the SRC API.

    Re-queues the task with exponential backoff if under max_attempts.
    After max_attempts, marks as failed and reports to Sentry.
    """
    sync_task.last_error = error_msg
    sync_task.save(
        update_fields=["attempts", "last_error", "updated_at"],
    )

    if sync_task.attempts >= sync_task.max_attempts:
        sync_task.status = sync_task.Status.FAILED
        sync_task.save(update_fields=["status", "updated_at"])
        sentry_sdk.capture_message(
            f"SRC sync task {sync_task.id} failed after "
            f"{sync_task.attempts} attempts: {error_msg}",
            level="error",
        )
        return

    backoff_idx = min(
        sync_task.attempts - 1,
        len(RETRY_BACKOFF) - 1,
    )
    delay = RETRY_BACKOFF[backoff_idx]
    sync_src_action.apply_async(
        args=[sync_task.id],
        countdown=delay,
    )


# Re-export so tests can patch them on this module.
refresh_bot_session = _refresh_bot_session
trip_circuit_breaker = _trip_circuit_breaker


@shared_task(name="srl.tasks.sync_src_settings")
def sync_src_settings(
    sync_task_id: int,
) -> None:
    """Push a local run edit to SRC via v2 PutRunSettings.

    Mirrors the retry/park behavior of sync_src_action but routes
    failures through ErrorCategory and uses the shared bot session.
    """

    try:
        sync_task = SRCSyncTask.objects.select_related("run").get(id=sync_task_id)
    except SRCSyncTask.DoesNotExist:
        return

    if sync_task.status == SRCSyncTask.Status.SYNCED:
        return

    if not is_v2_enabled():
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.error_category = ErrorCategory.UNKNOWN
        sync_task.last_error = "v2 disabled by kill switch"
        sync_task.save(
            update_fields=[
                "status",
                "error_category",
                "last_error",
                "updated_at",
            ],
        )
        return

    sync_task.attempts += 1

    try:
        client = SrcV2Client()
        client.put_run_settings(sync_task.payload)

        sync_task.status = SRCSyncTask.Status.SYNCED
        sync_task.error_category = ""
        sync_task.last_error = ""
        sync_task.save(
            update_fields=[
                "status",
                "attempts",
                "error_category",
                "last_error",
                "updated_at",
            ],
        )
        return

    except SrcV2PermissionError as exc:
        # 403: bot likely lost mod status on this game. Refreshing the
        # session won't help; fail terminally and alert.
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.error_category = ErrorCategory.AUTH
        sync_task.last_error = str(exc)[:1000]
        sync_task.save(
            update_fields=[
                "status",
                "attempts",
                "error_category",
                "last_error",
                "updated_at",
            ],
        )
        sentry_sdk.capture_message(
            (
                f"SRC v2 PutRunSettings forbidden on sync task "
                f"{sync_task.id} (run {sync_task.run_id}); bot may have "
                f"lost moderator status on the game."
            ),
            level="error",
        )
        return

    except SrcV2AuthError as exc:
        sync_task.error_category = ErrorCategory.AUTH
        sync_task.last_error = str(exc)[:1000]
        sync_task.status = SRCSyncTask.Status.PENDING
        sync_task.save(
            update_fields=[
                "status",
                "attempts",
                "error_category",
                "last_error",
                "updated_at",
            ],
        )
        refresh_bot_session.delay()
        if sync_task.attempts < sync_task.max_attempts:
            sync_src_settings.apply_async(
                args=[sync_task_id],
                countdown=30,
            )
        else:
            sync_task.status = SRCSyncTask.Status.FAILED
            sync_task.save(update_fields=["status", "updated_at"])
        return

    except SrcV2ContractError as exc:
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.error_category = ErrorCategory.API_CONTRACT
        sync_task.last_error = str(exc)[:1000]
        sync_task.save(
            update_fields=[
                "status",
                "attempts",
                "error_category",
                "last_error",
                "updated_at",
            ],
        )
        trip_circuit_breaker(
            reason=(
                f"PutRunSettings response did not match v2 contract on "
                f"sync task {sync_task.id}: {exc}"
            ),
            category=ErrorCategory.API_CONTRACT,
        )
        return

    except SrcV2ValidationError as exc:
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.error_category = ErrorCategory.VALIDATION
        sync_task.last_error = str(exc)[:1000]
        sync_task.save(
            update_fields=[
                "status",
                "attempts",
                "error_category",
                "last_error",
                "updated_at",
            ],
        )
        return

    except (SrcV2RateLimited, SrcV2ServerError, SrcV2NetworkError) as exc:
        sync_task.error_category = (
            ErrorCategory.RATE_LIMIT
            if isinstance(exc, SrcV2RateLimited)
            else (
                ErrorCategory.API_SERVER
                if isinstance(exc, SrcV2ServerError)
                else ErrorCategory.NETWORK
            )
        )
        sync_task.last_error = str(exc)[:1000]
        if sync_task.attempts < sync_task.max_attempts:
            countdown = V2_RETRY_BACKOFF[
                min(sync_task.attempts - 1, len(V2_RETRY_BACKOFF) - 1)
            ]
            sync_task.status = SRCSyncTask.Status.PENDING
            sync_task.save(
                update_fields=[
                    "status",
                    "attempts",
                    "error_category",
                    "last_error",
                    "updated_at",
                ],
            )
            sync_src_settings.apply_async(
                args=[sync_task_id],
                countdown=countdown,
            )
        else:
            sync_task.status = SRCSyncTask.Status.FAILED
            sync_task.save(
                update_fields=[
                    "status",
                    "attempts",
                    "error_category",
                    "last_error",
                    "updated_at",
                ],
            )
        return

    except SrcV2Error as exc:
        sync_task.status = SRCSyncTask.Status.FAILED
        sync_task.error_category = exc.category
        sync_task.last_error = str(exc)[:1000]
        sync_task.save(
            update_fields=[
                "status",
                "attempts",
                "error_category",
                "last_error",
                "updated_at",
            ],
        )
        return


# RECONCILIATION JOBS ARE BELOW! #


@shared_task(name="srl.tasks.replay_failed_edits")
def replay_failed_edits() -> int:
    """Re-queue recent failed EDIT_RUN tasks.

    Called when the kill switch transitions to "effective on" (either by an admin clearing the
    breaker or by a manual unpause). Tasks older than SRC_V2_REPLAY_MAX_AGE_DAYS are intentionally
    skipped; stale edits should be reviewed individually.
    """

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=getattr(cfg, "SRC_V2_REPLAY_MAX_AGE_DAYS", 7),
    )
    qs = SRCSyncTask.objects.filter(
        action=SRCSyncTask.ActionType.EDIT_RUN,
        status=SRCSyncTask.Status.FAILED,
        created_at__gte=cutoff,
    )
    count = 0
    for task in qs:
        task.status = SRCSyncTask.Status.PENDING
        task.error_category = ""
        task.last_error = ""
        task.attempts = 0
        task.save(
            update_fields=[
                "status",
                "error_category",
                "last_error",
                "attempts",
                "updated_at",
            ],
        )
        sync_src_settings.delay(task.id)
        count += 1
    return count


def _convert_to_lb_data(descriptor: dict) -> dict | None:
    var_values = descriptor.get("variable_values") or {}
    var_combo = list(var_values.items()) if var_values else None
    return create_leaderboard_link(
        game_id=descriptor["game_id"],
        category_id=descriptor["category_id"],
        il_id=descriptor.get("level_id"),
        var_combo=var_combo,
    )


def _build_filter_for_phase2(
    job: ReconciliationJob,
) -> dict:
    """Build the scope_filter passed to each sync_obsolete_runs child.

    - For LEADERBOARD scope: full (game, category, level, variables) match.
    - For GAME scope: just the game id.
    """
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


def _resolve_game(
    raw: str,
) -> str:
    """Quick helper function to resolve game_id to `Games` object (if needed)."""

    if not raw:
        return raw
    if Games.objects.filter(id=raw).exists():
        return raw
    by_slug = Games.objects.filter(slug=raw).only("id").first()
    if by_slug is not None:
        return by_slug.id
    return raw


@shared_task(bind=True, name="srl.run_reconciliation_job")
def run_reconciliation_job(
    self,
    job_id: str,
) -> None:
    job = ReconciliationJob.objects.get(id=job_id)
    job.celery_task_id = self.request.id or ""
    job.status = ReconStatus.RUNNING.value
    job.phase = ReconPhase.P1.value
    job.started_at = timezone.now()

    job.pending_children = 1
    job.save(
        update_fields=[
            "celery_task_id",
            "status",
            "phase",
            "started_at",
            "pending_children",
        ],
    )

    try:
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
            finally:
                try:
                    flush_counts()
                except Exception:
                    pass
    finally:
        try:
            if decrement_pending(job_id):
                finalize_after_drain(job_id)
        except Exception:
            pass


@shared_task(name="srl.dispatch_phase_2")
def dispatch_phase_2(
    recon_job_id: str,
) -> None:
    """Dispatch job that is usually conducted after players are determined to find obsolete runs"""

    with check_reconciliation(recon_job_id):
        job = ReconciliationJob.objects.get(id=recon_job_id)

        # Single-run reconciliations have no leaderboard to enumerate players from.
        if job.scope == ReconScope.RUN.value:
            return

        players = get_affected_players(recon_job_id)
        scope_filter = _build_filter_for_phase2(job)

        # If the GAME scope is used, it will put together all of the players who have a valid ID
        # based on who has submitted a run at all and not just what was reconciled.
        if job.scope == ReconScope.GAME.value:
            extra = _scan_game_player_ids(scope_filter["game_id"])
            players = players | extra

        for player_id in players:
            dispatch_with_recon(
                sync_obsolete_runs,
                player_id,
                scope_filter=scope_filter,
            )


@shared_task(name="srl.dispatch_phase_3")
def dispatch_phase_3(
    recon_job_id: str,
) -> None:
    """Used for Phase 3 where we do point recalculation and streaks determination."""

    with check_reconciliation(recon_job_id):
        variants = list(get_affected_variants(recon_job_id))
        if not variants:
            return

        # Group variants by (game, category, level) so we can bulk-load all
        # candidate runs and their RVVs once per group, then pick the first
        # candidate whose variable hash matches each variant.
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

            for variant in group_variants:
                run_id = run_id_by_hash.get(variant.variables_hash)
                if run_id is None:
                    continue

                run = Runs.objects.select_related("game", "category", "level").get(
                    id=run_id
                )
                leaderboard_dict = resolve_leaderboard(run)
                dispatch_chain_with_recon(
                    recalculate_leaderboard_task.si(leaderboard_dict),
                    recalculate_streaks_task.si(leaderboard_dict),
                )


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
