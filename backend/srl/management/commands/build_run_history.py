import argparse
import time
from typing import Any, Iterator

from api.signals import disable_history_signals
from api.v1.routers.utils.cache_utils import _HISTORY_CACHE_PREFIX
from django.core.cache import caches
from django.core.management.base import BaseCommand
from django.db import transaction

from srl.leaderboard.recalculation import (
    build_leaderboard_metadata,
    enumerate_leaderboard_variants,
    process_leaderboard,
)
from srl.models import (
    Games,
    RunHistory,
    Runs,
)


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
        """Enumerate all distinct leaderboard variants (optionally one game)."""
        base_query = Runs.objects.filter(
            vid_status="verified",
        ).exclude(
            v_date__isnull=True,
            date__isnull=True,
        )

        if game_filter:
            base_query = base_query.filter(game_id=game_filter)

        return enumerate_leaderboard_variants(base_query)

    def handle(
        self,
        *args: Any,
        **options: Any,
    ) -> None:
        game_filter = options.get("game")
        dry_run = options.get("dry_run", False)
        clear = options.get("clear", False)

        if not dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "============================================================\n"
                    "WARNING: build_run_history may reshape historical RunHistory\n"
                    "entries.\n"
                    "\n"
                    "The /api/v1/pointslb/history endpoints derive monthly/yearly\n"
                    "results from the FIRST RunHistory entry per run; running this\n"
                    "command can change those totals retroactively.\n"
                    "\n"
                    "This command will automatically invalidate the historical\n"
                    "cache namespace (pointslb:history:*) when it completes.\n"
                    "============================================================",
                )
            )

            time.sleep(3)

        with disable_history_signals():
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

            _, game_is_ce, *_ = build_leaderboard_metadata(leaderboards)

            game_ids = {lb["game_id"] for lb in leaderboards}
            game_slugs: dict[str, str] = {}
            for game in Games.objects.filter(id__in=game_ids).only(
                "id",
                "name",
                "slug",
            ):
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
                            process_leaderboard(
                                leaderboard,
                                dry_run=dry_run,
                                game_is_ce=game_is_ce,
                            )
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

        self._purge_history_cache()

    def _purge_history_cache(self) -> None:
        cache = caches["default"]
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(f"{_HISTORY_CACHE_PREFIX}:*")
            self.stdout.write(
                self.style.SUCCESS("Historical cache cleared."),
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Cache backend does not support delete_pattern - historical "
                    "caches may be stale until manually cleared.",
                )
            )
