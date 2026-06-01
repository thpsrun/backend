import argparse
import time

from django.core.management.base import BaseCommand, CommandError

from srl.models import Players
from srl.srcom.games import backfill_moderators
from srl.srcom.import_progress import (
    is_drained_obsolete,
    is_drained_runs,
    progress_get,
    seed,
    seed_obsolete,
    set_phase,
)
from srl.srcom.leaderboards import sync_game_runs, sync_obsolete_runs
from srl.srcom.series import import_game_metadata, iter_series_games, sync_series
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
            help="Accepted but unused; obsolete pass is now triggered by --watch after run drain",
        )
        parser.add_argument(
            "--yes",
            "-y",
            action="store_true",
            help="Skip confirmation prompt",
        )
        parser.add_argument(
            "--watch",
            action="store_true",
            help="Watch progress of a queued import instead of starting a new one",
        )
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=2.5,
            help="Seconds between --watch polls (default: 2.5)",
        )

    def handle(
        self,
        *_args: str,
        **options: object,
    ) -> None:
        series_input: str | None = options["series"]  # type: ignore
        skip_runs: bool = options["skip_runs"]  # type: ignore
        skip_obsolete: bool = options["skip_obsolete"]  # type: ignore
        watch: bool = options["watch"]  # type: ignore
        auto_yes: bool = options["yes"]  # type: ignore
        poll_interval: float = float(options["poll_interval"])  # type: ignore

        if not series_input:
            series_input = input(
                "Enter the Speedrun.com series abbreviation or ID: ",
            ).strip()
            if not series_input:
                raise CommandError("No series abbreviation or ID provided.")

        try:
            series_data = src_api(f"https://speedrun.com/api/v1/series/{series_input}")
        except ValueError as e:
            raise CommandError(
                f"Could not find series '{series_input}' on Speedrun.com: {e}",
            )

        series_id: str = series_data["id"]
        series_name: str = series_data["names"]["international"]

        if watch:
            self._watch(series_id, skip_obsolete, poll_interval)
            return

        if not auto_yes:
            confirm = (
                input(f"\nProceed with importing '{series_name}'? [y/N] ")
                .strip()
                .lower()
            )
            if confirm not in ("y", "yes"):
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        series_obj, _ = sync_series(series_id)
        self.stdout.write(self.style.SUCCESS(f"Series: {series_obj}"))

        self.stdout.write("Fetching games in series...")
        src_games = list(iter_series_games(series_id))
        game_ids = [g["id"] for g in src_games if g.get("id")]
        self.stdout.write(self.style.SUCCESS(f" - Found {len(game_ids)} game(s)\n"))

        seed(
            series_id,
            games_total=len(game_ids),
            game_ids=game_ids,
        )

        for i, game_id in enumerate(game_ids, start=1):
            self.stdout.write(
                self.style.HTTP_INFO(f"Metadata [{i}/{len(game_ids)}] {game_id}"),
            )
            try:
                game_data = import_game_metadata(game_id)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f" - Failed: {e}"))
                continue
            self.stdout.write(
                f" - {game_data.names.international}: "
                f"{len(game_data.platforms)} platforms, "
                f"{len(game_data.categories or [])} categories, "
                f"{len(game_data.levels or [])} levels, "
                f"{len(game_data.variables or [])} variables",
            )

        if skip_runs:
            set_phase(series_id, "done")
            self.stdout.write(self.style.WARNING("\nSkipped run import (--skip-runs)."))
            return

        set_phase(series_id, "runs")
        for game_id in game_ids:
            sync_game_runs.delay(game_id, progress_key=series_id)

        self.stdout.write(
            self.style.SUCCESS(f"\nQueued run import for {len(game_ids)} game(s)."),
        )
        self.stdout.write(
            f"Watch progress: python manage.py init_series {series_input} --watch",
        )

    def _watch(
        self,
        series_id: str,
        skip_obsolete: bool,
        poll_interval: float,
    ) -> None:
        c = self._poll_until_runs_drained(series_id, poll_interval)
        if c is None:
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"\nRun phase complete: {c['runs_done']} run(s) created, "
                f"{c['runs_failed']} failed.",
            ),
        )

        for game_id in c["game_ids"]:
            try:
                backfill_moderators(game_id)
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f" - moderator backfill failed {game_id}: {e}"),
                )

        if skip_obsolete:
            set_phase(series_id, "done")
            self.stdout.write(
                self.style.WARNING("Skipped obsolete pass (--skip-obsolete).")
            )
            return

        self._run_obsolete(series_id, poll_interval)
        set_phase(series_id, "done")
        self.stdout.write(self.style.SUCCESS("\nImport complete."))

    def _poll_until_runs_drained(
        self,
        series_id: str,
        poll_interval: float,
    ) -> dict | None:
        stable = 0
        while True:
            c = progress_get(series_id)
            if c is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"No active import for '{series_id}' (or it expired).",
                    ),
                )
                return None
            self._render(c)
            if c["phase"] == "done":
                return c
            if c["games_total"] > 0 and is_drained_runs(c):
                stable += 1
                if stable >= 2:
                    return c
            else:
                stable = 0
            try:
                time.sleep(poll_interval)
            except KeyboardInterrupt:
                self.stdout.write(
                    self.style.WARNING(
                        "\nStopped watching. Workers continue in the background; "
                        "re-run --watch to resume.",
                    ),
                )
                return None

    def _run_obsolete(
        self,
        series_id: str,
        poll_interval: float,
    ) -> None:
        set_phase(series_id, "obsolete")
        players = list(Players.objects.values_list("id", flat=True))
        seed_obsolete(series_id, players_total=len(players))
        self.stdout.write(
            self.style.HTTP_INFO(f"Obsolete pass: {len(players)} player(s)..."),
        )
        for pid in players:
            sync_obsolete_runs.delay(pid, progress_key=series_id)

        while True:
            c = progress_get(series_id)
            if c is None:
                return
            self.stdout.write(
                f"Obsolete: {c['players_done'] + c['players_failed']}/{c['players_total']} "
                f"(failed: {c['players_failed']})",
            )
            if is_drained_obsolete(c):
                return
            try:
                time.sleep(poll_interval)
            except KeyboardInterrupt:
                self.stdout.write(
                    self.style.WARNING("\nStopped watching obsolete pass.")
                )
                return

    def _render(
        self,
        c: dict,
    ) -> None:
        line = (
            f"[{c['phase']}] Leaderboards {c['lb_done']}/{c['lb_total']} "
            f"({c['games_enumerated']}/{c['games_total']} games) | "
            f"Runs {c['runs_done']} (failed {c['runs_failed']})"
        )
        workers = self._inspect_active()
        if workers is not None:
            line += f" | Workers: {workers}"
        self.stdout.write(line)

    def _inspect_active(
        self,
    ) -> str | None:
        try:
            from website.celery import app

            active = app.control.inspect(timeout=1.0).active()
            if not active:
                return None
            tasks = sum(len(v) for v in active.values())
            return f"{len(active)} worker(s), {tasks} task(s)"
        except Exception:
            return None
