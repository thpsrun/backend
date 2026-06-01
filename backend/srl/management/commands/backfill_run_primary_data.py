import logging

from django.core.management.base import BaseCommand

from srl.models import METHOD_TO_TIME_FIELD, TIMING_FALLBACK_PRIORITY, Runs

log = logging.getLogger(__name__)


_TIMING_FIELDS: dict[str, tuple[str, str]] = {
    "rta": ("time", "time_secs"),
    "lrt": ("timenl", "timenl_secs"),
    "igt": ("timeigt", "timeigt_secs"),
}


class Command(BaseCommand):
    help = (
        "Copy a run's existing timing data into its schema-resolved primary "
        "slot when that slot is empty. Brings legacy runs into compliance "
        "with the game's current primary timing method by duplicating the "
        "value from whichever method has data, ordered by "
        "TIMING_FALLBACK_PRIORITY. Idempotent."
    )

    def add_arguments(
        self,
        parser,
    ) -> None:
        parser.add_argument(
            "--game",
            type=str,
            default=None,
            help="Limit backfill to runs of this game slug.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without saving.",
        )

    def handle(
        self,
        *args,
        **options,
    ) -> None:
        dry_run: bool = options["dry_run"]
        game_slug: str | None = options["game"]
        prefix = "DRY RUN: " if dry_run else ""

        qs = Runs.objects.select_related(
            "game",
            "category",
        ).prefetch_related(
            "runvariablevalues_set__variable",
            "runvariablevalues_set__value",
        )
        if game_slug:
            qs = qs.filter(game__slug=game_slug)

        updated, skipped, orphans = 0, 0, 0
        for run in qs.iterator(chunk_size=500):
            resolved = self._resolve_primary(run)
            primary_display, primary_secs = _TIMING_FIELDS[resolved]
            if (getattr(run, primary_secs) or 0) > 0:
                skipped += 1
                continue

            source: str | None = None
            for candidate in TIMING_FALLBACK_PRIORITY:
                if candidate == resolved:
                    continue
                cand_value = getattr(run, METHOD_TO_TIME_FIELD[candidate]) or 0
                if cand_value > 0:
                    source = candidate
                    break

            if source is None:
                orphans += 1
                log.warning(
                    "orphan run %s: no source method has data, leaving empty",
                    run.id,
                )
                continue

            source_display, source_secs = _TIMING_FIELDS[source]
            if not dry_run:
                setattr(run, primary_display, getattr(run, source_display))
                setattr(run, primary_secs, getattr(run, source_secs))
                run.save(update_fields=[primary_display, primary_secs])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}backfill_run_primary_data: updated={updated} "
                f"skipped={skipped} orphans={orphans}",
            ),
        )

    def _resolve_primary(
        self,
        run: Runs,
    ) -> str:
        for rvv in run.runvariablevalues_set.all():  # type: ignore
            if rvv.value.defaulttime:
                return rvv.value.defaulttime
        for rvv in run.runvariablevalues_set.all():  # type: ignore
            if rvv.variable.defaulttime:
                return rvv.variable.defaulttime
        if run.category and run.category.defaulttime:
            return run.category.defaulttime
        if run.runtype == "il":
            return run.game.idefaulttime
        return run.game.defaulttime
