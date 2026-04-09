import argparse
from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from srl.models import Games, Runs
from srl.utils import calculate_bonus, get_anniversary, get_streak_start_date
from api.v1.schemas.runs import compute_run_subcategory


class Command(BaseCommand):
    help = "Check WR streak anniversaries and award bonus points"

    def add_arguments(
        self,
        parser: argparse.ArgumentParser,
    ) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Calculate but don't save changes",
        )
        parser.add_argument(
            "--game",
            type=str,
            help="Limit to a specific game ID",
        )
        parser.add_argument(
            "--date",
            type=str,
            help="Override check date (YYYY-MM-DD format, for testing/backfill)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show per-run details",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Check all WRs regardless of anniversary date (for initial population/audit)",
        )

    def get_max_points(
        self,
        game: Games,
        runtype: str,
    ) -> int:
        """Get the max points for a run based on game type."""
        if game.is_ce:
            return settings.POINTS_MAX_CE
        elif runtype == "main":
            return game.pointsmax
        else:
            return game.ipointsmax

    def is_anniversary_today(
        self,
        streak_start: date,
        check_date: date,
    ) -> tuple[bool, int]:
        """Check if today is a monthly anniversary of the streak start."""
        if check_date <= streak_start:
            return False, 0

        delta = relativedelta(check_date, streak_start)
        months_held = delta.years * 12 + delta.months

        if months_held <= 0:
            return False, 0

        anniversary_day = get_anniversary(
            streak_start.day,
            check_date.year,
            check_date.month,
        )

        is_anniversary = check_date.day == anniversary_day
        return is_anniversary, months_held

    def handle(
        self,
        *args: Any,
        **options: Any,
    ) -> None:
        """Execute the command to check streak anniversaries and award bonuses."""
        dry_run = options.get("dry_run", False)
        game_filter = options.get("game")
        date_override = options.get("date")
        verbose = options.get("verbose", False)
        check_all = options.get("all", False)

        if date_override:
            try:
                check_date = date.fromisoformat(date_override)
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(
                        f"Invalid date format: {date_override}. Use YYYY-MM-DD."
                    )
                )
                return
        else:
            check_date = date.today()

        if dry_run:
            self.stdout.write(
                self.style.NOTICE("DRY RUN MODE: No changes will be saved.")
            )

        if check_all:
            self.stdout.write(f"Checking ALL WR streaks as of {check_date}...\n")
        else:
            self.stdout.write(f"Checking streak anniversaries for {check_date}...\n")

        wr_queryset = (
            Runs.objects.filter(
                place=1,
                obsolete=False,
                vid_status="verified",
                bonus__lt=settings.STREAK_MAX_MONTHS,
            )
            .select_related("game", "category", "level")
            .prefetch_related("players", "runvariablevalues_set__value")
        )

        if game_filter:
            wr_queryset = wr_queryset.filter(
                Q(game__id__iexact=game_filter) | Q(game__slug__iexact=game_filter)
            )

        games_cache: dict[str, Games] = {}
        for game in Games.objects.filter(
            id__in=wr_queryset.values_list("game_id", flat=True).distinct()
        ):
            games_cache[game.id] = game

        anniversaries_found = 0
        streaks_awarded = 0
        runs_to_update: list[Runs] = []

        for run in wr_queryset:
            game = games_cache.get(run.game_id)  # type: ignore
            if not game:
                continue

            if game.is_ce:
                continue

            streak_start = get_streak_start_date(run)
            if not streak_start:
                continue

            if check_date <= streak_start:
                months_held = 0
            else:
                delta = relativedelta(check_date, streak_start)
                months_held = delta.years * 12 + delta.months

            if not check_all:
                is_anniversary, _ = self.is_anniversary_today(streak_start, check_date)
                if not is_anniversary:
                    continue

            anniversaries_found += 1

            run_subcat = compute_run_subcategory(run)
            if check_all:
                if months_held == run.bonus:
                    if verbose:
                        self.stdout.write(
                            f"  [{game.slug.upper()}] {run_subcat}: {run.id} - "
                            f"already at {run.bonus} months (no change)"
                        )
                    continue
            elif months_held <= run.bonus:
                if verbose:
                    self.stdout.write(
                        f"  [{game.slug.upper()}] {run_subcat}: {run.id} - "
                        f"already at {run.bonus} months (no change)"
                    )
                continue

            max_points = self.get_max_points(game, run.runtype)  # type: ignore
            new_bonus = min(months_held, settings.STREAK_MAX_MONTHS)
            streak_bonus = calculate_bonus(run.runtype, new_bonus, game.is_ce)  # type: ignore
            new_points = max_points + streak_bonus

            player_names = ", ".join(p.name for p in run.players.all()) or "Anonymous"

            if verbose:
                self.stdout.write(
                    f"[{game.slug.upper()}] {run_subcat}: {run.id} ({player_names}) -> "
                    f"streak started {streak_start}, {new_bonus} month(s) "
                    f"({max_points} + {streak_bonus} bonus = {new_points} points)"
                )

            run.bonus = new_bonus
            run.points = new_points
            runs_to_update.append(run)
            streaks_awarded += 1

        if runs_to_update and not dry_run:
            with transaction.atomic():
                Runs.objects.bulk_update(runs_to_update, ["points", "bonus"])

        self.stdout.write("")
        if check_all:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Summary: {anniversaries_found} WRs checked, {streaks_awarded} updated"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Summary: {anniversaries_found} anniversaries found, {streaks_awarded} awarded"
                )
            )

        if dry_run:
            self.stdout.write(
                self.style.NOTICE("\nThis was a dry run. No changes saved.")
            )
