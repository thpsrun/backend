import argparse
from typing import Any, Iterator

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, F, QuerySet
from django.db.models.functions import Coalesce

from srl.models import Games, RunHistory, Runs
from srl.models.run_history import RunHistoryEndReason
from srl.srcom.utils import filter_by_variable_map
from srl.utils import calculate_bonus, points_formula, runs_share_player


class Command(BaseCommand):
    help = "Build RunHistory entries by crawling all runs chronologically"

    def add_arguments(
        self,
        parser: argparse.ArgumentParser,
    ) -> None:
        parser.add_argument(
            "--game",
            type=str,
            help="Limit to a specific game ID (for testing/partial rebuilds)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Calculate but don't write to database",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing RunHistory before rebuilding",
        )

    def get_leaderboards(
        self,
        game_filter: str | None,
    ) -> Iterator[dict]:
        """Enumerate all distinct leaderboard variants.

        Groups runs by (game_id, category_id, level_id, runtype), then within each
        group finds all distinct variable-value combinations via RunVariableValues.
        """
        base_query = Runs.objects.filter(
            vid_status="verified",
        ).exclude(
            v_date__isnull=True,
            date__isnull=True,
        )

        if game_filter:
            base_query = base_query.filter(game_id=game_filter)

        groups = base_query.values(
            "game_id",
            "category_id",
            "level_id",
            "runtype",
        ).distinct()

        for group in groups:
            group_qs = base_query.filter(**group)
            group_run_ids = group_qs.values_list("id", flat=True)

            # Find all distinct variable-value signatures for this group's runs
            from srl.models import RunVariableValues  # noqa: PLC0415
            rvv_qs = (
                RunVariableValues.objects
                .filter(run_id__in=group_run_ids)
                .values("run_id", "variable_id", "value_id")
            )

            # Build a map of run_id -> frozenset of (var_id, val_id) pairs
            run_signatures: dict[str, frozenset] = {}
            for rvv in rvv_qs:
                run_id = rvv["run_id"]
                if run_id not in run_signatures:
                    run_signatures[run_id] = frozenset()
                run_signatures[run_id] = run_signatures[run_id] | frozenset(
                    [(rvv["variable_id"], rvv["value_id"])]
                )

            # Add runs with no variable values (empty signature)
            for run_id in group_run_ids:
                if run_id not in run_signatures:
                    run_signatures[run_id] = frozenset()

            # Yield one leaderboard dict per distinct signature
            seen_sigs: set[frozenset] = set()
            for signature in run_signatures.values():
                if signature not in seen_sigs:
                    seen_sigs.add(signature)
                    yield {
                        **group,
                        "variable_value_map": dict(signature),
                    }

    def get_runs_for_leaderboard(
        self,
        leaderboard: dict,
    ) -> QuerySet[Runs]:
        """Get all verified runs for a speedrun leaderboard, sorted by effective date."""
        base_qs = Runs.objects.filter(
            game_id=leaderboard["game_id"],
            category_id=leaderboard["category_id"],
            level_id=leaderboard["level_id"],
            runtype=leaderboard["runtype"],
            vid_status="verified",
        ).exclude(
            v_date__isnull=True,
            date__isnull=True,
        )
        base_qs = filter_by_variable_map(base_qs, leaderboard["variable_value_map"])
        return base_qs.annotate(
            effective_date=Coalesce(F("v_date"), F("date")),
        ).order_by("effective_date")

    def get_time_column(
        self,
        game_id: str,
        runtype: str = "main",
    ) -> str:
        """Get the time column to use for a game based on its default timing method."""
        try:
            game = Games.objects.only("defaulttime", "idefaulttime").get(id=game_id)
            time_columns = {
                "realtime": "time_secs",
                "realtime_noloads": "timenl_secs",
                "ingame": "timeigt_secs",
            }
            if runtype == "main":
                return time_columns.get(game.defaulttime, "time_secs")
            else:
                return time_columns.get(game.idefaulttime, "time_secs")
        except Games.DoesNotExist:
            return "time_secs"

    def process_leaderboard(
        self,
        leaderboard: dict,
        dry_run: bool,
        game_is_ce: dict[str, bool],
        game_time_columns: dict[str, dict[str, str]],
    ) -> tuple[int, int, int]:
        runs = list(
            self.get_runs_for_leaderboard(leaderboard).prefetch_related("players")
        )
        if not runs:
            return 0, 0, 0

        game_times = game_time_columns.get(leaderboard["game_id"], {})
        if leaderboard["runtype"] == "main":
            time_column = game_times.get("main", "time_secs")
        else:
            time_column = game_times.get("il", "time_secs")

        is_ce = game_is_ce.get(leaderboard["game_id"], False)
        if is_ce:
            max_points = settings.POINTS_MAX_CE
        elif leaderboard["runtype"] == "main":
            max_points = settings.POINTS_MAX_FG
        else:
            max_points = settings.POINTS_MAX_IL

        current_wr_time: float | None = None
        current_wr_run: Runs | None = None
        current_wr_player_ids: set[str] = set()
        active_entries: dict[str, tuple[RunHistory, float]] = {}
        player_best_runs: dict[str, tuple[str, float]] = {}
        entries_created_count = 0
        entries_to_update: list[RunHistory] = []
        runs_streak_updates: dict[str, int] = {}

        for run in runs:
            run_time = getattr(run, time_column) or 0
            if run_time <= 0:
                continue

            effective_date = run.effective_date  # type: ignore

            player_ids = [player.id for player in run.players.all()]

            for player_id in player_ids:
                if player_id in player_best_runs:
                    old_run_id, old_time = player_best_runs[player_id]
                    if run_time < old_time and old_run_id in active_entries:
                        old_entry, _ = active_entries[old_run_id]
                        old_entry.end_date = effective_date
                        old_entry.end_reason = RunHistoryEndReason.OBSOLETED
                        entries_to_update.append(old_entry)
                        del active_entries[old_run_id]

                if (
                    player_id not in player_best_runs
                    or run_time < player_best_runs[player_id][1]
                ):
                    player_best_runs[player_id] = (run.id, run_time)

            is_new_wr = current_wr_time is None or run_time < current_wr_time

            if is_new_wr:
                old_wr_id = current_wr_run.id if current_wr_run else None
                new_wr_player_ids = set(player_ids)

                streak_continues = current_wr_run is not None and runs_share_player(
                    current_wr_player_ids, new_wr_player_ids
                )

                old_bonus = 0
                if streak_continues and old_wr_id:
                    old_bonus = runs_streak_updates.get(old_wr_id, 0)
                    if old_bonus == 0 and current_wr_run:
                        old_bonus = current_wr_run.bonus

                run_ids_to_update = list(active_entries.keys())

                for run_id in run_ids_to_update:
                    entry, old_run_time = active_entries[run_id]

                    entry.end_date = effective_date
                    if run_id == old_wr_id:
                        entry.end_reason = RunHistoryEndReason.LOST_WR

                        if not streak_continues:
                            runs_streak_updates[run_id] = 0
                    else:
                        entry.end_reason = RunHistoryEndReason.RECALCULATION
                    entries_to_update.append(entry)

                    new_points = points_formula(
                        wr=run_time,
                        run=old_run_time,
                        max_points=max_points,
                        short=True if run_time < 60 else False,
                    )

                    new_entry = RunHistory(
                        run_id=run_id,
                        start_date=effective_date,
                        end_date=None,
                        points=new_points,
                        end_reason=None,
                    )
                    if not dry_run:
                        new_entry.save()
                    entries_created_count += 1
                    active_entries[run_id] = (new_entry, old_run_time)

                current_wr_time = run_time
                current_wr_run = run
                current_wr_player_ids = new_wr_player_ids

                new_bonus = old_bonus if streak_continues else 0
                runs_streak_updates[run.id] = new_bonus

                streak_bonus = calculate_bonus(
                    leaderboard["runtype"],
                    new_bonus,
                    is_ce,
                )
                new_wr_points = max_points + streak_bonus

                new_wr_entry = RunHistory(
                    run_id=run.id,
                    start_date=effective_date,
                    end_date=None,
                    points=new_wr_points,
                    end_reason=None,
                )
                if not dry_run:
                    new_wr_entry.save()
                entries_created_count += 1
                active_entries[run.id] = (new_wr_entry, run_time)

            else:
                points = points_formula(
                    wr=current_wr_time,  # type: ignore
                    run=run_time,
                    max_points=max_points,
                    short=True if current_wr_time < 60 else False,
                )

                new_entry = RunHistory(
                    run_id=run.id,
                    start_date=effective_date,
                    end_date=None,
                    points=points,
                    end_reason=None,
                )
                if not dry_run:
                    new_entry.save()
                entries_created_count += 1
                active_entries[run.id] = (new_entry, run_time)

        if not dry_run and entries_to_update:
            RunHistory.objects.bulk_update(
                entries_to_update,
                ["end_date", "end_reason"],
            )

        current_points_map: dict[str, int] = {
            run_id: entry.points for run_id, (entry, _) in active_entries.items()
        }

        runs_to_fix: list[Runs] = []
        for run in runs:
            expected_points = current_points_map.get(run.id)
            expected_streak = runs_streak_updates.get(run.id)
            needs_update = False

            if expected_points is not None and run.points != expected_points:
                run.points = expected_points
                needs_update = True

            if expected_streak is not None and run.bonus != expected_streak:
                run.bonus = expected_streak
                needs_update = True

            if needs_update:
                runs_to_fix.append(run)

        if not dry_run and runs_to_fix:
            Runs.objects.bulk_update(runs_to_fix, ["points", "bonus"])

        return entries_created_count, len(runs), len(runs_to_fix)

    def handle(
        self,
        *args: Any,
        **options: Any,
    ) -> None:
        """Execute the command to build RunHistory entries."""
        game_filter = options.get("game")
        dry_run = options.get("dry_run", False)
        clear = options.get("clear", False)

        if dry_run:
            self.stdout.write(
                self.style.NOTICE("DRY RUN MODE: No changes will be saved.")
            )

        if clear and not dry_run:
            self.stdout.write(
                self.style.WARNING("Clearing existing history entries...")
            )
            if game_filter:
                deleted, _ = RunHistory.objects.filter(
                    run__game_id=game_filter
                ).delete()
            else:
                deleted, _ = RunHistory.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} entries."))

        leaderboards = list(self.get_leaderboards(game_filter))
        total_leaderboards = len(leaderboards)
        self.stdout.write(f"Found {total_leaderboards} leaderboards to process.\n")

        game_ids = {lb["game_id"] for lb in leaderboards}
        time_column_map = {
            "realtime": "time_secs",
            "realtime_noloads": "timenl_secs",
            "ingame": "timeigt_secs",
        }
        game_time_columns: dict[str, dict[str, str]] = {}
        game_is_ce: dict[str, bool] = {}
        game_slugs: dict[str, str] = {}
        for game in Games.objects.filter(id__in=game_ids).only(
            "id",
            "name",
            "slug",
            "defaulttime",
            "idefaulttime",
        ):
            game_time_columns[game.id] = {
                "main": time_column_map.get(game.defaulttime, "time_secs"),
                "il": time_column_map.get(game.idefaulttime, "time_secs"),
            }
            game_is_ce[game.id] = game.is_ce
            game_slugs[game.id] = game.slug.upper() if game.slug else game.id

        total_entries = 0
        total_runs = 0
        processed_count = 0
        error_count = 0

        for leaderboard in leaderboards:
            processed_count += 1
            progress = f"[{processed_count}/{total_leaderboards}]"
            game_slug = game_slugs.get(leaderboard["game_id"], "???")

            try:
                with transaction.atomic():
                    entries_created, runs_processed, points_fixed = (
                        self.process_leaderboard(
                            leaderboard,
                            dry_run,
                            game_is_ce,
                            game_time_columns,
                        )
                    )

                if runs_processed > 0:
                    total_entries += entries_created
                    total_runs += runs_processed
                    vmap = leaderboard["variable_value_map"]
                    variant_label = ",".join(f"{k}={v}" for k, v in sorted(vmap.items())) or "(no variants)"
                    msg = (
                        f"{progress} [{game_slug}/{leaderboard['runtype']}] {variant_label}: "
                        f"{runs_processed} runs, {entries_created} entries"
                    )
                    if points_fixed > 0:
                        msg += f", {points_fixed} points fixed"
                    self.stdout.write(msg)

            except Exception as e:
                error_count += 1
                vmap = leaderboard.get("variable_value_map", {})
                variant_label = ",".join(f"{k}={v}" for k, v in sorted(vmap.items())) or "(no variants)"
                self.stdout.write(
                    self.style.ERROR(
                        f"{progress} [{game_slug}/{leaderboard['runtype']}] ERROR in {variant_label}: {str(e)}"
                    )
                )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS("RUN HISTORY COMPLETE"))
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(f"Leaderboards processed: {processed_count}")
        self.stdout.write(f"Errors: {error_count}")
        self.stdout.write(f"Total runs: {total_runs}")
        self.stdout.write(f"Total history entries created: {total_entries}")

        if dry_run:
            self.stdout.write(
                self.style.NOTICE("\nThis was a dry run. No changes saved.")
            )
