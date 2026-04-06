from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from srl.models import RunPlayers, Runs


class Command(BaseCommand):
    help = "Verify and optionally repair RunPlayers associations for all runs."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Actually fix issues (default is dry-run mode)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed output for each run processed",
        )

    def handle(self, *args, **options) -> None:
        fix_mode = options["fix"]
        verbose = options["verbose"]

        self.stdout.write(
            self.style.NOTICE(
                f"{'FIX MODE' if fix_mode else 'DRY RUN MODE'}: "
                "Verifying RunPlayers associations..."
            )
        )

        total_runs = 0
        runs_with_players = 0
        runs_without_players = 0
        orphaned_runplayers = 0

        runs_queryset = Runs.objects.prefetch_related("run_players__player").all()
        total_runs = runs_queryset.count()

        for run in runs_queryset.iterator(chunk_size=1000):
            run_players_count = run.run_players.count()  # type: ignore

            if run_players_count > 0:
                runs_with_players += 1
                if verbose:
                    player_names = ", ".join(
                        [rp.player.name for rp in run.run_players.all()]  # type: ignore
                    )
                    self.stdout.write(f"  Run {run.id}: {player_names}")
            else:
                runs_without_players += 1
                if verbose:
                    self.stdout.write(
                        self.style.WARNING(f"  Run {run.id}: No players (Anonymous)")
                    )

        orphaned_runplayers = RunPlayers.objects.filter(run__isnull=True).count()

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("VERIFICATION RESULTS"))
        self.stdout.write("=" * 50)
        self.stdout.write(f"Total runs: {total_runs}")
        self.stdout.write(f"Runs with players: {runs_with_players}")
        self.stdout.write(f"Anonymous runs (no players): {runs_without_players}")
        self.stdout.write(f"Orphaned RunPlayers entries: {orphaned_runplayers}")

        if fix_mode and orphaned_runplayers > 0:
            with transaction.atomic():
                deleted_count = RunPlayers.objects.filter(run__isnull=True).delete()[0]
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\nCleaned up {deleted_count} orphaned RunPlayers entries."
                    )
                )

        duplicates = (
            RunPlayers.objects.values("run", "player")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )

        if duplicates.exists():
            self.stdout.write(
                self.style.WARNING(f"\nFound {duplicates.count()} duplicate entries!")
            )
            if fix_mode:
                with transaction.atomic():
                    for dup in duplicates:
                        entries = RunPlayers.objects.filter(
                            run_id=dup["run"],
                            player_id=dup["player"],
                        ).order_by("id")
                        to_delete = entries[1:]
                        for entry in to_delete:
                            entry.delete()
                self.stdout.write(self.style.SUCCESS("Duplicates cleaned up."))

        self.stdout.write("\n" + "=" * 50)
        if not fix_mode:
            self.stdout.write(
                self.style.NOTICE("This was a dry run. No changes saved.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Verification and fixes complete!"))
