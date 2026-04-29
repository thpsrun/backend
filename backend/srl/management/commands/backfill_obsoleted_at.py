from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max, Q

from srl.models import RunHistoryEndReason, Runs


class Command(BaseCommand):
    help = (
        "Backfill Runs.obsoleted_at from the latest closed RunHistory entry "
        "with end_reason=OBSOLETED. Idempotent. Runs with no qualifying "
        "RunHistory entry remain NULL (treated as obsolete-since-forever)."
    )

    def add_arguments(
        self,
        parser,
    ) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute backfill values but do not persist.",
        )

    def handle(
        self,
        *args,
        **options,
    ) -> None:
        dry_run: bool = options["dry_run"]
        prefix = "DRY RUN: " if dry_run else ""

        candidates = (
            Runs.objects
            .filter(obsolete=True, obsoleted_at__isnull=True)
            .annotate(
                latest_obsoleted_close=Max(
                    "history__end_date",
                    filter=Q(history__end_reason=RunHistoryEndReason.OBSOLETED),
                ),
            )
            .filter(latest_obsoleted_close__isnull=False)
        )

        total = candidates.count()
        self.stdout.write(f"{prefix}Found {total} obsolete runs eligible for backfill.")

        if dry_run or total == 0:
            return

        updates: list[Runs] = []
        for run in candidates.only("id", "obsoleted_at"):
            run.obsoleted_at = run.latest_obsoleted_close
            updates.append(run)

        with transaction.atomic():
            Runs.objects.bulk_update(updates, ["obsoleted_at"], batch_size=500)

        self.stdout.write(self.style.SUCCESS(f"Backfilled {len(updates)} runs."))
