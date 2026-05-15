import argparse

from django.core.management.base import BaseCommand, CommandError

from srl.models import Players, Series
from srl.srcom import sync_obsolete_runs
from srl.srcom.series import import_new_game, iter_series_games
from srl.utils import src_api


class Command(BaseCommand):
    help = (
        "Initialize a Speedrun.com series by abbreviation or ID. "
        "Imports all games, categories, levels, variables, and runs."
    )

    def add_arguments(
        self,
        parser: argparse.ArgumentParser,
    ) -> None:
        parser.add_argument(
            "series",
            nargs="?",
            type=str,
            help="Speedrun.com series abbreviation or ID (e.g. 'thps2' or 'zd3ymn07')",
        )
        parser.add_argument(
            "--skip-runs",
            action="store_true",
            help="Only import metadata (games, categories, levels, variables) - skip run import",
        )
        parser.add_argument(
            "--skip-obsolete",
            action="store_true",
            help="Skip the per-player obsolete runs pass",
        )
        parser.add_argument(
            "--obsolete-passes",
            type=int,
            default=2,
            help="Number of passes to find a player's obsolete runs (default: 2)",
        )
        parser.add_argument(
            "--yes",
            "-y",
            action="store_true",
            help="Skip confirmation prompt",
        )

    def handle(
        self,
        *_args: str,
        **options: object,
    ) -> None:
        series_input: str | None = options["series"]  # type: ignore
        skip_runs: bool = options["skip_runs"]  # type: ignore
        skip_obsolete: bool = options["skip_obsolete"]  # type: ignore
        obsolete_passes: int = options["obsolete_passes"]  # type: ignore
        auto_yes: bool = options["yes"]  # type: ignore

        if not series_input:
            series_input = input(
                "Enter the Speedrun.com series abbreviation or ID: "
            ).strip()
            if not series_input:
                raise CommandError("No series abbreviation or ID provided.")

        self.stdout.write(f"Looking up series '{series_input}' on Speedrun.com...")

        try:
            series_data = src_api(f"https://speedrun.com/api/v1/series/{series_input}")
        except ValueError as e:
            raise CommandError(
                f"Could not find series '{series_input}' on Speedrun.com: {e}"
            )

        series_id: str = series_data["id"]
        series_name: str = series_data["names"]["international"]
        series_url: str = series_data["weblink"]

        self.stdout.write(self.style.SUCCESS(f" - Found: {series_name}"))
        self.stdout.write(f" - ID: {series_id}")
        self.stdout.write(f" - URL: {series_url}")

        if not auto_yes:
            confirm = (
                input(f"\nProceed with importing '{series_name}'? [y/N] ")
                .strip()
                .lower()
            )
            if confirm not in ("y", "yes"):
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        series_obj, created = Series.objects.update_or_create(
            id=series_id,
            defaults={
                "name": series_name[:20],
                "url": series_url,
            },
        )
        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"\n{action} Series: {series_obj}"))

        self.stdout.write("\nFetching games in series...")

        src_games = list(iter_series_games(series_id))
        if not src_games:
            self.stdout.write(self.style.WARNING(" - No games found in series."))

        self.stdout.write(self.style.SUCCESS(f" - Found {len(src_games)} game(s)\n"))

        for i, game_raw in enumerate(src_games, start=1):
            game_name = game_raw.get("names", {}).get("international", "Unknown")
            game_id = game_raw.get("id", "???")
            self.stdout.write(
                self.style.HTTP_INFO(f"[{i}/{len(src_games)}] {game_name} ({game_id})")
            )

            try:
                summary = import_new_game(game_id, skip_runs=skip_runs)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f" - Failed: {e}"))
                continue

            self.stdout.write(f" - Platforms: {summary['platforms']}")
            self.stdout.write(f" - Categories: {summary['categories']}")
            self.stdout.write(f" - Levels: {summary['levels']}")
            self.stdout.write(f" - Variables: {summary['variables']}")

            if skip_runs:
                self.stdout.write(
                    self.style.WARNING(" - Skipped run import (--skip-runs)")
                )
            else:
                self.stdout.write(" - Queued leaderboard run sync")

            self.stdout.write("")

        if not skip_obsolete and not skip_runs:
            self.stdout.write(self.style.HTTP_INFO("Starting obsolete run passes..."))
            self.stdout.write(
                " - This catches runs not exposed via the leaderboards endpoint.\n"
                " - Tasks are queued to Celery - progress depends on worker throughput.\n"
            )

            for pass_num in range(1, obsolete_passes + 1):
                players = Players.objects.only("id", "name").all()
                player_count = players.count()

                if player_count == 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f" - Pass {pass_num}: No players in database yet. "
                            "Obsolete runs will need to be imported after "
                            "initial Celery tasks complete."
                        )
                    )
                    break

                self.stdout.write(
                    f" - Pass {pass_num}/{obsolete_passes}: "
                    f"Queuing {player_count} player(s)..."
                )

                for j, player in enumerate(players, start=1):
                    sync_obsolete_runs.delay(player.id)
                    if j % 50 == 0:
                        self.stdout.write(f"   Queued {j}/{player_count}...")

                self.stdout.write(
                    self.style.SUCCESS(
                        f" - Pass {pass_num} complete: {player_count} player(s) queued"
                    )
                )
        elif skip_obsolete:
            self.stdout.write(
                self.style.WARNING("Skipped obsolete runs pass (--skip-obsolete)")
            )

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Series initialization complete!"))
        self.stdout.write("=" * 60)
        self.stdout.write(f" - Series: {series_name} ({series_id})")
        self.stdout.write(f" - Games: {len(src_games)}")

        if not skip_runs:
            self.stdout.write(
                "\n  Celery tasks have been queued. Monitor your worker logs for progress."
            )
            self.stdout.write(
                f" - Expect rate limiting - importing {len(src_games)} game(s) "
                "may take a while."
            )
        self.stdout.write("")
