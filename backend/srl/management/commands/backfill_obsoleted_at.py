from django.core.management.base import BaseCommand
from django.db import transaction

from srl.models import RunPlayers, Runs
from srl.srcom.leaderboards import _resolve_obsoleted_at_for_player


class Command(BaseCommand):
    help = (
        "Populate Runs.obsoleted_at for every obsolete run from achievement-date "
        "chronology: an obsolete run is stamped with the date its own player's next "
        "faster run was achieved."
    )

    def add_arguments(
        self,
        parser,
    ) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute backfill values but roll back without persisting.",
        )

    def handle(
        self,
        *args,
        **options,
    ) -> None:
        dry_run: bool = options["dry_run"]
        prefix = "DRY RUN:" if dry_run else ""

        player_ids = sorted(set(RunPlayers.objects.values_list("player_id", flat=True)))
        self.stdout.write(
            f"{prefix} Resolving obsoleted_at across {len(player_ids)} players..."
        )

        before_null = Runs.objects.filter(
            obsolete=True, obsoleted_at__isnull=True
        ).count()

        with transaction.atomic():
            for player_id in player_ids:
                _resolve_obsoleted_at_for_player(player_id)

            after_null = Runs.objects.filter(
                obsolete=True, obsoleted_at__isnull=True
            ).count()
            after_set = Runs.objects.filter(
                obsolete=True, obsoleted_at__isnull=False
            ).count()

            self.stdout.write(
                f"{prefix}obsolete runs now dated: {after_set} "
                f"(was-null resolved: {before_null - after_null}, "
                f"still-null/born-obsolete: {after_null})"
            )

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.NOTICE("Dry run completed - rolled back."))
                return

        self.stdout.write(self.style.SUCCESS("Backfill complete."))
