import argparse
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from srl.models import Games
from srl.srcom.games import BoxartDownloadError, save_boxart_locally


class Command(BaseCommand):
    help = (
        "Download Games.boxart images from their remote URLs into MEDIA_ROOT/boxart "
        "and rewrite each game's boxart field to the resulting /media/boxart/... path."
    )

    def add_arguments(
        self,
        parser: argparse.ArgumentParser,
    ) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without downloading or writing to the database.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-download even if boxart is already pointed at MEDIA_URL.",
        )

    def handle(
        self,
        *args: Any,
        **options: Any,
    ) -> None:
        dry_run: bool = options.get("dry_run", False)
        force: bool = options.get("force", False)

        if dry_run:
            self.stdout.write(
                self.style.NOTICE("DRY RUN MODE: No downloads or DB writes."),
            )

        media_prefix: str = settings.MEDIA_URL

        games = Games.objects.exclude(boxart="").order_by("id")
        total: int = games.count()
        downloaded: int = 0
        skipped: int = 0
        failed: int = 0

        for game in games.iterator():
            url: str = game.boxart
            if not force and url.startswith(media_prefix):
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(f"  {game.id} ({game.name}): would download {url}")
                downloaded += 1
                continue

            try:
                new_value: str = save_boxart_locally(game.id, url)
            except BoxartDownloadError as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {game.id} ({game.name}): FAILED {url} -- {exc}",
                    ),
                )
                failed += 1
                continue
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"  {game.id} ({game.name}): UNEXPECTED {type(exc).__name__}: {exc}",
                    ),
                )
                failed += 1
                continue

            Games.objects.filter(pk=game.pk).update(boxart=new_value)
            self.stdout.write(f"  {game.id} ({game.name}): -> {new_value}")
            downloaded += 1

        verb: str = "Would download" if dry_run else "Downloaded"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {downloaded}, skipped {skipped}, failed {failed} "
                f"of {total} games.",
            ),
        )
