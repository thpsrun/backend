import argparse
import os
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, UnidentifiedImageError

from srl.models import Players
from srl.srcom._static_fetch import StaticAssetDownloadError
from srl.srcom.players import save_pfp_locally
from srl.srcom.schema.src import SrcPlayersModel
from srl.utils import src_api


class Command(BaseCommand):
    help = (
        "Find pfp files that are missing or not valid images (e.g. Cloudflare "
        "challenge pages saved as `.jpg`), look the players up in the SRC API, "
        "and re-download via the CF-impersonating client. Scans both the "
        "MEDIA_ROOT/pfp/ directory and Players.pfp field URLs."
    )

    def add_arguments(
        self,
        parser: argparse.ArgumentParser,
    ) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only classify; do not call SRC or download.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help=(
                "Also flag Players whose pfp is still a remote URL (never "
                "successfully downloaded locally). Off by default."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Stop after attempting this many repairs.",
        )

    def handle(
        self,
        *args: Any,
        **options: Any,
    ) -> None:
        dry_run: bool = options.get("dry_run", False)
        include_remote: bool = options.get("all", False)
        limit: int | None = options.get("limit")

        if dry_run:
            self.stdout.write(
                self.style.NOTICE("DRY RUN MODE: No SRC calls or writes."),
            )

        broken: dict[str, str] = {}

        pfp_dir: str = os.path.join(settings.MEDIA_ROOT, "pfp")
        scanned_files: int = 0
        if os.path.isdir(pfp_dir):
            for filename in sorted(os.listdir(pfp_dir)):
                abs_path: str = os.path.join(pfp_dir, filename)
                if not os.path.isfile(abs_path):
                    continue
                scanned_files += 1
                stem, _ = os.path.splitext(filename)
                needs_repair, reason = _classify_local_file(abs_path)
                if needs_repair:
                    broken[stem] = f"file {filename}: {reason}"

        media_prefix: str = settings.MEDIA_URL
        media_root: str = settings.MEDIA_ROOT
        qs = Players.objects.exclude(pfp__isnull=True).exclude(pfp="").only("id", "pfp")
        scanned_players: int = 0
        for player in qs.iterator():
            scanned_players += 1
            pfp_url: str = player.pfp or ""

            if pfp_url.startswith(media_prefix):
                rel_path: str = pfp_url[len(media_prefix) :]
                abs_path = os.path.join(media_root, rel_path)
                needs_repair, reason = _classify_local_file(abs_path)
                if needs_repair and player.id not in broken:
                    broken[player.id] = f"field {pfp_url}: {reason}"
            elif include_remote:
                if player.id not in broken:
                    broken[player.id] = f"field {pfp_url}: remote URL still set"

        self.stdout.write(
            f"Scanned {scanned_files} files in {pfp_dir} and "
            f"{scanned_players} players. Found {len(broken)} broken pfps.",
        )
        for pid in sorted(broken):
            self.stdout.write(f"  {pid}: {broken[pid]}")

        if dry_run or not broken:
            return

        repaired: int = 0
        failed: int = 0
        attempts: int = 0

        for player_id in sorted(broken):
            if limit is not None and attempts >= limit:
                self.stdout.write(self.style.NOTICE(f"Hit --limit {limit}; stopping."))
                break
            attempts += 1

            self.stdout.write(f"\nRepairing {player_id} ({broken[player_id]})")

            try:
                src_data = src_api(f"https://speedrun.com/api/v1/users/{player_id}")
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f"  SRC lookup failed: {type(exc).__name__}: {exc}",
                    ),
                )
                failed += 1
                continue

            if not isinstance(src_data, dict):
                self.stdout.write(
                    self.style.WARNING("  SRC lookup returned unexpected payload"),
                )
                failed += 1
                continue

            try:
                src_player = SrcPlayersModel.model_validate(src_data)
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f"  SRC payload invalid: {type(exc).__name__}: {exc}",
                    ),
                )
                failed += 1
                continue

            if src_player.pfp is None:
                self.stdout.write(
                    self.style.WARNING("  SRC user has no pfp; clearing field"),
                )
                Players.objects.filter(pk=player_id).update(pfp=None)
                _try_unlink(os.path.join(pfp_dir, f"{player_id}.jpg"))
                repaired += 1
                continue

            try:
                new_value: str = save_pfp_locally(player_id, src_player.pfp)
            except StaticAssetDownloadError as exc:
                self.stdout.write(
                    self.style.WARNING(f"  download failed: {exc}"),
                )
                failed += 1
                continue

            Players.objects.filter(pk=player_id).update(pfp=new_value)
            self.stdout.write(f"  -> {new_value}")
            repaired += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. repaired={repaired} failed={failed} "
                f"of {len(broken)} broken.",
            ),
        )


def _classify_local_file(
    abs_path: str,
) -> tuple[bool, str]:
    """Return (needs_repair, reason) for a local pfp file."""
    if not os.path.exists(abs_path):
        return True, "file missing"
    try:
        size: int = os.path.getsize(abs_path)
    except OSError as exc:
        return True, f"stat failed: {exc}"
    if size == 0:
        return True, "zero-byte file"
    try:
        with Image.open(abs_path) as img:
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        return True, f"not a valid image ({type(exc).__name__})"
    return False, "ok"


def _try_unlink(
    path: str,
) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass
