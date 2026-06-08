import argparse
from typing import Any

from api.signals import disable_history_signals
from api.v1.routers.utils.cache_utils import _HISTORY_CACHE_PREFIX
from django.core.cache import caches
from django.core.management.base import BaseCommand
from django.db import transaction

from srl.leaderboard.recalculation import (
    build_leaderboard_metadata,
    clear_leaderboard_history,
    enumerate_leaderboard_variants,
    process_leaderboard,
)
from srl.models import Categories, Levels, Runs
from srl.srcom.categories import sync_categories
from srl.srcom.levels import sync_levels
from srl.utils import src_api_probe


class Command(BaseCommand):
    """Repair IL runs missing their level (and category) FK, then rebuild history."""

    help = (
        "Find IL runs with no level, restore their category + level from the SRC "
        "API, then rebuild RunHistory for the affected leaderboard variants."
    )

    def add_arguments(
        self,
        parser: argparse.ArgumentParser,
    ) -> None:
        """Register CLI options."""
        parser.add_argument(
            "--game",
            type=str,
            help="Limit to a game slug (e.g. thps34). Default: all games.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report intended changes; write nothing.",
        )
        parser.add_argument(
            "--no-history",
            action="store_true",
            help="Fix runs only; skip the RunHistory rebuild.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Cap the number of runs processed (testing / incremental).",
        )

    def handle(
        self,
        *args: Any,
        **options: Any,
    ) -> None:
        """Repair FKs for level-less IL runs and rebuild affected history."""
        game_slug = options.get("game")
        dry_run = options.get("dry_run", False)
        no_history = options.get("no_history", False)
        limit = options.get("limit")

        qs = Runs.objects.filter(runtype="il", level__isnull=True).order_by("id")
        if game_slug:
            qs = qs.filter(game__slug=game_slug)
        if limit:
            qs = qs[:limit]

        targets = list(qs)
        self.stdout.write(f"Found {len(targets)} IL run(s) with no level assigned.")

        repaired: list[Runs] = []
        counts = {
            "repaired": 0,
            "missing_on_src": 0,
            "no_level_on_src": 0,
            "sync_failed": 0,
            "fetch_error": 0,
        }

        for run in targets:
            try:
                status, payload = src_api_probe(
                    f"https://speedrun.com/api/v1/runs/{run.id}",
                )
            except Exception as exc:
                counts["fetch_error"] += 1
                self.stdout.write(
                    self.style.ERROR(f"  {run.id}: SRC fetch error: {exc}"),
                )
                continue

            if status == 404:
                counts["missing_on_src"] += 1
                self.stdout.write(
                    self.style.WARNING(f"  {run.id}: not found on SRC (404), skipped."),
                )
                continue

            data = (payload or {}).get("data") if isinstance(payload, dict) else None
            if status != 200 or not data:
                counts["fetch_error"] += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"  {run.id}: unexpected SRC response (HTTP {status}), skipped.",
                    ),
                )
                continue

            level_id = data.get("level")
            category_id = data.get("category")

            if not level_id:
                counts["no_level_on_src"] += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  {run.id}: SRC reports no level "
                        f"(full-game mistyped as IL?), skipped.",
                    ),
                )
                continue

            if not self._ensure_category(category_id, run.id):
                counts["sync_failed"] += 1
                continue
            if not self._ensure_level(level_id, run.id):
                counts["sync_failed"] += 1
                continue

            run.category_id = category_id
            run.level_id = level_id
            repaired.append(run)
            counts["repaired"] += 1
            self.stdout.write(f"  {run.id}: category={category_id}, level={level_id}")

        if repaired and not dry_run:
            Runs.objects.bulk_update(
                repaired,
                ["category_id", "level_id"],
                batch_size=200,
            )
            self.stdout.write(self.style.SUCCESS(f"Updated {len(repaired)} run(s)."))
        elif dry_run:
            self.stdout.write(self.style.NOTICE("DRY RUN: no FK changes written."))

        self.stdout.write(
            f"Repaired={counts['repaired']} "
            f"missing_on_src={counts['missing_on_src']} "
            f"no_level_on_src={counts['no_level_on_src']} "
            f"sync_failed={counts['sync_failed']} "
            f"fetch_error={counts['fetch_error']}",
        )

        if no_history:
            self.stdout.write(
                self.style.NOTICE("--no-history: skipping RunHistory rebuild."),
            )
            return
        if not repaired:
            self.stdout.write("No runs repaired; nothing to rebuild.")
            return

        self._rebuild_history(repaired, dry_run)

    def _ensure_category(
        self,
        category_id: str | None,
        run_id: str,
    ) -> bool:
        """Make sure the category exists locally; sync on demand. Returns success."""
        if not category_id:
            self.stdout.write(
                self.style.ERROR(f"  {run_id}: SRC payload has no category, skipped."),
            )
            return False
        if Categories.objects.filter(id=category_id).exists():
            return True
        try:
            sync_categories(category_id)
        except Exception as exc:
            self.stdout.write(
                self.style.ERROR(
                    f"  {run_id}: sync_categories({category_id}) failed: {exc}",
                ),
            )
            return False
        return Categories.objects.filter(id=category_id).exists()

    def _ensure_level(
        self,
        level_id: str,
        run_id: str,
    ) -> bool:
        """Make sure the level exists locally; sync on demand. Returns success."""
        if Levels.objects.filter(id=level_id).exists():
            return True
        try:
            sync_levels(level_id)
        except Exception as exc:
            self.stdout.write(
                self.style.ERROR(
                    f"  {run_id}: sync_levels({level_id}) failed: {exc}",
                ),
            )
            return False
        return Levels.objects.filter(id=level_id).exists()

    def _rebuild_history(
        self,
        repaired: list[Runs],
        dry_run: bool,
    ) -> None:
        """Rebuild RunHistory for only the leaderboard variants that changed."""
        affected_keys = {(r.game_id, r.category_id, r.level_id) for r in repaired}
        game_ids = {g for (g, _c, _l) in affected_keys}
        cat_ids = {c for (_g, c, _l) in affected_keys}
        level_ids = {lv for (_g, _c, lv) in affected_keys}

        base_query = Runs.objects.filter(
            vid_status="verified",
            runtype="il",
            game_id__in=game_ids,
            category_id__in=cat_ids,
            level_id__in=level_ids,
        ).exclude(
            v_date__isnull=True,
            date__isnull=True,
        )

        variants = [
            v
            for v in enumerate_leaderboard_variants(base_query)
            if (v["game_id"], v["category_id"], v["level_id"]) in affected_keys
        ]
        self.stdout.write(
            f"Rebuilding history for {len(variants)} affected variant(s).",
        )
        if not variants:
            return

        _, game_is_ce, *_ = build_leaderboard_metadata(variants)

        total_entries = 0
        with disable_history_signals():
            for variant in variants:
                with transaction.atomic():
                    if not dry_run:
                        clear_leaderboard_history(variant)
                    entries, _runs, _pts = process_leaderboard(
                        variant,
                        dry_run=dry_run,
                        game_is_ce=game_is_ce,
                    )
                    total_entries += entries

        self.stdout.write(
            self.style.SUCCESS(
                f"History rebuild: {total_entries} entries across "
                f"{len(variants)} variant(s).",
            ),
        )

        if not dry_run:
            self._purge_history_cache()

    def _purge_history_cache(
        self,
    ) -> None:
        """Invalidate the pointslb history cache namespace."""
        cache = caches["default"]
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(f"{_HISTORY_CACHE_PREFIX}:*")
            self.stdout.write(self.style.SUCCESS("Historical cache cleared."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Cache backend lacks delete_pattern - history caches may be "
                    "stale until cleared manually.",
                ),
            )
