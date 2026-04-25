import argparse
import datetime
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Min
from django.db.models.functions import Coalesce

from srl.models import Players, Runs


class Command(BaseCommand):
    help = "Set each player's joined date from their earliest verified run."

    def add_arguments(
        self,
        parser: argparse.ArgumentParser,
    ) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing to the database.",
        )

    def handle(
        self,
        *args: Any,
        **options: Any,
    ) -> None:
        dry_run = options.get("dry_run", False)

        if dry_run:
            self.stdout.write(
                self.style.NOTICE("DRY RUN MODE: No changes will be saved.")
            )

        # Find the earliest effective date per player in a single query
        earliest_dates = (
            Runs.objects.filter(vid_status="verified")
            .annotate(effective_date=Coalesce("v_date", "date"))
            .exclude(effective_date__isnull=True)
            .values("players__id")
            .annotate(earliest=Min("effective_date"))
            .exclude(players__id__isnull=True)
        )

        date_map: dict[str, datetime.date] = {
            row["players__id"]: row["earliest"].date() for row in earliest_dates
        }

        players = Players.objects.filter(id__in=date_map.keys())
        updated: list[Players] = []

        for player in players:
            new_date = date_map[player.id]
            if player.joined != new_date:
                if dry_run:
                    self.stdout.write(
                        f"  {player.name} ({player.id}): "
                        f"{player.joined} -> {new_date}"
                    )
                player.joined = new_date
                updated.append(player)

        if not dry_run and updated:
            Players.objects.bulk_update(updated, ["joined"])

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Would update' if dry_run else 'Updated'} "
                f"{len(updated)} of {len(date_map)} players."
            )
        )
