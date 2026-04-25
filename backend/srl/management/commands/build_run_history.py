import argparse
from typing import Any, Iterator

from django.core.management.base import BaseCommand
from django.db import transaction

from srl.leaderboard.recalculation import TIME_COLUMN_MAP, process_leaderboard
from srl.models import Games, RunHistory, Runs


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

            rvv_qs = RunVariableValues.objects.filter(run_id__in=group_run_ids).values(
                "run_id", "variable_id", "value_id"
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
                "main": TIME_COLUMN_MAP.get(game.defaulttime, "time_secs"),
                "il": TIME_COLUMN_MAP.get(game.idefaulttime, "time_secs"),
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
                    entries_created, runs_processed, points_fixed = process_leaderboard(
                        leaderboard,
                        dry_run,
                        game_is_ce,
                        game_time_columns,
                    )

                if runs_processed > 0:
                    total_entries += entries_created
                    total_runs += runs_processed
                    vmap = leaderboard["variable_value_map"]
                    variant_label = (
                        ",".join(f"{k}={v}" for k, v in sorted(vmap.items()))
                        or "(no variants)"
                    )
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
                variant_label = (
                    ",".join(f"{k}={v}" for k, v in sorted(vmap.items()))
                    or "(no variants)"
                )
                self.stdout.write(self.style.ERROR(f"ERROR: {str(e)}"))

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
